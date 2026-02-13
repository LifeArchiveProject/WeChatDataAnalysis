import base64
import hashlib
import html
import os
import re
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, quote, urlparse

from fastapi import HTTPException

from .app_paths import get_output_databases_dir
from .logging_config import get_logger

try:
    import zstandard as zstd  # type: ignore
except Exception:
    zstd = None

logger = get_logger(__name__)

_OUTPUT_DATABASES_DIR = get_output_databases_dir()
_DEBUG_SESSIONS = os.environ.get("WECHAT_TOOL_DEBUG_SESSIONS", "0") == "1"


def _list_decrypted_accounts() -> list[str]:
    if not _OUTPUT_DATABASES_DIR.exists():
        return []

    accounts: list[str] = []
    for p in _OUTPUT_DATABASES_DIR.iterdir():
        if not p.is_dir():
            continue
        if (p / "session.db").exists() and (p / "contact.db").exists():
            accounts.append(p.name)

    accounts.sort()
    return accounts


def _resolve_account_dir(account: Optional[str]) -> Path:
    accounts = _list_decrypted_accounts()
    if not accounts:
        raise HTTPException(
            status_code=404,
            detail="No decrypted databases found. Please decrypt first.",
        )

    selected = account or accounts[0]
    base = _OUTPUT_DATABASES_DIR.resolve()
    candidate = (_OUTPUT_DATABASES_DIR / selected).resolve()

    if candidate != base and base not in candidate.parents:
        raise HTTPException(status_code=400, detail="Invalid account path.")

    if not candidate.exists() or not candidate.is_dir():
        raise HTTPException(status_code=404, detail="Account not found.")

    if not (candidate / "session.db").exists():
        raise HTTPException(status_code=404, detail="session.db not found for this account.")
    if not (candidate / "contact.db").exists():
        raise HTTPException(status_code=404, detail="contact.db not found for this account.")

    return candidate


def _should_keep_session(username: str, include_official: bool) -> bool:
    if not username:
        return False

    if not include_official and username.startswith("gh_"):
        return False

    if username.startswith(("weixin", "qqmail", "fmessage", "medianote", "floatbottle", "newsapp")):
        return False

    if "@kefu.openim" in username:
        return False
    if "@openim" in username:
        return False
    if "service_" in username:
        return False

    if username in {
        "brandsessionholder",
        "brandservicesessionholder",
        "notifymessage",
        "opencustomerservicemsg",
        "notification_messages",
        "userexperience_alarm",
    }:
        return False

    return username.endswith("@chatroom") or username.startswith("wxid_") or ("@" not in username)


def _format_session_time(ts: Optional[int]) -> str:
    """智能时间格式化：今天显示时间，昨天显示"昨天 HH:MM"，本周显示"星期X HH:MM"，本年显示"M月D日 HH:MM"，跨年显示"YYYY年M月D日 HH:MM"""
    if not ts:
        return ""
    try:
        dt = datetime.fromtimestamp(int(ts))
        now = datetime.now()
        time_str = dt.strftime("%H:%M")

        # 计算日期差异（基于日历日期）
        today_start = datetime(now.year, now.month, now.day)
        target_start = datetime(dt.year, dt.month, dt.day)
        day_diff = (today_start - target_start).days

        # 今天
        if day_diff == 0:
            return time_str

        # 昨天
        if day_diff == 1:
            return f"昨天 {time_str}"

        # 本周内（2-6天前，显示星期）
        if 2 <= day_diff <= 6:
            week_days = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
            # Python weekday(): Monday=0, Sunday=6
            return f"{week_days[dt.weekday()]} {time_str}"

        # 本年内
        if dt.year == now.year:
            return f"{dt.month}月{dt.day}日 {time_str}"

        # 跨年
        return f"{dt.year}年{dt.month}月{dt.day}日 {time_str}"
    except Exception:
        return ""


def _infer_last_message_brief(msg_type: Optional[int], sub_type: Optional[int]) -> str:
    t = int(msg_type or 0)
    s = int(sub_type or 0)

    if t == 1:
        return "[Text]"
    if t == 3:
        return "[Image]"
    if t == 34:
        return "[Voice]"
    if t == 42:
        return "[Contact Card]"
    if t == 43:
        return "[Video]"
    if t == 47:
        return "[Emoji]"
    if t == 48:
        return "[Location]"
    if t == 49:
        if s == 5:
            return "[Link]"
        if s == 6:
            return "[File]"
        if s in (33, 36):
            return "[Mini Program]"
        if s == 57:
            return "[Quote]"
        if s in (63, 88):
            return "[Live]"
        if s == 87:
            return "[Announcement]"
        if s == 2000:
            return "[Transfer]"
        if s == 2003:
            return "[Red Packet]"
        if s == 19:
            return "[聊天记录]"
        return "[App Message]"
    if t == 10000:
        return "[System]"
    return "[Message]"


def _infer_message_brief_by_local_type(local_type: Optional[int]) -> str:
    t = int(local_type or 0)
    if t == 1:
        return ""
    if t == 3:
        return "[Image]"
    if t == 34:
        return "[Voice]"
    if t == 43:
        return "[Video]"
    if t == 47:
        return "[Emoji]"
    if t == 48:
        return "[Location]"
    if t == 50:
        return "[VoIP]"
    if t == 10000:
        return "[System]"
    if t == 244813135921:
        return "[Quote]"
    if t == 17179869233:
        return "[Link]"
    if t == 21474836529:
        return "[Article]"
    if t == 154618822705:
        return "[Mini Program]"
    if t == 12884901937:
        return "[Music]"
    if t == 8594229559345:
        return "[Red Packet]"
    if t == 81604378673:
        return "[聊天记录]"
    if t == 266287972401:
        return "[Pat]"
    if t == 8589934592049:
        return "[Transfer]"
    if t == 270582939697:
        return "[Live]"
    if t == 25769803825:
        return "[File]"
    return "[Message]"


def _quote_ident(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def _resolve_msg_table_name(conn: sqlite3.Connection, username: str) -> Optional[str]:
    if not username:
        return None
    md5_hex = hashlib.md5(username.encode("utf-8")).hexdigest()
    expected = f"msg_{md5_hex}".lower()
    expected_chat = f"chat_{md5_hex}".lower()

    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = [r[0] for r in rows if r and r[0]]

    for name in names:
        if str(name).lower() == expected:
            return str(name)

    for name in names:
        if str(name).lower() == expected_chat:
            return str(name)

    for name in names:
        ln = str(name).lower()
        if ln.startswith("msg_") and md5_hex in ln:
            return str(name)
        if ln.startswith("chat_") and md5_hex in ln:
            return str(name)

    for name in names:
        if md5_hex in str(name).lower():
            return str(name)

    partial = md5_hex[:24]
    for name in names:
        if partial in str(name).lower():
            return str(name)

    return None


def _query_head_image_usernames(head_image_db_path: Path, usernames: list[str]) -> set[str]:
    uniq = list(dict.fromkeys([u for u in usernames if u]))
    if not uniq:
        return set()
    if not head_image_db_path.exists():
        return set()

    conn = sqlite3.connect(str(head_image_db_path))
    try:
        placeholders = ",".join(["?"] * len(uniq))
        rows = conn.execute(
            f"SELECT username FROM head_image WHERE username IN ({placeholders})",
            uniq,
        ).fetchall()
        return {str(r[0]) for r in rows if r and r[0]}
    finally:
        conn.close()


def _build_avatar_url(account_dir_name: str, username: str) -> str:
    return f"/api/chat/avatar?account={quote(account_dir_name)}&username={quote(username)}"


def _decode_sqlite_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="ignore")
        except Exception:
            return ""
    if isinstance(value, memoryview):
        try:
            return bytes(value).decode("utf-8", errors="ignore")
        except Exception:
            return ""
    return str(value)


def _is_mostly_printable_text(s: str) -> bool:
    if not s:
        return False
    sample = s[:600]
    if not sample:
        return False
    printable = sum(1 for ch in sample if ch.isprintable() or ch in {"\n", "\r", "\t"})
    return (printable / len(sample)) >= 0.85


def _looks_like_xml(s: str) -> bool:
    if not s:
        return False
    t = s.lstrip()
    if t.startswith('"') and t.endswith('"'):
        t = t.strip('"').lstrip()
    return t.startswith("<")


