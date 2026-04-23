from functools import lru_cache
from pathlib import Path
import os
import base64
import hashlib
import json
import re
import httpx
import html # 修复&amp;转义的问题！！！
import sqlite3
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from typing import Any, Optional
from urllib.parse import urlparse

from starlette.background import BackgroundTask

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, FileResponse  # 返回视频文件

from ..chat_helpers import _load_contact_rows, _pick_display_name, _resolve_account_dir
from ..logging_config import get_logger
from ..media_helpers import _read_and_maybe_decrypt_media, _resolve_account_wxid_dir
from ..path_fix import PathFixRoute
from .. import sns_media as _sns_media
from ..wcdb_realtime import (
    WCDBRealtimeError,
    WCDB_REALTIME,
    decrypt_sns_image as _wcdb_decrypt_sns_image,
    exec_query as _wcdb_exec_query,
    get_sns_timeline as _wcdb_get_sns_timeline,
)

try:
    import zstandard as zstd  # type: ignore
except Exception:
    zstd = None

logger = get_logger(__name__)

router = APIRouter(route_class=PathFixRoute)

_SNS_VIDEO_KEY_RE = re.compile(r'<enc\s+key="(\d+)"', flags=re.IGNORECASE)
_MP_BIZ_RE = re.compile(r"__biz=([A-Za-z0-9_=+-]+)")
_ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
_SNS_APP_NAME_RE = re.compile(r"<appname[^>]*>([\s\S]*?)</appname>", flags=re.IGNORECASE)
_SNS_XML_CDATA_BLOCK_RE = re.compile(r"<!\[CDATA\[[\s\S]*?\]\]>", flags=re.IGNORECASE)
_SNS_XML_BARE_AMP_RE = re.compile(r"&(?!(?:[a-zA-Z]+|#\d+|#x[0-9a-fA-F]+);)")
_SNS_XML_INVALID_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

_SNS_REALTIME_SYNC_STATE_FILE = "_sns_realtime_sync_state.json"
_SNS_DECRYPTED_DB_LOCKS: dict[str, threading.Lock] = {}
_SNS_DECRYPTED_DB_LOCKS_MU = threading.Lock()

_SNS_TIMELINE_AUTO_CACHE_TTL_SECONDS = 60
# Key: (account_dir.name, sorted(usernames), keyword) -> (expires_at_ts, force_sqlite)
_SNS_TIMELINE_AUTO_CACHE: dict[tuple[str, tuple[str, ...], str], tuple[float, bool]] = {}
_SNS_TIMELINE_AUTO_CACHE_MU = threading.Lock()


def _sns_timeline_auto_cache_key(account_dir: Path, users: list[str], kw: str) -> tuple[str, tuple[str, ...], str]:
    # Normalize so different param orders map to the same key.
    a = str(Path(account_dir).name)
    u = tuple(sorted([str(x or "").strip() for x in (users or []) if str(x or "").strip()]))
    k = str(kw or "").strip()
    return (a, u, k)


def _sns_timeline_auto_cache_get(key: tuple[str, tuple[str, ...], str]) -> Optional[bool]:
    now = time.time()
    with _SNS_TIMELINE_AUTO_CACHE_MU:
        rec = _SNS_TIMELINE_AUTO_CACHE.get(key)
        if not rec:
            return None
        exp_ts, val = rec
        if exp_ts <= now:
            try:
                del _SNS_TIMELINE_AUTO_CACHE[key]
            except Exception:
                pass
            return None
        return bool(val)


def _sns_timeline_auto_cache_set(
    key: tuple[str, tuple[str, ...], str],
    val: bool,
    *,
    ttl_seconds: int = _SNS_TIMELINE_AUTO_CACHE_TTL_SECONDS,
) -> None:
    ttl = int(ttl_seconds or _SNS_TIMELINE_AUTO_CACHE_TTL_SECONDS)
    if ttl <= 0:
        ttl = _SNS_TIMELINE_AUTO_CACHE_TTL_SECONDS
    exp_ts = time.time() + float(ttl)
    with _SNS_TIMELINE_AUTO_CACHE_MU:
        _SNS_TIMELINE_AUTO_CACHE[key] = (exp_ts, bool(val))


def _sns_decrypted_db_lock(account: str) -> threading.Lock:
    key = str(account or "").strip()
    if not key:
        key = "_"
    with _SNS_DECRYPTED_DB_LOCKS_MU:
        lock = _SNS_DECRYPTED_DB_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _SNS_DECRYPTED_DB_LOCKS[key] = lock
        return lock


def _parse_csv_list(raw: Optional[str]) -> list[str]:
    if raw is None:
        return []
    s = str(raw or "").strip()
    if not s:
        return []
    # Best-effort: allow comma-separated list in one query param.
    return [p.strip() for p in s.split(",") if p.strip()]


def _safe_int(v: Any) -> int:
    try:
        return int(v)
    except Exception:
        return 0


def _count_sns_timeline_rows_in_decrypted_sqlite(
    sns_db_path: Path,
    *,
    users: list[str],
    kw: str,
) -> int:
    """Count rows in decrypted `sns.db` for a given query (raw rows, not timeline-filtered)."""
    sns_db_path = Path(sns_db_path)
    try:
        if (not sns_db_path.exists()) or (not sns_db_path.is_file()):
            return 0
    except Exception:
        return 0

    filters: list[str] = []
    params: list[Any] = []

    if users:
        placeholders = ",".join(["?"] * len(users))
        filters.append(f"user_name IN ({placeholders})")
        params.extend(users)

    if kw:
        filters.append("content LIKE ?")
        params.append(f"%{kw}%")

    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
    sql = f"SELECT COUNT(*) AS c FROM SnsTimeLine {where_sql}"

    try:
        conn = sqlite3.connect(str(sns_db_path), timeout=2.0)
        try:
            conn.execute("PRAGMA busy_timeout=2000")
            row = conn.execute(sql, params).fetchone()
            return int((row[0] if row else 0) or 0)
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception:
        return 0


def _count_sns_timeline_posts_in_decrypted_sqlite(
    sns_db_path: Path,
    *,
    users: list[str],
    kw: str,
) -> int:
    """Count visible-post rows in decrypted `sns.db` for a given query.

    This matches `/api/sns/users`'s `postCount` definition:
    - content not null/empty
    - exclude cover rows: `<type>7</type>`
    """
    sns_db_path = Path(sns_db_path)
    try:
        if (not sns_db_path.exists()) or (not sns_db_path.is_file()):
            return 0
    except Exception:
        return 0

    filters: list[str] = []
    params: list[Any] = []

    # Base filter: align with list_sns_users() postCount.
    filters.append("content IS NOT NULL")
    filters.append("content != ?")
    params.append("")
    filters.append("content NOT LIKE ?")
    params.append("%<type>7</type>%")

    if users:
        placeholders = ",".join(["?"] * len(users))
        filters.append(f"user_name IN ({placeholders})")
        params.extend(users)

    if kw:
        filters.append("content LIKE ?")
        params.append(f"%{kw}%")

    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
    sql = f"SELECT COUNT(*) AS c FROM SnsTimeLine {where_sql}"

    try:
        conn = sqlite3.connect(str(sns_db_path), timeout=2.0)
        try:
            conn.execute("PRAGMA busy_timeout=2000")
            row = conn.execute(sql, params).fetchone()
            return int((row[0] if row else 0) or 0)
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception:
        return 0


def _to_signed_i64(v: int) -> int:
    x = int(v) & 0xFFFFFFFFFFFFFFFF
    if x >= 0x8000000000000000:
        x -= 0x10000000000000000
    return int(x)

def _to_unsigned_i64_str(v: Any) -> str:
    """Return unsigned decimal string for a signed/unsigned 64-bit integer-ish value.

    Moments `tid/id` is often an unsigned u64 stored as signed i64 (negative) in sqlite/WCDB.
    Frontend cache-key formulas expect the *unsigned* decimal string.
    """
    try:
        x = int(v)
    except Exception:
        return str(v or "").strip()
    return str(x & 0xFFFFFFFFFFFFFFFF)


def _read_sns_realtime_sync_state(account_dir: Path) -> dict[str, Any]:
    p = Path(account_dir) / _SNS_REALTIME_SYNC_STATE_FILE
    try:
        if not p.exists() or (not p.is_file()):
            return {}
    except Exception:
        return {}

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

    return data if isinstance(data, dict) else {}


