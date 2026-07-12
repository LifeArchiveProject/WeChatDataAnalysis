import base64
import csv
import html
import json
import re
import sqlite3
import unicodedata
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

try:
    from pypinyin import Style, lazy_pinyin
except Exception:  # pragma: no cover - depends on optional runtime package availability
    class Style:  # type: ignore[no-redef]
        NORMAL = "normal"

    def lazy_pinyin(value: Any, *args: Any, **kwargs: Any) -> list[str]:  # type: ignore[no-redef]
        text = str(value or "")
        # Fallback without pypinyin: keep ASCII segments for deterministic sorting,
        # and place CJK/emoji under '#'. This keeps contacts API usable in minimal envs.
        return [text] if text.isascii() else []

from ..chat_helpers import (
    _build_avatar_url,
    _pick_avatar_url,
    _pick_display_name,
    _resolve_account_dir,
    _should_keep_session,
)
from ..path_fix import PathFixRoute
from ..export_integrity import (
    export_css,
    load_wce_integrity_native,
    seal_bytes_artifact,
    seal_protected_html_bytes,
    write_file_integrity_sidecars,
    write_protected_html_file,
)
from ..xlsx_export import build_xlsx_workbook
from ..wcdb_realtime import (
    WCDB_REALTIME,
    WCDBRealtimeError,
    exec_query as _wcdb_exec_query,
    get_avatar_urls as _wcdb_get_avatar_urls,
    get_contact as _wcdb_get_contact,
    get_contacts_compact as _wcdb_get_contacts_compact,
    get_display_names as _wcdb_get_display_names,
    get_sessions as _wcdb_get_sessions,
)

router = APIRouter(route_class=PathFixRoute)


_SYSTEM_USERNAMES = {
    "filehelper",
    "fmessage",
    "floatbottle",
    "medianote",
    "newsapp",
    "qmessage",
    "qqmail",
    "tmessage",
    "brandsessionholder",
    "brandservicesessionholder",
    "notifymessage",
    "opencustomerservicemsg",
    "notification_messages",
    "userexperience_alarm",
}

_SOURCE_SCENE_LABELS = {
    1: "通过QQ号添加",
    3: "通过微信号添加",
    6: "通过手机号添加",
    10: "通过名片添加",
    14: "通过群聊添加",
    15: "通过搜索手机号添加",
    17: "通过名片分享添加",
    30: "通过扫一扫添加",
}

_COUNTRY_LABELS = {
    "AD": "安道尔",
    "AE": "阿联酋",
    "AG": "安提瓜和巴布达",
    "AU": "澳大利亚",
    "CN": "中国大陆",
    "CX": "圣诞岛",
    "DE": "德国",
    "DZ": "阿尔及利亚",
    "EC": "厄瓜多尔",
    "EG": "埃及",
    "ER": "厄立特里亚",
    "FR": "法国",
    "GB": "英国",
    "HK": "中国香港",
    "HR": "克罗地亚",
    "IE": "爱尔兰",
    "IS": "冰岛",
    "JE": "泽西岛",
    "JP": "日本",
    "KP": "朝鲜",
    "KR": "韩国",
    "MA": "摩洛哥",
    "MO": "中国澳门",
    "MP": "北马里亚纳群岛",
    "MV": "马尔代夫",
    "MY": "马来西亚",
    "NO": "挪威",
    "RU": "俄罗斯",
    "SB": "所罗门群岛",
    "SG": "新加坡",
    "SY": "叙利亚",
    "TH": "泰国",
    "TW": "中国台湾",
    "US": "美国",
    "UK": "英国",
    "VA": "梵蒂冈",
    "WF": "瓦利斯和富图纳",
    "CA": "加拿大",
    "CH": "瑞士",
    "IT": "意大利",
    "ES": "西班牙",
    "NL": "荷兰",
}

_CN_PROVINCE_LABELS = {
    "Anhui": "安徽",
    "Beijing": "北京",
    "Chongqing": "重庆",
    "Fujian": "福建",
    "Gansu": "甘肃",
    "Guangdong": "广东",
    "Guangxi": "广西",
    "Guizhou": "贵州",
    "Hainan": "海南",
    "Hebei": "河北",
    "Heilongjiang": "黑龙江",
    "Henan": "河南",
    "Hubei": "湖北",
    "Hunan": "湖南",
    "Inner Mongolia": "内蒙古",
    "Jiangsu": "江苏",
    "Jiangxi": "江西",
    "Jilin": "吉林",
    "Liaoning": "辽宁",
    "Ningxia": "宁夏",
    "Qinghai": "青海",
    "Shaanxi": "陕西",
    "Shandong": "山东",
    "Shanghai": "上海",
    "Shanxi": "山西",
    "Sichuan": "四川",
    "Tianjin": "天津",
    "Tibet": "西藏",
    "Xinjiang": "新疆",
    "Yunnan": "云南",
    "Zhejiang": "浙江",
}

_CN_CITY_LABELS = {
    "Anqing": "安庆",
    "Baoshan": "保山",
    "Bishan": "璧山",
    "Changning": "长宁",
    "Changping": "昌平",
    "Changsha": "长沙",
    "Chaoyang": "朝阳",
    "Chengdu": "成都",
    "Chow": "崇左",
    "Dalian": "大连",
    "Daqing": "大庆",
    "Deyang": "德阳",
    "Dongguan": "东莞",
    "Foshan": "佛山",
    "Fuzhou": "福州",
    "Guangyuan": "广元",
    "Guangzhou": "广州",
    "Haikou": "海口",
    "Haidian": "海淀",
    "Hangzhou": "杭州",
    "Harbin": "哈尔滨",
    "Hefei": "合肥",
    "Heze": "菏泽",
    "Heyuan": "河源",
    "Huizhou": "惠州",
    "Huangpu": "黄浦",
    "Huzhou": "湖州",
    "Jiaxing": "嘉兴",
    "Jinan": "济南",
    "Jing": "静安",
    "Jingdezhen": "景德镇",
    "Jinzhong": "晋中",
    "Kunming": "昆明",
    "Leshan": "乐山",
    "Linyi": "临沂",
    "Lishui": "丽水",
    "Liuzhou": "柳州",
    "Longyan": "龙岩",
    "Luzhou": "泸州",
    "Meishan": "眉山",
    "Mianyang": "绵阳",
    "Minhang": "闵行",
    "Nanchang": "南昌",
    "Nanchong": "南充",
    "Nanjing": "南京",
    "Neijiang": "内江",
    "Ningbo": "宁波",
    "Ningde": "宁德",
    "Peace": "和平",
    "Po": "普陀",
    "Pudong New District": "浦东新区",
    "Qingdao": "青岛",
    "Qingpu": "青浦",
    "Quanzhou": "泉州",
    "Shapingba": "沙坪坝",
    "Shaoyang": "邵阳",
    "Shenyang": "沈阳",
    "Shenzhen": "深圳",
    "Shiyan": "十堰",
    "Songjiang": "松江",
    "Suzhou": "苏州",
    "Taiyuan": "太原",
    "Taizhou": "台州",
    "Tongzhou": "通州",
    "Urumqi": "乌鲁木齐",
    "Wenzhou": "温州",
    "Wuhan": "武汉",
    "Wuwei": "武威",
    "Wuzhou": "梧州",
    "Xiamen": "厦门",
    "Xi'an": "西安",
    "Xianning": "咸宁",
    "Xining": "西宁",
    "Xingtai": "邢台",
    "Xuchang": "许昌",
    "Xuhui": "徐汇",
    "Xuzhou": "徐州",
    "Yaan": "雅安",
    "Yangpu": "杨浦",
    "Yangquan": "阳泉",
    "Yellowstone": "黄石",
    "Yibin": "宜宾",
    "Yongchuan": "永川",
    "Yueyang": "岳阳",
    "Yulin": "玉林",
    "Yuzhong": "渝中",
    "Zhaoqing": "肇庆",
    "Zhengzhou": "郑州",
    "Zhuhai": "珠海",
}

_CN_CITY_LABELS_BY_PROVINCE = {
    ("Anhui", "Suzhou"): "宿州",
    ("Beijing", "East"): "东城",
    ("Beijing", "West"): "西城",
    ("Jiangsu", "Taizhou"): "泰州",
    ("Shanghai", "Jing"): "静安",
    ("Sichuan", "Florida"): "佛罗里达",
    ("Tianjin", "west"): "河西",
    ("Zhejiang", "Taizhou"): "台州",
}

_REGION_LOOKUP_PATH = Path(__file__).resolve().parents[1] / "resources" / "contact_region_lookup.json"


class ContactTypeFilter(BaseModel):
    friends: bool = True
    groups: bool = True
    officials: bool = True
    official_subscriptions: Optional[bool] = None
    official_services: Optional[bool] = None
    former_friends: bool = False
    blocked: bool = False


class ContactExportRequest(BaseModel):
    account: Optional[str] = Field(None, description="账号目录名（可选，默认使用第一个）")
    source: Optional[str] = Field("auto", description="数据源：auto/realtime 直接读取 WCDB；decrypted 使用旧本地库")
    output_dir: str = Field(..., description="导出目录绝对路径")
    format: str = Field("json", description="导出格式：html/json/txt/excel（兼容 csv）")
    include_avatar_link: bool = Field(True, description="是否导出 avatarLink 字段")
    contact_types: ContactTypeFilter = Field(default_factory=ContactTypeFilter)
    keyword: Optional[str] = Field(None, description="关键词筛选（可选）")


class ContactBrowserExportSealRequest(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=180)
    content_base64: str = Field(..., min_length=1, max_length=100_000_000)