def _decode_message_content(compress_value: Any, message_value: Any) -> str:
    def try_decode_text_blob(text: str) -> Optional[str]:
        t = (text or "").strip()
        if not t:
            return None

        # zstd frame magic: 28 b5 2f fd
        zstd_magic = b"\x28\xb5\x2f\xfd"

        if len(t) >= 16 and len(t) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", t):
            try:
                raw = bytes.fromhex(t)
                if zstd is not None and raw.startswith(zstd_magic):
                    try:
                        out = zstd.decompress(raw)
                        s2 = out.decode("utf-8", errors="ignore")
                        s2 = html.unescape(s2.strip())
                        if _looks_like_xml(s2) or _is_mostly_printable_text(s2):
                            return s2
                    except Exception:
                        pass
                s2 = raw.decode("utf-8", errors="ignore")
                s2 = html.unescape(s2.strip())
                # Avoid decoding user-sent pure-hex text (e.g. "68656c6c6f") into arbitrary strings;
                # only accept non-zstd hex if it still looks like a message XML payload.
                s2_lower = s2.lower()
                if (
                    _looks_like_xml(s2)
                    or ("<msg" in s2_lower and "</msg>" in s2_lower)
                    or "<appmsg" in s2_lower
                ):
                    return s2
            except Exception:
                return None

        if len(t) >= 24 and len(t) % 4 == 0 and re.fullmatch(r"[A-Za-z0-9+/=]+", t):
            try:
                raw = base64.b64decode(t)
                if zstd is not None and raw.startswith(zstd_magic):
                    try:
                        out = zstd.decompress(raw)
                        s2 = out.decode("utf-8", errors="ignore")
                        s2 = html.unescape(s2.strip())
                        if _looks_like_xml(s2) or _is_mostly_printable_text(s2):
                            return s2
                    except Exception:
                        pass
                s2 = raw.decode("utf-8", errors="ignore")
                s2 = html.unescape(s2.strip())
                s2_lower = s2.lower()
                if (
                    _looks_like_xml(s2)
                    or ("<msg" in s2_lower and "</msg>" in s2_lower)
                    or "<appmsg" in s2_lower
                ):
                    return s2
            except Exception:
                return None

        return None

    msg_text = _decode_sqlite_text(message_value)

    # Realtime WCDB mode can return message_content as a hex/base64 encoded blob string
    # (often a zstd frame starting with 28b52ffd...), while compress_content is null.
    # NOTE: some callers set sqlite3.text_factory=bytes, so TEXT may arrive as bytes even when it
    # is actually hex/base64 text; decode from msg_text, not from the raw python type.
    s = html.unescape(msg_text.strip())
    s2 = try_decode_text_blob(s)
    if s2:
        msg_text = s2

    if isinstance(message_value, (bytes, bytearray, memoryview)):
        raw = bytes(message_value) if isinstance(message_value, memoryview) else message_value
        if raw.startswith(b"\x28\xb5\x2f\xfd") and zstd is not None:
            try:
                out = zstd.decompress(raw)
                s = out.decode("utf-8", errors="ignore")
                s = html.unescape(s.strip())
                if _looks_like_xml(s) or _is_mostly_printable_text(s):
                    msg_text = s
            except Exception:
                pass

    if compress_value is None:
        return msg_text

    if isinstance(compress_value, str):
        s = html.unescape(compress_value.strip())
        s2 = try_decode_text_blob(s)
        if s2:
            return s2
        if _looks_like_xml(s) or _is_mostly_printable_text(s):
            return s
        return msg_text

    data: Optional[bytes] = None
    if isinstance(compress_value, memoryview):
        data = bytes(compress_value)
    elif isinstance(compress_value, (bytes, bytearray)):
        data = bytes(compress_value)

    if not data:
        return msg_text

    if zstd is not None:
        try:
            out = zstd.decompress(data)
            s = out.decode("utf-8", errors="ignore")
            s = html.unescape(s.strip())
            if _looks_like_xml(s) or _is_mostly_printable_text(s):
                return s
        except Exception:
            pass

    try:
        s = data.decode("utf-8", errors="ignore")
        s = html.unescape(s.strip())
        s2 = try_decode_text_blob(s)
        if s2:
            return s2
        if _looks_like_xml(s) or _is_mostly_printable_text(s):
            return s
    except Exception:
        pass

    return msg_text


_MD5_HEX_RE = re.compile(rb"(?i)[0-9a-f]{32}")
_DAT_MD5_RE = re.compile(rb"(?i)([0-9a-f]{32})(?:[._][thbc])?\.dat")
_PACKED_INFO_HEX_RE = re.compile(r"(?i)^[0-9a-f]+$")


def _extract_md5_from_blob(blob: Any) -> str:
    if blob is None:
        return ""
    if isinstance(blob, memoryview):
        data = bytes(blob)
    elif isinstance(blob, (bytes, bytearray)):
        data = bytes(blob)
    else:
        try:
            data = bytes(blob)
        except Exception:
            return ""

    if not data:
        return ""

    # Prefer md5 that appears as an actual `.dat` filename (incl. _t.dat/.t.dat variants).
    # This matches echotrace's idea: packed_info often contains multiple 32-hex tokens, but only
    # the one referenced by a file path is the correct on-disk basename.
    try:
        m2 = _DAT_MD5_RE.findall(data)
    except Exception:
        m2 = []
    if m2:
        best2 = Counter([x.lower() for x in m2]).most_common(1)[0][0]
        try:
            return best2.decode("ascii", errors="ignore")
        except Exception:
            return ""

    m = _MD5_HEX_RE.findall(data)
    if not m:
        return ""
    best = Counter([x.lower() for x in m]).most_common(1)[0][0]
    try:
        return best.decode("ascii", errors="ignore")
    except Exception:
        return ""


def _extract_md5_from_packed_info(packed_info: Any) -> str:
    if packed_info is None:
        return ""

    data: bytes = b""
    if isinstance(packed_info, memoryview):
        data = packed_info.tobytes()
    elif isinstance(packed_info, (bytes, bytearray)):
        data = bytes(packed_info)
    elif isinstance(packed_info, str):
        s = packed_info.strip()
        if s.lower().startswith("0x"):
            s = s[2:]
        if s and _PACKED_INFO_HEX_RE.fullmatch(s) and (len(s) % 2 == 0):
            try:
                data = bytes.fromhex(s)
            except Exception:
                data = b""
        else:
            data = s.encode("utf-8", errors="ignore")
    else:
        if isinstance(packed_info, (int, float, bool)):
            data = b""
        else:
            try:
                data = bytes(packed_info)
            except Exception:
                data = b""

    md5 = _extract_md5_from_blob(data)
    md5 = str(md5 or "").strip().lower()
    if len(md5) == 32 and all(c in "0123456789abcdef" for c in md5):
        return md5
    return ""


def _resource_lookup_chat_id(resource_conn: sqlite3.Connection, username: str) -> Optional[int]:
    if not username:
        return None
    try:
        row = resource_conn.execute(
            "SELECT rowid FROM ChatName2Id WHERE user_name = ? LIMIT 1",
            (username,),
        ).fetchone()
        if row and row[0] is not None:
            return int(row[0])
    except Exception:
        return None
    return None


def _lookup_resource_md5(
    resource_conn: sqlite3.Connection,
    chat_id: Optional[int],
    message_local_type: int,
    server_id: int,
    local_id: int,
    create_time: int,
) -> str:
    if server_id <= 0 and local_id <= 0:
        return ""

    where_chat = ""
    params_prefix: list[Any] = []
    if chat_id is not None and int(chat_id) > 0:
        where_chat = " AND chat_id = ?"
        params_prefix.append(int(chat_id))

    where_type = ""
    if int(message_local_type) > 0:
        where_type = " AND message_local_type = ?"
        params_prefix.append(int(message_local_type))

    try:
        if server_id > 0:
            row = resource_conn.execute(
                "SELECT packed_info FROM MessageResourceInfo WHERE message_svr_id = ?"
                + where_chat
                + where_type
                + " ORDER BY message_id DESC LIMIT 1",
                [int(server_id)] + params_prefix,
            ).fetchone()
            if row and row[0] is not None:
                md5 = _extract_md5_from_blob(row[0])
                if md5:
                    return md5
    except Exception:
        pass

    try:
        if local_id > 0 and create_time > 0:
            row = resource_conn.execute(
                "SELECT packed_info FROM MessageResourceInfo WHERE message_local_id = ? AND message_create_time = ?"
                + where_chat
                + where_type
                + " ORDER BY message_id DESC LIMIT 1",
                [int(local_id), int(create_time)] + params_prefix,
            ).fetchone()
            if row and row[0] is not None:
                return _extract_md5_from_blob(row[0])
    except Exception:
        pass

    return ""