def _write_sns_realtime_sync_state(account_dir: Path, data: dict[str, Any]) -> None:
    p = Path(account_dir) / _SNS_REALTIME_SYNC_STATE_FILE
    try:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _ensure_decrypted_sns_db(account_dir: Path) -> Path:
    """Ensure `{account}/sns.db` exists with at least a minimal `SnsTimeLine` table.

    We keep it minimal (tid/user_name/content) so it stays compatible with older schema
    while enabling incremental cache/writeback from WCDB realtime.
    """
    account_dir = Path(account_dir)
    sns_db_path = account_dir / "sns.db"

    # If something weird exists at that path, bail out.
    try:
        if sns_db_path.exists() and (not sns_db_path.is_file()):
            raise RuntimeError("sns.db path is not a file")
    except Exception as e:
        raise RuntimeError(f"Invalid sns.db path: {e}") from e

    conn = sqlite3.connect(str(sns_db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS SnsTimeLine(
              tid INTEGER PRIMARY KEY,
              user_name TEXT,
              content TEXT
            )
            """
        )
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return sns_db_path


def _upsert_sns_timeline_rows_to_decrypted_db(
    account_dir: Path,
    rows: list[tuple[int, str, str, Optional[str]]],
    *,
    source: str,
) -> int:
    """Upsert rows into decrypted `{account}/sns.db` to avoid local missing data.

    rows: [(tid_signed, user_name, content_xml, pack_info_buf_or_none)]
    """
    if not rows:
        return 0

    sns_db_path = _ensure_decrypted_sns_db(account_dir)

    # Serialize writes per-account to avoid sqlite "database is locked" errors under concurrency.
    with _sns_decrypted_db_lock(Path(account_dir).name):
        conn = sqlite3.connect(str(sns_db_path), timeout=2.0)
        try:
            conn.execute("PRAGMA busy_timeout=2000")
            cols: set[str] = set()
            try:
                info_rows = conn.execute("PRAGMA table_info(SnsTimeLine)").fetchall()
                for r in info_rows or []:
                    try:
                        cols.add(str(r[1] or "").strip())
                    except Exception:
                        continue
            except Exception:
                cols = set()

            has_pack = "pack_info_buf" in cols

            if has_pack:
                sql = """
                    INSERT INTO SnsTimeLine (tid, user_name, content, pack_info_buf)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(tid) DO UPDATE SET
                      user_name=excluded.user_name,
                      content=COALESCE(NULLIF(excluded.content, ''), SnsTimeLine.content),
                      pack_info_buf=COALESCE(excluded.pack_info_buf, SnsTimeLine.pack_info_buf)
                """
                data = [(int(tid), str(u or "").strip(), str(c or ""), p) for tid, u, c, p in rows]
            else:
                sql = """
                    INSERT INTO SnsTimeLine (tid, user_name, content)
                    VALUES (?, ?, ?)
                    ON CONFLICT(tid) DO UPDATE SET
                      user_name=excluded.user_name,
                      content=COALESCE(NULLIF(excluded.content, ''), SnsTimeLine.content)
                """
                data = [(int(tid), str(u or "").strip(), str(c or "")) for tid, u, c, _p in rows]

            conn.executemany(sql, data)
            conn.commit()
            return len(rows)
        except Exception as e:
            logger.debug("[sns] decrypted sns.db upsert failed source=%s err=%s", source, e)
            try:
                conn.rollback()
            except Exception:
                pass
            return 0
        finally:
            try:
                conn.close()
            except Exception:
                pass

def _extract_mp_biz_from_url(url: str) -> str:
    """Extract `__biz` from mp.weixin.qq.com URLs (best-effort)."""
    u = html.unescape(str(url or "")).replace("&amp;", "&").strip()
    if not u:
        return ""
    m = _MP_BIZ_RE.search(u)
    if not m:
        return ""
    return str(m.group(1) or "").strip()


@lru_cache(maxsize=16)
def _build_biz_to_official_index(contact_db_path: str, mtime_ns: int, size: int) -> dict[str, dict[str, Any]]:
    """Build mapping: __biz -> { username, serviceType } from contact.db.biz_info."""
    out: dict[str, dict[str, Any]] = {}
    if not contact_db_path:
        return out

    conn = sqlite3.connect(str(contact_db_path))
    conn.row_factory = sqlite3.Row
    try:
        try:
            rows = conn.execute(
                "SELECT username, brand_info, external_info, home_url FROM biz_info"
            ).fetchall()
        except Exception:
            rows = []

        for r in rows:
            try:
                uname = str(r["username"] or "").strip()
            except Exception:
                uname = ""
            if not uname:
                continue

            try:
                brand_info = str(r["brand_info"] or "")
            except Exception:
                brand_info = ""
            try:
                external_info = str(r["external_info"] or "")
            except Exception:
                external_info = ""
            try:
                home_url = str(r["home_url"] or "")
            except Exception:
                home_url = ""

            service_type: Optional[int] = None
            if external_info:
                try:
                    j = json.loads(external_info)
                    st = j.get("ServiceType")
                    if st is not None:
                        service_type = int(st)
                except Exception:
                    service_type = None

            blob = " ".join([brand_info, external_info, home_url])
            for biz in _MP_BIZ_RE.findall(blob):
                b = str(biz or "").strip()
                if not b:
                    continue
                prev = out.get(b)
                if prev is None:
                    out[b] = {"username": uname, "serviceType": service_type}
                else:
                    if prev.get("serviceType") is None and service_type is not None:
                        prev["serviceType"] = service_type
    finally:
        conn.close()

    return out


def _get_biz_to_official_index(contact_db_path: Path) -> dict[str, dict[str, Any]]:
    if not contact_db_path.exists():
        return {}
    st = contact_db_path.stat()
    mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)))
    return _build_biz_to_official_index(str(contact_db_path), mtime_ns, int(st.st_size))


def _extract_sns_video_key(raw_xml: Any) -> str:
    """Extract Isaac64 video key from raw XML, e.g. `<enc key="1578806206" ...>`."""
    text = _decode_sns_text_blob(raw_xml)
    m = _SNS_VIDEO_KEY_RE.search(text or "")
    return str(m.group(1) or "").strip() if m else ""


def _looks_like_xml_text(s: str) -> bool:
    if not s:
        return False
    t = str(s).lstrip()
    if t.startswith('"') and t.endswith('"'):
        t = t.strip('"').lstrip()
    return t.startswith("<")


def _sanitize_wechat_xml_for_et(xml_text: str) -> str:
    """Best-effort sanitize for ElementTree parsing.

    WeChat Moments "XML" is sometimes not well-formed XML (commonly: raw `&` inside URLs),
    which breaks `xml.etree.ElementTree.fromstring`. We keep CDATA blocks intact and:
    - strip invalid control chars
    - escape bare `&` outside CDATA blocks
    """

    s = str(xml_text or "")
    if not s:
        return ""

    s = _SNS_XML_INVALID_CHARS_RE.sub("", s)

    parts: list[str] = []
    last = 0
    for m in _SNS_XML_CDATA_BLOCK_RE.finditer(s):
        head = s[last : m.start()]
        if head:
            parts.append(_SNS_XML_BARE_AMP_RE.sub("&amp;", head))
        parts.append(m.group(0))
        last = m.end()

    tail = s[last:]
    if tail:
        parts.append(_SNS_XML_BARE_AMP_RE.sub("&amp;", tail))

    return "".join(parts)


def _decode_sns_text_blob(value: Any) -> str:
    """Decode text/blob values that may be hex/base64 encoded and/or zstd-compressed.

    WeChat WCDB realtime can return TEXT/BLOB fields as:
    - plain XML string
    - hex string (often a zstd frame starting with 28b52ffd...)
    - base64 string (same)
    """

    if value is None:
        return ""

    if isinstance(value, memoryview):
        raw = bytes(value)
        if raw and zstd is not None and raw.startswith(_ZSTD_MAGIC):
            try:
                raw = zstd.decompress(raw)
            except Exception:
                pass
        try:
            s = raw.decode("utf-8", errors="ignore")
        except Exception:
            s = ""
        s = html.unescape(str(s or "").strip())
        return s if _looks_like_xml_text(s) else (str(s or "").strip())

    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
        if raw and zstd is not None and raw.startswith(_ZSTD_MAGIC):
            try:
                raw = zstd.decompress(raw)
            except Exception:
                pass
        try:
            s = raw.decode("utf-8", errors="ignore")
        except Exception:
            s = ""
        s = html.unescape(str(s or "").strip())
        return s if _looks_like_xml_text(s) else (str(s or "").strip())

    try:
        text = str(value or "")
    except Exception:
        return ""

    text = html.unescape(text.strip())
    if not text:
        return ""

    if _looks_like_xml_text(text):
        return text

    def _accept_xml(decoded: str) -> str:
        s2 = html.unescape(str(decoded or "").strip())
        return s2 if _looks_like_xml_text(s2) else ""

    # Hex string (optionally prefixed with 0x)
    t_hex = text[2:] if text.lower().startswith("0x") else text
    if len(t_hex) >= 16 and len(t_hex) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", t_hex):
        try:
            raw = bytes.fromhex(t_hex)
            if raw and zstd is not None and raw.startswith(_ZSTD_MAGIC):
                try:
                    raw = zstd.decompress(raw)
                except Exception:
                    raw = b""
            if raw:
                s2 = _accept_xml(raw.decode("utf-8", errors="ignore"))
                if s2:
                    return s2
        except Exception:
            pass

    # Base64 string
    if len(text) >= 24 and len(text) % 4 == 0 and re.fullmatch(r"[A-Za-z0-9+/=]+", text):
        try:
            raw = base64.b64decode(text)
            if raw and zstd is not None and raw.startswith(_ZSTD_MAGIC):
                try:
                    raw = zstd.decompress(raw)
                except Exception:
                    raw = b""
            if raw:
                s2 = _accept_xml(raw.decode("utf-8", errors="ignore"))
                if s2:
                    return s2
        except Exception:
            pass

    return text


def _extract_sns_source_name(raw_xml: Any) -> str:
    text = _decode_sns_text_blob(raw_xml)
    if not text:
        return ""
    m = _SNS_APP_NAME_RE.search(text)
    if not m:
        return ""
    v = str(m.group(1) or "")
    v = v.replace("<![CDATA[", "").replace("]]>", "")
    v = re.sub(r"<[^>]+>", "", v)
    return html.unescape(v.strip())


def _build_location_text(node: Optional[ET.Element]) -> str:
    if node is None:
        return ""

    def _get(key: str) -> str:
        return str(node.get(key) or node.findtext(key) or "").strip()

    def _clean(v: str) -> str:
        # Some WeChat XML uses special whitespace (NBSP / thin spaces) inside the location string.
        return (
            str(v or "")
            .replace("\u00a0", " ")
            .replace("\u2006", " ")
            .strip()
        )

    city = _clean(_get("city"))
    poi = _clean(_get("poiName") or _get("poi") or _get("label"))
    address = _clean(_get("address") or _get("poiAddress"))

    # Avoid duplicated city prefix like: "广安市·广安市·xxx".
    if city and poi and poi.startswith(city):
        rest = poi[len(city):].lstrip(" ·")
        if rest:
            poi = rest

    # WeChat UI typically renders `city·poi/address`.
    if city and (poi or address):
        return f"{city}·{poi or address}".strip()

    for cand in (poi, address, city):
        if cand:
            return cand
    return ""


def _parse_timeline_xml(xml_text: str, fallback_username: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "username": fallback_username,
        "createTime": 0,
        "contentDesc": "",
        "location": "",
        "sourceName": "",
        "media": [],
        "likes": [],
        "comments": [],
        "type": 1,  # 默认类型
        "title": "",
        "contentUrl": "",
        "finderFeed": {}
    }

    xml_str = _decode_sns_text_blob(xml_text)
    if not xml_str:
        return out


    try:
        root = ET.fromstring(_sanitize_wechat_xml_for_et(xml_str))
    except Exception:
        return out

    # External share source label (e.g. QQ音乐 / 哔哩哔哩) is usually stored in `<appInfo><appName>...`.
    try:
        for el in root.iter():
            try:
                tag = str(el.tag or "").lower()
            except Exception:
                continue
            if tag in {"appname", "sourcename"}:
                v = str(el.text or "").strip()
                if v:
                    out["sourceName"] = html.unescape(v).strip()
                    break
            try:
                attrs = el.attrib or {}
            except Exception:
                attrs = {}
            for k, v in attrs.items():
                if str(k or "").lower() in {"appname", "sourcename"}:
                    vv = str(v or "").strip()
                    if vv:
                        out["sourceName"] = html.unescape(vv).strip()
                        break
            if out["sourceName"]:
                break
    except Exception:
        pass

    def _find_text(*paths: str) -> str:
        for p in paths:
            try:
                v = root.findtext(p)
            except Exception:
                v = None
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""
    # &amp转义！！
    def _clean_url(u: str) -> str:
        if not u:
            return ""

        cleaned = html.unescape(u)
        cleaned = cleaned.replace("&amp;", "&")
        return cleaned.strip()

    out["username"] = _find_text(".//TimelineObject/username", ".//TimelineObject/user_name",
                                 ".//username") or fallback_username
    out["createTime"] = _safe_int(_find_text(".//TimelineObject/createTime", ".//createTime"))
    out["contentDesc"] = _find_text(".//TimelineObject/contentDesc", ".//contentDesc")
    out["location"] = _build_location_text(root.find(".//location"))

    # --- 提取内容类型 ---
    post_type = _safe_int(_find_text(".//ContentObject/type", ".//type"))
    out["type"] = post_type

    # --- 如果是公众号文章 (Type 3) ---
    if post_type == 3:
        out["title"] = _find_text(".//ContentObject/title")
        out["contentUrl"] = _clean_url(_find_text(".//ContentObject/contentUrl"))

    # --- 如果是外部分享链接 (Type 5) ---
    if post_type == 5:
        out["title"] = _find_text(
            ".//ContentObject/title",
            ".//ContentObject/linkTitle",
            ".//ContentObject/name",
            ".//ContentObject/desc",
            ".//ContentObject/description",
        )
        out["contentUrl"] = _clean_url(
            _find_text(
                ".//ContentObject/contentUrl",
                ".//ContentObject/linkUrl",
                ".//ContentObject/url",
                ".//ContentObject/jumpUrl",
            )
        )

    # --- 如果是音乐分享/链接卡片 (Type 42) ---
    if post_type == 42:
        # WeChat sometimes stores link/music share metadata under ContentObject fields.
        out["title"] = _find_text(
            ".//ContentObject/title",
            ".//ContentObject/linkTitle",
            ".//ContentObject/name",
            ".//ContentObject/desc",
        )
        out["contentUrl"] = _clean_url(
            _find_text(
                ".//ContentObject/contentUrl",
                ".//ContentObject/linkUrl",
                ".//ContentObject/url",
                ".//ContentObject/jumpUrl",
            )
        )

    # --- 如果是视频号 (Type 28) ---
    if post_type == 28:
        out["title"] = _find_text(".//ContentObject/title")
        out["contentUrl"] = _clean_url(_find_text(".//ContentObject/contentUrl"))
        out["finderFeed"] = {
            "nickname": _find_text(".//finderFeed/nickname"),
            "desc": _find_text(".//finderFeed/desc"),
            "thumbUrl": _clean_url(
                _find_text(".//finderFeed/mediaList/media/thumbUrl", ".//finderFeed/mediaList/media/coverUrl")),
            "url": _clean_url(_find_text(".//finderFeed/mediaList/media/url"))
        }

    media: list[dict[str, Any]] = []
    try:
        for m in root.findall(".//mediaList//media"):
            mt = _safe_int(m.findtext("type"))
            url_el = m.find("url") if m.find("url") is not None else m.find("urlV")
            thumb_el = m.find("thumb") if m.find("thumb") is not None else m.find("thumbV")

            url = _clean_url(url_el.text if url_el is not None else "")
            thumb = _clean_url(thumb_el.text if thumb_el is not None else "")

            url_attrs = dict(url_el.attrib) if url_el is not None and url_el.attrib else {}
            thumb_attrs = dict(thumb_el.attrib) if thumb_el is not None and thumb_el.attrib else {}
            media_id = str(m.findtext("id") or "").strip()
            size_el = m.find("size")
            size = dict(size_el.attrib) if size_el is not None and size_el.attrib else {}

            if not url and not thumb:
                continue

            media.append({
                "type": mt,
                "id": media_id,
                "url": url,
                "thumb": thumb,
                "urlAttrs": url_attrs,
                "thumbAttrs": thumb_attrs,
                "size": size,
            })
    except Exception:
        pass
    out["media"] = media

    # Fallback: some type=42 shares only expose the jump URL via media[0].url.
    if post_type in (5, 42):
        if (not str(out.get("contentUrl") or "").strip()) and media:
            m0 = media[0] if isinstance(media[0], dict) else {}
            u0 = str(m0.get("url") or "").strip()
            if u0:
                out["contentUrl"] = u0

    likes: list[str] = []
    try:
        for u in root.findall(".//likeList//like//username"):
            if u is None or not u.text:
                continue
            v = str(u.text).strip()
            if v:
                likes.append(v)
    except Exception:
        likes = []
    out["likes"] = likes

    comments: list[dict[str, Any]] = []
    try:
        for c in root.findall(".//commentList//comment"):
            content = str(c.findtext("content") or "").strip()
            if not content:
                continue
            comments.append(
                {
                    "username": str(c.findtext("username") or "").strip(),
                    "nickname": str(c.findtext("nickName") or "").strip(),
                    "content": content,
                    "refUsername": str(c.findtext("refUserName") or "").strip(),
                    "refNickname": str(c.findtext("refNickName") or "").strip(),
                }
            )
    except Exception:
        comments = []
    out["comments"] = comments

    return out


@lru_cache(maxsize=16)
def _sns_video_roots(wxid_dir_str: str) -> tuple[str, ...]:
    """List all month cache roots that contain `Sns/Video`."""
    wxid_dir = Path(str(wxid_dir_str or "").strip())
    cache_root = wxid_dir / "cache"
    try:
        month_dirs = [p for p in cache_root.iterdir() if p.is_dir()]
    except Exception:
        month_dirs = []

    roots: list[str] = []
    for mdir in month_dirs:
        video_root = mdir / "Sns" / "Video"
        try:
            if video_root.exists() and video_root.is_dir():
                roots.append(str(video_root))
        except Exception:
            continue
    roots.sort()
    return tuple(roots)

def _resolve_sns_cached_video_path(
    wxid_dir: Path,
    post_id: str,
    media_id: str
) -> Optional[str]:
    """基于逆向出的固定盐值 3，解析朋友圈视频的本地缓存路径"""
    if not post_id or not media_id:
        return None

    raw_key = f"{post_id}_{media_id}_3"  # 暂时硬编码，大概率是对的
    try:
        key32 = hashlib.md5(raw_key.encode("utf-8")).hexdigest()
    except Exception:
        return None

    sub = key32[:2]
    rest = key32[2:]

    roots = _sns_video_roots(str(wxid_dir))
    for root_str in roots:
        try:
            base_path = Path(root_str) / sub / rest
            for ext in [".mp4", ".tmp"]:
                p = base_path.with_suffix(ext)
                if p.exists() and p.is_file():
                    return str(p)
        except Exception:
            continue

    return None

def _get_sns_covers(account_dir: Path, target_wxid: str, limit: int = 20) -> list[dict[str, Any]]:
    """无论多古老，强行揪出用户的朋友圈封面历史 (type=7)。

    返回倒序（最新在前）的列表，包含 createTime 便于前端叠加显示。
    """
    wxid = str(target_wxid or "").strip()
    if not wxid:
        return []

    try:
        lim = int(limit or 20)
    except Exception:
        lim = 20
    if lim <= 0:
        lim = 1
    # Keep payload bounded; cover history isn't worth huge queries.
    if lim > 50:
        lim = 50

    wxid_esc = wxid.replace("'", "''")
    cover_sql = (
        "SELECT tid, content FROM SnsTimeLine "
        f"WHERE user_name = '{wxid_esc}' AND content LIKE '%<type>7</type>%' "
        "ORDER BY tid DESC "
        f"LIMIT {lim}"
    )

    rows: list[dict[str, Any]] = []

    # 1) Prefer real-time WCDB if available (reads db_storage/sns/sns.db).
    try:
        if WCDB_REALTIME.is_connected(account_dir.name):
            conn = WCDB_REALTIME.ensure_connected(account_dir)
            with conn.lock:
                sns_db_path = conn.db_storage_dir / "sns" / "sns.db"
                if not sns_db_path.exists():
                    sns_db_path = conn.db_storage_dir / "sns.db"
                # 利用 exec_query 强行查
                rows = _wcdb_exec_query(conn.handle, kind="media", path=str(sns_db_path), sql=cover_sql) or []
    except Exception as e:
        logger.warning("[sns] WCDB cover fetch failed: %s", e)

    # 2) Fallback to local decrypted snapshot sns.db.
    if not rows:
        sns_db_path = account_dir / "sns.db"
        if sns_db_path.exists():
            try:
                # 只读模式防止锁死
                conn_sq = sqlite3.connect(f"file:{sns_db_path}?mode=ro", uri=True)
                conn_sq.row_factory = sqlite3.Row
                rows_sq = conn_sq.execute(cover_sql).fetchall()
                conn_sq.close()
                rows = [{"tid": r["tid"], "content": r["content"]} for r in (rows_sq or [])]
            except Exception as e:
                logger.warning("[sns] SQLite cover fetch failed: %s", e)

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rr in rows:
        if not isinstance(rr, dict):
            continue
        cover_xml = rr.get("content")
        if not cover_xml:
            continue

        try:
            cover_tid = int(rr.get("tid") or 0)
        except Exception:
            cover_tid = 0

        parsed = _parse_timeline_xml(str(cover_xml or ""), wxid)
        media = parsed.get("media") or []
        if not isinstance(media, list) or not media:
            continue

        cid = _to_unsigned_i64_str(cover_tid or "")
        if cid in seen:
            continue
        seen.add(cid)

        out.append(
            {
                "id": cid,
                "tid": cover_tid,
                "username": wxid,
                "createTime": int(parsed.get("createTime") or 0),
                "media": media,
                "type": 7,
            }
        )
    return out


def _get_sns_cover(account_dir: Path, target_wxid: str) -> Optional[dict[str, Any]]:
    """兼容旧逻辑：返回最近的一张朋友圈封面 (type=7)"""
    covers = _get_sns_covers(account_dir, target_wxid, limit=1)
    return covers[0] if covers else None




@router.get("/api/sns/self_info", summary="获取个人信息（wxid和nickname）")
def api_sns_self_info(account: Optional[str] = None):

    account_dir = _resolve_account_dir(account)
    wxid = account_dir.name

    logger.info(f"[self_info] 开始获取账号信息, 预设 wxid: {wxid}")

    nickname = wxid
    source = "wxid_dir"

    try:
        status = WCDB_REALTIME.get_status(account_dir)
        if status.get("dll_present") and status.get("key_present"):
            rt_conn = WCDB_REALTIME.ensure_connected(account_dir)
            with rt_conn.lock:

                names_map = _wcdb_get_display_names(rt_conn.handle, [wxid])
                if names_map and names_map.get(wxid):
                    nickname = names_map[wxid]
                    source = "wcdb_realtime"
                    logger.info(f"[self_info] 从 WCDB 实时连接获取成功: {nickname}")
                    return {"wxid": wxid, "nickname": nickname, "source": source}
    except Exception as e:
        logger.debug(f"[self_info] WCDB 路径跳过或失败: {e}")

    contact_db_path = account_dir / "contact.db"
    if contact_db_path.exists():
        conn = None
        try:
            db_uri = f"file:{contact_db_path}?mode=ro"
            conn = sqlite3.connect(db_uri, uri=True, timeout=5)
            conn.row_factory = sqlite3.Row

            cursor = conn.execute("PRAGMA table_info(contact)")
            cols = {row["name"].lower() for row in cursor.fetchall()}
            logger.debug(f"[self_info] contact 表现有字段: {cols}")

            target_nick_col = "nick_name" if "nick_name" in cols else ("nickname" if "nickname" in cols else None)

            if target_nick_col:
                sql = f"SELECT remark, {target_nick_col} as nickname_val, alias FROM contact WHERE username = ? LIMIT 1"
                row = conn.execute(sql, (wxid,)).fetchone()


                if row:
                    raw_remark = str(row["remark"] or "").strip() if "remark" in row.keys() else ""
                    raw_nick = str(row["nickname_val"] or "").strip()
                    raw_alias = str(row["alias"] or "").strip() if "alias" in row.keys() else ""

                    if raw_remark:
                        nickname = raw_remark
                        source = "contact_db_remark"
                    elif raw_nick:
                        nickname = raw_nick
                        source = "contact_db_nickname"
                    elif raw_alias:
                        nickname = raw_alias
                        source = "contact_db_alias"

                    logger.info(f"[self_info] 从数据库提取成功: {nickname} (src: {source})")
            else:
                logger.warning("[self_info] contact 表中找不到任何昵称相关字段")

        except sqlite3.OperationalError as e:
            logger.error(f"[self_info] 数据库繁忙或锁定: {e}")
        except Exception as e:
            logger.exception(f"[self_info] 查询异常: {e}")
        finally:
            if conn: conn.close()
    else:
        logger.warning(f"[self_info] 找不到 contact.db: {contact_db_path}")

    return {
        "wxid": wxid,
        "nickname": nickname,
        "source": source
    }


@router.post("/api/sns/realtime/sync_latest", summary="实时朋友圈同步到解密库（增量）")
def sync_sns_realtime_timeline_latest(
    account: Optional[str] = None,
    max_scan: int = 200,
    force: int = 0,
):
    """Sync latest visible Moments from WCDB realtime into decrypted `{account}/sns.db`.

    This is best-effort and intentionally **append-only**: we never delete rows from the decrypted snapshot
    even if the post is deleted/hidden later, so users can still browse/export historical cached content.
    """
    try:
        lim = int(max_scan or 200)
    except Exception:
        lim = 200
    if lim <= 0:
        lim = 200
    if lim > 2000:
        lim = 2000

    try:
        force_flag = bool(int(force or 0))
    except Exception:
        force_flag = False

    account_dir = _resolve_account_dir(account)

    # If there is no local decrypted sns.db yet, force a first-time materialization.
    try:
        if not (account_dir / "sns.db").exists():
            force_flag = True
    except Exception:
        force_flag = True

    info = WCDB_REALTIME.get_status(account_dir)
    available = bool(info.get("dll_present") and info.get("key_present") and info.get("db_storage_dir"))
    if not available:
        raise HTTPException(status_code=404, detail="WCDB realtime not available.")

    st = _read_sns_realtime_sync_state(account_dir)
    last_max_id_u = 0
    try:
        last_max_id_u = int(str(st.get("maxId") or st.get("max_id") or "0").strip() or "0")
    except Exception:
        last_max_id_u = 0

    conn = WCDB_REALTIME.ensure_connected(account_dir)

    t0 = time.perf_counter()
    rows: list[dict[str, Any]] = []
    max_id_u = 0
    upsert_rows: list[tuple[int, str, str, Optional[str]]] = []

    with conn.lock:
        rows = _wcdb_get_sns_timeline(
            conn.handle,
            limit=lim,
            offset=0,
            usernames=[],
            keyword="",
        )

        if not rows:
            return {
                "status": "ok",
                "scanned": 0,
                "upserted": 0,
                "maxId": str(last_max_id_u or 0),
                "elapsedMs": int((time.perf_counter() - t0) * 1000.0),
            }

        # Compute the newest unsigned tid/id from WCDB rows.
        for r in rows:
            if not isinstance(r, dict):
                continue
            try:
                tid_u = int(r.get("id") or 0)
            except Exception:
                continue
            if tid_u > max_id_u:
                max_id_u = tid_u

        if (not force_flag) and max_id_u and (max_id_u <= last_max_id_u):
            # No new top item; skip heavy exec_query + sqlite writes.
            return {
                "status": "noop",
                "scanned": len(rows),
                "upserted": 0,
                "maxId": str(max_id_u),
                "lastMaxId": str(last_max_id_u),
                "elapsedMs": int((time.perf_counter() - t0) * 1000.0),
            }

        username_by_tid: dict[int, str] = {}
        rawxml_by_tid: dict[int, str] = {}
        tids: list[int] = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            uname = str(r.get("username") or "").strip()
            try:
                tid_u = int(r.get("id") or 0)
            except Exception:
                continue
            tid_s = _to_signed_i64(tid_u)
            tids.append(tid_s)
            if uname:
                username_by_tid[tid_s] = uname
            raw_xml = str(r.get("rawXml") or "")
            if raw_xml:
                rawxml_by_tid[tid_s] = raw_xml

        tids = [t for t in list(dict.fromkeys(tids)) if isinstance(t, int)]

        sql_rows: list[dict[str, Any]] = []
        try:
            sns_db_path = conn.db_storage_dir / "sns" / "sns.db"
            if not sns_db_path.exists():
                sns_db_path = conn.db_storage_dir / "sns.db"

            if tids and sns_db_path.exists():
                in_sql = ",".join([str(x) for x in tids])
                # Newer schema may have pack_info_buf; try it first, then fall back.
                sql = f"SELECT tid, user_name, content, pack_info_buf FROM SnsTimeLine WHERE tid IN ({in_sql})"
                try:
                    sql_rows = _wcdb_exec_query(conn.handle, kind="media", path=str(sns_db_path), sql=sql)
                except Exception:
                    sql = f"SELECT tid, user_name, content FROM SnsTimeLine WHERE tid IN ({in_sql})"
                    sql_rows = _wcdb_exec_query(conn.handle, kind="media", path=str(sns_db_path), sql=sql)
        except Exception:
            sql_rows = []

        if sql_rows:
            for rr in sql_rows:
                if not isinstance(rr, dict):
                    continue
                try:
                    tid_val = int(rr.get("tid") or 0)
                except Exception:
                    continue
                content_xml = _decode_sns_text_blob(rr.get("content"))
                if not content_xml:
                    continue
                uname = str(rr.get("user_name") or rr.get("username") or "").strip()
                if not uname:
                    uname = username_by_tid.get(tid_val, "")
                if not uname:
                    continue
                pack = rr.get("pack_info_buf")
                pack_text = None if pack is None else str(pack)
                upsert_rows.append((tid_val, uname, content_xml, pack_text))
        else:
            # Fallback: store rawXml from WCDB rows (may be enough for parsing/export).
            for tid_val, uname in username_by_tid.items():
                raw_xml = rawxml_by_tid.get(tid_val) or ""
                if not raw_xml:
                    continue
                upsert_rows.append((int(tid_val), str(uname), str(raw_xml), None))

    upserted = _upsert_sns_timeline_rows_to_decrypted_db(
        account_dir,
        upsert_rows,
        source="realtime-sync-latest",
    )

    if max_id_u:
        st2 = dict(st)
        st2["maxId"] = str(max_id_u)
        st2["updatedAt"] = int(time.time())
        _write_sns_realtime_sync_state(account_dir, st2)

    return {
        "status": "ok",
        "scanned": len(rows),
        "upserted": int(upserted),
        "maxId": str(max_id_u or 0),
        "lastMaxId": str(last_max_id_u or 0),
        "elapsedMs": int((time.perf_counter() - t0) * 1000.0),
    }


@router.get("/api/sns/timeline", summary="获取朋友圈时间线")
def list_sns_timeline(
    account: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    usernames: Optional[str] = None,
    keyword: Optional[str] = None,
):
    if limit <= 0:
        raise HTTPException(status_code=400, detail="Invalid limit.")
    if limit > 200:
        limit = 200
    if offset < 0:
        offset = 0

    account_dir = _resolve_account_dir(account)
    contact_db_path = account_dir / "contact.db"

    users = _parse_csv_list(usernames)
    kw = str(keyword or "").strip()

    cover_data = None
    covers_data: list[dict[str, Any]] = []
    if offset == 0:
        target_wxid = users[0] if users else account_dir.name
        covers_data = _get_sns_covers(account_dir, target_wxid, limit=20)
        cover_data = covers_data[0] if covers_data else None

    def _list_from_decrypted_sqlite() -> dict[str, Any]:
        """Legacy path: query the decrypted sns.db under output/databases/{account}.

        Note: This path may contain historical timeline items that are no longer
        visible in WeChat due to privacy settings (e.g. "only last 3 days").
        """
        sns_db_path = account_dir / "sns.db"
        if not sns_db_path.exists():
            raise HTTPException(status_code=404, detail="sns.db not found for this account.")

        filters: list[str] = []
        params: list[Any] = []

        if users:
            placeholders = ",".join(["?"] * len(users))
            filters.append(f"user_name IN ({placeholders})")
            params.extend(users)

        if kw:
            filters.append("content LIKE ?")
            params.append(f"%{kw}%")

        where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""

        sql = f"""
            SELECT tid, user_name, content
            FROM SnsTimeLine
            {where_sql}
            ORDER BY tid DESC
            LIMIT ? OFFSET ?
        """
        # Fetch 1 extra row to determine hasMore.
        params_with_page = params + [limit + 1, offset]

        conn2 = sqlite3.connect(str(sns_db_path))
        conn2.row_factory = sqlite3.Row
        try:
            rows2 = conn2.execute(sql, params_with_page).fetchall()
        except sqlite3.OperationalError as e:
            logger.warning("[sns] query failed: %s", e)
            raise HTTPException(status_code=500, detail=f"sns.db query failed: {e}")
        finally:
            conn2.close()

        has_more2 = len(rows2) > limit
        rows2 = rows2[:limit]

        post_usernames2 = [str(r["user_name"] or "").strip() for r in rows2 if str(r["user_name"] or "").strip()]
        contact_rows2 = _load_contact_rows(contact_db_path, post_usernames2) if contact_db_path.exists() else {}
        biz_index2 = _get_biz_to_official_index(contact_db_path) if contact_db_path.exists() else {}
        official_usernames2: set[str] = set()

        timeline2: list[dict[str, Any]] = []
        for r in rows2:
            try:
                tid2 = r["tid"]
            except Exception:
                tid2 = None
            uname2 = str(r["user_name"] or "").strip()

            content_xml = str(r["content"] or "")
            parsed2 = _parse_timeline_xml(content_xml, uname2)

            # Best-effort: attach ISAAC64 video key for SNS videos/live-photos (WeFlow compatible).
            video_key2 = _extract_sns_video_key(content_xml)
            if video_key2:
                pmedia2 = parsed2.get("media")
                if isinstance(pmedia2, list):
                    for m0 in pmedia2:
                        if not isinstance(m0, dict):
                            continue
                        if "videoKey" not in m0:
                            m0["videoKey"] = video_key2
                        lp = m0.get("livePhoto")
                        if isinstance(lp, dict):
                            if not str(lp.get("key") or "").strip():
                                lp["key"] = video_key2

            display2 = _pick_display_name(contact_rows2.get(uname2), uname2) if uname2 else uname2
            post_type2 = int(parsed2.get("type", 1) or 1)

            official2: dict[str, Any] = {}
            if post_type2 == 3:
                content_url2 = str(parsed2.get("contentUrl") or "")
                biz2 = _extract_mp_biz_from_url(content_url2)
                info2 = biz_index2.get(biz2) if biz2 else None
                off_username2 = str(info2.get("username") or "").strip() if isinstance(info2, dict) else ""
                off_service_type2 = info2.get("serviceType") if isinstance(info2, dict) else None
                official2 = {
                    "biz": biz2,
                    "username": off_username2,
                    "serviceType": off_service_type2,
                    "displayName": "",
                }
                if off_username2:
                    official_usernames2.add(off_username2)

            timeline2.append(
                {
                    "id": _to_unsigned_i64_str(tid2) if tid2 is not None else (str(parsed2.get("createTime") or "") or uname2),
                    "tid": tid2,
                    "username": uname2 or parsed2.get("username") or "",
                    "displayName": display2,
                    "createTime": int(parsed2.get("createTime") or 0),
                    "contentDesc": str(parsed2.get("contentDesc") or ""),
                    "location": str(parsed2.get("location") or ""),
                    "sourceName": str(parsed2.get("sourceName") or ""),
                    "media": parsed2.get("media") or [],
                    "likes": parsed2.get("likes") or [],
                    "comments": parsed2.get("comments") or [],
                    "type": post_type2,
                    "title": parsed2.get("title", ""),
                    "contentUrl": parsed2.get("contentUrl", ""),
                    "finderFeed": parsed2.get("finderFeed", {}),
                    "official": official2,
                }
            )

        if official_usernames2 and contact_db_path.exists():
            official_rows2 = _load_contact_rows(contact_db_path, list(official_usernames2))
            for item in timeline2:
                off2 = item.get("official")
                if not isinstance(off2, dict):
                    continue
                u0_2 = str(off2.get("username") or "").strip()
                if not u0_2:
                    continue
                row2 = official_rows2.get(u0_2)
                if row2 is None:
                    continue
                off2["displayName"] = str(_pick_display_name(row2, u0_2)).strip()

        return {
            "timeline": timeline2,
            "hasMore": has_more2,
            "limit": limit,
            "offset": offset,
            "source": "sqlite",
            "cover": cover_data,
            "covers": covers_data,
        }

    auto_cache_key = _sns_timeline_auto_cache_key(account_dir, users, kw) if users else None
    # If we previously detected that WCDB only returns a visible subset for this contact (less than
    # the local decrypted snapshot), skip WCDB for subsequent pages to keep pagination flowing.
    if auto_cache_key is not None and offset > 0:
        try:
            if _sns_timeline_auto_cache_get(auto_cache_key):
                out = _list_from_decrypted_sqlite()
                out["source"] = "sqlite-auto"
                return out
        except Exception:
            pass

    def _list_from_wcdb_snstimeline_table(wcdb_conn: Any) -> Optional[dict[str, Any]]:
        """Query encrypted `SnsTimeLine` table directly (bypass timeline API filtering).

        In some cases (commonly: contact sets "only show last 3 days"), the WCDB timeline API returns
        an empty list even though the encrypted `sns.db` still contains cached historical rows.
        """
        if not users:
            return None

        def _q(v: str) -> str:
            return "'" + str(v or "").replace("'", "''") + "'"

        try:
            sns_db_path = wcdb_conn.db_storage_dir / "sns" / "sns.db"
            if not sns_db_path.exists():
                sns_db_path = wcdb_conn.db_storage_dir / "sns.db"
        except Exception:
            return None

        if not (sns_db_path.exists() and sns_db_path.is_file()):
            return None

        filters: list[str] = [
            "content IS NOT NULL",
            "content != ''",
            # Cover rows are returned separately via `cover`, do not mix into timeline.
            "content NOT LIKE '%<type>7</type>%'",
        ]

        ulist = [str(u or "").strip() for u in users if str(u or "").strip()]
        if ulist:
            filters.append(f"user_name IN ({','.join([_q(u) for u in ulist])})")

        if kw:
            kw_esc = str(kw).replace("'", "''")
            filters.append(f"content LIKE '%{kw_esc}%'")

        where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
        # Fetch 1 extra row to determine hasMore.
        sql = f"""
            SELECT tid, user_name, content, pack_info_buf
            FROM SnsTimeLine
            {where_sql}
            ORDER BY tid DESC
            LIMIT {int(limit) + 1} OFFSET {int(offset)}
        """

        sql_rows: list[dict[str, Any]] = []
        with wcdb_conn.lock:
            try:
                sql_rows = _wcdb_exec_query(wcdb_conn.handle, kind="media", path=str(sns_db_path), sql=sql)
            except Exception:
                # Older schema without pack_info_buf.
                sql = f"""
                    SELECT tid, user_name, content
                    FROM SnsTimeLine
                    {where_sql}
                    ORDER BY tid DESC
                    LIMIT {int(limit) + 1} OFFSET {int(offset)}
                """
                sql_rows = _wcdb_exec_query(wcdb_conn.handle, kind="media", path=str(sns_db_path), sql=sql)

        if not sql_rows:
            return None

        has_more3 = len(sql_rows) > int(limit)
        sql_rows = sql_rows[: int(limit)]

        post_usernames3: list[str] = []
        upsert_rows3: list[tuple[int, str, str, Optional[str]]] = []

        # Prepare contact/biz mapping (same as other code paths).
        for rr in sql_rows:
            if not isinstance(rr, dict):
                continue
            uname3 = str(rr.get("user_name") or rr.get("username") or "").strip()
            if uname3:
                post_usernames3.append(uname3)

        contact_rows3 = _load_contact_rows(contact_db_path, post_usernames3) if contact_db_path.exists() else {}
        biz_index3 = _get_biz_to_official_index(contact_db_path) if contact_db_path.exists() else {}
        official_usernames3: set[str] = set()

        timeline3: list[dict[str, Any]] = []
        for rr in sql_rows:
            if not isinstance(rr, dict):
                continue

            try:
                tid3 = int(rr.get("tid") or 0)
            except Exception:
                continue

            uname3 = str(rr.get("user_name") or rr.get("username") or "").strip()
            if not uname3:
                continue

            content_xml3 = _decode_sns_text_blob(rr.get("content"))
            if not content_xml3:
                continue

            parsed3 = _parse_timeline_xml(content_xml3, uname3)

            # Attach ISAAC64 key for SNS video/live-photo.
            video_key3 = _extract_sns_video_key(content_xml3)
            if video_key3:
                pmedia3 = parsed3.get("media")
                if isinstance(pmedia3, list):
                    for m0 in pmedia3:
                        if not isinstance(m0, dict):
                            continue
                        if "videoKey" not in m0:
                            m0["videoKey"] = video_key3
                        lp = m0.get("livePhoto")
                        if isinstance(lp, dict):
                            if not str(lp.get("key") or "").strip():
                                lp["key"] = video_key3

            post_type3 = int(parsed3.get("type", 1) or 1)
            if post_type3 == 7:
                continue

            display3 = _pick_display_name(contact_rows3.get(uname3), uname3) if uname3 else uname3

            official3: dict[str, Any] = {}
            if post_type3 == 3:
                content_url3 = str(parsed3.get("contentUrl") or "")
                biz3 = _extract_mp_biz_from_url(content_url3)
                info3 = biz_index3.get(biz3) if biz3 else None
                off_username3 = str(info3.get("username") or "").strip() if isinstance(info3, dict) else ""
                off_service_type3 = info3.get("serviceType") if isinstance(info3, dict) else None
                official3 = {
                    "biz": biz3,
                    "username": off_username3,
                    "serviceType": off_service_type3,
                    "displayName": "",
                }
                if off_username3:
                    official_usernames3.add(off_username3)

            timeline3.append(
                {
                    "id": _to_unsigned_i64_str(tid3),
                    "tid": _to_unsigned_i64_str(tid3),
                    "username": uname3,
                    "displayName": str(display3 or "").replace("\xa0", " ").strip() or uname3,
                    "createTime": int(parsed3.get("createTime") or 0),
                    "contentDesc": str(parsed3.get("contentDesc") or ""),
                    "location": str(parsed3.get("location") or ""),
                    "sourceName": str(parsed3.get("sourceName") or ""),
                    "media": parsed3.get("media") or [],
                    "likes": parsed3.get("likes") or [],
                    "comments": parsed3.get("comments") or [],
                    "type": post_type3,
                    "title": parsed3.get("title", ""),
                    "contentUrl": parsed3.get("contentUrl", ""),
                    "finderFeed": parsed3.get("finderFeed", {}),
                    "official": official3,
                }
            )

            pack3 = rr.get("pack_info_buf")
            upsert_rows3.append((int(tid3), uname3, content_xml3, None if pack3 is None else str(pack3)))

        if official_usernames3 and contact_db_path.exists():
            official_rows3 = _load_contact_rows(contact_db_path, list(official_usernames3))
            for item in timeline3:
                off3 = item.get("official")
                if not isinstance(off3, dict):
                    continue
                u0_3 = str(off3.get("username") or "").strip()
                if not u0_3:
                    continue
                row3 = official_rows3.get(u0_3)
                if row3 is None:
                    continue
                off3["displayName"] = str(_pick_display_name(row3, u0_3) or "").replace("\xa0", " ").strip()

        # Incremental writeback: cache what we just fetched into decrypted snapshot.
        if upsert_rows3:
            _upsert_sns_timeline_rows_to_decrypted_db(account_dir, upsert_rows3, source="timeline-wcdb-direct")

        if not timeline3:
            return None

        return {
            "timeline": timeline3,
            "hasMore": has_more3,
            "limit": limit,
            "offset": offset,
            "source": "wcdb-direct",
            "cover": cover_data,
            "covers": covers_data,
        }

    # Prefer real-time WCDB access (reads the latest encrypted db_storage/sns/sns.db).
    # Fallback to the decrypted sqlite copy in output/{account}/sns.db.
    try:
        conn = WCDB_REALTIME.ensure_connected(account_dir)
        writeback_rows: list[tuple[int, str, str, Optional[str]]] = []

        cached_posts_total = 0
        if users:
            # Used to decide whether to auto-switch to the decrypted sqlite snapshot when WCDB only
            # returns a small visible subset (privacy settings, etc.).
            try:
                with _sns_decrypted_db_lock(Path(account_dir).name):
                    cached_posts_total = _count_sns_timeline_posts_in_decrypted_sqlite(
                        account_dir / "sns.db",
                        users=users,
                        kw=kw,
                    )
            except Exception:
                cached_posts_total = 0

        def _clean_name(v: Any) -> str:
            return str(v or "").replace("\xa0", " ").strip()

        # Base timeline (includes likes/comments) from WCDB API.
        with conn.lock:
            wcdb_fetch_limit = limit + 1
            wcdb_probe_total: Optional[int] = None

            # Probe WCDB total when we already have a small (<=200) local cache.
            # This lets us switch to sqlite on the *first page* without requiring the user
            # to scroll to the end of WCDB's (possibly smaller) visible subset.
            if users and offset == 0 and cached_posts_total > int(limit) and cached_posts_total <= 200:
                wcdb_fetch_limit = 201  # 200 + 1 sentinel

            rows = _wcdb_get_sns_timeline(
                conn.handle,
                limit=wcdb_fetch_limit,
                offset=offset,
                usernames=users,
                keyword=kw,
            )

            if wcdb_fetch_limit == 201:
                try:
                    wcdb_probe_total = len(rows) if isinstance(rows, list) else 0
                except Exception:
                    wcdb_probe_total = None

            # If WCDB ends within 200 and is smaller than the local snapshot, serve snapshot immediately.
            if (
                users
                and offset == 0
                and isinstance(wcdb_probe_total, int)
                and wcdb_probe_total >= 0
                and wcdb_probe_total <= 200
                and cached_posts_total > wcdb_probe_total
            ):
                try:
                    if auto_cache_key is None:
                        auto_cache_key = _sns_timeline_auto_cache_key(account_dir, users, kw)
                    _sns_timeline_auto_cache_set(auto_cache_key, True)
                except Exception:
                    pass
                out = _list_from_decrypted_sqlite()
                out["source"] = "sqlite-auto"
                return out

            # Best-effort: enrich posts with XML-only fields (location + media attrs/size)
            # by querying SnsTimeLine.content from the encrypted sns.db.
            username_by_tid: dict[int, str] = {}
            content_by_tid: dict[int, str] = {}
            try:
                sns_db_path = conn.db_storage_dir / "sns" / "sns.db"
                if not sns_db_path.exists():
                    sns_db_path = conn.db_storage_dir / "sns.db"

                tids: list[int] = []
                for r in (rows or [])[: int(limit)]:
                    if not isinstance(r, dict):
                        continue
                    uname0 = str(r.get("username") or "").strip()
                    try:
                        tid_u = int(r.get("id") or 0)
                    except Exception:
                        continue
                    tid_s = _to_signed_i64(tid_u)
                    tids.append(tid_s)
                    if uname0:
                        username_by_tid[tid_s] = uname0

                tids = list(dict.fromkeys(tids))
                if tids and sns_db_path.exists():
                    in_sql = ",".join([str(x) for x in tids])
                    sql = f"SELECT tid, user_name, content, pack_info_buf FROM SnsTimeLine WHERE tid IN ({in_sql})"
                    try:
                        sql_rows = _wcdb_exec_query(conn.handle, kind="media", path=str(sns_db_path), sql=sql)
                    except Exception:
                        sql = f"SELECT tid, user_name, content FROM SnsTimeLine WHERE tid IN ({in_sql})"
                        sql_rows = _wcdb_exec_query(conn.handle, kind="media", path=str(sns_db_path), sql=sql)
                    for rr in sql_rows:
                        try:
                            tid_val = int(rr.get("tid"))
                        except Exception:
                            continue
                        content_xml = _decode_sns_text_blob(rr.get("content"))
                        if content_xml:
                            content_by_tid[tid_val] = content_xml
                        uname1 = str(rr.get("user_name") or rr.get("username") or "").strip()
                        if not uname1:
                            uname1 = username_by_tid.get(tid_val, "")
                        if uname1 and content_xml:
                            pack = rr.get("pack_info_buf")
                            writeback_rows.append((tid_val, uname1, content_xml, None if pack is None else str(pack)))
            except Exception:
                content_by_tid = {}
                writeback_rows = []

        has_more = len(rows) > limit
        rows = rows[:limit]

        # Incremental writeback: cache what we just saw into the decrypted snapshot,
        # so later "not visible" (e.g. only last 3 days) still has local data.
        if writeback_rows:
            _upsert_sns_timeline_rows_to_decrypted_db(
                account_dir,
                writeback_rows,
                source="timeline-wcdb",
            )

        post_usernames = [str((r or {}).get("username") or "").strip() for r in rows if isinstance(r, dict)]
        post_usernames = [u for u in post_usernames if u]
        contact_rows = _load_contact_rows(contact_db_path, post_usernames) if contact_db_path.exists() else {}
        biz_index = _get_biz_to_official_index(contact_db_path) if contact_db_path.exists() else {}
        official_usernames: set[str] = set()

        timeline: list[dict[str, Any]] = []
        for r in rows:
            if not isinstance(r, dict):
                continue

            uname = str(r.get("username") or "").strip()
            nickname = _clean_name(r.get("nickname"))
            display = nickname or (_pick_display_name(contact_rows.get(uname), uname) if uname else uname)

            create_time = _safe_int(r.get("createTime"))
            content_desc = str(r.get("contentDesc") or "")
            media = r.get("media") if isinstance(r.get("media"), list) else []
            likes = r.get("likes") if isinstance(r.get("likes"), list) else []
            likes = [_clean_name(x) for x in likes if _clean_name(x)]
            comments = r.get("comments") if isinstance(r.get("comments"), list) else []

            # WeFlow: live photo / SNS video decryption key comes from `<enc key="...">` in raw XML.
            # Keep it local to avoid sending huge rawXml to the frontend.
            video_key = _extract_sns_video_key(r.get("rawXml"))
            if video_key and isinstance(media, list):
                for m0 in media:
                    if not isinstance(m0, dict):
                        continue
                    if "videoKey" not in m0:
                        m0["videoKey"] = video_key
                    lp = m0.get("livePhoto")
                    if isinstance(lp, dict):
                        if not str(lp.get("key") or "").strip():
                            lp["key"] = video_key

            # Enrich with parsed XML when available.
            location = str(r.get("location") or "")
            source_name = _extract_sns_source_name(r.get("rawXml"))

            post_type = 1
            title = ""
            content_url = ""
            finder_feed = {}
            try:
                tid_u = int(r.get("id") or 0)
                tid_s = (tid_u & 0xFFFFFFFFFFFFFFFF)
                if tid_s >= 0x8000000000000000:
                    tid_s -= 0x10000000000000000
                xml = content_by_tid.get(int(tid_s))
                if xml:
                    parsed = _parse_timeline_xml(xml, uname)
                    if parsed.get("location"):
                        location = str(parsed.get("location") or "")
                    sn0 = str(parsed.get("sourceName") or "").strip()
                    if sn0:
                        source_name = sn0

                    post_type = parsed.get("type", 1)

                    if post_type == 7:  #  朋友圈封面
                        continue

                    title = parsed.get("title", "")
                    content_url = parsed.get("contentUrl", "")
                    finder_feed = parsed.get("finderFeed", {})

                    pmedia = parsed.get("media") or []
                    if isinstance(pmedia, list) and isinstance(media, list) and pmedia:
                        # Merge by index (best-effort).
                        merged: list[dict[str, Any]] = []
                        for i, m0 in enumerate(media):
                            mp = pmedia[i] if i < len(pmedia) else None
                            if not isinstance(mp, dict):
                                merged.append(m0 if isinstance(m0, dict) else {})
                                continue
                            mm = dict(mp)
                            if isinstance(m0, dict):
                                for k in ("url", "thumb"):
                                    v = m0.get(k)
                                    if v:
                                        mm[k] = v
                                for k, v in m0.items():
                                    if k not in mm:
                                        mm[k] = v
                            merged.append(mm)
                        media = merged

                    # If rawXml didn't contain `<enc key="...">`, try extracting from the content XML.
                    # Some WCDB timeline APIs omit rawXml, but the encrypted sns.db content still has the key.
                    if isinstance(media, list) and (not video_key):
                        video_key_xml = _extract_sns_video_key(xml)
                        if video_key_xml:
                            for m0 in media:
                                if not isinstance(m0, dict):
                                    continue
                                if "videoKey" not in m0:
                                    m0["videoKey"] = video_key_xml
                                lp = m0.get("livePhoto")
                                if isinstance(lp, dict):
                                    if not str(lp.get("key") or "").strip():
                                        lp["key"] = video_key_xml
            except Exception:
                pass

            official: dict[str, Any] = {}
            if post_type == 3:
                biz = _extract_mp_biz_from_url(content_url)
                info = biz_index.get(biz) if biz else None
                off_username = str(info.get("username") or "").strip() if isinstance(info, dict) else ""
                off_service_type = info.get("serviceType") if isinstance(info, dict) else None
                official = {
                    "biz": biz,
                    "username": off_username,
                    "serviceType": off_service_type,
                    "displayName": "",
                }
                if off_username:
                    official_usernames.add(off_username)

            pid = str(r.get("id") or "") or str(create_time or "") or uname
            timeline.append(
                {
                    "id": pid,
                    "tid": r.get("id"),
                    "username": uname,
                    "displayName": _clean_name(display) or uname,
                    "createTime": create_time,
                    "contentDesc": content_desc,
                    "location": str(location or ""),
                    "sourceName": str(source_name or ""),
                    "media": media,
                    "likes": likes,
                    "comments": comments,
                    "type": post_type,
                    "title": title,
                    "contentUrl": content_url,
                    "finderFeed": finder_feed,
                    "official": official,
                }
            )

        if official_usernames and contact_db_path.exists():
            official_rows = _load_contact_rows(contact_db_path, list(official_usernames))
            for item in timeline:
                off = item.get("official")
                if not isinstance(off, dict):
                    continue
                u0 = str(off.get("username") or "").strip()
                if not u0:
                    continue
                row = official_rows.get(u0)
                if row is None:
                    continue
                off["displayName"] = _clean_name(_pick_display_name(row, u0))

        wcdb_resp = {
            "timeline": timeline,
            "hasMore": has_more,
            "limit": limit,
            "offset": offset,
            "source": "wcdb",
            "cover": cover_data,
            "covers": covers_data,
        }

        # Some contacts may have Moments cached in the decrypted sqlite, while the WCDB
        # real-time API returns empty (commonly caused by privacy settings like
        # "only show last 3 days"). In that case, fall back to the decrypted sqlite
        # so the UI doesn't show an empty timeline when data exists locally.
        if (not timeline) and users:
            # 1) Try querying encrypted `SnsTimeLine` table directly (can bypass API filtering).
            try:
                direct = _list_from_wcdb_snstimeline_table(conn)
            except Exception:
                direct = None
            if isinstance(direct, dict) and direct.get("timeline"):
                return direct

            # 2) Fallback to decrypted sqlite snapshot (historical cached content).
            try:
                legacy = _list_from_decrypted_sqlite()
            except HTTPException:
                legacy = None
            except Exception:
                legacy = None
            if isinstance(legacy, dict) and legacy.get("timeline"):
                return legacy

        # Auto-fallback: if WCDB timeline ends but the local decrypted snapshot has more rows for this
        # contact query, switch to the snapshot so the frontend can keep paging.
        if users and timeline and (not has_more):
            try:
                with _sns_decrypted_db_lock(Path(account_dir).name):
                    cached_total = _count_sns_timeline_posts_in_decrypted_sqlite(
                        account_dir / "sns.db",
                        users=users,
                        kw=kw,
                    )
                wcdb_total = int(offset) + int(len(timeline))
                if cached_total > wcdb_total:
                    if auto_cache_key is None:
                        auto_cache_key = _sns_timeline_auto_cache_key(account_dir, users, kw)
                    _sns_timeline_auto_cache_set(auto_cache_key, True)
                    out = _list_from_decrypted_sqlite()
                    out["source"] = "sqlite-auto"
                    return out
            except Exception:
                pass

        return wcdb_resp
    except WCDBRealtimeError as e:
        logger.info("[sns] wcdb realtime unavailable: %s", e)
    except Exception as e:
        logger.warning("[sns] wcdb realtime failed: %s", e)

    return _list_from_decrypted_sqlite()


@router.get("/api/sns/users", summary="列出朋友圈联系人（按发圈数统计）")
def list_sns_users(
    account: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = 5000,
):
    account_dir = _resolve_account_dir(account)
    sns_db_path = account_dir / "sns.db"
    if not sns_db_path.exists():
        raise HTTPException(status_code=404, detail="sns.db not found for this account.")

    contact_db_path = account_dir / "contact.db"

    try:
        lim = int(limit or 5000)
    except Exception:
        lim = 5000
    if lim <= 0:
        lim = 5000
    if lim > 5000:
        lim = 5000

    kw = str(keyword or "").strip().lower()

    conn = sqlite3.connect(str(sns_db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
              user_name AS username,
              SUM(
                CASE
                  WHEN content IS NOT NULL AND content != '' AND content NOT LIKE '%<type>7</type>%'
                  THEN 1 ELSE 0
                END
              ) AS postCount,
              COUNT(*) AS totalCount
            FROM SnsTimeLine
            GROUP BY user_name
            ORDER BY postCount DESC, totalCount DESC
            """
        )
        rows = cur.fetchall() or []
    finally:
        try:
            conn.close()
        except Exception:
            pass

    usernames = [str(r["username"] or "").strip() for r in rows if r is not None]
    usernames = [u for u in usernames if u]
    contact_rows = _load_contact_rows(contact_db_path, usernames) if contact_db_path.exists() else {}

    items: list[dict[str, Any]] = []

    def _clean_name(v: Any) -> str:
        return str(v or "").replace("\xa0", " ").strip()

    for r in rows:
        try:
            uname = str(r["username"] or "").strip()
        except Exception:
            uname = ""
        if not uname:
            continue

        try:
            post_count = int(r["postCount"] or 0)
        except Exception:
            post_count = 0
        if post_count <= 0:
            continue

        row = contact_rows.get(uname)
        display = _clean_name(_pick_display_name(row, uname)) or uname

        if kw:
            if kw not in uname.lower() and kw not in display.lower():
                continue

        items.append({"username": uname, "displayName": display, "postCount": post_count})
        if len(items) >= lim:
            break

    return {"items": items, "count": len(items), "limit": lim}


def _is_allowed_sns_media_host(host: str) -> bool:
    return _sns_media.is_allowed_sns_media_host(host)


def _fix_sns_cdn_url(url: str, *, token: str = "", is_video: bool = False) -> str:
    return _sns_media.fix_sns_cdn_url(url, token=token, is_video=is_video)


def _detect_mp4_ftyp(head: bytes) -> bool:
    return bool(head) and len(head) >= 8 and head[4:8] == b"ftyp"


@lru_cache(maxsize=1)
def _weflow_wxisaac64_script_path() -> str:
    """Locate the Node helper that wraps WeFlow's wasm_video_decode.* assets."""
    repo_root = Path(__file__).resolve().parents[3]
    script = repo_root / "tools" / "weflow_wasm_keystream.js"
    if script.exists() and script.is_file():
        return str(script)
    return ""


@lru_cache(maxsize=64)
def _weflow_wxisaac64_keystream(key: str, size: int) -> bytes:
    return _sns_media.weflow_wxisaac64_keystream(key, size)


_SNS_REMOTE_VIDEO_CACHE_EXTS = [
    ".mp4",
    ".bin",  # legacy/unknown
]


def _sns_remote_video_cache_dir_and_stem(account_dir: Path, *, url: str, key: str) -> tuple[Path, str]:
    digest = hashlib.md5(f"video|{url}|{key}".encode("utf-8", errors="ignore")).hexdigest()
    cache_dir = account_dir / "sns_remote_video_cache" / digest[:2]
    return cache_dir, digest


def _sns_remote_video_cache_existing_path(cache_dir: Path, stem: str) -> Optional[Path]:
    for ext in _SNS_REMOTE_VIDEO_CACHE_EXTS:
        p = cache_dir / f"{stem}{ext}"
        try:
            if p.exists() and p.is_file():
                return p
        except Exception:
            continue
    return None


async def _download_sns_remote_to_file(url: str, dest_path: Path, *, max_bytes: int) -> tuple[str, str]:
    """Download SNS media to file (streaming) from Tencent CDN.

    Returns: (content_type, x_enc)
    """
    u = str(url or "").strip()
    if not u:
        return "", ""

    # Safety: only allow Tencent CDN hosts.
    try:
        p = urlparse(u)
        host = str(p.hostname or "").lower()
        if not _is_allowed_sns_media_host(host):
            raise HTTPException(status_code=400, detail="SNS media host not allowed.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid SNS media URL.")

    base_headers = {
        "User-Agent": "MicroMessenger Client",
        "Accept": "*/*",
        # Do not request compression for video streams.
        "Connection": "keep-alive",
    }

    header_variants = [
        {},
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) WindowsWechat(0x63090719) XWEB/8351",
            "Referer": "https://servicewechat.com/",
            "Origin": "https://servicewechat.com",
        },
        {"Referer": "https://wx.qq.com/", "Origin": "https://wx.qq.com"},
        {"Referer": "https://mp.weixin.qq.com/", "Origin": "https://mp.weixin.qq.com"},
    ]

    last_err: Exception | None = None
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for extra in header_variants:
            headers = dict(base_headers)
            headers.update(extra)
            try:
                if dest_path.exists():
                    try:
                        dest_path.unlink(missing_ok=True)
                    except Exception:
                        pass

                total = 0
                async with client.stream("GET", u, headers=headers) as resp:
                    resp.raise_for_status()
                    content_type = str(resp.headers.get("Content-Type") or "").strip()
                    x_enc = str(resp.headers.get("x-enc") or "").strip()
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    with dest_path.open("wb") as f:
                        async for chunk in resp.aiter_bytes():
                            if not chunk:
                                continue
                            total += len(chunk)
                            if total > max_bytes:
                                raise HTTPException(status_code=400, detail="SNS video too large.")
                            f.write(chunk)
                return content_type, x_enc
            except HTTPException:
                raise
            except Exception as e:
                last_err = e
                continue

    raise last_err or RuntimeError("sns remote download failed")