def _normalize_text(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _to_int(v: Any) -> int:
    try:
        return int(v or 0)
    except Exception:
        return 0


def _to_optional_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    s = _normalize_text(v)
    if not s:
        return None
    try:
        return int(s)
    except Exception:
        return None


def _timestamp_date_text(value: Any) -> str:
    ts = _to_int(value)
    if ts <= 0:
        return ""
    if ts > 10_000_000_000:
        ts = ts // 1000
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _normalize_contacts_source(value: Optional[str]) -> str:
    v = str(value or "").strip().lower()
    if not v:
        return "auto"
    if v in {"auto", "default", "wechat"}:
        return "auto"
    if v in {"realtime", "real-time", "wcdb"}:
        return "realtime"
    if v in {"decrypted", "local", "sqlite", "snapshot", "output"}:
        return "decrypted"
    raise HTTPException(status_code=400, detail="Invalid source, use 'auto', 'realtime' or 'decrypted'.")


def _resolve_contacts_source_for_account(source_norm: str, account_dir: Path) -> str:
    # 新模式：auto 一律走 direct WCDB。旧本地 contact.db/session.db 只在显式 decrypted 时使用。
    if source_norm == "auto":
        return "realtime"
    return source_norm


def _pick_case_insensitive_value(item: dict[str, Any], *keys: str) -> Any:
    if not isinstance(item, dict):
        return None
    for key in keys:
        if key in item:
            return item.get(key)
    lowered = {str(k).lower(): v for k, v in item.items()}
    for key in keys:
        lk = str(key).lower()
        if lk in lowered:
            return lowered.get(lk)
    return None


_PINYIN_CLEAN_RE = re.compile(r"[^a-z0-9]+")
_PINYIN_ALPHA_RE = re.compile(r"[A-Za-z]")

_BUILTIN_OFFICIAL_HELPER_USERNAMES = {
    "gh_f0a92aa7146c",  # 微信收款助手，不作为普通公众号/服务号分类展示
}

_FRIEND_EXCLUDE_USERNAMES = {"medianote", "floatbottle", "qmessage", "qqmail", "fmessage"}


def _is_enterprise_openim_username(username: str) -> bool:
    lowered = _normalize_text(username).lower()
    return "@openim" in lowered and "@kefu.openim" not in lowered


def _is_allowed_enterprise_openim_by_local_type(username: str, local_type: int) -> bool:
    return _is_enterprise_openim_username(username) and int(local_type or 0) == 5

# 多音字姓氏：pypinyin 对单字默认读音不一定是姓氏读音（例如：曾= ceng / zeng）。
# 这里在“姓名首字”场景优先采用常见姓氏读音，用于联系人列表的分组/排序。
_SURNAME_PINYIN_OVERRIDES: dict[str, str] = {
    "曾": "zeng",
    "区": "ou",
    "仇": "qiu",
    "解": "xie",
    "单": "shan",
    "查": "zha",
    "乐": "yue",
    "朴": "piao",
    "盖": "ge",
    "缪": "miao",
}


@lru_cache(maxsize=4096)
def _build_contact_pinyin_key(name: str) -> str:
    text = _normalize_text(name)
    if not text:
        return ""

    # Keep non-CJK segments so English names can be sorted/grouped as expected.
    first = text[0]
    override = _SURNAME_PINYIN_OVERRIDES.get(first)
    if override:
        rest = text[1:]
        parts = [override]
        if rest:
            parts.extend(lazy_pinyin(rest, style=Style.NORMAL, errors="default"))
    else:
        parts = lazy_pinyin(text, style=Style.NORMAL, errors="default")
    out: list[str] = []
    for part in parts:
        cleaned = _PINYIN_CLEAN_RE.sub("", _normalize_text(part).lower())
        if cleaned:
            out.append(cleaned)
    return "".join(out)


@lru_cache(maxsize=4096)
def _build_contact_pinyin_initial(name: str) -> str:
    text = _normalize_text(name).lstrip()
    if not text:
        return "#"

    first = text[0]
    if "A" <= first <= "Z":
        return first
    if "a" <= first <= "z":
        return first.upper()

    override = _SURNAME_PINYIN_OVERRIDES.get(first)
    if override:
        return override[0].upper()

    # For CJK, try to convert the first character to pinyin initial.
    parts = lazy_pinyin(first, style=Style.NORMAL, errors="ignore")
    if parts:
        m = _PINYIN_ALPHA_RE.search(parts[0])
        if m:
            return m.group(0).upper()

    # Emoji / digits / symbols, etc.
    return "#"


def _decode_varint(raw: bytes, offset: int) -> tuple[Optional[int], int]:
    value = 0
    shift = 0
    pos = int(offset)
    n = len(raw)
    while pos < n:
        byte = raw[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if (byte & 0x80) == 0:
            return value, pos
        shift += 7
        if shift > 63:
            return None, n
    return None, n


def _decode_proto_text(raw: bytes) -> str:
    if not raw:
        return ""
    try:
        text = raw.decode("utf-8", errors="ignore")
    except Exception:
        return ""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text).strip()


def _coerce_blob_bytes(value: Any) -> bytes:
    if value is None:
        return b""
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, list):
        try:
            return bytes([int(x) & 0xFF for x in value])
        except Exception:
            return b""
    if isinstance(value, dict):
        for key in ("hex", "data_hex", "dataHex"):
            raw = value.get(key)
            if raw:
                return _coerce_blob_bytes(str(raw))
        for key in ("base64", "b64", "data_b64", "dataB64"):
            raw = _normalize_text(value.get(key))
            if raw:
                try:
                    return base64.b64decode(raw, validate=True)
                except Exception:
                    return b""
        return b""

    text = _normalize_text(value)
    if not text:
        return b""
    compact = re.sub(r"\s+", "", text)
    if compact.lower().startswith("0x"):
        compact = compact[2:]
    if len(compact) >= 2 and len(compact) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", compact):
        try:
            return bytes.fromhex(compact)
        except Exception:
            return b""
    try:
        return base64.b64decode(text, validate=True)
    except Exception:
        return b""


def _parse_contact_extra_buffer(extra_buffer: Any) -> dict[str, Any]:
    out = {
        "gender": 0,
        "signature": "",
        "country": "",
        "province": "",
        "city": "",
        "source_scene": None,
        "add_time": None,
        "add_time_text": "",
    }
    if extra_buffer is None:
        return out

    raw = _coerce_blob_bytes(extra_buffer)
    if not raw:
        return out

    idx = 0
    n = len(raw)
    while idx < n:
        tag, idx_next = _decode_varint(raw, idx)
        if tag is None:
            break
        idx = idx_next
        field_no = tag >> 3
        wire_type = tag & 0x7

        if wire_type == 0:
            val, idx_next = _decode_varint(raw, idx)
            if val is None:
                break
            idx = idx_next
            if field_no == 2:
                # 性别: 1=男, 2=女, 0=未知
                out["gender"] = int(val)
            if field_no == 8:
                out["source_scene"] = int(val)
            if field_no == 41:
                # 微信联系人资料页的“添加时间”。实测位于 extra_buffer 的 field 41。
                out["add_time"] = int(val)
                out["add_time_text"] = _timestamp_date_text(val)
            continue

        if wire_type == 2:
            size, idx_next = _decode_varint(raw, idx)
            if size is None:
                break
            idx = idx_next
            end = idx + int(size)
            if end > n:
                break
            chunk = raw[idx:end]
            idx = end

            if field_no in {4, 5, 6, 7}:
                text = _decode_proto_text(chunk)
                if field_no == 4:
                    out["signature"] = text
                elif field_no == 5:
                    out["country"] = text
                elif field_no == 6:
                    out["province"] = text
                elif field_no == 7:
                    out["city"] = text
            continue

        if wire_type == 1:
            idx += 8
            continue
        if wire_type == 5:
            idx += 4
            continue

        break

    return out


@lru_cache(maxsize=1)
def _load_region_lookup_data() -> dict[str, Any]:
    """Load generated country/province/city lookup data.

    The resource is generated from the already-present WeFlow region data
    (`WeFlow/electron/services/contactRegionLookupData.ts`), which itself was
    built from province-city-china + pypinyin.  Keep lookup best-effort: contact
    rendering must not fail just because this optional dictionary is missing.
    """

    try:
        with _REGION_LOOKUP_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _region_lookup_key(value: Any) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^0-9a-z]+", "", folded.lower())


def _lookup_region_country_label(country: str) -> str:
    key = _region_lookup_key(country)
    if not key:
        return ""
    data = _load_region_lookup_data()
    countries = data.get("countryNameByKey")
    if isinstance(countries, dict):
        label = countries.get(key)
        if isinstance(label, str):
            label = _normalize_text(label)
            # 微信资料页里 CN 通常展示为“中国大陆”，而公开 ISO 数据集只写“中国”。
            if label == "中国":
                return "中国大陆"
            if label == "香港":
                return "中国香港"
            if label == "澳门":
                return "中国澳门"
            if label == "台湾":
                return "中国台湾"
            return label
    return ""


def _lookup_region_province_label(province: str) -> str:
    key = _region_lookup_key(province)
    if not key:
        return ""
    data = _load_region_lookup_data()
    provinces = data.get("provinceNameByKey")
    if isinstance(provinces, dict):
        label = provinces.get(key)
        if isinstance(label, str):
            return _normalize_text(label)
    return ""


def _lookup_region_province_key(province: str) -> str:
    raw = _normalize_text(province)
    if not raw:
        return ""
    data = _load_region_lookup_data()
    by_name = data.get("provinceKeyByName")
    if isinstance(by_name, dict):
        direct = by_name.get(raw)
        if isinstance(direct, str) and direct:
            return direct
        translated = _CN_PROVINCE_LABELS.get(raw)
        if translated:
            direct = by_name.get(translated)
            if isinstance(direct, str) and direct:
                return direct
    key = _region_lookup_key(raw)
    provinces = data.get("provinceNameByKey")
    if key and isinstance(provinces, dict) and key in provinces:
        return key
    return ""