def _strip_cdata(s: str) -> str:
    if not s:
        return ""
    out = s.replace("<![CDATA[", "").replace("]]>", "")
    return out.strip()


def _normalize_xml_url(url: str) -> str:
    """Normalize URLs extracted from XML attributes/tags (e.g. decode '&amp;')."""
    u = str(url or "").strip()
    if not u:
        return ""
    try:
        return html.unescape(u).strip()
    except Exception:
        return u.replace("&amp;", "&").strip()


def _is_mp_weixin_article_url(url: str) -> bool:
    u = str(url or "").strip()
    if not u:
        return False

    try:
        host = str(urlparse(u).hostname or "").strip().lower()
        if host == "mp.weixin.qq.com" or host.endswith(".mp.weixin.qq.com"):
            return True
    except Exception:
        pass

    lu = u.lower()
    return "mp.weixin.qq.com/" in lu


def _is_mp_weixin_feed_article_url(url: str) -> bool:
    """Detect WeChat's PC feed/recommendation mp.weixin.qq.com share URLs.

    These links often carry an `exptype` like:
      masonry_feed_brief_content_elite_for_pcfeeds_u2i

    WeChat desktop tends to render them in a cover-card style (image + bottom title),
    so we use this as a hint to choose the 'cover' linkStyle.
    """

    u = str(url or "").strip()
    if not u:
        return False

    try:
        parsed = urlparse(u)
        q = parse_qs(parsed.query or "")
        for v in (q.get("exptype") or []):
            if "masonry_feed" in str(v or "").lower():
                return True
    except Exception:
        pass

    return "exptype=masonry_feed" in u.lower()


def _classify_link_share(*, app_type: int, url: str, source_username: str, desc: str) -> tuple[str, str]:
    src = str(source_username or "").strip().lower()
    is_official_article = bool(
        app_type in (5, 68)
        and (_is_mp_weixin_article_url(url) or src.startswith("gh_"))
    )

    link_type = "official_article" if is_official_article else "web_link"

    d = str(desc or "").strip()
    hashtag_count = len(re.findall(r"#[^#\s]+", d))

    # 公众号文章中「封面图 + 底栏标题」卡片特征：摘要以 #话题# 风格为主。
    cover_like = bool(
        is_official_article
        and (
            d.startswith("#")
            or hashtag_count >= 2
            or _is_mp_weixin_feed_article_url(url)
        )
    )
    link_style = "cover" if cover_like else "default"
    return link_type, link_style


def _extract_xml_tag_text(xml_text: str, tag: str) -> str:
    if not xml_text or not tag:
        return ""
    m = re.search(
        rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>",
        xml_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return ""
    return _strip_cdata(m.group(1) or "")


def _extract_xml_attr(xml_text: str, attr: str) -> str:
    if not xml_text or not attr:
        return ""
    m = re.search(rf"{re.escape(attr)}\s*=\s*['\"]([^'\"]+)['\"]", xml_text, flags=re.IGNORECASE)
    return (m.group(1) or "").strip() if m else ""


def _extract_xml_tag_or_attr(xml_text: str, name: str) -> str:
    v = _extract_xml_tag_text(xml_text, name)
    if v:
        return v
    return _extract_xml_attr(xml_text, name)


def _parse_system_message_content(raw_text: str) -> str:
    text = str(raw_text or "").strip()
    if not text:
        return "[系统消息]"

    def _clean_system_text(value: str) -> str:
        candidate = str(value or "").strip()
        if not candidate:
            return ""

        nested_content = _extract_xml_tag_text(candidate, "content")
        if nested_content:
            candidate = nested_content

        candidate = re.sub(r"<!\[CDATA\[", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\]\]>", "", candidate)
        candidate = re.sub(r"</?[_a-zA-Z0-9]+[^>]*>", "", candidate)
        candidate = re.sub(r"\s+", " ", candidate).strip()
        return candidate

    if "revokemsg" in text.lower():
        replace_msg = _extract_xml_tag_text(text, "replacemsg")
        cleaned_replace_msg = _clean_system_text(replace_msg)
        if cleaned_replace_msg:
            return cleaned_replace_msg

        revoke_msg = _extract_xml_tag_text(text, "revokemsg")
        cleaned_revoke_msg = _clean_system_text(revoke_msg)
        if cleaned_revoke_msg:
            return cleaned_revoke_msg

        return "撤回了一条消息"

    content_text = _clean_system_text(text)
    return content_text or "[系统消息]"


def _extract_refermsg_block(xml_text: str) -> str:
    if not xml_text:
        return ""
    m = re.search(r"(<refermsg[^>]*>.*?</refermsg>)", xml_text, flags=re.IGNORECASE | re.DOTALL)
    return (m.group(1) or "").strip() if m else ""