def _maybe_decrypt_sns_video_file(path: Path, key: str) -> bool:
    return _sns_media.maybe_decrypt_sns_video_file(path, key)


async def _materialize_sns_remote_video(
    *,
    account_dir: Path,
    url: str,
    key: str,
    token: str,
    use_cache: bool,
) -> Optional[Path]:
    return await _sns_media.materialize_sns_remote_video(
        account_dir=account_dir,
        url=url,
        key=key,
        token=token,
        use_cache=use_cache,
    )


def _best_effort_unlink(path: str) -> None:
    _sns_media.best_effort_unlink(path)


def _detect_image_mime(data: bytes) -> str:
    return _sns_media.detect_image_mime(data)


_SNS_REMOTE_CACHE_EXTS = [
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".bmp",
    ".avif",
    ".heic",
    ".heif",
    ".bin",  # legacy/unknown
]


def _mime_to_ext(mt: str) -> str:
    m = str(mt or "").split(";", 1)[0].strip().lower()
    return {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
        "image/avif": ".avif",
        "image/heic": ".heic",
        "image/heif": ".heif",
    }.get(m, ".bin")


def _ext_to_mime(ext: str) -> str:
    e = str(ext or "").strip().lower().lstrip(".")
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
        "bmp": "image/bmp",
        "avif": "image/avif",
        "heic": "image/heic",
        "heif": "image/heif",
    }.get(e, "")