def _lookup_region_city_label(province: str, city: str) -> str:
    key = _region_lookup_key(city)
    if not key:
        return ""
    data = _load_region_lookup_data()
    province_key = _lookup_region_province_key(province)
    by_province = data.get("cityNameByProvinceKey")
    if province_key and isinstance(by_province, dict):
        province_cities = by_province.get(province_key)
        if isinstance(province_cities, dict):
            label = province_cities.get(key)
            if isinstance(label, str):
                return _normalize_text(label)
    cities = data.get("cityNameByKey")
    if isinstance(cities, dict):
        label = cities.get(key)
        if isinstance(label, str):
            return _normalize_text(label)
    return ""


def _is_mainland_china_country(country: str) -> bool:
    raw = _normalize_text(country)
    if raw in {"中国", "中国大陆", "中华人民共和国"}:
        return True
    key = _region_lookup_key(raw)
    return key in {"cn", "chn", "china", "156", "zhongguo", "zhongguodalu"}


def _country_label(country: str) -> str:
    c = _normalize_text(country)
    if not c:
        return ""
    if c in {"中国", "中国大陆", "中华人民共和国"}:
        return "中国大陆"
    if c == "香港":
        return "中国香港"
    if c == "澳门":
        return "中国澳门"
    if c == "台湾":
        return "中国台湾"
    if c.upper() in _COUNTRY_LABELS:
        return _COUNTRY_LABELS[c.upper()]
    return _lookup_region_country_label(c) or c


def _region_value_label(country: str, province: str, city: str, *, level: str) -> str:
    value = _normalize_text(province if level == "province" else city)
    if not value:
        return ""

    country_code = _normalize_text(country).upper()
    if country_code == "CN" or _is_mainland_china_country(country):
        if level == "province":
            return _CN_PROVINCE_LABELS.get(value) or _lookup_region_province_label(value) or value
        contextual = _CN_CITY_LABELS_BY_PROVINCE.get((_normalize_text(province), value))
        if contextual:
            return contextual
        return _CN_CITY_LABELS.get(value) or _lookup_region_city_label(province, value) or value

    # 港澳等地区的区名也常以英文 key 存在，先覆盖本库已验证的常见值。
    contextual_global = {
        ("HK", "Wong Tai Sin"): "黄大仙",
        ("HK", "Yau Tsim Mong"): "油尖旺",
        ("MO", "Cathedral"): "大堂区",
        ("MO", "Fatima"): "花地玛堂区",
        ("CH", "Geneve"): "日内瓦",
        ("RU", "Moscow"): "莫斯科",
        ("RU", "St. Peterburg"): "圣彼得堡",
        ("US", "California"): "加利福尼亚",
        ("US", "Louisiana"): "路易斯安那",
        ("US", "Cupertino"): "库比蒂诺",
        ("US", "New Orleans"): "新奥尔良",
        ("AU", "Victoria"): "维多利亚",
        ("AU", "Melbourne"): "墨尔本",
        ("JP", "Chiba-ken"): "千叶县",
        ("JP", "Abiko-shi"): "我孙子市",
        ("MY", "Pulau Pinang"): "槟城",
        ("MY", "Butterworth"): "北海",
        ("DE", "Berlin"): "柏林",
        ("IE", "Dublin"): "都柏林",
        ("AE", "Ash Shariqah"): "沙迦",
        ("FR", "Frejus"): "弗雷瑞斯",
    }
    return contextual_global.get((country_code, value)) or _lookup_region_city_label(province, value) or value


def _source_scene_label(source_scene: Optional[int]) -> str:
    if source_scene is None:
        return ""
    if source_scene in _SOURCE_SCENE_LABELS:
        return _SOURCE_SCENE_LABELS[source_scene]
    return f"场景码 {source_scene}"


def _official_account_kind(type_value: Any) -> str:
    t = _to_optional_int(type_value)
    if t == 0:
        return "subscription"
    if t == 1:
        return "service"
    if t in {2, 3}:
        return "enterprise"
    return "unknown"


def _contact_kind_is_official_subscription_bucket(kind: Any) -> bool:
    # UI 只展示“公众号/服务号”两张卡；企业号/未知公众号归入“公众号”卡，
    # 避免出现无法通过 6 分类筛选到的官方账号。
    return _normalize_text(kind) != "service"


def _resolve_official_filter(
    include_officials: bool,
    include_official_subscriptions: Optional[bool],
    include_official_services: Optional[bool],
) -> tuple[bool, bool]:
    subscriptions = bool(include_officials) if include_official_subscriptions is None else bool(include_official_subscriptions)
    services = bool(include_officials) if include_official_services is None else bool(include_official_services)
    return subscriptions, services


def _contact_type_selected(
    item: dict[str, Any],
    *,
    include_friends: bool,
    include_groups: bool,
    include_official_subscriptions: bool,
    include_official_services: bool,
    include_former_friends: bool,
    include_blocked: bool,
) -> bool:
    t = _normalize_text(item.get("type"))
    if t == "friend":
        return bool(include_friends)
    if t == "group":
        return bool(include_groups)
    if t == "official":
        kind = _normalize_text(item.get("officialAccountKind"))
        if kind == "service":
            return bool(include_official_services)
        return bool(include_official_subscriptions)
    if t == "former_friend":
        return bool(include_former_friends)
    if t == "blocked":
        return bool(include_blocked)
    return False


def _filter_contacts_by_type(
    contacts: list[dict[str, Any]],
    *,
    include_friends: bool,
    include_groups: bool,
    include_officials: bool,
    include_official_subscriptions: Optional[bool],
    include_official_services: Optional[bool],
    include_former_friends: bool,
    include_blocked: bool,
) -> list[dict[str, Any]]:
    subscriptions, services = _resolve_official_filter(
        include_officials,
        include_official_subscriptions,
        include_official_services,
    )
    if not any([include_friends, include_groups, subscriptions, services, include_former_friends, include_blocked]):
        return []
    return [
        item
        for item in contacts
        if _contact_type_selected(
            item,
            include_friends=include_friends,
            include_groups=include_groups,
            include_official_subscriptions=subscriptions,
            include_official_services=services,
            include_former_friends=include_former_friends,
            include_blocked=include_blocked,
        )
    ]


def _build_region(country: str, province: str, city: str) -> str:
    parts: list[str] = []
    country_text = _country_label(country)
    province_text = _region_value_label(country, province, city, level="province")
    city_text = _region_value_label(country, province, city, level="city")
    if country_text:
        parts.append(country_text)
    if province_text:
        parts.append(province_text)
    if city_text:
        parts.append(city_text)
    return "·".join(parts)