def _extract_refermsg_content(refer_block: str) -> str:
    if not refer_block:
        return ""

    cdata_match = re.search(
        r"<content\b[^>]*>\s*<!\[CDATA\[(.*?)\]\]>\s*</content>",
        refer_block,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if cdata_match:
        return str(cdata_match.group(1) or "").strip()

    return _extract_xml_tag_text(refer_block, "content")


def _summarize_nested_quote_content(raw_content: str) -> str:
    candidate = str(raw_content or "").strip()
    if not candidate:
        return ""

    lower = candidate.lower()
    if "<msg" not in lower and "<appmsg" not in lower:
        return candidate

    for tag in ("title", "des"):
        value = _extract_xml_tag_text(candidate, tag)
        if value:
            return value

    content_value = _extract_xml_tag_text(candidate, "content")
    if content_value and (not str(content_value).lstrip().startswith("<")):
        return content_value

    return ""


def _extract_nested_quote_thumb_url(raw_content: str) -> str:
    candidate = str(raw_content or "").strip()
    if not candidate:
        return ""

    probes = [candidate]

    if candidate.startswith("wxid_"):
        colon = candidate.find(":")
        if 0 < colon <= 64:
            rest = candidate[colon + 1 :].strip()
            if rest:
                probes.append(rest)

    for probe in probes:
        for key in ("thumburl", "cdnthumburl", "cdnthumurl", "coverurl", "cover"):
            value = _normalize_xml_url(_extract_xml_tag_or_attr(probe, key))
            if value:
                return value

    return ""


def _infer_transfer_status_text(
    is_sent: bool,
    paysubtype: str,
    receivestatus: str,
    sendertitle: str,
    receivertitle: str,
    senderdes: str,
    receiverdes: str,
) -> str:
    t = str(paysubtype or "").strip()
    rs = str(receivestatus or "").strip()

    if rs == "1":
        return "已被接收" if is_sent else "已收款"
    if rs == "2":
        return "已退还"
    if rs == "3":
        return "已过期"

    if t == "4":
        return "已退还"
    if t == "9":
        return "已被退还"
    if t == "10":
        return "已过期"

    if t == "8":
        return "发起转账"
    if t == "3":
        return "已被接收" if is_sent else "已收款"
    if t == "1":
        return "转账"

    title = sendertitle if is_sent else receivertitle
    if title:
        return title
    des = senderdes if is_sent else receiverdes
    if des:
        return des
    return "转账"


def _split_group_sender_prefix(
    text: str,
    known_sender_username: str = "",
    known_sender_alias: str = "",
) -> tuple[str, str]:
    if not text:
        return "", text
    sep = text.find(":\n")
    if sep <= 0:
        return "", text
    prefix = text[:sep].strip()
    body = text[sep + 2 :].lstrip("\n")
    if not prefix or len(prefix) > 128:
        return "", text
    if re.search(r"\s", prefix):
        return "", text

    strong_hint = prefix.startswith("wxid_") or prefix.endswith("@chatroom") or "@" in prefix
    probe = body.lstrip()
    body_is_xml = probe.startswith("<") or probe.startswith('"<')

    known_values = {str(known_sender_username or "").strip(), str(known_sender_alias or "").strip()}
    known_values.discard("")
    if known_values:
        if prefix in known_values:
            return prefix, body
        if strong_hint or body_is_xml:
            return prefix, body
        return "", text

    if strong_hint or body_is_xml:
        return prefix, body
    return "", text


def _extract_sender_from_group_xml(xml_text: str) -> str:
    if not xml_text:
        return ""

    probe_text = xml_text
    try:
        # Avoid picking nested quoted-message sender from <refermsg>.
        probe_text = re.sub(
            r"(<refermsg[^>]*>.*?</refermsg>)",
            "",
            xml_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
    except Exception:
        probe_text = xml_text

    v = _extract_xml_tag_text(probe_text, "fromusername")
    if v:
        return v
    v = _extract_xml_attr(probe_text, "fromusername")
    if v:
        return v
    return ""


def _parse_pat_message(text: str, contact_rows: dict[str, sqlite3.Row]) -> str:
    template = _extract_xml_tag_text(text, "template")
    if not template:
        return "[拍一拍]"
    wxids = list({m.group(1) for m in re.finditer(r"\$\{([^}]+)\}", template) if m.group(1)})
    rendered = template
    for wxid in wxids:
        row = contact_rows.get(wxid)
        name = _pick_display_name(row, wxid)
        rendered = rendered.replace(f"${{{wxid}}}", name)
    return rendered.strip() or "[拍一拍]"


def _parse_quote_message(text: str) -> str:
    title = _extract_xml_tag_text(text, "title")
    if title:
        return title
    refer = _extract_xml_tag_text(text, "content")
    if refer:
        return refer
    return "[引用消息]"


def _parse_app_message(text: str) -> dict[str, Any]:
    app_type_raw = _extract_xml_tag_text(text, "type")
    try:
        app_type = int(str(app_type_raw or "0").strip() or "0")
    except Exception:
        app_type = 0
    title = _extract_xml_tag_text(text, "title")
    des = _extract_xml_tag_text(text, "des")
    url = _normalize_xml_url(_extract_xml_tag_text(text, "url"))

    # Some appmsg payloads (notably mp.weixin.qq.com link shares) include a "source" block:
    #   <sourceusername>gh_xxx</sourceusername>
    #   <sourcedisplayname>公众号名</sourcedisplayname>
    # We'll surface that as `from` so the frontend can render the publisher line like WeChat.
    source_display_name = (
        _extract_xml_tag_text(text, "sourcedisplayname")
        or _extract_xml_tag_text(text, "sourceDisplayName")
        or _extract_xml_tag_text(text, "appname")
    )
    source_username = (
        _extract_xml_tag_text(text, "sourceusername")
        or _extract_xml_tag_text(text, "sourceUsername")
    )

    lower = text.lower()

    if app_type == 19:
        # 合并转发聊天记录（Chat History）
        # 注意：recorditem 的 CDATA 内部可能包含 <refermsg> 等标签，不能据此把整条消息误判为引用消息。
        record_item = _extract_xml_tag_text(text, "recorditem")
        preview = (des or "").strip()
        if not preview:
            if record_item:
                preview = str(_extract_xml_tag_text(record_item, "desc") or "").strip()

        return {
            "renderType": "chatHistory",
            "content": preview or "[聊天记录]",
            "title": (title or "").strip() or "聊天记录",
            "recordItem": record_item or "",
        }

    if app_type in (4, 5, 68) and url:
        # Many appmsg link cards (notably Bilibili shares with <type>4</type>) include a <patMsg> metadata block.
        # DO NOT treat "<patmsg" presence as a pat message: it would misclassify normal link cards as "[拍一拍]".
        thumb_url = _normalize_xml_url(
            _extract_xml_tag_text(text, "thumburl") or _extract_xml_tag_text(text, "cdnthumburl")
        )
        link_type, link_style = _classify_link_share(
            app_type=app_type,
            url=url,
            source_username=str(source_username or "").strip(),
            desc=str(des or "").strip(),
        )
        return {
            "renderType": "link",
            "content": des or title or "[链接]",
            "title": title or des or "",
            "url": url,
            "thumbUrl": thumb_url or "",
            "from": str(source_display_name or "").strip(),
            "fromUsername": str(source_username or "").strip(),
            "linkType": link_type,
            "linkStyle": link_style,
        }

    if app_type in (6, 74):
        file_name = title or ""
        total_len = _extract_xml_tag_text(text, "totallen")
        file_md5 = (
            _extract_xml_tag_or_attr(text, "md5")
            or _extract_xml_tag_or_attr(text, "filemd5")
            or _extract_xml_tag_or_attr(text, "file_md5")
        )
        return {
            "renderType": "file",
            "content": f"[文件] {file_name}".strip(),
            "title": file_name,
            "size": total_len or "",
            "fileMd5": file_md5 or "",
        }

    refermsg_probe = lower
    if "<recorditem" in lower and "<refermsg" in lower:
        # 合并转发聊天记录/其它 appmsg 里可能在 recorditem CDATA 内包含 refermsg，
        # 需要先剔除 recorditem 再判断是否为真正的引用消息。
        try:
            refermsg_probe = re.sub(
                r"(<recorditem[^>]*>.*?</recorditem>)",
                "",
                text,
                flags=re.IGNORECASE | re.DOTALL,
            ).lower()
        except Exception:
            refermsg_probe = lower

    if app_type == 57 or "<refermsg" in refermsg_probe:
        refer_block = _extract_refermsg_block(text)

        try:
            text_wo_refer = re.sub(
                r"(<refermsg[^>]*>.*?</refermsg>)",
                "",
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )
        except Exception:
            text_wo_refer = text

        reply_text = _extract_xml_tag_text(text_wo_refer, "title") or _extract_xml_tag_text(text, "title")
        refer_displayname = _extract_xml_tag_or_attr(refer_block, "displayname")
        refer_fromusr = (
            _extract_xml_tag_or_attr(refer_block, "fromusr")
            or _extract_xml_tag_or_attr(refer_block, "fromusername")
            or ""
        )
        refer_svrid = _extract_xml_tag_or_attr(refer_block, "svrid")
        refer_content = _extract_refermsg_content(refer_block)
        refer_type = _extract_xml_tag_or_attr(refer_block, "type")

        rt = (reply_text or "").strip()
        rc = (refer_content or "").strip()
        if rt and rc:
            if rc == rt:
                refer_content = ""
            else:
                lines = [ln.strip() for ln in rc.splitlines()]
                if lines and lines[0] == rt:
                    refer_content = "\n".join(rc.splitlines()[1:]).lstrip()
                elif rc.startswith(rt):
                    rest = rc[len(rt) :].lstrip()
                    refer_content = rest

        t = str(refer_type or "").strip()
        quote_thumb_url = ""
        quote_voice_length = ""
        if t == "3":
            refer_content = "[图片]"
        elif t == "47":
            refer_content = "[表情]"
        elif t == "43" or t == "62":
            refer_content = "[视频]"
        elif t == "34":
            # Some versions embed voice length (ms) in refermsg.content, e.g.
            # "wxid_xxx:15369:1:" -> 15s
            try:
                rc = str(refer_content or "").strip()
                parts = rc.split(":")
                if len(parts) >= 2:
                    dur_raw = (parts[1] or "").strip()
                    if dur_raw.isdigit():
                        quote_voice_length = str(int(dur_raw))
            except Exception:
                quote_voice_length = ""
            refer_content = "[语音]"
        elif t == "57":
            summarized = _summarize_nested_quote_content(str(refer_content or ""))
            if summarized:
                refer_content = summarized
            elif str(refer_content or "").lstrip().startswith("<"):
                refer_content = "[引用消息]"
        elif t in {"49", "5", "68"}:
            raw_link_content = str(refer_content or "").strip()
            summarized = _summarize_nested_quote_content(raw_link_content)
            link_text = str(summarized or raw_link_content).strip()
            quote_thumb_url = _extract_nested_quote_thumb_url(raw_link_content)

            if link_text.startswith("wxid_"):
                colon = link_text.find(":")
                if 0 < colon <= 64:
                    maybe_rest = link_text[colon + 1 :].strip()
                    if maybe_rest:
                        second_try = _summarize_nested_quote_content(maybe_rest)
                        link_text = str(second_try or maybe_rest).strip()
                    if not quote_thumb_url:
                        quote_thumb_url = _extract_nested_quote_thumb_url(maybe_rest)

            refer_content = f"[链接] {link_text}".strip() if link_text else "[链接]"

        return {
            "renderType": "quote",
            "content": reply_text or "[引用消息]",
            "quoteUsername": str(refer_fromusr or "").strip(),
            "quoteTitle": refer_displayname or "",
            "quoteContent": refer_content or "",
            "quoteType": t,
            "quoteThumbUrl": quote_thumb_url,
            "quoteServerId": str(refer_svrid or "").strip(),
            "quoteVoiceLength": quote_voice_length,
        }

    # Some versions may mark pat messages via sysmsg/appmsg tag attribute: <sysmsg type="patmsg">...</sysmsg>.
    # Be strict here: lots of non-pat appmsg payloads still carry a nested <patMsg>...</patMsg> metadata block.
    patmsg_attr = bool(re.search(r"<(sysmsg|appmsg)\b[^>]*\btype=['\"]patmsg['\"]", lower))
    if app_type == 62 or patmsg_attr:
        return {"renderType": "system", "content": "[拍一拍]"}

    if app_type == 2000 or (
        "<wcpayinfo" in text and ("transfer" in text.lower() or "paysubtype" in text.lower())
    ):
        feedesc = _extract_xml_tag_or_attr(text, "feedesc")
        pay_memo = _extract_xml_tag_or_attr(text, "pay_memo")
        paysubtype = _extract_xml_tag_or_attr(text, "paysubtype")
        receivestatus = _extract_xml_tag_or_attr(text, "receivestatus")
        sendertitle = _extract_xml_tag_or_attr(text, "sendertitle")
        receivertitle = _extract_xml_tag_or_attr(text, "receivertitle")
        senderdes = _extract_xml_tag_or_attr(text, "senderdes")
        receiverdes = _extract_xml_tag_or_attr(text, "receiverdes")
        transferid = _extract_xml_tag_or_attr(text, "transferid")
        invalidtime = _extract_xml_tag_or_attr(text, "invalidtime")

        logger.debug(
            f"[转账解析] paysubtype={paysubtype}, receivestatus={receivestatus}, "
            f"transferid={transferid}, feedesc={feedesc}"
        )

        return {
            "renderType": "transfer",
            "content": (pay_memo or "").strip(),
            "title": (feedesc or title or "").strip(),
            "amount": feedesc or "",
            "paySubType": str(paysubtype or "").strip(),
            "receiveStatus": str(receivestatus or "").strip(),
            "senderTitle": sendertitle or "",
            "receiverTitle": receivertitle or "",
            "senderDes": senderdes or "",
            "receiverDes": receiverdes or "",
            "transferId": str(transferid or "").strip(),
            "invalidTime": str(invalidtime or "").strip(),
        }

    if app_type in (2001, 2003) or (
        "<wcpayinfo" in text and ("redenvelope" in text.lower() or "sendertitle" in text.lower())
    ):
        sendertitle = _extract_xml_tag_text(text, "sendertitle")
        receivertitle = _extract_xml_tag_text(text, "receivertitle")
        senderdes = _extract_xml_tag_text(text, "senderdes")
        receiverdes = _extract_xml_tag_text(text, "receiverdes")
        cover = _extract_xml_tag_text(text, "receiverc2cshowsourceurl")
        return {
            "renderType": "redPacket",
            "content": (sendertitle or receivertitle or title or "红包").strip() or "红包",
            "title": (senderdes or receiverdes or des or "").strip(),
            "coverUrl": cover or "",
        }

    if title or des:
        return {"renderType": "text", "content": title or des}

    return {"renderType": "text", "content": "[应用消息]"}


def _iter_message_db_paths(account_dir: Path) -> list[Path]:
    if not account_dir.exists():
        return []

    candidates: list[Path] = []
    for p in account_dir.glob("*.db"):
        n = p.name
        ln = n.lower()
        if ln in {"session.db", "contact.db", "head_image.db"}:
            continue
        if ln == "message_resource.db":
            continue
        if ln == "message_fts.db":
            continue

        if re.match(r"^message(_\d+)?\.db$", ln):
            candidates.append(p)
            continue
        if re.match(r"^biz_message(_\d+)?\.db$", ln):
            candidates.append(p)
            continue
        if "message" in ln and ln.endswith(".db"):
            candidates.append(p)
            continue
    candidates.sort(key=lambda x: x.name)
    return candidates


def _resolve_msg_table_name_by_map(lower_to_actual: dict[str, str], username: str) -> Optional[str]:
    if not username:
        return None
    md5_hex = hashlib.md5(username.encode("utf-8")).hexdigest()
    expected = f"msg_{md5_hex}".lower()
    expected_chat = f"chat_{md5_hex}".lower()

    if expected in lower_to_actual:
        return lower_to_actual[expected]
    if expected_chat in lower_to_actual:
        return lower_to_actual[expected_chat]

    for ln, actual in lower_to_actual.items():
        if ln.startswith("msg_") and md5_hex in ln:
            return actual
        if ln.startswith("chat_") and md5_hex in ln:
            return actual

    for ln, actual in lower_to_actual.items():
        if md5_hex in ln:
            return actual

    partial = md5_hex[:24]
    for ln, actual in lower_to_actual.items():
        if partial in ln:
            return actual

    return None


def _build_latest_message_preview(
    username: str,
    local_type: int,
    raw_text: str,
    is_group: bool,
    sender_username: str = "",
) -> str:
    raw_text = (raw_text or "").strip()
    sender_prefix = ""
    if is_group and raw_text and (not raw_text.startswith("<")) and (not raw_text.startswith('"<')):
        sender_prefix, raw_text = _split_group_sender_prefix(raw_text, sender_username)
    if is_group and (not sender_prefix) and sender_username:
        sender_prefix = str(sender_username).strip()

    content_text = ""
    if local_type == 10000:
        content_text = _parse_system_message_content(raw_text)
    elif local_type == 244813135921:
        parsed = _parse_app_message(raw_text)
        qt = str(parsed.get("quoteTitle") or "").strip()
        qc = str(parsed.get("quoteContent") or "").strip()
        c0 = str(parsed.get("content") or "").strip()
        content_text = qc or c0 or qt or "[引用消息]"
    elif local_type == 49:
        parsed = _parse_app_message(raw_text)
        rt = str(parsed.get("renderType") or "")
        content_text = str(parsed.get("content") or "")
        title_text = str(parsed.get("title") or "").strip()
        if rt == "chatHistory":
            content_text = "[聊天记录]"
        if rt == "file" and title_text:
            content_text = title_text
        if (not content_text) and rt == "transfer":
            content_text = (
                str(parsed.get("senderTitle") or "")
                or str(parsed.get("receiverTitle") or "")
                or "转账"
            )
        if not content_text:
            content_text = title_text or str(parsed.get("url") or "")
    elif local_type == 25769803825:
        parsed = _parse_app_message(raw_text)
        title_text = str(parsed.get("title") or "").strip()
        content_text = title_text or str(parsed.get("content") or "").strip() or "[文件]"
    elif local_type == 3:
        content_text = "[图片]"
    elif local_type == 34:
        duration = _extract_xml_attr(raw_text, "voicelength")
        content_text = f"[语音 {duration}秒]" if duration else "[语音]"
    elif local_type == 43 or local_type == 62:
        content_text = "[视频]"
    elif local_type == 47:
        content_text = "[动画表情]"
    else:
        if raw_text and (not raw_text.startswith("<")) and (not raw_text.startswith('"<')):
            content_text = raw_text
        else:
            content_text = _infer_message_brief_by_local_type(local_type)

    content_text = (content_text or "").strip() or _infer_message_brief_by_local_type(local_type)
    content_text = re.sub(r"\s+", " ", content_text).strip()
    if sender_prefix and content_text:
        return f"{sender_prefix}: {content_text}"
    return content_text


def _extract_group_preview_sender_username(preview_text: str) -> str:
    text = str(preview_text or "").strip()
    if not text:
        return ""

    match = re.match(r"^([^:\s]{1,128}):\s*.+$", text)
    if not match:
        return ""

    sender = str(match.group(1) or "").strip()
    if not sender:
        return ""

    if sender.startswith("wxid_") or sender.endswith("@chatroom") or ("@" in sender):
        return sender
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{1,127}", sender):
        return sender
    return ""


def _normalize_session_preview_text(
    preview_text: str,
    *,
    is_group: bool,
    sender_display_names: Optional[dict[str, str]] = None,
) -> str:
    text = re.sub(r"\s+", " ", str(preview_text or "").strip()).strip()
    if not text:
        return ""

    text = text.replace("[表情]", "[动画表情]")
    if (not is_group) or text.startswith("[草稿]"):
        return text

    match = re.match(r"^([^:\s]{1,128}):\s*(.+)$", text)
    if not match:
        return text

    sender_username = str(match.group(1) or "").strip()
    body = str(match.group(2) or "").strip()
    if (not sender_username) or (not body):
        return text

    display_name = str((sender_display_names or {}).get(sender_username) or "").strip()
    if display_name and display_name != sender_username:
        return f"{display_name}: {body}"
    return text


def _replace_preview_sender_prefix(preview_text: str, sender_display_name: str) -> str:
    text = re.sub(r"\s+", " ", str(preview_text or "").strip()).strip()
    if not text:
        return ""

    display_name = str(sender_display_name or "").strip()
    if (not display_name) or text.startswith("[草稿]"):
        return text

    match = re.match(r"^([^:\n]{1,128}):\s*(.+)$", text)
    if not match:
        return text

    body = re.sub(r"\s+", " ", str(match.group(2) or "").strip()).strip()
    if not body:
        return text
    return f"{display_name}: {body}"


def _build_group_sender_display_name_map(
    contact_db_path: Path,
    previews: dict[str, str],
) -> dict[str, str]:
    group_sender_usernames: set[str] = set()
    for conv_username, preview_text in previews.items():
        if not str(conv_username or "").endswith("@chatroom"):
            continue
        sender_username = _extract_group_preview_sender_username(preview_text)
        if sender_username:
            group_sender_usernames.add(sender_username)

    if not group_sender_usernames:
        return {}

    display_names: dict[str, str] = {}
    sender_contact_rows = _load_contact_rows(contact_db_path, list(group_sender_usernames))
    for sender_username in group_sender_usernames:
        row = sender_contact_rows.get(sender_username)
        if row is None:
            continue
        display_name = _pick_display_name(row, sender_username)
        if display_name and display_name != sender_username:
            display_names[sender_username] = display_name
    return display_names


def _load_latest_message_previews(account_dir: Path, usernames: list[str]) -> dict[str, str]:
    if not usernames:
        return {}

    db_paths = _iter_message_db_paths(account_dir)
    if not db_paths:
        return {}

    remaining = {u for u in usernames if u}
    best: dict[str, tuple[tuple[int, int, int], str]] = {}
    expected_ts_by_user: dict[str, int] = {}

    session_db_path = Path(account_dir) / "session.db"
    if session_db_path.exists() and remaining:
        sconn = sqlite3.connect(str(session_db_path))
        sconn.row_factory = sqlite3.Row
        try:
            uniq = list(dict.fromkeys([u for u in remaining if u]))
            chunk_size = 900
            for i in range(0, len(uniq), chunk_size):
                chunk = uniq[i : i + chunk_size]
                placeholders = ",".join(["?"] * len(chunk))
                try:
                    rows = sconn.execute(
                        f"SELECT username, sort_timestamp, last_timestamp FROM SessionTable WHERE username IN ({placeholders})",
                        chunk,
                    ).fetchall()
                    for r in rows:
                        u = str(r["username"] or "").strip()
                        if not u:
                            continue
                        ts = int(r["sort_timestamp"] or 0)
                        if ts <= 0:
                            ts = int(r["last_timestamp"] or 0)
                        expected_ts_by_user[u] = int(ts or 0)
                except sqlite3.OperationalError:
                    rows = sconn.execute(
                        f"SELECT username, last_timestamp FROM SessionTable WHERE username IN ({placeholders})",
                        chunk,
                    ).fetchall()
                    for r in rows:
                        u = str(r["username"] or "").strip()
                        if not u:
                            continue
                        expected_ts_by_user[u] = int(r["last_timestamp"] or 0)
        except Exception:
            expected_ts_by_user = {}
        finally:
            sconn.close()

    if _DEBUG_SESSIONS:
        logger.info(
            f"[sessions.preview] account_dir={account_dir} usernames={len(remaining)} dbs={len(db_paths)}"
        )
        logger.info(
            f"[sessions.preview] db_paths={', '.join([p.name for p in db_paths[:8]])}{'...' if len(db_paths) > 8 else ''}"
        )

    for db_path in db_paths:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            names = [str(r[0]) for r in rows if r and r[0]]
            lower_to_actual = {n.lower(): n for n in names}

            found: dict[str, str] = {}
            for u in list(remaining):
                tn = _resolve_msg_table_name_by_map(lower_to_actual, u)
                if tn:
                    found[u] = tn

            if not found:
                continue

            conn.text_factory = bytes
            for u, tn in found.items():
                quoted = _quote_ident(tn)
                try:
                    try:
                        r = conn.execute(
                            "SELECT "
                            "m.local_type, m.message_content, m.compress_content, m.create_time, m.sort_seq, m.local_id, "
                            "n.user_name AS sender_username "
                            f"FROM {quoted} m "
                            "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
                            "ORDER BY m.sort_seq DESC, m.local_id DESC "
                            "LIMIT 1"
                        ).fetchone()
                    except Exception:
                        r = conn.execute(
                            "SELECT "
                            "local_type, message_content, compress_content, create_time, sort_seq, local_id, '' AS sender_username "
                            f"FROM {quoted} "
                            "ORDER BY sort_seq DESC, local_id DESC "
                            "LIMIT 1"
                        ).fetchone()
                except Exception as e:
                    if _DEBUG_SESSIONS:
                        logger.info(
                            f"[sessions.preview] db={db_path.name} username={u} table={tn} query_failed={e}"
                        )
                    continue
                if r is None:
                    continue

                local_type = int(r["local_type"] or 0)
                create_time = int(r["create_time"] or 0)
                sort_seq = int(r["sort_seq"] or 0) if r["sort_seq"] is not None else 0
                local_id = int(r["local_id"] or 0)

                expected_ts = int(expected_ts_by_user.get(u) or 0)
                if expected_ts > 0 and create_time > 0 and create_time < expected_ts:
                    try:
                        r2 = conn.execute(
                            "SELECT "
                            "m.local_type, m.message_content, m.compress_content, m.create_time, m.sort_seq, m.local_id, "
                            "n.user_name AS sender_username "
                            f"FROM {quoted} m "
                            "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
                            "ORDER BY COALESCE(m.create_time, 0) DESC, COALESCE(m.sort_seq, 0) DESC, m.local_id DESC "
                            "LIMIT 1"
                        ).fetchone()
                    except Exception:
                        try:
                            r2 = conn.execute(
                                "SELECT "
                                "local_type, message_content, compress_content, create_time, sort_seq, local_id, '' AS sender_username "
                                f"FROM {quoted} "
                                "ORDER BY COALESCE(create_time, 0) DESC, COALESCE(sort_seq, 0) DESC, local_id DESC "
                                "LIMIT 1"
                            ).fetchone()
                        except Exception:
                            r2 = None

                    if r2 is not None:
                        r = r2
                        local_type = int(r["local_type"] or 0)
                        create_time = int(r["create_time"] or 0)
                        sort_seq = int(r["sort_seq"] or 0) if r["sort_seq"] is not None else 0
                        local_id = int(r["local_id"] or 0)

                sort_key = (create_time, sort_seq, local_id)

                raw_text = _decode_message_content(r["compress_content"], r["message_content"]).strip()
                sender_username = _decode_sqlite_text(r["sender_username"]).strip()
                preview = _build_latest_message_preview(
                    username=u,
                    local_type=local_type,
                    raw_text=raw_text,
                    is_group=bool(u.endswith("@chatroom")),
                    sender_username=sender_username,
                )
                if not preview:
                    continue

                prev = best.get(u)
                if prev is None or sort_key > prev[0]:
                    best[u] = (sort_key, preview)
        finally:
            conn.close()

    previews = {u: v[1] for u, v in best.items() if v and v[1]}
    if _DEBUG_SESSIONS:
        logger.info(
            f"[sessions.preview] built_previews={len(previews)} remaining_without_preview={len(remaining - set(previews.keys()))}"
        )
    return previews


def _pick_display_name(contact_row: Optional[sqlite3.Row], fallback_username: str) -> str:
    if contact_row is None:
        return fallback_username

    for key in ("remark", "nick_name", "alias"):
        try:
            v = contact_row[key]
        except Exception:
            v = None
        if isinstance(v, str) and v.strip():
            return v.strip()

    return fallback_username


def _pick_avatar_url(contact_row: Optional[sqlite3.Row]) -> Optional[str]:
    if contact_row is None:
        return None

    for key in ("big_head_url", "small_head_url"):
        try:
            v = contact_row[key]
        except Exception:
            v = None
        if isinstance(v, str) and v.strip():
            return v.strip()

    return None


def _load_contact_rows(contact_db_path: Path, usernames: list[str]) -> dict[str, sqlite3.Row]:
    uniq = list(dict.fromkeys([u for u in usernames if u]))
    if not uniq:
        return {}

    result: dict[str, sqlite3.Row] = {}

    conn = sqlite3.connect(str(contact_db_path))
    conn.row_factory = sqlite3.Row
    try:
        def query_table(table: str, targets: list[str]) -> None:
            if not targets:
                return
            placeholders = ",".join(["?"] * len(targets))
            sql = f"""
                SELECT username, remark, nick_name, alias, big_head_url, small_head_url
                FROM {table}
                WHERE username IN ({placeholders})
            """
            rows = conn.execute(sql, targets).fetchall()
            for r in rows:
                result[r["username"]] = r

        query_table("contact", uniq)
        missing = [u for u in uniq if u not in result]
        query_table("stranger", missing)
        return result
    finally:
        conn.close()


def _load_group_nickname_map_from_contact_db(
    contact_db_path: Path,
    chatroom_id: str,
    sender_usernames: list[str],
) -> dict[str, str]:
    """Best-effort mapping for group member nickname (aka group card) from contact.db.

    WeChat stores per-chatroom member nicknames in `contact.db.chat_room.ext_buffer` as a protobuf-like blob.
    This helper parses that blob and returns { sender_username -> group_nickname } for the requested senders.

    Notes:
    - Best-effort: never raises; returns {} on any failure.
    - Only resolves usernames included in `sender_usernames` to keep parsing cheap.
    """

    chatroom = str(chatroom_id or "").strip()
    if not chatroom.endswith("@chatroom"):
        return {}

    targets = list(dict.fromkeys([str(x or "").strip() for x in sender_usernames if str(x or "").strip()]))
    if not targets:
        return {}
    target_set = set(targets)

    def decode_varint(raw: bytes, offset: int) -> tuple[Optional[int], int]:
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

    def iter_fields(raw: bytes):
        idx = 0
        n = len(raw)
        while idx < n:
            tag, idx_next = decode_varint(raw, idx)
            if tag is None or idx_next <= idx:
                break
            idx = idx_next
            field_no = int(tag) >> 3
            wire_type = int(tag) & 0x7

            if wire_type == 0:
                _, idx_next = decode_varint(raw, idx)
                if idx_next <= idx:
                    break
                idx = idx_next
                continue

            if wire_type == 2:
                size, idx_next = decode_varint(raw, idx)
                if size is None or idx_next <= idx:
                    break
                idx = idx_next
                end = idx + int(size)
                if end > n:
                    break
                chunk = raw[idx:end]
                idx = end
                yield field_no, wire_type, chunk
                continue

            if wire_type == 1:
                idx += 8
                continue
            if wire_type == 5:
                idx += 4
                continue
            break

    def is_strong_username_hint(s: str) -> bool:
        v = str(s or "").strip()
        return v.startswith("wxid_") or v.endswith("@chatroom") or v.startswith("gh_") or ("@" in v)

    def looks_like_username(s: str) -> bool:
        v = str(s or "").strip()
        if not v:
            return False
        if is_strong_username_hint(v):
            return True
        # Common alias-style WeChat IDs are ASCII-ish and do not contain whitespace.
        if len(v) < 6 or len(v) > 32:
            return False
        if re.search(r"\s", v):
            return False
        if not re.match(r"^[A-Za-z][A-Za-z0-9_-]+$", v):
            return False
        if v.isdigit():
            return False
        return True

    def pick_display(strings: list[tuple[int, str]], target: str) -> str:
        best_score = -1
        best = ""
        for i, (fno, value) in enumerate(strings):
            v = str(value or "").strip()
            if (not v) or v == target:
                continue
            if is_strong_username_hint(v):
                continue
            if "\n" in v or "\r" in v:
                continue
            if len(v) > 64:
                continue

            score = 0
            if int(fno) == 2:
                score += 100
            if not looks_like_username(v):
                score += 20
            score += max(0, 32 - len(v))
            # Stable tie-breaker: prefer earlier appearance.
            score = score * 1000 - i
            if score > best_score:
                best_score = score
                best = v
        return best

    try:
        conn = sqlite3.connect(str(contact_db_path))
    except Exception:
        return {}

    try:
        row = conn.execute(
            "SELECT ext_buffer FROM chat_room WHERE username = ? LIMIT 1",
            (chatroom,),
        ).fetchone()
        if row is None:
            return {}

        ext = row[0]
        if ext is None:
            return {}
        if isinstance(ext, memoryview):
            ext_buf = ext.tobytes()
        elif isinstance(ext, (bytes, bytearray)):
            ext_buf = bytes(ext)
        else:
            return {}
        if not ext_buf:
            return {}

        out: dict[str, str] = {}
        for _, wire_type, chunk in iter_fields(ext_buf):
            if wire_type != 2 or (not chunk):
                continue

            # Parse submessage and collect UTF-8 strings.
            strings: list[tuple[int, str]] = []
            try:
                for sfno, swire, sval in iter_fields(chunk):
                    if swire != 2:
                        continue
                    if not sval:
                        continue
                    if len(sval) > 256:
                        continue
                    try:
                        txt = bytes(sval).decode("utf-8", errors="strict")
                    except Exception:
                        continue
                    txt = txt.strip()
                    if not txt:
                        continue
                    strings.append((int(sfno), txt))
            except Exception:
                continue

            if not strings:
                continue

            present = [v for _, v in strings if v in target_set and v not in out]
            if not present:
                continue

            for target in present:
                disp = pick_display(strings, target)
                if disp:
                    out[target] = disp
            if len(out) >= len(target_set):
                break

        return out
    except Exception:
        return {}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _load_usernames_by_display_names(contact_db_path: Path, names: list[str]) -> dict[str, str]:
    """Best-effort mapping from display name -> username using contact.db.

    Some appmsg/link payloads only provide `sourcedisplayname` (surfaced as `from`) but not
    `sourceusername` (`fromUsername`). We use this mapping to recover `fromUsername` so the
    frontend can render the publisher avatar via `/api/chat/avatar`.
    """

    uniq = list(dict.fromkeys([str(n or "").strip() for n in names if str(n or "").strip()]))
    if not uniq:
        return {}

    placeholders = ",".join(["?"] * len(uniq))
    hits: dict[str, set[str]] = {}

    conn = sqlite3.connect(str(contact_db_path))
    conn.row_factory = sqlite3.Row
    try:
        def query_table(table: str) -> None:
            for col in ("remark", "nick_name", "alias"):
                sql = f"""
                    SELECT username, {col} AS display_name
                    FROM {table}
                    WHERE {col} IN ({placeholders})
                """
                try:
                    rows = conn.execute(sql, uniq).fetchall()
                except Exception:
                    rows = []
                for r in rows:
                    try:
                        dn = str(r["display_name"] or "").strip()
                        u = str(r["username"] or "").strip()
                    except Exception:
                        continue
                    if not dn or not u:
                        continue
                    hits.setdefault(dn, set()).add(u)

        query_table("contact")
        query_table("stranger")

        # Only return unambiguous mappings (display name -> exactly 1 username).
        out: dict[str, str] = {}
        for dn, users in hits.items():
            if len(users) == 1:
                out[dn] = next(iter(users))
        return out
    finally:
        conn.close()


def _make_search_tokens(q: str) -> list[str]:
    tokens = [t for t in re.split(r"\s+", str(q or "").strip()) if t]
    if len(tokens) > 8:
        tokens = tokens[:8]
    return tokens


def _make_snippet(text: str, tokens: list[str], *, max_len: int = 90) -> str:
    s = str(text or "").strip()
    if not s:
        return ""
    if not tokens or max_len <= 0:
        return s[:max_len]

    lowered = s.lower()
    best_idx = None
    best_tok = ""
    for t in tokens:
        i = lowered.find(t.lower())
        if i >= 0 and (best_idx is None or i < best_idx):
            best_idx = i
            best_tok = t
    if best_idx is None:
        return s[:max_len]

    left = max(0, best_idx - max_len // 2)
    right = min(len(s), left + max_len)
    if right - left < max_len and left > 0:
        left = max(0, right - max_len)
    out = s[left:right].strip()
    if left > 0:
        out = "…" + out
    if right < len(s):
        out = out + "…"
    if best_tok and best_tok not in out:
        out = s[:max_len].strip()
    return out


def _match_tokens(haystack: str, tokens: list[str]) -> bool:
    if not tokens:
        return False
    h = (haystack or "").lower()
    return all(t.lower() in h for t in tokens)


def _to_char_token_text(s: str) -> str:
    t = str(s or "").strip()
    if not t:
        return ""
    chars = [ch for ch in t.lower() if not ch.isspace()]
    return " ".join(chars)


def _build_fts_query(q: str) -> str:
    tokens = _make_search_tokens(q)
    parts: list[str] = []
    for tok in tokens:
        clean = str(tok or "").replace('"', "").strip()
        if not clean:
            continue
        phrase = " ".join([ch for ch in clean if not ch.isspace()])
        phrase = phrase.strip()
        if not phrase:
            continue
        parts.append(f"\"{phrase}\"")
    return " AND ".join(parts)


def _row_to_search_hit(
    r: sqlite3.Row,
    *,
    db_path: Path,
    table_name: str,
    username: str,
    account_dir: Path,
    is_group: bool,
    my_rowid: Optional[int],
) -> dict[str, Any]:
    local_id = int(r["local_id"] or 0)
    create_time = int(r["create_time"] or 0)
    sort_seq = int(r["sort_seq"] or 0) if r["sort_seq"] is not None else 0
    local_type = int(r["local_type"] or 0)
    sender_username = _decode_sqlite_text(r["sender_username"]).strip()

    is_sent = False
    if my_rowid is not None:
        try:
            is_sent = int(r["real_sender_id"] or 0) == int(my_rowid)
        except Exception:
            is_sent = False

    raw_text = _decode_message_content(r["compress_content"], r["message_content"]).strip()

    sender_prefix = ""
    if is_group and raw_text and (not raw_text.startswith("<")) and (not raw_text.startswith('"<')):
        sender_prefix, raw_text = _split_group_sender_prefix(raw_text, sender_username)

    if is_group and sender_prefix and (not sender_username):
        sender_username = sender_prefix

    if is_group and (not sender_username) and raw_text and (raw_text.startswith("<") or raw_text.startswith('"<')):
        xml_sender = _extract_sender_from_group_xml(raw_text)
        if xml_sender:
            sender_username = xml_sender

    if is_sent:
        sender_username = account_dir.name
    elif (not is_group) and (not sender_username):
        sender_username = username

    render_type = "text"
    content_text = raw_text
    title = ""
    url = ""
    quote_username = ""
    quote_title = ""
    quote_content = ""
    quote_thumb_url = ""
    link_type = ""
    link_style = ""
    amount = ""
    pay_sub_type = ""
    transfer_status = ""
    voip_type = ""

    if local_type == 10000:
        render_type = "system"
        content_text = _parse_system_message_content(raw_text)
    elif local_type == 49:
        parsed = _parse_app_message(raw_text)
        render_type = str(parsed.get("renderType") or "text")
        content_text = str(parsed.get("content") or "")
        title = str(parsed.get("title") or "")
        url = str(parsed.get("url") or "")
        quote_title = str(parsed.get("quoteTitle") or "")
        quote_content = str(parsed.get("quoteContent") or "")
        quote_thumb_url = str(parsed.get("quoteThumbUrl") or "")
        link_type = str(parsed.get("linkType") or "")
        link_style = str(parsed.get("linkStyle") or "")
        quote_username = str(parsed.get("quoteUsername") or "")
        amount = str(parsed.get("amount") or "")
        pay_sub_type = str(parsed.get("paySubType") or "")
        if render_type == "transfer":
            transfer_status = _infer_transfer_status_text(
                is_sent=is_sent,
                paysubtype=pay_sub_type,
                receivestatus=str(parsed.get("receiveStatus") or ""),
                sendertitle=str(parsed.get("senderTitle") or ""),
                receivertitle=str(parsed.get("receiverTitle") or ""),
                senderdes=str(parsed.get("senderDes") or ""),
                receiverdes=str(parsed.get("receiverDes") or ""),
            )
            if not content_text:
                content_text = transfer_status or "转账"
    elif local_type == 266287972401:
        render_type = "system"
        content_text = "[拍一拍]"
    elif local_type == 244813135921:
        render_type = "quote"
        parsed = _parse_app_message(raw_text)
        content_text = str(parsed.get("content") or "[引用消息]")
        quote_title = str(parsed.get("quoteTitle") or "")
        quote_content = str(parsed.get("quoteContent") or "")
        quote_thumb_url = str(parsed.get("quoteThumbUrl") or "")
        quote_username = str(parsed.get("quoteUsername") or "")
    elif local_type == 3:
        render_type = "image"
        content_text = "[图片]"
    elif local_type == 34:
        render_type = "voice"
        duration = _extract_xml_attr(raw_text, "voicelength")
        content_text = f"[语音 {duration}秒]" if duration else "[语音]"
    elif local_type == 43 or local_type == 62:
        render_type = "video"
        content_text = "[视频]"
    elif local_type == 47:
        render_type = "emoji"
        content_text = "[表情]"
    elif local_type == 50:
        render_type = "voip"
        try:
            block = raw_text
            m_voip = re.search(
                r"(<VoIPBubbleMsg[^>]*>.*?</VoIPBubbleMsg>)",
                raw_text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if m_voip:
                block = m_voip.group(1) or raw_text
            room_type = str(_extract_xml_tag_text(block, "room_type") or "").strip()
            if room_type == "0":
                voip_type = "video"
            elif room_type == "1":
                voip_type = "audio"
            voip_msg = str(_extract_xml_tag_text(block, "msg") or "").strip()
            content_text = voip_msg or "通话"
        except Exception:
            content_text = "通话"
    elif local_type != 1:
        if not content_text:
            content_text = _infer_message_brief_by_local_type(local_type)
        else:
            if content_text.startswith("<") or content_text.startswith('"<'):
                if "<appmsg" in content_text.lower():
                    parsed = _parse_app_message(content_text)
                    rt = str(parsed.get("renderType") or "")
                    if rt and rt != "text":
                        render_type = rt
                        content_text = str(parsed.get("content") or content_text)
                        title = str(parsed.get("title") or title)
                        url = str(parsed.get("url") or url)
                        quote_title = str(parsed.get("quoteTitle") or quote_title)
                        quote_content = str(parsed.get("quoteContent") or quote_content)
                        quote_thumb_url = str(parsed.get("quoteThumbUrl") or quote_thumb_url)
                        link_type = str(parsed.get("linkType") or link_type)
                        link_style = str(parsed.get("linkStyle") or link_style)
                        amount = str(parsed.get("amount") or amount)
                        pay_sub_type = str(parsed.get("paySubType") or pay_sub_type)
                        quote_username = str(parsed.get("quoteUsername") or quote_username)

                        if render_type == "transfer":
                            transfer_status = _infer_transfer_status_text(
                                is_sent=is_sent,
                                paysubtype=pay_sub_type,
                                receivestatus=str(parsed.get("receiveStatus") or ""),
                                sendertitle=str(parsed.get("senderTitle") or ""),
                                receivertitle=str(parsed.get("receiverTitle") or ""),
                                senderdes=str(parsed.get("senderDes") or ""),
                                receiverdes=str(parsed.get("receiverDes") or ""),
                            )
                            if not content_text:
                                content_text = transfer_status or "转账"
                t = _extract_xml_tag_text(content_text, "title")
                d = _extract_xml_tag_text(content_text, "des")
                content_text = t or d or _infer_message_brief_by_local_type(local_type)

    if not content_text:
        content_text = _infer_message_brief_by_local_type(local_type)

    return {
        "id": f"{db_path.stem}:{table_name}:{local_id}",
        "db": str(db_path.stem),
        "table": str(table_name),
        "username": str(username),
        "localId": local_id,
        "serverId": int(r["server_id"] or 0),
        "type": local_type,
        "createTime": create_time,
        "sortSeq": sort_seq,
        "senderUsername": sender_username,
        "isSent": bool(is_sent),
        "renderType": render_type,
        "content": content_text,
        "title": title,
        "url": url,
        "linkType": link_type,
        "linkStyle": link_style,
        "quoteUsername": quote_username,
        "quoteTitle": quote_title,
        "quoteContent": quote_content,
        "quoteThumbUrl": quote_thumb_url,
        "amount": amount,
        "paySubType": pay_sub_type,
        "transferStatus": transfer_status,
        "voipType": voip_type,
    }