def _sns_remote_cache_dir_and_stem(account_dir: Path, *, url: str, key: str) -> tuple[Path, str]:
    digest = hashlib.md5(f"{url}|{key}".encode("utf-8", errors="ignore")).hexdigest()
    cache_dir = account_dir / "sns_remote_cache" / digest[:2]
    return cache_dir, digest


def _sns_remote_cache_existing_path(cache_dir: Path, stem: str) -> Optional[Path]:
    for ext in _SNS_REMOTE_CACHE_EXTS:
        p = cache_dir / f"{stem}{ext}"
        try:
            if p.exists() and p.is_file():
                return p
        except Exception:
            continue
    return None


def _sniff_image_mime_from_file(path: Path) -> str:
    try:
        with path.open("rb") as f:
            head = f.read(64)
        return _detect_image_mime(head)
    except Exception:
        return ""


async def _download_sns_remote_bytes(url: str) -> tuple[bytes, str, str]:
    """Download SNS media bytes from Tencent CDN with a few safe header variants."""
    u = str(url or "").strip()
    if not u:
        return b"", "", ""

    max_bytes = 25 * 1024 * 1024

    base_headers = {
        "User-Agent": "MicroMessenger Client",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        # Avoid brotli dependency issues; images are already compressed anyway.
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
    }

    # Some CDN endpoints return a small placeholder image for certain UA/Referer
    # combinations but still respond 200. Try the simplest (base headers only)
    # first to maximize the chance of getting the real media in one request.
    header_variants = [
        {},
        # WeFlow/Electron: MicroMessenger UA + servicewechat.com referer passes some CDN anti-hotlink checks.
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) WindowsWechat(0x63090719) XWEB/8351",
            "Referer": "https://servicewechat.com/",
            "Origin": "https://servicewechat.com",
        },
        {"Referer": "https://wx.qq.com/", "Origin": "https://wx.qq.com"},
        {"Referer": "https://mp.weixin.qq.com/", "Origin": "https://mp.weixin.qq.com"},
    ]

    last_err: Exception | None = None
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        for extra in header_variants:
            headers = dict(base_headers)
            headers.update(extra)
            try:
                resp = await client.get(u, headers=headers)
                resp.raise_for_status()
                payload = bytes(resp.content or b"")
                if len(payload) > max_bytes:
                    raise HTTPException(status_code=400, detail="SNS media too large (>25MB).")
                content_type = str(resp.headers.get("Content-Type") or "").strip()
                x_enc = str(resp.headers.get("x-enc") or "").strip()
                return payload, content_type, x_enc
            except HTTPException:
                raise
            except Exception as e:
                last_err = e
                continue

    raise last_err or RuntimeError("sns remote download failed")