def _safe_export_part(s: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "_", str(s or "").strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "account"


def _is_valid_contact_username(username: str) -> bool:
    u = _normalize_text(username)
    if not u:
        return False
    if u in _SYSTEM_USERNAMES:
        return False
    if u.startswith("fake_"):
        return False
    if (
        not _should_keep_session(u, include_official=True)
        and not u.startswith("gh_")
        and not u.startswith("weixin")
        and not _is_enterprise_openim_username(u)
    ):
        return False
    return True


def _get_table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except Exception:
        return set()

    out: set[str] = set()
    for row in rows:
        try:
            name = _normalize_text(row["name"] if "name" in row.keys() else row[1]).lower()
        except Exception:
            continue
        if name:
            out.add(name)
    return out


def _build_contact_select_sql(table: str, columns: set[str]) -> Optional[str]:
    if "username" not in columns:
        return None

    specs: list[tuple[list[str], str, str]] = [
        (["username", "user_name", "userName"], "username", "''"),
        (["remark", "Remark"], "remark", "''"),
        (["nick_name", "nickname", "nickName"], "nick_name", "''"),
        (["alias", "Alias"], "alias", "''"),
        (["local_type", "localType"], "local_type", "0"),
        (["verify_flag", "verifyFlag"], "verify_flag", "0"),
        (["flag", "contact_flag", "contactFlag"], "flag", "0"),
        (["quan_pin", "quanPin"], "quan_pin", "''"),
        (["big_head_url", "bigHeadUrl", "big_head_img_url", "bigHeadImgUrl", "avatarUrl"], "big_head_url", "''"),
        (["small_head_url", "smallHeadUrl", "small_head_img_url", "smallHeadImgUrl"], "small_head_url", "''"),
        (["description", "Description"], "description", "''"),
        (["extra_buffer", "extraBuffer"], "extra_buffer", "x''"),
    ]

    select_parts: list[str] = []
    for candidates, alias, fallback in specs:
        source = ""
        for candidate in candidates:
            if candidate.lower() in columns:
                source = candidate
                break
        if source:
            if source == alias:
                select_parts.append(source)
            else:
                select_parts.append(f"{source} AS {alias}")
        else:
            select_parts.append(f"{fallback} AS {alias}")
    return f"SELECT {', '.join(select_parts)} FROM {table}"


def _load_contact_rows_map(contact_db_path: Path, *, include_stranger: bool = False) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not contact_db_path.exists():
        return out

    conn = sqlite3.connect(str(contact_db_path))
    conn.row_factory = sqlite3.Row
    try:
        def read_rows(table: str) -> list[sqlite3.Row]:
            columns = _get_table_columns(conn, table)
            sql = _build_contact_select_sql(table, columns)
            if not sql:
                return []
            try:
                return conn.execute(sql).fetchall()
            except Exception:
                return []
            return []

        table_names = ("contact", "stranger") if include_stranger else ("contact",)
        for table in table_names:
            rows = read_rows(table)
            for row in rows:
                username = _normalize_text(row["username"] if "username" in row.keys() else "")
                if (not username) or (username in out):
                    continue

                extra_info = _parse_contact_extra_buffer(
                    row["extra_buffer"] if "extra_buffer" in row.keys() else b""
                )
                out[username] = {
                    "username": username,
                    "remark": _normalize_text(row["remark"] if "remark" in row.keys() else ""),
                    "nick_name": _normalize_text(row["nick_name"] if "nick_name" in row.keys() else ""),
                    "alias": _normalize_text(row["alias"] if "alias" in row.keys() else ""),
                    "local_type": _to_int(row["local_type"] if "local_type" in row.keys() else 0),
                    "verify_flag": _to_int(row["verify_flag"] if "verify_flag" in row.keys() else 0),
                    "flag": _to_int(row["flag"] if "flag" in row.keys() else 0),
                    "quan_pin": _normalize_text(row["quan_pin"] if "quan_pin" in row.keys() else ""),
                    "big_head_url": _normalize_text(row["big_head_url"] if "big_head_url" in row.keys() else ""),
                    "small_head_url": _normalize_text(row["small_head_url"] if "small_head_url" in row.keys() else ""),
                    "description": _normalize_text(row["description"] if "description" in row.keys() else ""),
                    "_table": table,
                    "gender": _to_int(extra_info.get("gender")),
                    "signature": _normalize_text(extra_info.get("signature")),
                    "country": _normalize_text(extra_info.get("country")),
                    "province": _normalize_text(extra_info.get("province")),
                    "city": _normalize_text(extra_info.get("city")),
                    "source_scene": _to_optional_int(extra_info.get("source_scene")),
                    "add_time": _to_optional_int(extra_info.get("add_time")),
                    "add_time_text": _normalize_text(extra_info.get("add_time_text")),
                }
        return out
    finally:
        conn.close()


def _load_official_account_type_map(contact_db_path: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    if not contact_db_path.exists():
        return out

    conn = sqlite3.connect(str(contact_db_path))
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            _normalize_text(row["name"] if "name" in row.keys() else row[0]).lower(): _normalize_text(row["name"] if "name" in row.keys() else row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        table_name = tables.get("biz_info")
        if not table_name:
            return out
        columns = _get_table_columns(conn, table_name)
        if "username" not in columns or "type" not in columns:
            return out
        try:
            rows = conn.execute(f"SELECT username, type FROM {table_name}").fetchall()
        except Exception:
            return out
        for row in rows:
            username = _normalize_text(row["username"] if "username" in row.keys() else "")
            account_type = _to_optional_int(row["type"] if "type" in row.keys() else None)
            if username and account_type is not None:
                out[username] = account_type
        return out
    finally:
        conn.close()


def _load_session_sort_timestamps(session_db_path: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    if not session_db_path.exists():
        return out

    conn = sqlite3.connect(str(session_db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows: list[sqlite3.Row] = []
        queries = [
            "SELECT username, COALESCE(sort_timestamp, 0) AS ts FROM SessionTable",
            "SELECT username, COALESCE(last_timestamp, 0) AS ts FROM SessionTable",
        ]
        for sql in queries:
            try:
                rows = conn.execute(sql).fetchall()
                break
            except Exception:
                continue

        for row in rows:
            username = _normalize_text(row["username"] if "username" in row.keys() else "")
            if not username:
                continue
            ts = _to_int(row["ts"] if "ts" in row.keys() else 0)
            prev = out.get(username, 0)
            if ts > prev:
                out[username] = ts
        return out
    finally:
        conn.close()


def _load_session_group_usernames(session_db_path: Path) -> set[str]:
    out: set[str] = set()
    if not session_db_path.exists():
        return out

    conn = sqlite3.connect(str(session_db_path))
    conn.row_factory = sqlite3.Row
    try:
        queries = [
            "SELECT username FROM SessionTable",
            "SELECT username FROM sessiontable",
        ]
        for sql in queries:
            try:
                rows = conn.execute(sql).fetchall()
            except Exception:
                continue
            for row in rows:
                username = _normalize_text(row["username"] if "username" in row.keys() else "")
                if username and ("@chatroom" in username):
                    out.add(username)
            return out
        return out
    finally:
        conn.close()


def _infer_contact_type(username: str, row: dict[str, Any]) -> Optional[str]:
    if not username:
        return None

    if username.endswith("@chatroom"):
        return "group"

    local_type = _to_int(_pick_case_insensitive_value(row, "local_type", "localType", "WCDB_CT_local_type"))
    flag = _to_int(_pick_case_insensitive_value(row, "flag", "contact_flag", "contactFlag", "WCDB_CT_flag"))
    verify_flag = _to_int(_pick_case_insensitive_value(row, "verify_flag", "verifyFlag", "VerifyFlag"))
    quan_pin = _normalize_text(_pick_case_insensitive_value(row, "quan_pin", "quanPin", "WCDB_CT_quan_pin"))
    alias = _normalize_text(_pick_case_insensitive_value(row, "alias", "Alias", "WCDB_CT_alias"))
    remark = _normalize_text(_pick_case_insensitive_value(row, "remark", "Remark", "WCDB_CT_remark"))
    lowered_username = username.lower()
    is_openim_enterprise = _is_enterprise_openim_username(username)

    if is_openim_enterprise and not _is_allowed_enterprise_openim_by_local_type(username, local_type):
        return None

    if lowered_username == "weixin":
        return "official"

    if (
        username.startswith("gh_")
        and username not in _BUILTIN_OFFICIAL_HELPER_USERNAMES
        and local_type in {1, 4}
    ):
        return "official"
    if local_type == 4 and verify_flag != 0:
        return "official"

    if (not username.startswith("gh_")) and ((flag & 8) == 8):
        return "blocked"

    is_former_friend_residual = (not username.startswith("gh_")) and (
        (local_type == 0 and bool(quan_pin))
        or (local_type == 3 and flag != 4 and bool(quan_pin or alias or remark))
    )
    if is_former_friend_residual:
        return "former_friend"

    is_visible_weixin_contact = lowered_username.startswith("weixin") and lowered_username != "weixin"
    if is_openim_enterprise:
        return "friend"

    if is_visible_weixin_contact:
        return "friend"

    if local_type == 1 and username not in _FRIEND_EXCLUDE_USERNAMES:
        return "friend"

    return None


def _matches_keyword(contact: dict[str, Any], keyword: str) -> bool:
    kw = _normalize_text(keyword).lower()
    if not kw:
        return True

    fields = [
        contact.get("username", ""),
        contact.get("displayName", ""),
        contact.get("remark", ""),
        contact.get("nickname", ""),
        contact.get("alias", ""),
        contact.get("region", ""),
        contact.get("source", ""),
        contact.get("country", ""),
        contact.get("province", ""),
        contact.get("city", ""),
    ]
    for field in fields:
        if kw in _normalize_text(field).lower():
            return True
    return False


def _contact_item_from_session(
    *,
    account_dir: Path,
    base_url: str,
    username: str,
    display_name: str,
    avatar_link: str,
    sort_ts: int,
) -> dict[str, Any]:
    contact_type = "group" if "@chatroom" in username else ("official" if username.startswith("gh_") or username == "weixin" else "friend")
    display_name = _normalize_text(display_name) or username
    return {
        "username": username,
        "displayName": display_name,
        "remark": "",
        "nickname": display_name if display_name != username else "",
        "alias": "",
        "gender": 0,
        "signature": "",
        "type": contact_type,
        "country": "",
        "province": "",
        "city": "",
        "region": "",
        "sourceScene": None,
        "source": "",
        "addTime": None,
        "addTimeText": "",
        "commonChatroomCount": None,
        "commonChatrooms": [],
        "avatar": base_url + _build_avatar_url(account_dir.name, username),
        "avatarLink": _normalize_text(avatar_link),
        "_sortTs": int(sort_ts or 0),
    }


def _attach_official_account_kind(
    item: dict[str, Any],
    official_account_type_map: dict[str, int],
) -> dict[str, Any]:
    if _normalize_text(item.get("type")) != "official":
        item.pop("officialAccountType", None)
        item.pop("officialAccountKind", None)
        return item

    username = _normalize_text(item.get("username"))
    if username in official_account_type_map:
        account_type = official_account_type_map.get(username)
        item["officialAccountType"] = account_type
        item["officialAccountKind"] = _official_account_kind(account_type)
    else:
        item["officialAccountKind"] = "unknown"
    return item


def _profile_contact_type(username: str, row: Optional[dict[str, Any]] = None) -> str:
    inferred = _infer_contact_type(username, row or {})
    if inferred and inferred != "former_friend":
        return inferred
    if "@chatroom" in username:
        return "group"
    if username.startswith("gh_") or username == "weixin":
        return "official"
    return "friend"


def _pick_contact_row_value(row: dict[str, Any], *keys: str) -> Any:
    return _pick_case_insensitive_value(row, *keys)


def _pick_contact_row_text(row: dict[str, Any], *keys: str) -> str:
    return _normalize_text(_pick_contact_row_value(row, *keys))


def _normalize_contact_profile_row(row: dict[str, Any], fallback_username: str) -> dict[str, Any]:
    username = (
        _pick_contact_row_text(row, "username", "user_name", "userName", "UserName")
        or _normalize_text(fallback_username)
    )
    extra_info = _parse_contact_extra_buffer(
        _pick_contact_row_value(row, "extra_buffer", "extraBuffer", "ExtraBuffer")
    )

    country = _pick_contact_row_text(row, "country", "Country") or _normalize_text(extra_info.get("country"))
    province = _pick_contact_row_text(row, "province", "Province") or _normalize_text(extra_info.get("province"))
    city = _pick_contact_row_text(row, "city", "City") or _normalize_text(extra_info.get("city"))
    signature = (
        _pick_contact_row_text(row, "signature", "sign", "description", "desc", "Description")
        or _normalize_text(extra_info.get("signature"))
    )
    source_scene = _to_optional_int(
        _pick_contact_row_value(row, "source_scene", "sourceScene", "SourceScene")
    )
    if source_scene is None:
        source_scene = _to_optional_int(extra_info.get("source_scene"))
    add_time = _to_optional_int(
        _pick_contact_row_value(row, "add_time", "addTime", "AddTime")
    )
    if add_time is None:
        add_time = _to_optional_int(extra_info.get("add_time"))
    add_time_text = (
        _pick_contact_row_text(row, "add_time_text", "addTimeText", "AddTimeText")
        or _normalize_text(extra_info.get("add_time_text"))
        or _timestamp_date_text(add_time)
    )

    return {
        "username": username,
        "remark": _pick_contact_row_text(row, "remark", "Remark", "WCDB_CT_remark"),
        "nick_name": _pick_contact_row_text(row, "nick_name", "nickname", "nickName", "NickName", "WCDB_CT_nick_name"),
        "alias": _pick_contact_row_text(row, "alias", "Alias", "WCDB_CT_alias"),
        "local_type": _to_int(_pick_contact_row_value(row, "local_type", "localType", "LocalType", "WCDB_CT_local_type")),
        "verify_flag": _to_int(_pick_contact_row_value(row, "verify_flag", "verifyFlag", "VerifyFlag")),
        "flag": _to_int(_pick_contact_row_value(row, "flag", "contact_flag", "contactFlag", "WCDB_CT_flag")),
        "quan_pin": _pick_contact_row_text(row, "quan_pin", "quanPin", "WCDB_CT_quan_pin"),
        "big_head_url": _pick_contact_row_text(
            row,
            "big_head_url",
            "bigHeadUrl",
            "bigHeadURL",
            "big_head_img_url",
            "bigHeadImgUrl",
            "avatarUrl",
        ),
        "small_head_url": _pick_contact_row_text(
            row,
            "small_head_url",
            "smallHeadUrl",
            "smallHeadURL",
            "small_head_img_url",
            "smallHeadImgUrl",
        ),
        "gender": _to_int(_pick_contact_row_value(row, "gender", "Gender") or extra_info.get("gender")),
        "signature": signature,
        "country": country,
        "province": province,
        "city": city,
        "source_scene": source_scene,
        "add_time": add_time,
        "add_time_text": add_time_text,
    }


def _contact_item_from_profile_row(
    *,
    account_dir: Path,
    base_url: str,
    username: str,
    row: Optional[dict[str, Any]],
    display_name_fallback: str = "",
    avatar_link_fallback: str = "",
) -> dict[str, Any]:
    normalized = _normalize_contact_profile_row(row or {}, username) if row else {"username": username}
    resolved_username = _normalize_text(normalized.get("username")) or username
    display_name = _pick_display_name(normalized, resolved_username)
    if display_name == resolved_username and display_name_fallback:
        display_name = display_name_fallback
    avatar_link = _normalize_text(_pick_avatar_url(normalized) or avatar_link_fallback)
    country = _normalize_text(normalized.get("country"))
    province = _normalize_text(normalized.get("province"))
    city = _normalize_text(normalized.get("city"))
    source_scene = _to_optional_int(normalized.get("source_scene"))
    add_time = _to_optional_int(normalized.get("add_time"))
    add_time_text = _normalize_text(normalized.get("add_time_text")) or _timestamp_date_text(add_time)
    return {
        "username": resolved_username,
        "displayName": _normalize_text(display_name) or display_name_fallback or resolved_username,
        "remark": _normalize_text(normalized.get("remark")),
        "nickname": _normalize_text(normalized.get("nick_name")),
        "alias": _normalize_text(normalized.get("alias")),
        "gender": _to_int(normalized.get("gender")),
        "signature": _normalize_text(normalized.get("signature")),
        "type": _profile_contact_type(resolved_username, normalized),
        "country": country,
        "province": province,
        "city": city,
        "region": _build_region(country, province, city),
        "sourceScene": source_scene,
        "source": _source_scene_label(source_scene),
        "addTime": add_time,
        "addTimeText": add_time_text,
        "commonChatroomCount": None,
        "commonChatrooms": [],
        "avatar": base_url + _build_avatar_url(account_dir.name, resolved_username),
        "avatarLink": avatar_link,
        "pinyinKey": _build_contact_pinyin_key(_normalize_text(display_name) or resolved_username),
        "pinyinInitial": _build_contact_pinyin_initial(_normalize_text(display_name) or resolved_username),
    }


def _sql_literal(value: str) -> str:
    return "'" + str(value or "").replace("'", "''") + "'"


def _query_realtime_contact_rows(handle: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    # 通讯录分类口径来自 contact 表。stranger/session 里的历史私聊很多，
    # 不能兜底算作“好友”，否则好友数会膨胀到所有历史会话数量。
    for table in ("contact",):
        try:
            table_rows = _wcdb_exec_query(
                handle,
                kind="contact",
                path=None,
                sql=f"SELECT * FROM {table}",
            )
        except Exception:
            continue
        for row in table_rows or []:
            if not isinstance(row, dict):
                continue
            username = _normalize_text(
                _pick_case_insensitive_value(row, "username", "user_name", "userName", "UserName")
            )
            if not username or username in seen:
                continue
            seen.add(username)
            rows.append(row)
    return rows


def _query_realtime_official_account_type_map(handle: int) -> dict[str, int]:
    out: dict[str, int] = {}
    try:
        rows = _wcdb_exec_query(
            handle,
            kind="contact",
            path=None,
            sql="SELECT username, type FROM biz_info",
        )
    except Exception:
        return out
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        username = _normalize_text(_pick_case_insensitive_value(row, "username", "user_name", "userName"))
        account_type = _to_optional_int(_pick_case_insensitive_value(row, "type", "biz_type", "bizType"))
        if username and account_type is not None:
            out[username] = account_type
    return out


def _query_realtime_contact_row(handle: int, username: str) -> Optional[dict[str, Any]]:
    u = _normalize_text(username)
    if not u:
        return None

    quoted = _sql_literal(u)
    for table in ("contact", "stranger"):
        try:
            rows = _wcdb_exec_query(
                handle,
                kind="contact",
                path=None,
                sql=f"SELECT * FROM {table} WHERE username={quoted} LIMIT 1",
            )
        except Exception:
            continue
        if rows:
            first = rows[0]
            if isinstance(first, dict):
                full_row = dict(first)
                try:
                    compact = _wcdb_get_contact(handle, u)
                    if isinstance(compact, dict):
                        for key, value in compact.items():
                            if value not in (None, "") and not full_row.get(key):
                                full_row[key] = value
                except Exception:
                    pass
                return full_row
    try:
        row = _wcdb_get_contact(handle, u)
        if isinstance(row, dict) and row:
            return row
    except Exception:
        pass
    return None


def _query_realtime_common_chatrooms(handle: int, username: str) -> list[dict[str, Any]]:
    u = _normalize_text(username)
    if not u or u.endswith("@chatroom"):
        return []

    quoted = _sql_literal(u)
    try:
        rows = _wcdb_exec_query(
            handle,
            kind="contact",
            path=None,
            sql=f"""
            SELECT cr.username AS username, cr.id AS roomId
            FROM chatroom_member cm
            JOIN name2id nm ON nm.rowid = cm.member_id
            JOIN chat_room cr ON cr.id = cm.room_id
            WHERE nm.username = {quoted}
            ORDER BY cr.username
            """,
        )
    except Exception:
        return []

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        room_username = _normalize_text(_pick_case_insensitive_value(row, "username", "room_username", "roomUsername"))
        if not room_username or room_username in seen:
            continue
        seen.add(room_username)
        out.append({
            "username": room_username,
            "roomId": _to_int(_pick_case_insensitive_value(row, "roomId", "room_id", "id")),
        })
    return out


def _get_contact_profile_realtime(
    *,
    account_dir: Path,
    base_url: str,
    username: str,
) -> tuple[dict[str, Any], bool]:
    try:
        rt_conn = WCDB_REALTIME.ensure_connected(account_dir)
    except WCDBRealtimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Realtime contact profile unavailable: {e}")

    row: Optional[dict[str, Any]] = None
    display_name_fallback = ""
    avatar_link_fallback = ""
    common_chatrooms: list[dict[str, Any]] = []
    common_chatroom_names: dict[str, str] = {}
    common_chatroom_avatar_links: dict[str, str] = {}
    try:
        with rt_conn.lock:
            row = _query_realtime_contact_row(rt_conn.handle, username)
            common_chatrooms = _query_realtime_common_chatrooms(rt_conn.handle, username)
            room_usernames = [
                _normalize_text(item.get("username"))
                for item in common_chatrooms
                if _normalize_text(item.get("username"))
            ]
            if room_usernames:
                try:
                    common_chatroom_names = _wcdb_get_display_names(rt_conn.handle, room_usernames)
                except Exception:
                    common_chatroom_names = {}
                try:
                    common_chatroom_avatar_links = _wcdb_get_avatar_urls(rt_conn.handle, room_usernames)
                except Exception:
                    common_chatroom_avatar_links = {}
            if row is None:
                try:
                    display_name_fallback = _normalize_text(_wcdb_get_display_names(rt_conn.handle, [username]).get(username))
                except Exception:
                    display_name_fallback = ""
                try:
                    avatar_link_fallback = _normalize_text(_wcdb_get_avatar_urls(rt_conn.handle, [username]).get(username))
                except Exception:
                    avatar_link_fallback = ""
    except WCDBRealtimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Realtime contact profile lookup failed: {e}")

    contact = _contact_item_from_profile_row(
        account_dir=account_dir,
        base_url=base_url,
        username=username,
        row=row,
        display_name_fallback=display_name_fallback,
        avatar_link_fallback=avatar_link_fallback,
    )
    for room in common_chatrooms:
        room_username = _normalize_text(room.get("username"))
        room["displayName"] = _normalize_text(common_chatroom_names.get(room_username)) or room_username
        room["avatar"] = base_url + _build_avatar_url(account_dir.name, room_username)
        room["avatarLink"] = _normalize_text(common_chatroom_avatar_links.get(room_username))
    contact["commonChatroomCount"] = len(common_chatrooms)
    contact["commonChatrooms"] = common_chatrooms[:20]
    return (contact, row is not None)


def _get_contact_profile_decrypted(
    *,
    account_dir: Path,
    base_url: str,
    username: str,
) -> tuple[dict[str, Any], bool]:
    contact_rows = _load_contact_rows_map(account_dir / "contact.db", include_stranger=True)
    row = contact_rows.get(username)
    return (
        _contact_item_from_profile_row(
            account_dir=account_dir,
            base_url=base_url,
            username=username,
            row=row,
        ),
        row is not None,
    )


def _collect_contacts_for_account_realtime(
    *,
    account_dir: Path,
    base_url: str,
    keyword: Optional[str],
    include_friends: bool,
    include_groups: bool,
    include_officials: bool,
    include_official_subscriptions: Optional[bool] = None,
    include_official_services: Optional[bool] = None,
    include_former_friends: bool = False,
    include_blocked: bool = False,
) -> list[dict[str, Any]]:
    official_subscriptions, official_services = _resolve_official_filter(
        include_officials,
        include_official_subscriptions,
        include_official_services,
    )
    if not any([include_friends, include_groups, official_subscriptions, official_services, include_former_friends, include_blocked]):
        return []

    try:
        rt_conn = WCDB_REALTIME.ensure_connected(account_dir)
    except WCDBRealtimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Realtime contacts unavailable: {e}")

    try:
        with rt_conn.lock:
            raw_sessions = _wcdb_get_sessions(rt_conn.handle)
    except WCDBRealtimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Realtime session lookup failed: {e}")

    session_ts_map: dict[str, int] = {}
    session_usernames: list[str] = []
    for item in raw_sessions or []:
        if not isinstance(item, dict):
            continue
        username = _normalize_text(
            _pick_case_insensitive_value(item, "username", "user_name", "UserName")
        )
        if not username or username in session_ts_map:
            continue
        if not _is_valid_contact_username(username):
            continue
        sort_ts = _to_int(
            _pick_case_insensitive_value(item, "sort_timestamp", "sortTimestamp", "last_timestamp", "lastTimestamp")
        )
        session_ts_map[username] = sort_ts
        session_usernames.append(username)

    contact_rows: list[dict[str, Any]] = []
    contact_source_available = False
    official_account_type_map: dict[str, int] = {}
    try:
        with rt_conn.lock:
            # One full-table query provides every field needed by the list,
            # including extra_buffer, type flags and avatar URLs. Older DLLs
            # without exec_query support retain the compact API as a fallback.
            contact_rows = _query_realtime_contact_rows(rt_conn.handle)
            if contact_rows:
                contact_source_available = True
            else:
                try:
                    contact_rows = _wcdb_get_contacts_compact(rt_conn.handle, [])
                    contact_source_available = True
                except Exception:
                    contact_rows = []
            official_account_type_map = _query_realtime_official_account_type_map(rt_conn.handle)
    except Exception:
        contact_rows = []
        contact_source_available = False
        official_account_type_map = {}

    contact_rows_by_username: dict[str, dict[str, Any]] = {}
    for row in contact_rows:
        if not isinstance(row, dict):
            continue
        username = _normalize_text(
            _pick_case_insensitive_value(row, "username", "user_name", "userName", "UserName")
        )
        if username and username not in contact_rows_by_username:
            contact_rows_by_username[username] = row

    usernames = list(dict.fromkeys([*contact_rows_by_username, *session_usernames]))
    display_name_usernames = [
        username
        for username in usernames
        if _pick_display_name(contact_rows_by_username.get(username), username) == username
    ]
    avatar_url_usernames = [
        username
        for username in usernames
        if not _pick_avatar_url(contact_rows_by_username.get(username))
    ]
    display_names: dict[str, str] = {}
    avatar_links: dict[str, str] = {}
    if display_name_usernames or avatar_url_usernames:
        with rt_conn.lock:
            if display_name_usernames:
                try:
                    display_names = _wcdb_get_display_names(rt_conn.handle, display_name_usernames)
                except Exception:
                    display_names = {}
            if avatar_url_usernames:
                try:
                    avatar_links = _wcdb_get_avatar_urls(rt_conn.handle, avatar_url_usernames)
                except Exception:
                    avatar_links = {}

    contacts: list[dict[str, Any]] = []
    seen_contacts: set[str] = set()
    row_usernames: set[str] = set()

    for row in contact_rows:
        username = _normalize_text(
            _pick_case_insensitive_value(row, "username", "user_name", "userName", "UserName")
        )
        if not username or username in row_usernames:
            continue
        row_usernames.add(username)
        if not _is_valid_contact_username(username):
            continue
        contact_type = _infer_contact_type(username, row)
        if contact_type is None:
            continue
        item = _contact_item_from_profile_row(
            account_dir=account_dir,
            base_url=base_url,
            username=username,
            row=row,
            display_name_fallback=_normalize_text(display_names.get(username)),
            avatar_link_fallback=_normalize_text(avatar_links.get(username)),
        )
        item["type"] = contact_type
        item["_sortTs"] = _to_int(session_ts_map.get(username, 0))
        _attach_official_account_kind(item, official_account_type_map)
        if not _matches_keyword(item, keyword or ""):
            continue
        if not _contact_type_selected(
            item,
            include_friends=bool(include_friends),
            include_groups=bool(include_groups),
            include_official_subscriptions=official_subscriptions,
            include_official_services=official_services,
            include_former_friends=bool(include_former_friends),
            include_blocked=bool(include_blocked),
        ):
            continue
        seen_contacts.add(username)
        contacts.append(item)

    for username in session_usernames:
        if username in row_usernames or username in seen_contacts:
            continue
        # 只用 session 兜底群聊。私聊/公众号若不在通讯录表，不应计入通讯录分类。
        # 只有联系人接口本身不可用时，才退回 session 全量口径。
        if contact_source_available and "@chatroom" not in username:
            continue
        item = _contact_item_from_session(
            account_dir=account_dir,
            base_url=base_url,
            username=username,
            display_name=str(display_names.get(username) or username),
            avatar_link=str(avatar_links.get(username) or ""),
            sort_ts=int(session_ts_map.get(username, 0) or 0),
        )
        if "@chatroom" in username:
            item["type"] = "group"
        _attach_official_account_kind(item, official_account_type_map)
        if not _matches_keyword(item, keyword or ""):
            continue
        if not _contact_type_selected(
            item,
            include_friends=bool(include_friends),
            include_groups=bool(include_groups),
            include_official_subscriptions=official_subscriptions,
            include_official_services=official_services,
            include_former_friends=bool(include_former_friends),
            include_blocked=bool(include_blocked),
        ):
            continue
        seen_contacts.add(username)
        contacts.append(item)

    contacts.sort(
        key=lambda x: (
            -_to_int(x.get("_sortTs", 0)),
            _normalize_text(x.get("displayName", "")).lower(),
            _normalize_text(x.get("username", "")).lower(),
        )
    )
    for item in contacts:
        item.pop("_sortTs", None)
        name_for_pinyin = _normalize_text(item.get("displayName")) or _normalize_text(item.get("username"))
        item["pinyinKey"] = _build_contact_pinyin_key(name_for_pinyin)
        item["pinyinInitial"] = _build_contact_pinyin_initial(name_for_pinyin)
    return contacts


def _collect_contacts_for_account(
    *,
    account_dir: Path,
    base_url: str,
    keyword: Optional[str],
    include_friends: bool,
    include_groups: bool,
    include_officials: bool,
    include_official_subscriptions: Optional[bool] = None,
    include_official_services: Optional[bool] = None,
    include_former_friends: bool = False,
    include_blocked: bool = False,
    source: Optional[str] = None,
) -> list[dict[str, Any]]:
    official_subscriptions, official_services = _resolve_official_filter(
        include_officials,
        include_official_subscriptions,
        include_official_services,
    )
    if not any([include_friends, include_groups, official_subscriptions, official_services, include_former_friends, include_blocked]):
        return []

    source_norm = _resolve_contacts_source_for_account(_normalize_contacts_source(source), account_dir)
    if source_norm == "realtime":
        return _collect_contacts_for_account_realtime(
            account_dir=account_dir,
            base_url=base_url,
            keyword=keyword,
            include_friends=include_friends,
            include_groups=include_groups,
            include_officials=include_officials,
            include_official_subscriptions=include_official_subscriptions,
            include_official_services=include_official_services,
            include_former_friends=include_former_friends,
            include_blocked=include_blocked,
        )

    contact_db_path = account_dir / "contact.db"
    session_db_path = account_dir / "session.db"
    contact_rows = _load_contact_rows_map(contact_db_path, include_stranger=True)
    official_account_type_map = _load_official_account_type_map(contact_db_path)
    session_ts_map = _load_session_sort_timestamps(session_db_path)
    session_group_usernames = _load_session_group_usernames(session_db_path)

    contacts: list[dict[str, Any]] = []
    for username, row in contact_rows.items():
        allow_verified_stranger = (
            _normalize_text(row.get("_table")) == "stranger"
            and _to_int(row.get("verify_flag")) != 0
        )
        if not _is_valid_contact_username(username) and not allow_verified_stranger:
            continue

        contact_type = _infer_contact_type(username, row)
        if contact_type is None:
            continue

        display_name = _pick_display_name(row, username)
        if not display_name:
            display_name = username

        avatar_link = _normalize_text(_pick_avatar_url(row) or "")
        avatar = base_url + _build_avatar_url(account_dir.name, username)
        country = _normalize_text(row.get("country"))
        province = _normalize_text(row.get("province"))
        city = _normalize_text(row.get("city"))
        source_scene = _to_optional_int(row.get("source_scene"))
        gender = _to_int(row.get("gender"))
        signature = _normalize_text(row.get("signature"))
        add_time = _to_optional_int(row.get("add_time"))
        add_time_text = _normalize_text(row.get("add_time_text")) or _timestamp_date_text(add_time)

        item = {
            "username": username,
            "displayName": display_name,
            "remark": _normalize_text(row.get("remark")),
            "nickname": _normalize_text(row.get("nick_name")),
            "alias": _normalize_text(row.get("alias")),
            "gender": gender,
            "signature": signature,
            "type": contact_type,
            "country": country,
            "province": province,
            "city": city,
            "region": _build_region(country, province, city),
            "sourceScene": source_scene,
            "source": _source_scene_label(source_scene),
            "addTime": add_time,
            "addTimeText": add_time_text,
            "commonChatroomCount": None,
            "avatar": avatar,
            "avatarLink": avatar_link,
            "_sortTs": _to_int(session_ts_map.get(username, 0)),
        }
        _attach_official_account_kind(item, official_account_type_map)

        if not _matches_keyword(item, keyword or ""):
            continue
        if not _contact_type_selected(
            item,
            include_friends=bool(include_friends),
            include_groups=bool(include_groups),
            include_official_subscriptions=official_subscriptions,
            include_official_services=official_services,
            include_former_friends=bool(include_former_friends),
            include_blocked=bool(include_blocked),
        ):
            continue
        contacts.append(item)

    if include_groups:
        for username in session_group_usernames:
            if username in contact_rows:
                continue
            if not _is_valid_contact_username(username):
                continue

            avatar_link = ""
            avatar = base_url + _build_avatar_url(account_dir.name, username)

            item = {
                "username": username,
                "displayName": username,
                "remark": "",
                "nickname": "",
                "alias": "",
                "gender": 0,
                "signature": "",
                "type": "group",
                "country": "",
                "province": "",
                "city": "",
                "region": "",
                "sourceScene": None,
                "source": "",
                "addTime": None,
                "addTimeText": "",
                "commonChatroomCount": None,
                "avatar": avatar,
                "avatarLink": avatar_link,
                "_sortTs": _to_int(session_ts_map.get(username, 0)),
            }

            if not _matches_keyword(item, keyword or ""):
                continue
            if not _contact_type_selected(
                item,
                include_friends=bool(include_friends),
                include_groups=bool(include_groups),
                include_official_subscriptions=official_subscriptions,
                include_official_services=official_services,
                include_former_friends=bool(include_former_friends),
                include_blocked=bool(include_blocked),
            ):
                continue
            contacts.append(item)

    contacts.sort(
        key=lambda x: (
            -_to_int(x.get("_sortTs", 0)),
            _normalize_text(x.get("displayName", "")).lower(),
            _normalize_text(x.get("username", "")).lower(),
        )
    )
    for item in contacts:
        item.pop("_sortTs", None)
        name_for_pinyin = _normalize_text(item.get("displayName")) or _normalize_text(item.get("username"))
        item["pinyinKey"] = _build_contact_pinyin_key(name_for_pinyin)
        item["pinyinInitial"] = _build_contact_pinyin_initial(name_for_pinyin)
    return contacts


def _build_counts(contacts: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "friends": 0,
        "groups": 0,
        "officials": 0,
        "officialSubscriptions": 0,
        "officialServices": 0,
        "officialEnterprises": 0,
        "officialUnknown": 0,
        "official_subscription": 0,
        "official_service": 0,
        "official_enterprise": 0,
        "official_unknown": 0,
        "services": 0,
        "formerFriends": 0,
        "former_friends": 0,
        "former_friend": 0,
        "blocked": 0,
        "total": 0,
    }
    for item in contacts:
        t = _normalize_text(item.get("type"))
        if t == "friend":
            counts["friends"] += 1
        elif t == "group":
            counts["groups"] += 1
        elif t == "official":
            counts["officials"] += 1
            kind = _normalize_text(item.get("officialAccountKind")) or "unknown"
            if kind == "service":
                counts["officialServices"] += 1
                counts["official_service"] += 1
                counts["services"] += 1
            elif kind == "enterprise":
                counts["officialEnterprises"] += 1
                counts["official_enterprise"] += 1
                counts["officialSubscriptions"] += 1
                counts["official_subscription"] += 1
            elif kind == "unknown":
                counts["officialUnknown"] += 1
                counts["official_unknown"] += 1
                counts["officialSubscriptions"] += 1
                counts["official_subscription"] += 1
            else:
                counts["officialSubscriptions"] += 1
                counts["official_subscription"] += 1
        elif t == "former_friend":
            counts["formerFriends"] += 1
            counts["former_friends"] += 1
            counts["former_friend"] += 1
        elif t == "blocked":
            counts["blocked"] += 1
    counts["total"] = len(contacts)
    return counts


def _build_export_contacts(
    contacts: list[dict[str, Any]],
    *,
    include_avatar_link: bool,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in contacts:
        row = {
            "username": _normalize_text(item.get("username")),
            "displayName": _normalize_text(item.get("displayName")),
            "remark": _normalize_text(item.get("remark")),
            "nickname": _normalize_text(item.get("nickname")),
            "alias": _normalize_text(item.get("alias")),
            "type": _normalize_text(item.get("type")),
            "officialAccountKind": _normalize_text(item.get("officialAccountKind")),
            "officialAccountType": item.get("officialAccountType") if item.get("officialAccountType") is not None else "",
            "region": _normalize_text(item.get("region")),
            "country": _normalize_text(item.get("country")),
            "province": _normalize_text(item.get("province")),
            "city": _normalize_text(item.get("city")),
            "source": _normalize_text(item.get("source")),
            "sourceScene": _to_optional_int(item.get("sourceScene")),
        }
        if include_avatar_link:
            row["avatarLink"] = _normalize_text(item.get("avatarLink")) or _normalize_text(item.get("avatar"))
        out.append(row)
    return out


def _write_json_export(
    output_path: Path,
    *,
    account: str,
    source: str,
    contacts: list[dict[str, Any]],
    include_avatar_link: bool,
    keyword: str,
    contact_types: ContactTypeFilter,
) -> None:
    payload = {
        "exportedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "account": account,
        "source": source,
        "count": len(contacts),
        "filters": {
            "keyword": keyword,
            "contactTypes": {
                "friends": bool(contact_types.friends),
                "groups": bool(contact_types.groups),
                "officials": bool(contact_types.officials),
                "officialSubscriptions": (
                    bool(contact_types.officials)
                    if contact_types.official_subscriptions is None
                    else bool(contact_types.official_subscriptions)
                ),
                "officialServices": (
                    bool(contact_types.officials)
                    if contact_types.official_services is None
                    else bool(contact_types.official_services)
                ),
                "formerFriends": bool(contact_types.former_friends),
                "blocked": bool(contact_types.blocked),
            },
            "includeAvatarLink": bool(include_avatar_link),
        },
        "contacts": contacts,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _contact_export_columns(include_avatar_link: bool) -> list[tuple[str, str]]:
    columns: list[tuple[str, str]] = [
        ("username", "用户名"),
        ("displayName", "显示名称"),
        ("remark", "备注"),
        ("nickname", "昵称"),
        ("alias", "微信号"),
        ("type", "类型"),
        ("officialAccountKind", "公众号类型"),
        ("officialAccountType", "公众号类型码"),
        ("region", "地区"),
        ("country", "国家/地区码"),
        ("province", "省份"),
        ("city", "城市"),
        ("source", "来源"),
        ("sourceScene", "来源场景码"),
    ]
    if include_avatar_link:
        columns.append(("avatarLink", "头像链接"))
    return columns


def _write_csv_export(
    output_path: Path,
    *,
    contacts: list[dict[str, Any]],
    include_avatar_link: bool,
) -> None:
    columns = _contact_export_columns(include_avatar_link)

    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([label for _, label in columns])
        for item in contacts:
            writer.writerow([_normalize_text(item.get(key, "")) for key, _ in columns])


def _write_txt_export(
    output_path: Path,
    *,
    account: str,
    source: str,
    contacts: list[dict[str, Any]],
    include_avatar_link: bool,
) -> None:
    columns = _contact_export_columns(include_avatar_link)
    lines = ["联系人导出", f"账号: {account}", f"数据源: {source}", f"数量: {len(contacts)}", ""]
    for index, contact in enumerate(contacts, start=1):
        lines.append(f"[{index}] " + " | ".join(
            f"{label}: {_normalize_text(contact.get(key, ''))}" for key, label in columns if _normalize_text(contact.get(key, ""))
        ))
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n")


def _write_html_export(
    output_path: Path,
    *,
    export_id: str,
    account: str,
    source: str,
    contacts: list[dict[str, Any]],
    include_avatar_link: bool,
) -> tuple[Path, Path]:
    identity_fields = [("username", "用户名"), ("displayName", "显示名称")]
    detail_fields = [
        ("remark", "备注"),
        ("nickname", "昵称"),
        ("alias", "微信号"),
        ("region", "地区"),
        ("source", "来源"),
    ]

    def render_value(value: Any) -> str:
        text = _normalize_text(value)
        if not text:
            return '<span class="empty-value">未填写</span>'
        return html.escape(text)

    def render_card(contact: dict[str, Any]) -> str:
        display_name = next(
            (
                _normalize_text(contact.get(key))
                for key in ("displayName", "remark", "nickname", "username")
                if _normalize_text(contact.get(key))
            ),
            "未命名联系人",
        )
        initial = display_name[:1].upper() if display_name else "?"
        avatar_url = _normalize_text(contact.get("avatarLink")) if include_avatar_link else ""
        if avatar_url and not re.match(r"^https?://", avatar_url, flags=re.IGNORECASE):
            avatar_url = ""

        avatar_image = f'<span class="contact-avatar fallback">{html.escape(initial)}</span>'
        if avatar_url:
            escaped_avatar_url = html.escape(avatar_url, quote=True)
            avatar_image += (
                f'<img class="contact-avatar" src="{escaped_avatar_url}" alt="{html.escape(display_name, quote=True)}的头像" '
                'loading="lazy" referrerpolicy="no-referrer" onerror="this.hidden=true">'
            )

        identity = "".join(
            f'<div class="contact-field"><span>{html.escape(label)}</span><b>{render_value(contact.get(key, ""))}</b></div>'
            for key, label in identity_fields
        )
        details = "".join(
            f'<div class="contact-field"><span>{html.escape(label)}</span><b>{render_value(contact.get(key, ""))}</b></div>'
            for key, label in detail_fields
        )
        return f'''<article class="contact-card">
  <div class="contact-head"><figure><div class="avatar-frame">{avatar_image}</div></figure><div class="identity-fields">{identity}</div></div>
  <div class="contact-details">{details}</div>
</article>'''

    cards = "\n".join(render_card(contact) for contact in contacts)
    content = f'<section class="contact-grid">{cards}</section>' if cards else '<div class="empty-state">没有符合条件的联系人</div>'
    document = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>联系人导出</title><style>{export_css("contacts")}</style></head><body><div class="records-page"><main class="records-frame"><header class="masthead"><div><h1>联系人</h1><span class="count">共<strong>{len(contacts)}</strong>个联系人</span></div><div class="export-meta">账号 {html.escape(account)} · 数据源 {html.escape(source)}</div></header><div class="section-bar"><strong>全部联系人</strong><span>已显示 {len(contacts)} 个</span></div>{content}</main></div></body></html>
'''
    return write_protected_html_file(output_path, document, export_id)


def _write_excel_export(
    output_path: Path,
    *,
    contacts: list[dict[str, Any]],
    include_avatar_link: bool,
) -> None:
    columns = _contact_export_columns(include_avatar_link)
    workbook = build_xlsx_workbook(
        [("联系人", [label for _, label in columns], [[_normalize_text(item.get(key, "")) for key, _ in columns] for item in contacts])]
    )
    output_path.write_bytes(workbook)


@router.get("/api/chat/contacts/profile", summary="获取单个联系人资料")
def get_chat_contact_profile(
    request: Request,
    account: Optional[str] = None,
    username: str = "",
    source: Optional[str] = None,
):
    account_dir = _resolve_account_dir(account)
    source_norm = _resolve_contacts_source_for_account(_normalize_contacts_source(source), account_dir)
    base_url = str(request.base_url).rstrip("/")
    normalized_username = _normalize_text(username)
    if not normalized_username:
        raise HTTPException(status_code=400, detail="username is required.")

    if source_norm == "realtime":
        contact, found = _get_contact_profile_realtime(
            account_dir=account_dir,
            base_url=base_url,
            username=normalized_username,
        )
    else:
        contact, found = _get_contact_profile_decrypted(
            account_dir=account_dir,
            base_url=base_url,
            username=normalized_username,
        )

    return {
        "status": "success",
        "account": account_dir.name,
        "source": source_norm,
        "found": bool(found),
        "contact": contact,
    }


@router.get("/api/chat/contacts", summary="获取联系人列表")
def list_chat_contacts(
    request: Request,
    account: Optional[str] = None,
    source: Optional[str] = None,
    keyword: Optional[str] = None,
    include_friends: bool = True,
    include_groups: bool = True,
    include_officials: bool = True,
    include_official_subscriptions: Optional[bool] = None,
    include_official_services: Optional[bool] = None,
    include_former_friends: bool = False,
    include_blocked: bool = False,
):
    account_dir = _resolve_account_dir(account)
    source_norm = _resolve_contacts_source_for_account(_normalize_contacts_source(source), account_dir)
    base_url = str(request.base_url).rstrip("/")

    all_contacts = _collect_contacts_for_account(
        account_dir=account_dir,
        base_url=base_url,
        keyword=keyword,
        include_friends=True,
        include_groups=True,
        include_officials=True,
        include_official_subscriptions=True,
        include_official_services=True,
        include_former_friends=True,
        include_blocked=True,
        source=source_norm,
    )
    contacts = _filter_contacts_by_type(
        all_contacts,
        include_friends=bool(include_friends),
        include_groups=bool(include_groups),
        include_officials=bool(include_officials),
        include_official_subscriptions=include_official_subscriptions,
        include_official_services=include_official_services,
        include_former_friends=bool(include_former_friends),
        include_blocked=bool(include_blocked),
    )

    return {
        "status": "success",
        "account": account_dir.name,
        "source": source_norm,
        "total": len(contacts),
        "counts": _build_counts(all_contacts),
        "contacts": contacts,
    }


@router.post("/api/chat/contacts/export", summary="导出联系人")
def export_chat_contacts(request: Request, req: ContactExportRequest):
    load_wce_integrity_native()
    account_dir = _resolve_account_dir(req.account)
    source_norm = _resolve_contacts_source_for_account(_normalize_contacts_source(req.source), account_dir)

    output_dir_raw = _normalize_text(req.output_dir)
    if not output_dir_raw:
        raise HTTPException(status_code=400, detail="output_dir is required.")

    output_dir = Path(output_dir_raw).expanduser()
    if not output_dir.is_absolute():
        raise HTTPException(status_code=400, detail="output_dir must be an absolute path.")

    export_id = uuid.uuid4().hex
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to prepare output_dir: {e}")

    base_url = str(request.base_url).rstrip("/")
    contacts = _collect_contacts_for_account(
        account_dir=account_dir,
        base_url=base_url,
        keyword=req.keyword,
        include_friends=bool(req.contact_types.friends),
        include_groups=bool(req.contact_types.groups),
        include_officials=bool(req.contact_types.officials),
        include_official_subscriptions=req.contact_types.official_subscriptions,
        include_official_services=req.contact_types.official_services,
        include_former_friends=bool(req.contact_types.former_friends),
        include_blocked=bool(req.contact_types.blocked),
        source=source_norm,
    )

    export_contacts = _build_export_contacts(
        contacts,
        include_avatar_link=bool(req.include_avatar_link),
    )

    fmt = _normalize_text(req.format).lower()
    if fmt not in {"html", "json", "txt", "excel", "csv"}:
        raise HTTPException(status_code=400, detail="Unsupported format, use 'html', 'json', 'txt', or 'excel'.")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_account = _safe_export_part(account_dir.name)
    extension = "xlsx" if fmt == "excel" else fmt
    output_path = output_dir / f"contacts_{safe_account}_{ts}.{extension}"

    try:
        if fmt == "json":
            _write_json_export(
                output_path,
                account=account_dir.name,
                source=source_norm,
                contacts=export_contacts,
                include_avatar_link=bool(req.include_avatar_link),
                keyword=_normalize_text(req.keyword),
                contact_types=req.contact_types,
            )
        elif fmt == "csv":
            _write_csv_export(
                output_path,
                contacts=export_contacts,
                include_avatar_link=bool(req.include_avatar_link),
            )
        elif fmt == "txt":
            _write_txt_export(
                output_path,
                account=account_dir.name,
                source=source_norm,
                contacts=export_contacts,
                include_avatar_link=bool(req.include_avatar_link),
            )
        elif fmt == "html":
            integrity_manifest_path, integrity_signature_path = _write_html_export(
                output_path,
                export_id=export_id,
                account=account_dir.name,
                source=source_norm,
                contacts=export_contacts,
                include_avatar_link=bool(req.include_avatar_link),
            )
        else:
            _write_excel_export(
                output_path,
                contacts=export_contacts,
                include_avatar_link=bool(req.include_avatar_link),
            )
        if fmt != "html":
            integrity_manifest_path, integrity_signature_path = write_file_integrity_sidecars(output_path, export_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export contacts: {e}")

    return {
        "status": "success",
        "account": account_dir.name,
        "source": source_norm,
        "format": fmt,
        "outputPath": str(output_path),
        "integrityManifestPath": str(integrity_manifest_path),
        "integritySignaturePath": str(integrity_signature_path),
        "count": len(export_contacts),
    }


@router.get("/api/chat/contacts/export/style", summary="获取原生联系人导出样式")
def get_chat_contacts_export_style():
    return Response(content=export_css("contacts"), media_type="text/css; charset=utf-8")


@router.post("/api/chat/contacts/export/seal", summary="签名浏览器端联系人导出文件")
def seal_chat_contacts_browser_export(req: ContactBrowserExportSealRequest):
    try:
        payload = base64.b64decode(req.content_base64, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid export payload.") from exc
    if len(payload) > 64 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Export payload is too large.")
    file_name = Path(req.file_name).name
    sealed = (
        seal_protected_html_bytes(file_name, payload, uuid.uuid4().hex)
        if file_name.lower().endswith((".html", ".htm"))
        else seal_bytes_artifact(file_name, payload, uuid.uuid4().hex)
    )
    return {
        "status": "success",
        **sealed,
    }