async def _try_fetch_and_decrypt_sns_remote(
    *,
    account_dir: Path,
    url: str,
    key: str,
    token: str,
    use_cache: bool,
) -> Optional[Response]:
    """Try remote download+decrypt first (accurate when keys are present)."""
    res = await _sns_media.try_fetch_and_decrypt_sns_image_remote(
        account_dir=account_dir,
        url=str(url or ""),
        key=str(key or ""),
        token=str(token or ""),
        use_cache=bool(use_cache),
    )
    if res is None:
        return None

    resp = Response(content=res.payload, media_type=res.media_type)
    resp.headers["Cache-Control"] = "public, max-age=86400" if use_cache else "no-store"
    return resp


@router.get("/api/sns/media", summary="获取朋友圈图片（下载解密优先）")
async def get_sns_media(
        account: Optional[str] = None,
        token: Optional[str] = None,
        key: Optional[str] = None,
        use_cache: int = 1,
        url: Optional[str] = None,
):
    account_dir = _resolve_account_dir(account)

    try:
        use_cache_flag = bool(int(use_cache or 1))
    except Exception:
        use_cache_flag = True

    # 0) Prefer WeFlow-style remote download + decrypt (accurate, avoids local cache mismatch).
    remote_resp = await _try_fetch_and_decrypt_sns_remote(
        account_dir=account_dir,
        url=str(url or ""),
        key=str(key or ""),
        token=str(token or ""),
        use_cache=use_cache_flag,
    )
    if remote_resp is not None:
        return remote_resp

    raise HTTPException(status_code=404, detail="SNS media not found.")


@router.get("/api/sns/article_thumb", summary="提取公众号文章封面图")
async def proxy_article_thumb(url: str):
    u = str(url or "").strip()
    if not u.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid URL")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = await client.get(u, headers=headers)
            resp.raise_for_status()
            html_text = resp.text

            match = re.search(r'["\'](https?://[^"\']*?mmbiz_[a-zA-Z]+[^"\']*?)["\']', html_text)

            if not match:
                raise HTTPException(status_code=404, detail="未在 HTML 中找到图片 URL")

            img_url = match.group(1)
            img_url = html.unescape(img_url).replace("&amp;", "&")

            img_resp = await client.get(img_url, headers=headers)
            img_resp.raise_for_status()

            return Response(
                content=img_resp.content,
                media_type=img_resp.headers.get("Content-Type", "image/jpeg")
            )

    except Exception as e:
        logger.warning(f"[sns] 提取公众号封面失败 url={u[:50]}... : {e}")
        raise HTTPException(status_code=404, detail="无法获取文章封面")


@router.get("/api/sns/video_remote", summary="获取朋友圈远程视频/实况（下载解密优先）")
async def get_sns_video_remote(
        account: Optional[str] = None,
        url: Optional[str] = None,
        token: Optional[str] = None,
        key: Optional[str] = None,
        use_cache: int = 1,
):
    account_dir = _resolve_account_dir(account)

    try:
        use_cache_flag = bool(int(use_cache or 1))
    except Exception:
        use_cache_flag = True

    path = await _materialize_sns_remote_video(
        account_dir=account_dir,
        url=str(url or ""),
        key=str(key or ""),
        token=str(token or ""),
        use_cache=use_cache_flag,
    )
    if path is None:
        raise HTTPException(status_code=404, detail="SNS remote video not found.")

    headers = {"Cache-Control": "public, max-age=86400" if use_cache_flag else "no-store"}

    if use_cache_flag:
        return FileResponse(str(path), media_type="video/mp4", headers=headers)

    # Cache disabled: delete the temp file after response.
    return FileResponse(
        str(path),
        media_type="video/mp4",
        headers=headers,
        background=BackgroundTask(_best_effort_unlink, str(path)),
    )


@router.get("/api/sns/video", summary="获取朋友圈本地缓存视频")
async def get_sns_video(
        account: Optional[str] = None,
        post_id: Optional[str] = None,
        media_id: Optional[str] = None,
):
    if not post_id or not media_id:
        raise HTTPException(status_code=400, detail="Missing post_id or media_id")

    account_dir = _resolve_account_dir(account)
    wxid_dir = _resolve_account_wxid_dir(account_dir)

    if not wxid_dir:
        raise HTTPException(status_code=404, detail="WXID dir not found")

    video_path = _resolve_sns_cached_video_path(wxid_dir, post_id, media_id)

    if not video_path:
        raise HTTPException(status_code=404, detail="Local video cache not found")

    return FileResponse(video_path, media_type="video/mp4")
