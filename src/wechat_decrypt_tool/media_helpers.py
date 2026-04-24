import ctypes
import datetime
import glob
import hashlib
import ipaddress
import json
import mimetypes
import os
import re
import sqlite3
import struct
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

from fastapi import HTTPException

from .app_paths import get_output_databases_dir
from .chat_helpers import _decode_message_content
from .logging_config import get_logger
from .sqlite_diagnostics import is_usable_sqlite_db

logger = get_logger(__name__)

_MEDIA_INDEX_FILE_EXTS = {
    ".dat",
    ".gif",
    ".heic",
    ".heif",
    ".jpeg",
    ".jpg",
    ".m4v",
    ".mov",
    ".mp4",
    ".png",
    ".webp",
}
_MEDIA_INDEX_VIDEO_STREAM_EXTS = {
    ".m4v",
    ".mov",
    ".mp4",
}
_MEDIA_INDEX_VIDEO_INDEX_EXTS = _MEDIA_INDEX_VIDEO_STREAM_EXTS | {".dat"}
_MEDIA_INDEX_STRIP_SUFFIX_RE = re.compile(r"(?i)(?:_h|_t|_thumb)$")
_MEDIA_INDEX_DB_VERSION = 2


# 运行时输出目录（桌面端可通过 WECHAT_TOOL_DATA_DIR 指向可写目录）
_PACKAGE_ROOT = Path(__file__).resolve().parent
_SQLITE_HEADER = b"SQLite format 3\x00"
_EMOTICON_MD5_RE = re.compile(r"(?i)^[0-9a-f]{32}$")
_EMOTICON_MD5_ATTR_RE = re.compile(r"(?i)\bmd5\s*=\s*['\"]([0-9a-f]{32})['\"]")
_EMOTICON_MD5_TAG_RE = re.compile(r"(?is)<md5>\s*([0-9a-f]{32})\s*</md5>")
_EMOTICON_EXTERN_MD5_ATTR_RE = re.compile(r"(?i)\bextern_?md5\s*=\s*['\"]([0-9a-f]{32})['\"]")
_EMOTICON_EXTERN_MD5_TAG_RE = re.compile(r"(?is)<extern_?md5>\s*([0-9a-f]{32})\s*</extern_?md5>")
_EMOTICON_AES_KEY_ATTR_RE = re.compile(r"(?i)\baes_?key\s*=\s*['\"]([0-9a-f]{32})['\"]")
_EMOTICON_AES_KEY_TAG_RE = re.compile(r"(?is)<aes_?key>\s*([0-9a-f]{32})\s*</aes_?key>")
_EMOTICON_HTTP_URL_RE = re.compile(r"(?i)https?://[^\s<>\"']+")


def _is_valid_decrypted_sqlite(path: Path) -> bool:
    return is_usable_sqlite_db(path)


def _list_decrypted_accounts() -> list[str]:
    """列出已解密输出的账号目录名（仅保留包含 session.db + contact.db 的账号）"""
    output_db_dir = get_output_databases_dir()
    if not output_db_dir.exists():
        return []

    accounts: list[str] = []
    for p in output_db_dir.iterdir():
        if not p.is_dir():
            continue
        if _is_valid_decrypted_sqlite(p / "session.db") and _is_valid_decrypted_sqlite(p / "contact.db"):
            accounts.append(p.name)

    accounts.sort()
    return accounts


def _resolve_account_dir(account: Optional[str]) -> Path:
    """解析账号目录，并进行路径安全校验（防止路径穿越）"""
    output_db_dir = get_output_databases_dir()
    accounts = _list_decrypted_accounts()
    if not accounts:
        raise HTTPException(
            status_code=404,
            detail="No decrypted databases found. Please decrypt first.",
        )

    selected = str(account or "").strip() or accounts[0]
    if selected not in accounts:
        raise HTTPException(status_code=404, detail="Account not found.")
    base = output_db_dir.resolve()
    candidate = (output_db_dir / selected).resolve()

    if candidate != base and base not in candidate.parents:
        raise HTTPException(status_code=400, detail="Invalid account path.")

    if not candidate.exists() or not candidate.is_dir():
        raise HTTPException(status_code=404, detail="Account not found.")

    if not (candidate / "session.db").exists():
        raise HTTPException(status_code=404, detail="session.db not found for this account.")
    if not (candidate / "contact.db").exists():
        raise HTTPException(status_code=404, detail="contact.db not found for this account.")

    return candidate


def _detect_image_media_type(data: bytes) -> str:
    if not data:
        return "application/octet-stream"

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff") and len(data) >= 4:
        marker = data[3]
        # Most JPEG marker types are in 0xC0..0xFE (APP, SOF, DQT, DHT, SOS, COM, etc.).
        # This avoids false positives where random bytes start with 0xFFD8FF.
        if marker not in (0x00, 0xFF) and marker >= 0xC0:
            return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def _is_probably_valid_image(data: bytes, media_type: str) -> bool:
    """Heuristic validation to reduce false positives when guessing XOR keys.

    We keep it lightweight (no full parsing), only checking common trailers.
    """
    if not data:
        return False

    mt = str(media_type or "").strip().lower()
    if not mt.startswith("image/"):
        return False

    if mt == "image/jpeg":
        if _detect_image_media_type(data[:32]) != "image/jpeg":
            return False
        trimmed = data.rstrip(b"\x00")
        if len(trimmed) < 4 or not trimmed.startswith(b"\xff\xd8\xff"):
            return False
        if trimmed.endswith(b"\xff\xd9"):
            return True
        tail = trimmed[-4096:] if len(trimmed) > 4096 else trimmed
        i = tail.rfind(b"\xff\xd9")
        return i >= 0 and i >= len(tail) - 64 - 2

    if mt == "image/png":
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            return False
        trailer = b"\x00\x00\x00\x00IEND\xaeB`\x82"
        trimmed = data.rstrip(b"\x00")
        if trimmed.endswith(trailer):
            return True
        tail = trimmed[-256:] if len(trimmed) > 256 else trimmed
        i = tail.rfind(trailer)
        return i >= 0 and i >= len(tail) - 64 - len(trailer)

    if mt == "image/gif":
        if not (data.startswith(b"GIF87a") or data.startswith(b"GIF89a")):
            return False
        trimmed = data.rstrip(b"\x00")
        if trimmed.endswith(b"\x3B"):
            return True
        tail = trimmed[-256:] if len(trimmed) > 256 else trimmed
        i = tail.rfind(b"\x3B")
        return i >= 0 and i >= len(tail) - 16 - 1

    if mt == "image/webp":
        if len(data) < 12:
            return False
        return bool(data.startswith(b"RIFF") and data[8:12] == b"WEBP")

    # Unknown image types: fall back to header-only check.
    return _detect_image_media_type(data[:32]) != "application/octet-stream"


def _normalize_variant_basename(name: str) -> str:
    """Normalize a media filename stem by stripping common variant suffixes.

    Mirrors echotrace's idea of normalizing `.t/.h/.b/.c` and `_t/_h/_b/_c`.
    """
    v = str(name or "").strip()
    if not v:
        return ""
    lower = v.lower()
    for suf in ("_b", "_h", "_c", "_t", ".b", ".h", ".c", ".t"):
        if lower.endswith(suf) and len(lower) > len(suf):
            return lower[: -len(suf)]
    return lower


def _variant_rank(name: str) -> int:
    """Ordering used when trying multiple candidate resources.

    Prefer: big > high > original > cache > thumb.
    """
    n = str(name or "").lower()
    if n.endswith(("_b", ".b")):
        return 0
    if n.endswith(("_h", ".h")):
        return 1
    if n.endswith(("_c", ".c")):
        return 3
    if n.endswith(("_t", ".t")):
        return 4
    return 2


def _iter_media_source_candidates(source: Path, *, limit: int = 30) -> list[Path]:
    """Yield sibling variant files around a resolved source path.

    This is a lightweight approximation of echotrace's \"search many .dat variants then try them\".
    """
    if not source:
        return []

    try:
        if not source.exists():
            return []
    except Exception:
        return []

    try:
        if source.is_dir():
            return []
    except Exception:
        return []

    out: list[Path] = []
    try:
        out.append(source.resolve())
    except Exception:
        out.append(source)

    parent = source.parent
    stem = str(source.stem or "")
    base = _normalize_variant_basename(stem)
    if not base:
        return out

    preferred_names = [
        f"{base}_b.dat",
        f"{base}_h.dat",
        f"{base}.dat",
        f"{base}_c.dat",
        f"{base}_t.dat",
        f"{base}.b.dat",
        f"{base}.h.dat",
        f"{base}.c.dat",
        f"{base}.t.dat",
        f"{base}.gif",
        f"{base}.webp",
        f"{base}.png",
        f"{base}.jpg",
        f"{base}.jpeg",
    ]

    for name in preferred_names:
        p = parent / name
        try:
            if p.exists() and p.is_file():
                out.append(p.resolve())
        except Exception:
            continue

    # Add any other local .dat siblings with the same normalized base (limit to avoid explosion).
    try:
        for p in parent.glob(f"{base}*.dat"):
            try:
                if p.exists() and p.is_file():
                    out.append(p.resolve())
            except Exception:
                continue
            if len(out) >= int(limit):
                break
    except Exception:
        pass

    # De-dup while keeping order.
    seen: set[str] = set()
    uniq: list[Path] = []
    for p in out:
        try:
            k = str(p.resolve())
        except Exception:
            k = str(p)
        if k in seen:
            continue
        seen.add(k)
        uniq.append(p)
    return uniq


def _order_media_candidates(paths: list[Path]) -> list[Path]:
    """Sort candidate files similar to echotrace's variant preference + size heuristic."""
    def _stat(p: Path) -> tuple[int, float]:
        try:
            st = p.stat()
            return int(st.st_size), float(st.st_mtime)
        except Exception:
            return 0, 0.0

    def key(p: Path) -> tuple[int, int, int, float, str]:
        name = str(p.stem or "").lower()
        rank = _variant_rank(name)
        ext = str(p.suffix or "").lower()
        # Prefer already-decoded formats (non-.dat) within the same variant rank.
        ext_penalty = 1 if ext == ".dat" else 0
        size, mtime = _stat(p)
        return (rank, ext_penalty, -size, -mtime, str(p))

    try:
        return sorted(list(paths or []), key=key)
    except Exception:
        return list(paths or [])


def _is_safe_http_url(url: str) -> bool:
    u = str(url or "").strip()
    if not u:
        return False
    try:
        p = urlparse(u)
    except Exception:
        return False
    if p.scheme not in ("http", "https"):
        return False
    host = (p.hostname or "").strip()
    if not host:
        return False
    if host in {"localhost"}:
        return False
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return False
    except Exception:
        pass
    return True


def _download_http_bytes(url: str, *, timeout: int = 20, max_bytes: int = 30 * 1024 * 1024) -> bytes:
    if not _is_safe_http_url(url):
        raise HTTPException(status_code=400, detail="Unsafe URL.")

    try:
        import requests
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"requests not available: {e}")

    try:
        with requests.get(url, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            try:
                cl = int(r.headers.get("content-length") or 0)
                if cl and cl > int(max_bytes):
                    raise HTTPException(status_code=413, detail="Remote file too large.")
            except HTTPException:
                raise
            except Exception:
                pass

            chunks: list[bytes] = []
            total = 0
            for chunk in r.iter_content(chunk_size=256 * 1024):
                if not chunk:
                    continue
                chunks.append(chunk)
                total += len(chunk)
                if total > int(max_bytes):
                    raise HTTPException(status_code=413, detail="Remote file too large.")
            return b"".join(chunks)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Download failed: {e}")


def _decrypt_emoticon_aes_cbc(data: bytes, aes_key_hex: str) -> Optional[bytes]:
    """Decrypt WeChat emoticon payload from kNonStoreEmoticonTable.encrypt_url.

    Observed scheme (WeChat 4.x):
    - key = bytes.fromhex(aes_key_hex)  (16 bytes)
    - iv  = key
    - cipher = AES-128-CBC
    - padding = PKCS7
    """
    if not data:
        return None
    if len(data) % 16 != 0:
        return None

    khex = str(aes_key_hex or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{32}", khex):
        return None

    try:
        key = bytes.fromhex(khex)
        if len(key) != 16:
            return None
    except Exception:
        return None

    try:
        from Crypto.Cipher import AES
        from Crypto.Util import Padding

        pt_padded = AES.new(key, AES.MODE_CBC, iv=key).decrypt(data)
        pt = Padding.unpad(pt_padded, AES.block_size)
        return pt
    except Exception:
        return None


def _normalize_emoticon_md5(value: Any) -> str:
    md5 = str(value or "").strip().lower()
    return md5 if _EMOTICON_MD5_RE.fullmatch(md5) else ""


def _normalize_emoticon_aes_key(value: Any) -> str:
    key = str(value or "").strip().lower()
    return key if _EMOTICON_MD5_RE.fullmatch(key) else ""


def _first_emoticon_match(text: str, patterns: tuple[re.Pattern[str], ...]) -> str:
    if not text:
        return ""
    for pattern in patterns:
        try:
            match = pattern.search(text)
        except Exception:
            match = None
        if match:
            return str(match.group(1) or "").strip()
    return ""


def _extract_emoticon_message_md5(text: str) -> str:
    return _normalize_emoticon_md5(_first_emoticon_match(text, (_EMOTICON_MD5_ATTR_RE, _EMOTICON_MD5_TAG_RE)))


def _extract_emoticon_message_extern_md5(text: str) -> str:
    return _normalize_emoticon_md5(
        _first_emoticon_match(text, (_EMOTICON_EXTERN_MD5_ATTR_RE, _EMOTICON_EXTERN_MD5_TAG_RE))
    )


def _extract_emoticon_message_aes_key(text: str) -> str:
    return _normalize_emoticon_aes_key(_first_emoticon_match(text, (_EMOTICON_AES_KEY_ATTR_RE, _EMOTICON_AES_KEY_TAG_RE)))


def _extract_emoticon_message_urls(text: str) -> list[str]:
    if not text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for match in _EMOTICON_HTTP_URL_RE.finditer(text):
        url = str(match.group(0) or "").strip()
        if not url or url in seen or not _is_safe_http_url(url):
            continue
        seen.add(url)
        out.append(url)
    return out


def _emoticon_message_db_paths(account_dir: Path) -> list[Path]:
    return sorted(
        p
        for p in Path(account_dir).glob("message_*.db")
        if p.is_file() and p.name.lower() != "message_resource.db"
    )


def _emoticon_source_fingerprint(account_dir: Path) -> str:
    parts: list[str] = []
    paths = [Path(account_dir) / "emoticon.db", *_emoticon_message_db_paths(account_dir)]
    for path in paths:
        try:
            st = path.stat()
            parts.append(f"{path.name}:{st.st_size}:{st.st_mtime_ns}")
        except Exception:
            parts.append(f"{path.name}:missing")
    return "|".join(parts)


def _list_emoticon_message_tables(conn: sqlite3.Connection) -> list[str]:
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    except Exception:
        return []
    out: list[str] = []
    for row in rows:
        if not row:
            continue
        raw_name = row[0]
        if isinstance(raw_name, memoryview):
            raw_name = raw_name.tobytes()
        if isinstance(raw_name, (bytes, bytearray)):
            try:
                name = bytes(raw_name).decode("utf-8", errors="ignore")
            except Exception:
                continue
        else:
            name = str(raw_name or "")
        if name.lower().startswith(("msg_", "chat_")):
            out.append(name)
    return out


def _quote_sqlite_ident(name: str) -> str:
    return '"' + str(name or "").replace('"', '""') + '"'


def _iter_emoticon_varints(data: bytes) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    i = 0
    n = len(data)
    while i < n:
        key = int(data[i])
        i += 1
        field = key >> 3
        wire_type = key & 0x07
        if field <= 0:
            break

        if wire_type == 0:
            shift = 0
            value = 0
            while i < n:
                b = int(data[i])
                i += 1
                value |= (b & 0x7F) << shift
                if b < 0x80:
                    break
                shift += 7
            out.append((field, int(value)))
            continue

        if wire_type == 1:
            i += 8
            continue

        if wire_type == 2:
            shift = 0
            ln = 0
            while i < n:
                b = int(data[i])
                i += 1
                ln |= (b & 0x7F) << shift
                if b < 0x80:
                    break
                shift += 7
            i += int(ln)
            continue

        if wire_type == 5:
            i += 4
            continue

        break
    return out


def _extract_emoticon_builtin_expr_id(packed_info_data: Any) -> Optional[int]:
    data: bytes = b""
    if packed_info_data is None:
        return None
    if isinstance(packed_info_data, memoryview):
        data = packed_info_data.tobytes()
    elif isinstance(packed_info_data, (bytes, bytearray)):
        data = bytes(packed_info_data)
    elif isinstance(packed_info_data, str):
        s = packed_info_data.strip()
        if s:
            try:
                data = bytes.fromhex(s) if (len(s) % 2 == 0 and re.fullmatch(r"(?i)[0-9a-f]+", s)) else s.encode(
                    "utf-8",
                    errors="ignore",
                )
            except Exception:
                data = b""
    if not data:
        return None

    for field, value in _iter_emoticon_varints(data):
        if field == 2:
            return int(value)
    return None


@lru_cache(maxsize=2048)
def _lookup_emoticon_info(account_dir_str: str, md5: str) -> dict[str, str]:
    account_dir = Path(account_dir_str)
    md5s = str(md5 or "").strip().lower()
    if not md5s:
        return {}

    db_path = account_dir / "emoticon.db"
    if not db_path.exists():
        return {}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT md5, extern_md5, aes_key, cdn_url, encrypt_url, extern_url, thumb_url, tp_url "
            "FROM kNonStoreEmoticonTable "
            "WHERE lower(md5) = lower(?) OR lower(extern_md5) = lower(?) "
            "LIMIT 1",
            (md5s, md5s),
        ).fetchone()
        if not row:
            return {}
        return {k: str(row[k] or "") for k in row.keys()}
    except Exception:
        return {}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _merge_emoticon_candidate(
    catalog: dict[str, dict[str, Any]],
    md5: str,
    *,
    urls: Optional[list[str]] = None,
    aes_key: str = "",
    source: str = "",
) -> None:
    md5s = _normalize_emoticon_md5(md5)
    if not md5s:
        return

    entry = catalog.get(md5s)
    if entry is None:
        entry = {"md5": md5s, "urls": [], "aes_keys": [], "sources": []}
        catalog[md5s] = entry

    if source and source not in entry["sources"]:
        entry["sources"].append(source)

    key = _normalize_emoticon_aes_key(aes_key)
    if key and key not in entry["aes_keys"]:
        entry["aes_keys"].append(key)

    seen = set(entry["urls"])
    for url in urls or []:
        u = str(url or "").strip()
        if not u or u in seen or not _is_safe_http_url(u):
            continue
        seen.add(u)
        entry["urls"].append(u)


def _emoticon_catalog_public_stats(
    stats: dict[str, Any],
    catalog: dict[str, dict[str, Any]],
    *,
    elapsed_ms: float,
) -> dict[str, Any]:
    source_counts: dict[str, int] = {}
    with_urls = 0
    for entry in catalog.values():
        if entry.get("urls"):
            with_urls += 1
        for source in entry.get("sources") or []:
            source_counts[source] = source_counts.get(source, 0) + 1

    return {
        "emoticon_db_rows": int(stats.get("emoticon_db_rows") or 0),
        "emoticon_db_md5": int(stats.get("emoticon_db_md5") or 0),
        "emoticon_db_extern_md5": int(stats.get("emoticon_db_extern_md5") or 0),
        "emoticon_db_with_remote": int(stats.get("emoticon_db_with_remote") or 0),
        "message_db_count": int(stats.get("message_db_count") or 0),
        "message_table_count": int(stats.get("message_table_count") or 0),
        "message_xml_rows": int(stats.get("message_xml_rows") or 0),
        "message_xml_md5": int(stats.get("message_xml_md5") or 0),
        "message_xml_md5_with_url": int(stats.get("message_xml_md5_with_url") or 0),
        "message_xml_extern_md5": int(stats.get("message_xml_extern_md5") or 0),
        "message_builtin_expr_ids": int(stats.get("message_builtin_expr_ids") or 0),
        "message_builtin_expr_rows": int(stats.get("message_builtin_expr_rows") or 0),
        "total_candidates": len(catalog),
        "total_candidates_with_url": with_urls,
        "source_counts": source_counts,
        "elapsed_ms": round(float(elapsed_ms), 1),
    }


@lru_cache(maxsize=8)
def _collect_emoticon_download_catalog_cached(
    account_dir_str: str,
    fingerprint: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    started_at = datetime.datetime.now().timestamp()
    account_dir = Path(account_dir_str)
    catalog: dict[str, dict[str, Any]] = {}
    stats: dict[str, Any] = {}
    emoticon_primary: set[str] = set()
    emoticon_extern: set[str] = set()
    emoticon_with_remote: set[str] = set()
    message_md5: set[str] = set()
    message_md5_with_url: set[str] = set()
    message_extern_md5: set[str] = set()
    builtin_expr_ids: set[int] = set()
    builtin_expr_rows = 0
    message_rows = 0
    message_table_count = 0

    db_path = account_dir / "emoticon.db"
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
        except Exception as exc:
            conn = None
            logger.warning("[media] emoticon_catalog emoticon_db_open_failed: account=%s error=%s", account_dir.name, exc)
        if conn is None:
            rows = []
        else:
            rows = None
        if conn is not None:
            conn.row_factory = sqlite3.Row
        if conn is not None:
            try:
                rows = conn.execute(
                    "SELECT md5, extern_md5, aes_key, cdn_url, encrypt_url, extern_url, thumb_url, tp_url "
                    "FROM kNonStoreEmoticonTable ORDER BY rowid DESC"
                ).fetchall()
            except Exception as exc:
                logger.warning(
                    "[media] emoticon_catalog emoticon_db_scan_failed: account=%s error=%s",
                    account_dir.name,
                    exc,
                )
                rows = []
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        stats["emoticon_db_rows"] = len(rows or [])
        for row in rows or []:
            urls = [
                str(row[key] or "").strip()
                for key in ("cdn_url", "extern_url", "thumb_url", "tp_url", "encrypt_url")
                if str(row[key] or "").strip() and _is_safe_http_url(str(row[key] or "").strip())
            ]
            aes_key = str(row["aes_key"] or "").strip()
            md5s = _normalize_emoticon_md5(row["md5"])
            extern_md5 = _normalize_emoticon_md5(row["extern_md5"])
            if md5s:
                emoticon_primary.add(md5s)
                if urls:
                    emoticon_with_remote.add(md5s)
                    _merge_emoticon_candidate(catalog, md5s, urls=urls, aes_key=aes_key, source="emoticon_db_md5")
            if extern_md5:
                emoticon_extern.add(extern_md5)
                if urls:
                    emoticon_with_remote.add(extern_md5)
                    _merge_emoticon_candidate(
                        catalog,
                        extern_md5,
                        urls=urls,
                        aes_key=aes_key,
                        source="emoticon_db_extern_md5",
                    )

    message_db_paths = _emoticon_message_db_paths(account_dir)
    for message_db_path in message_db_paths:
        try:
            conn = sqlite3.connect(str(message_db_path))
        except Exception as exc:
            logger.warning(
                "[media] emoticon_catalog message_db_open_failed: account=%s db=%s error=%s",
                account_dir.name,
                message_db_path.name,
                exc,
            )
            continue
        conn.row_factory = sqlite3.Row
        try:
            for table_name in _list_emoticon_message_tables(conn):
                message_table_count += 1
                quoted = _quote_sqlite_ident(table_name)
                try:
                    rows = conn.execute(
                        f"SELECT compress_content, message_content, packed_info_data FROM {quoted} WHERE local_type = 47"
                    )
                except Exception:
                    continue

                for row in rows:
                    message_rows += 1
                    try:
                        builtin_id = _extract_emoticon_builtin_expr_id(row["packed_info_data"])
                    except Exception:
                        builtin_id = None
                    if builtin_id is not None:
                        builtin_expr_rows += 1
                        builtin_expr_ids.add(int(builtin_id))

                    try:
                        raw_text = _decode_message_content(row["compress_content"], row["message_content"])
                    except Exception:
                        raw_text = ""
                    md5s = _extract_emoticon_message_md5(raw_text)
                    if not md5s:
                        continue
                    message_md5.add(md5s)

                    extern_md5 = _extract_emoticon_message_extern_md5(raw_text)
                    if extern_md5:
                        message_extern_md5.add(extern_md5)

                    if md5s in message_md5_with_url:
                        continue

                    urls = _extract_emoticon_message_urls(raw_text)
                    if not urls:
                        continue
                    message_md5_with_url.add(md5s)
                    _merge_emoticon_candidate(
                        catalog,
                        md5s,
                        urls=urls,
                        aes_key=_extract_emoticon_message_aes_key(raw_text),
                        source="message_xml",
                    )
        except Exception as exc:
            logger.warning(
                "[media] emoticon_catalog message_db_scan_failed: account=%s db=%s error=%s",
                account_dir.name,
                message_db_path.name,
                exc,
            )
        finally:
            try:
                conn.close()
            except Exception:
                pass

    stats.update(
        {
            "fingerprint": fingerprint,
            "emoticon_db_md5": len(emoticon_primary),
            "emoticon_db_extern_md5": len(emoticon_extern),
            "emoticon_db_with_remote": len(emoticon_with_remote),
            "message_db_count": len(message_db_paths),
            "message_table_count": message_table_count,
            "message_xml_rows": message_rows,
            "message_xml_md5": len(message_md5),
            "message_xml_md5_with_url": len(message_md5_with_url),
            "message_xml_extern_md5": len(message_extern_md5),
            "message_builtin_expr_ids": len(builtin_expr_ids),
            "message_builtin_expr_rows": builtin_expr_rows,
        }
    )
    elapsed_ms = (datetime.datetime.now().timestamp() - started_at) * 1000.0
    public_stats = _emoticon_catalog_public_stats(stats, catalog, elapsed_ms=elapsed_ms)
    logger.info(
        "[media] emoticon_catalog scan_done: account=%s total_candidates=%s source_counts=%s "
        "emoticon_db_rows=%s emoticon_db_md5=%s emoticon_db_extern_md5=%s message_rows=%s "
        "message_md5=%s message_md5_with_url=%s message_extern_md5=%s builtin_expr_ids=%s elapsed_ms=%s",
        account_dir.name,
        public_stats["total_candidates"],
        public_stats["source_counts"],
        public_stats["emoticon_db_rows"],
        public_stats["emoticon_db_md5"],
        public_stats["emoticon_db_extern_md5"],
        public_stats["message_xml_rows"],
        public_stats["message_xml_md5"],
        public_stats["message_xml_md5_with_url"],
        public_stats["message_xml_extern_md5"],
        public_stats["message_builtin_expr_ids"],
        public_stats["elapsed_ms"],
    )
    return catalog, public_stats


def _collect_emoticon_download_catalog(account_dir: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    fingerprint = _emoticon_source_fingerprint(Path(account_dir))
    return _collect_emoticon_download_catalog_cached(str(Path(account_dir)), fingerprint)


def _collect_emoticon_download_candidates(account_dir: Path) -> list[str]:
    catalog, _stats = _collect_emoticon_download_catalog(Path(account_dir))
    return list(catalog.keys())


def _find_emoticon_message_remote_source(account_dir: Path, md5: str) -> dict[str, Any]:
    md5s = _normalize_emoticon_md5(md5)
    if not md5s:
        return {}

    for message_db_path in _emoticon_message_db_paths(Path(account_dir)):
        try:
            conn = sqlite3.connect(str(message_db_path))
        except Exception:
            continue
        conn.row_factory = sqlite3.Row
        try:
            for table_name in _list_emoticon_message_tables(conn):
                quoted = _quote_sqlite_ident(table_name)
                try:
                    rows = conn.execute(
                        f"SELECT compress_content, message_content FROM {quoted} WHERE local_type = 47"
                    )
                except Exception:
                    continue

                for row in rows:
                    try:
                        raw_text = _decode_message_content(row["compress_content"], row["message_content"])
                    except Exception:
                        raw_text = ""
                    if _extract_emoticon_message_md5(raw_text) != md5s:
                        continue
                    urls = _extract_emoticon_message_urls(raw_text)
                    if not urls:
                        continue
                    aes_key = _extract_emoticon_message_aes_key(raw_text)
                    out = {"md5": md5s, "urls": urls, "aes_keys": [], "sources": ["message_xml"]}
                    if aes_key:
                        out["aes_keys"].append(aes_key)
                    return out
        except Exception:
            continue
        finally:
            try:
                conn.close()
            except Exception:
                pass
    return {}


def _try_fetch_emoticon_from_sources(urls: list[str], aes_keys: list[str]) -> tuple[Optional[bytes], Optional[str]]:
    for url in urls:
        try:
            payload = _download_http_bytes(url)
        except Exception:
            continue

        candidates: list[bytes] = [payload]
        for aes_key_hex in aes_keys:
            dec = _decrypt_emoticon_aes_cbc(payload, aes_key_hex)
            if dec is not None:
                candidates.insert(0, dec)

        for data in candidates:
            if not data:
                continue
            try:
                data2, mt = _try_strip_media_prefix(data)
            except Exception:
                data2, mt = data, "application/octet-stream"

            if mt == "application/octet-stream":
                mt = _detect_image_media_type(data2[:32])
            if mt == "application/octet-stream":
                try:
                    if len(data2) >= 8 and data2[4:8] == b"ftyp":
                        mt = "video/mp4"
                except Exception:
                    pass

            if mt.startswith("image/") and (not _is_probably_valid_image(data2, mt)):
                continue
            if mt != "application/octet-stream":
                return data2, mt

    return None, None


def _try_fetch_emoticon_from_remote(
    account_dir: Path,
    md5: str,
    source: Optional[dict[str, Any]] = None,
) -> tuple[Optional[bytes], Optional[str]]:
    md5s = _normalize_emoticon_md5(md5)
    if not md5s:
        return None, None

    urls: list[str] = []
    aes_keys: list[str] = []

    if source:
        for u in source.get("urls") or []:
            u = str(u or "").strip()
            if u and u not in urls and _is_safe_http_url(u):
                urls.append(u)
        for key in source.get("aes_keys") or []:
            key = _normalize_emoticon_aes_key(key)
            if key and key not in aes_keys:
                aes_keys.append(key)
    else:
        info = _lookup_emoticon_info(str(account_dir), md5s)
        if info:
            for key in ("cdn_url", "extern_url", "thumb_url", "tp_url", "encrypt_url"):
                u = str(info.get(key) or "").strip()
                if u and u not in urls and _is_safe_http_url(u):
                    urls.append(u)
            aes_key = _normalize_emoticon_aes_key(info.get("aes_key"))
            if aes_key:
                aes_keys.append(aes_key)

    data, media_type = _try_fetch_emoticon_from_sources(urls, aes_keys)
    if data is not None and media_type:
        return data, media_type

    if source:
        return None, None

    message_source = _find_emoticon_message_remote_source(Path(account_dir), md5s)
    if not message_source:
        return None, None

    message_urls = [str(u or "").strip() for u in message_source.get("urls") or []]
    message_aes_keys = [
        _normalize_emoticon_aes_key(key) for key in (message_source.get("aes_keys") or []) if key
    ]
    return _try_fetch_emoticon_from_sources(
        [u for u in message_urls if u and _is_safe_http_url(u)],
        [k for k in message_aes_keys if k],
    )


class _WxAMConfig(ctypes.Structure):
    _fields_ = [
        ("mode", ctypes.c_int),
        ("reserved", ctypes.c_int),
    ]


@lru_cache(maxsize=1)
def _get_wxam_decoder():
    if os.name != "nt":
        return None
    dll_path = _PACKAGE_ROOT / "native" / "VoipEngine.dll"
    if not dll_path.exists():
        logger.warning(f"WxAM decoder DLL not found: {dll_path}")
        return None
    try:
        voip_engine = ctypes.WinDLL(str(dll_path))
        fn = voip_engine.wxam_dec_wxam2pic_5
        fn.argtypes = [
            ctypes.c_int64,
            ctypes.c_int,
            ctypes.c_int64,
            ctypes.POINTER(ctypes.c_int),
            ctypes.c_int64,
        ]
        fn.restype = ctypes.c_int64
        logger.info(f"WxAM decoder loaded: {dll_path}")
        return fn
    except Exception as e:
        logger.warning(f"Failed to load WxAM decoder DLL: {dll_path} ({e})")
        return None


def _wxgf_to_image_bytes(data: bytes) -> Optional[bytes]:
    if not data or not data.startswith(b"wxgf"):
        return None
    fn = _get_wxam_decoder()
    if fn is None:
        return None

    max_output_size = 52 * 1024 * 1024
    for mode in (0, 3):
        try:
            config = _WxAMConfig()
            config.mode = int(mode)
            config.reserved = 0

            input_buffer = ctypes.create_string_buffer(data, len(data))
            output_buffer = ctypes.create_string_buffer(max_output_size)
            output_size = ctypes.c_int(max_output_size)

            result = fn(
                ctypes.addressof(input_buffer),
                int(len(data)),
                ctypes.addressof(output_buffer),
                ctypes.byref(output_size),
                ctypes.addressof(config),
            )
            if result != 0 or output_size.value <= 0:
                continue
            out = output_buffer.raw[: int(output_size.value)]
            if _detect_image_media_type(out[:32]) != "application/octet-stream":
                return out
        except Exception:
            continue
    return None


def _try_strip_media_prefix(data: bytes) -> tuple[bytes, str]:
    if not data:
        return data, "application/octet-stream"

    try:
        head = data[: min(len(data), 256 * 1024)]
    except Exception:
        head = data

    # wxgf container
    try:
        idx = head.find(b"wxgf")
    except Exception:
        idx = -1
    if idx >= 0 and idx <= 128 * 1024:
        try:
            payload = data[idx:]
            converted = _wxgf_to_image_bytes(payload)
            if converted:
                mtw = _detect_image_media_type(converted[:32])
                if mtw != "application/octet-stream":
                    return converted, mtw
        except Exception:
            pass

    # common image/video headers with small prefix
    sigs: list[tuple[bytes, str]] = [
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"GIF87a", "image/gif"),
        (b"GIF89a", "image/gif"),
    ]
    for sig, mt in sigs:
        try:
            j = head.find(sig)
        except Exception:
            j = -1
        if j >= 0 and j <= 128 * 1024:
            sliced = data[j:]
            mt2 = _detect_image_media_type(sliced[:32])
            if mt2 != "application/octet-stream" and _is_probably_valid_image(sliced, mt2):
                return sliced, mt2

    try:
        j = head.find(b"RIFF")
    except Exception:
        j = -1
    if j >= 0 and j <= 128 * 1024:
        sliced = data[j:]
        try:
            if len(sliced) >= 12 and sliced[8:12] == b"WEBP":
                return sliced, "image/webp"
        except Exception:
            pass

    try:
        j = head.find(b"ftyp")
    except Exception:
        j = -1
    if j >= 4 and j <= 128 * 1024:
        sliced = data[j - 4 :]
        try:
            if len(sliced) >= 8 and sliced[4:8] == b"ftyp":
                return sliced, "video/mp4"
        except Exception:
            pass

    return data, "application/octet-stream"


def _load_account_source_info(account_dir: Path) -> dict[str, Any]:
    p = account_dir / "_source.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _guess_wxid_dir_from_common_paths(account_name: str) -> Optional[Path]:
    try:
        home = Path.home()
    except Exception:
        return None

    roots = [
        home / "Documents" / "xwechat_files",
        home / "Documents" / "WeChat Files",
    ]

    # Exact match first
    for root in roots:
        c = root / account_name
        try:
            if c.exists() and c.is_dir():
                return c
        except Exception:
            continue

    # Then try prefix match: wxid_xxx_yyyy
    for root in roots:
        try:
            if not root.exists() or not root.is_dir():
                continue
            for p in root.iterdir():
                if not p.is_dir():
                    continue
                if p.name.startswith(account_name + "_"):
                    return p
        except Exception:
            continue
    return None


def _resolve_account_wxid_dir(account_dir: Path) -> Optional[Path]:
    info = _load_account_source_info(account_dir)
    wxid_dir = str(info.get("wxid_dir") or "").strip()
    if wxid_dir:
        try:
            p = Path(wxid_dir)
            if p.exists() and p.is_dir():
                return p
        except Exception:
            pass
    return _guess_wxid_dir_from_common_paths(account_dir.name)


def _resolve_account_db_storage_dir(account_dir: Path) -> Optional[Path]:
    info = _load_account_source_info(account_dir)
    db_storage_path = str(info.get("db_storage_path") or "").strip()
    if db_storage_path:
        try:
            p = Path(db_storage_path)
            if p.exists() and p.is_dir():
                return p
        except Exception:
            pass

    wxid_dir = _resolve_account_wxid_dir(account_dir)
    if wxid_dir:
        c = wxid_dir / "db_storage"
        try:
            if c.exists() and c.is_dir():
                return c
        except Exception:
            pass
    return None


def _quote_ident(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def _resolve_hardlink_table_name(conn: sqlite3.Connection, prefix: str) -> Optional[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ? ORDER BY name DESC",
        (f"{prefix}%",),
    ).fetchall()
    if not rows:
        return None
    return str(rows[0][0]) if rows[0] and rows[0][0] else None


def _resolve_hardlink_dir2id_table_name(conn: sqlite3.Connection) -> Optional[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'dir2id%' ORDER BY name DESC"
    ).fetchall()
    if not rows:
        return None
    return str(rows[0][0]) if rows[0] and rows[0][0] else None


@dataclass(slots=True)
class _HardlinkEntry:
    file_name: str
    file_size: int
    modify_time: int
    dir1: int
    dir2: int
    dir_name: str


def _iter_files_under(root: Path):
    try:
        root_str = str(root)
    except Exception:
        return

    for current_root, _dirnames, filenames in os.walk(root_str):
        for filename in filenames:
            try:
                yield Path(current_root) / filename
            except Exception:
                continue


def _iter_media_lookup_keys(name: str) -> list[str]:
    lower_name = str(name or "").strip().lower()
    if not lower_name:
        return []

    stem = Path(lower_name).stem
    keys: list[str] = []
    for value in (lower_name, stem):
        if value and value not in keys:
            keys.append(value)

    stripped = _MEDIA_INDEX_STRIP_SUFFIX_RE.sub("", stem)
    if stripped and stripped not in keys:
        keys.append(stripped)

    return keys


def _iter_md5_candidates_from_name(name: str) -> list[str]:
    candidates: list[str] = []
    for key in _iter_media_lookup_keys(name):
        if _EMOTICON_MD5_RE.fullmatch(key) and key not in candidates:
            candidates.append(key)
    return candidates


def _build_hardlink_dir2id_map(conn: sqlite3.Connection) -> dict[int, str]:
    table_name = _resolve_hardlink_dir2id_table_name(conn)
    if not table_name:
        return {}

    quoted = _quote_ident(table_name)
    mapping: dict[int, str] = {}
    try:
        rows = conn.execute(f"SELECT rowid, username FROM {quoted}").fetchall()
    except Exception:
        return {}

    for rowid, username in rows:
        try:
            rid = int(rowid)
        except Exception:
            continue
        text = str(username or "").strip()
        if text:
            mapping[rid] = text
    return mapping


def _resolve_hardlink_entry_path(
    *,
    kind: str,
    entry: _HardlinkEntry,
    wxid_dir: Path,
    username: Optional[str],
    extra_roots: Optional[list[Path]] = None,
) -> Optional[Path]:
    kind_key = str(kind or "").lower().strip()
    file_name = str(entry.file_name or "").strip()
    if not file_name:
        return None

    roots: list[Path] = []
    for root in [wxid_dir] + list(extra_roots or []):
        if not root:
            continue
        try:
            resolved = root.resolve()
        except Exception:
            resolved = root
        if resolved not in roots:
            roots.append(resolved)

    if not roots:
        return None

    if kind_key in {"video", "video_thumb"}:
        guessed_month: Optional[str] = None
        if entry.modify_time and entry.modify_time > 0:
            try:
                dt = datetime.datetime.fromtimestamp(int(entry.modify_time))
                guessed_month = f"{dt.year:04d}-{dt.month:02d}"
            except Exception:
                guessed_month = None

        if re.fullmatch(r"\d{4}-\d{2}", str(entry.dir_name or "").strip()):
            guessed_month = str(entry.dir_name or "").strip()

        stem = Path(file_name).stem
        if kind_key == "video":
            file_variants = [file_name]
        else:
            file_variants = [
                f"{stem}_thumb.jpg",
                f"{stem}_thumb.jpeg",
                f"{stem}_thumb.png",
                f"{stem}_thumb.webp",
                f"{stem}.jpg",
                f"{stem}.jpeg",
                f"{stem}.png",
                f"{stem}.gif",
                f"{stem}.webp",
                f"{stem}.dat",
                file_name,
            ]

        def _iter_video_base_dirs(root: Path) -> list[Path]:
            bases: list[Path] = []
            candidates = [
                root / "msg" / "video",
                root / "video",
                root if str(root.name).lower() == "video" else None,
            ]
            for candidate in candidates:
                if not candidate:
                    continue
                try:
                    if candidate.exists() and candidate.is_dir():
                        bases.append(candidate)
                except Exception:
                    continue

            seen: set[str] = set()
            uniq: list[Path] = []
            for base in bases:
                try:
                    token = str(base.resolve())
                except Exception:
                    token = str(base)
                if token in seen:
                    continue
                seen.add(token)
                uniq.append(base)
            return uniq

        for root in roots:
            for base_dir in _iter_video_base_dirs(root):
                dirs_to_check: list[Path] = []
                if guessed_month:
                    dirs_to_check.append(base_dir / guessed_month)
                dirs_to_check.append(base_dir)
                for directory in dirs_to_check:
                    try:
                        if not directory.exists() or not directory.is_dir():
                            continue
                    except Exception:
                        continue
                    for variant in file_variants:
                        path = directory / variant
                        try:
                            if path.exists() and path.is_file():
                                return path
                        except Exception:
                            continue
        return None

    if kind_key == "file":
        file_size = int(entry.file_size) if int(entry.file_size or 0) > 0 else None
        guessed_month: Optional[str] = None
        if entry.modify_time and entry.modify_time > 0:
            try:
                dt = datetime.datetime.fromtimestamp(int(entry.modify_time))
                guessed_month = f"{dt.year:04d}-{dt.month:02d}"
            except Exception:
                guessed_month = None

        file_base_dirs: list[Path] = []
        for root in roots:
            candidates = [
                root / "msg" / "file",
                root / "file" if root.name.lower() == "msg" else None,
                root if root.name.lower() == "file" else None,
            ]
            for candidate in candidates:
                if not candidate:
                    continue
                try:
                    if candidate.exists() and candidate.is_dir() and candidate not in file_base_dirs:
                        file_base_dirs.append(candidate)
                except Exception:
                    continue

        if not file_base_dirs:
            return None

        file_stem = Path(file_name).stem

        def _iter_month_dirs(base: Path) -> list[Path]:
            result: list[Path] = []
            try:
                for child in base.iterdir():
                    try:
                        if not child.is_dir():
                            continue
                    except Exception:
                        continue
                    name = str(child.name)
                    if re.fullmatch(r"\d{4}-\d{2}", name):
                        result.append(child)
            except Exception:
                return []
            return sorted(result, key=lambda item: str(item.name))

        def _pick_best_hit(hits: list[Path]) -> Optional[Path]:
            if not hits:
                return None
            if file_size is not None and file_size >= 0:
                for hit in hits:
                    try:
                        if hit.stat().st_size == file_size:
                            return hit
                    except Exception:
                        continue
            return hits[0]

        for base in file_base_dirs:
            month_dirs = _iter_month_dirs(base)
            month_names: list[str] = []
            if guessed_month:
                month_names.append(guessed_month)
            for directory in month_dirs:
                name = str(directory.name)
                if name not in month_names:
                    month_names.append(name)

            for month_name in month_names:
                month_dir = base / month_name
                try:
                    if not (month_dir.exists() and month_dir.is_dir()):
                        continue
                except Exception:
                    continue

                direct = month_dir / file_name
                try:
                    if direct.exists() and direct.is_file():
                        return direct
                except Exception:
                    pass

                in_stem_dir = month_dir / file_stem / file_name
                try:
                    if in_stem_dir.exists() and in_stem_dir.is_file():
                        return in_stem_dir
                except Exception:
                    pass
        return None

    dir_name = str(entry.dir_name or "").strip()
    file_stem = Path(file_name).stem
    file_variants = [file_name, f"{file_stem}_h.dat", f"{file_stem}_t.dat"]

    for root in roots:
        if entry.dir1 and dir_name:
            for variant in file_variants:
                direct = (root / str(entry.dir1) / dir_name / variant).resolve()
                try:
                    if direct.exists() and direct.is_file():
                        return direct
                except Exception:
                    continue

        if username:
            chat_hash = hashlib.md5(str(username).encode()).hexdigest()
            for variant in file_variants:
                attach = (root / "msg" / "attach" / chat_hash / dir_name / "Img" / variant).resolve()
                try:
                    if attach.exists() and attach.is_file():
                        return attach
                except Exception:
                    continue
    return None


class MediaPathIndex:
    def __init__(
        self,
        *,
        account_dir: Path,
        usernames: Optional[Iterable[str]] = None,
        media_kinds: Optional[Iterable[str]] = None,
    ) -> None:
        self.account_dir = account_dir
        self.usernames = list(dict.fromkeys([str(item or "").strip() for item in (usernames or []) if str(item or "").strip()]))
        self.media_kinds = {
            str(kind or "").strip()
            for kind in (media_kinds or [])
            if str(kind or "").strip() in {"image", "emoji", "video", "video_thumb", "file"}
        }
        self.wxid_dir = _resolve_account_wxid_dir(account_dir)
        self.db_storage_dir = _resolve_account_db_storage_dir(account_dir)
        self.resource_dir = _get_resource_dir(account_dir)
        scope_text = "\n".join(sorted(self.usernames)) or "__all__"
        self._scope_key = hashlib.sha1(scope_text.encode("utf-8", errors="ignore")).hexdigest()
        self._cache_db_path = self.account_dir / "media_path_index.db"
        self._loaded_from_cache = False

        self._roots: list[Path] = []
        for root in [self.wxid_dir, self.db_storage_dir]:
            if not root:
                continue
            try:
                resolved = root.resolve()
            except Exception:
                resolved = root
            if resolved not in self._roots:
                self._roots.append(resolved)

        self._md5_hits: dict[str, dict[str, Path]] = {
            "image": {},
            "emoji": {},
            "video": {},
            "video_thumb": {},
            "file": {},
        }
        self._file_id_hits: dict[str, dict[str, Path]] = {
            "image": {},
            "emoji": {},
            "video": {},
            "video_thumb": {},
            "file": {},
        }
        self._user_file_id_hits: dict[str, dict[tuple[str, str], Path]] = {
            "image": {},
            "emoji": {},
            "video": {},
            "video_thumb": {},
            "file": {},
        }
        self._hardlink_hits: dict[str, dict[str, _HardlinkEntry]] = {
            "image": {},
            "emoji": {},
            "video": {},
            "video_thumb": {},
            "file": {},
        }
        self._query_cache: dict[tuple[str, str, str, str], Optional[Path]] = {}
        self._negative_cache: set[tuple[str, str, str, str]] = set()
        self._known_missing: set[tuple[str, str, str, str]] = set()
        self.stats = {
            "resourceFiles": 0,
            "hardlinkRows": 0,
            "scannedFiles": 0,
            "md5Keys": 0,
            "fileIdKeys": 0,
            "loadedEntries": 0,
            "loadedMisses": 0,
        }

    @classmethod
    def build(
        cls,
        *,
        account_dir: Path,
        usernames: Optional[Iterable[str]] = None,
        media_kinds: Optional[Iterable[str]] = None,
    ) -> "MediaPathIndex":
        index = cls(account_dir=account_dir, usernames=usernames, media_kinds=media_kinds)
        index._build()
        return index

    def _wants(self, kind: str) -> bool:
        if not self.media_kinds:
            return True
        return str(kind or "").strip() in self.media_kinds

    def _put_md5(self, kind: str, md5: str, path: Path) -> None:
        bucket = self._md5_hits.setdefault(kind, {})
        if md5 and md5 not in bucket:
            bucket[md5] = path
            self.stats["md5Keys"] += 1

    def _put_file_id(self, kind: str, key: str, path: Path, username: str = "") -> None:
        if not key:
            return
        bucket = self._file_id_hits.setdefault(kind, {})
        if key not in bucket:
            bucket[key] = path
            self.stats["fileIdKeys"] += 1
        user_key = str(username or "").strip()
        if user_key:
            ub = self._user_file_id_hits.setdefault(kind, {})
            ub.setdefault((user_key, key), path)

    def _register_kind_path(self, kind: str, path: Path, *, username: str = "") -> None:
        name = str(path.name or "").strip()
        if not name:
            return
        for md5 in _iter_md5_candidates_from_name(name):
            self._put_md5(kind, md5, path)
        for key in _iter_media_lookup_keys(name):
            self._put_file_id(kind, key, path, username=username)

    def _normalize_cache_key(
        self,
        *,
        kind: str,
        md5: str = "",
        file_id: str = "",
        username: str = "",
    ) -> tuple[str, str, str, str]:
        return (
            str(kind or "").strip().lower(),
            str(md5 or "").strip().lower(),
            str(file_id or "").strip().lower(),
            str(username or "").strip(),
        )

    def is_known_missing(
        self,
        *,
        kind: str,
        md5: str = "",
        file_id: str = "",
        username: str = "",
    ) -> bool:
        cache_key = self._normalize_cache_key(kind=kind, md5=md5, file_id=file_id, username=username)
        return cache_key in self._known_missing

    def _drop_cached_miss_for_path(self, *, kind: str, path: Path, username: str = "") -> list[tuple[str, str, str, str]]:
        kind_key = str(kind or "").strip().lower()
        username_key = str(username or "").strip()
        md5_values = set(_iter_md5_candidates_from_name(path.name))
        file_keys = set(_iter_media_lookup_keys(path.name))
        if not kind_key or (not md5_values and not file_keys):
            return []

        stale_keys = [
            cache_key
            for cache_key in self._known_missing
            if cache_key[0] == kind_key
            and cache_key[3] == username_key
            and ((cache_key[1] and cache_key[1] in md5_values) or (cache_key[2] and cache_key[2] in file_keys))
        ]
        for cache_key in stale_keys:
            self._known_missing.discard(cache_key)
            self._negative_cache.discard(cache_key)
            self._query_cache.pop(cache_key, None)
        return stale_keys

    def _persist_entry_rows(self, rows: list[tuple[str, str, str, str, str, str]]) -> None:
        if not rows:
            return
        try:
            conn = sqlite3.connect(str(self._cache_db_path))
        except Exception:
            return

        try:
            self._ensure_cache_schema(conn)
            with conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO media_index_entries(scope, kind, key_type, key, username, path) VALUES (?, ?, ?, ?, ?, ?)",
                    rows,
                )
        except Exception:
            logger.exception("[media-index] persist entry rows failed account=%s", str(self.account_dir.name or ""))
        finally:
            conn.close()

    def _persist_missing_rows(self, rows: list[tuple[str, str, str, str, str]]) -> None:
        if not rows:
            return
        try:
            conn = sqlite3.connect(str(self._cache_db_path))
        except Exception:
            return

        try:
            self._ensure_cache_schema(conn)
            with conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO media_index_misses(scope, kind, md5, file_id, username) VALUES (?, ?, ?, ?, ?)",
                    rows,
                )
        except Exception:
            logger.exception("[media-index] persist miss rows failed account=%s", str(self.account_dir.name or ""))
        finally:
            conn.close()

    def _delete_missing_rows(self, rows: list[tuple[str, str, str, str, str]]) -> None:
        if not rows:
            return
        try:
            conn = sqlite3.connect(str(self._cache_db_path))
        except Exception:
            return

        try:
            self._ensure_cache_schema(conn)
            with conn:
                conn.executemany(
                    "DELETE FROM media_index_misses WHERE scope = ? AND kind = ? AND md5 = ? AND file_id = ? AND username = ?",
                    rows,
                )
        except Exception:
            logger.exception("[media-index] delete miss rows failed account=%s", str(self.account_dir.name or ""))
        finally:
            conn.close()

    def remember_path(self, *, kind: str, path: Path, username: str = "") -> None:
        kind_key = str(kind or "").strip().lower()
        username_key = str(username or "").strip()
        if not kind_key:
            return
        try:
            path_obj = path if isinstance(path, Path) else Path(path)
        except Exception:
            return
        name = str(path_obj.name or "").strip()
        if not name:
            return

        self._register_kind_path(kind_key, path_obj, username=username_key)
        stale_keys = self._drop_cached_miss_for_path(kind=kind_key, path=path_obj, username=username_key)

        rows: list[tuple[str, str, str, str, str, str]] = []
        for md5 in _iter_md5_candidates_from_name(name):
            rows.append((self._scope_key, kind_key, "md5", md5, "", str(path_obj)))
        for key in _iter_media_lookup_keys(name):
            rows.append((self._scope_key, kind_key, "file_id", key, "", str(path_obj)))
            if username_key:
                rows.append((self._scope_key, kind_key, "file_id", key, username_key, str(path_obj)))
        self._persist_entry_rows(rows)
        self._delete_missing_rows(
            [
                (self._scope_key, stale_kind, stale_md5, stale_file_id, stale_username)
                for stale_kind, stale_md5, stale_file_id, stale_username in stale_keys
            ]
        )

    def mark_missing(
        self,
        *,
        kind: str,
        md5: str = "",
        file_id: str = "",
        username: str = "",
    ) -> None:
        cache_key = self._normalize_cache_key(kind=kind, md5=md5, file_id=file_id, username=username)
        if not cache_key[0] or (not cache_key[1] and not cache_key[2]):
            return
        if cache_key in self._known_missing:
            return
        self._known_missing.add(cache_key)
        self._negative_cache.add(cache_key)
        self._query_cache[cache_key] = None
        self._persist_missing_rows(
            [
                (
                    self._scope_key,
                    cache_key[0],
                    cache_key[1],
                    cache_key[2],
                    cache_key[3],
                )
            ]
        )

    def _build(self) -> None:
        started_at = time.perf_counter()
        if self._try_load_persisted():
            logger.info(
                "[media-index] loaded persisted account=%s usernames=%s kinds=%s md5Keys=%s fileIdKeys=%s loadedEntries=%s elapsedMs=%.1f",
                str(self.account_dir.name or ""),
                len(self.usernames),
                ",".join(sorted(self.media_kinds)) if self.media_kinds else "all",
                int(self.stats["md5Keys"]),
                int(self.stats["fileIdKeys"]),
                int(self.stats["loadedEntries"]),
                (time.perf_counter() - started_at) * 1000.0,
            )
            return
        self._index_decrypted_resources()
        self._load_hardlink_index()
        self._scan_media_roots()
        self._persist()
        logger.info(
            "[media-index] built account=%s usernames=%s kinds=%s resourceFiles=%s hardlinkRows=%s scannedFiles=%s md5Keys=%s fileIdKeys=%s elapsedMs=%.1f",
            str(self.account_dir.name or ""),
            len(self.usernames),
            ",".join(sorted(self.media_kinds)) if self.media_kinds else "all",
            int(self.stats["resourceFiles"]),
            int(self.stats["hardlinkRows"]),
            int(self.stats["scannedFiles"]),
            int(self.stats["md5Keys"]),
            int(self.stats["fileIdKeys"]),
            (time.perf_counter() - started_at) * 1000.0,
        )

    def _ensure_cache_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS media_index_meta (
                scope TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (scope, key)
            );
            CREATE TABLE IF NOT EXISTS media_index_entries (
                scope TEXT NOT NULL,
                kind TEXT NOT NULL,
                key_type TEXT NOT NULL,
                key TEXT NOT NULL,
                username TEXT NOT NULL DEFAULT '',
                path TEXT NOT NULL,
                PRIMARY KEY (scope, kind, key_type, key, username)
            );
            CREATE INDEX IF NOT EXISTS idx_media_index_entries_lookup
            ON media_index_entries(scope, kind, key_type, key, username);
            CREATE TABLE IF NOT EXISTS media_index_misses (
                scope TEXT NOT NULL,
                kind TEXT NOT NULL,
                md5 TEXT NOT NULL DEFAULT '',
                file_id TEXT NOT NULL DEFAULT '',
                username TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (scope, kind, md5, file_id, username)
            );
            CREATE INDEX IF NOT EXISTS idx_media_index_misses_lookup
            ON media_index_misses(scope, kind, md5, file_id, username);
            """
        )

    def _iter_signature_targets(self) -> list[tuple[str, Path, int]]:
        targets: list[tuple[str, Path, int]] = []
        hardlink_db_path = self.account_dir / "hardlink.db"
        if hardlink_db_path.exists():
            targets.append(("hardlink.db", hardlink_db_path, 0))

        try:
            if self.resource_dir.exists() and self.resource_dir.is_dir():
                targets.append(("resource", self.resource_dir, 1))
        except Exception:
            pass

        for username, directory in self._iter_attach_scan_dirs():
            targets.append((f"attach:{username or '*'}:{directory.name}", directory, 3))
        for directory in self._iter_video_scan_dirs():
            targets.append((f"video:{directory.name}", directory, 2))
        for directory in self._iter_file_scan_dirs():
            targets.append((f"file:{directory.name}", directory, 2))
        for directory in self._iter_cache_scan_dirs():
            targets.append((f"cache:{directory.name}", directory, 3))
        return targets

    def _snapshot_path(self, path: Path, max_depth: int) -> list[tuple[str, int, int, int]]:
        try:
            if not path.exists():
                return [(".", -1, 0, 0)]
        except Exception:
            return [(".", -1, 0, 0)]

        try:
            if path.is_file():
                stat = path.stat()
                return [(".", int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))), int(stat.st_size), 0)]
        except Exception:
            return [(".", -2, 0, 0)]

        rows: list[tuple[str, int, int, int]] = []
        root_str = str(path)
        for current_root, dirnames, _filenames in os.walk(root_str):
            rel = os.path.relpath(current_root, root_str)
            if rel == ".":
                depth = 0
                rel_key = "."
            else:
                depth = rel.count(os.sep) + 1
                rel_key = rel.replace("\\", "/")
            try:
                stat = os.stat(current_root)
                mtime_ns = int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)))
            except Exception:
                mtime_ns = -1
            rows.append((rel_key, mtime_ns, len(dirnames), depth))
            dirnames.sort()
            if depth >= max_depth:
                dirnames[:] = []
        return rows

    def _build_signature(self) -> str:
        payload: list[Any] = [
            ["version", _MEDIA_INDEX_DB_VERSION],
            ["account", str(self.account_dir.name or "")],
            ["scope", self._scope_key],
            ["usernames", sorted(self.usernames)],
            ["mediaKinds", sorted(self.media_kinds)],
        ]
        for label, path, max_depth in self._iter_signature_targets():
            payload.append(
                [
                    label,
                    str(path),
                    self._snapshot_path(path, max_depth=max_depth),
                ]
            )
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()

    def _iter_persist_rows(self):
        for kind, bucket in self._md5_hits.items():
            for key, path in bucket.items():
                yield (self._scope_key, kind, "md5", key, "", str(path))
        for kind, bucket in self._file_id_hits.items():
            for key, path in bucket.items():
                yield (self._scope_key, kind, "file_id", key, "", str(path))
        for kind, bucket in self._user_file_id_hits.items():
            for (username, key), path in bucket.items():
                yield (self._scope_key, kind, "file_id", key, str(username or ""), str(path))

    def _iter_persist_missing_rows(self):
        for kind, md5, file_id, username in sorted(self._known_missing):
            yield (self._scope_key, kind, md5, file_id, username)

    def _persist(self) -> None:
        try:
            conn = sqlite3.connect(str(self._cache_db_path))
        except Exception:
            return

        try:
            self._ensure_cache_schema(conn)
            signature = self._build_signature()
            meta_rows = [
                (self._scope_key, "version", str(_MEDIA_INDEX_DB_VERSION)),
                (self._scope_key, "signature", signature),
                (self._scope_key, "usernames", json.dumps(sorted(self.usernames), ensure_ascii=False)),
                (self._scope_key, "mediaKinds", json.dumps(sorted(self.media_kinds), ensure_ascii=False)),
                (self._scope_key, "resourceFiles", str(int(self.stats["resourceFiles"]))),
                (self._scope_key, "hardlinkRows", str(int(self.stats["hardlinkRows"]))),
                (self._scope_key, "scannedFiles", str(int(self.stats["scannedFiles"]))),
                (self._scope_key, "md5Keys", str(int(self.stats["md5Keys"]))),
                (self._scope_key, "fileIdKeys", str(int(self.stats["fileIdKeys"]))),
            ]
            with conn:
                conn.execute("DELETE FROM media_index_entries WHERE scope = ?", (self._scope_key,))
                conn.execute("DELETE FROM media_index_misses WHERE scope = ?", (self._scope_key,))
                conn.execute("DELETE FROM media_index_meta WHERE scope = ?", (self._scope_key,))
                conn.executemany(
                    "INSERT OR REPLACE INTO media_index_entries(scope, kind, key_type, key, username, path) VALUES (?, ?, ?, ?, ?, ?)",
                    self._iter_persist_rows(),
                )
                conn.executemany(
                    "INSERT OR REPLACE INTO media_index_misses(scope, kind, md5, file_id, username) VALUES (?, ?, ?, ?, ?)",
                    self._iter_persist_missing_rows(),
                )
                conn.executemany(
                    "INSERT OR REPLACE INTO media_index_meta(scope, key, value) VALUES (?, ?, ?)",
                    meta_rows,
                )
        except Exception:
            logger.exception("[media-index] persist failed account=%s", str(self.account_dir.name or ""))
        finally:
            conn.close()

    def _try_load_persisted(self) -> bool:
        try:
            if not self._cache_db_path.exists():
                return False
        except Exception:
            return False

        try:
            conn = sqlite3.connect(str(self._cache_db_path))
        except Exception:
            return False

        try:
            self._ensure_cache_schema(conn)
            rows = conn.execute(
                "SELECT key, value FROM media_index_meta WHERE scope = ?",
                (self._scope_key,),
            ).fetchall()
            if not rows:
                return False
            meta = {str(key): str(value) for key, value in rows}
            if meta.get("version") != str(_MEDIA_INDEX_DB_VERSION):
                return False

            stored_kinds_raw = str(meta.get("mediaKinds") or "[]")
            try:
                stored_kinds = set(json.loads(stored_kinds_raw))
            except Exception:
                stored_kinds = set()
            if self.media_kinds and not self.media_kinds.issubset(stored_kinds):
                return False

            current_signature = self._build_signature()
            if meta.get("signature") != current_signature:
                return False

            entry_rows = conn.execute(
                "SELECT kind, key_type, key, username, path FROM media_index_entries WHERE scope = ?",
                (self._scope_key,),
            ).fetchall()
            miss_rows = conn.execute(
                "SELECT kind, md5, file_id, username FROM media_index_misses WHERE scope = ?",
                (self._scope_key,),
            ).fetchall()
            if not entry_rows and not miss_rows:
                return False

            for kind, key_type, key, username, path in entry_rows:
                kind_s = str(kind or "").strip()
                key_type_s = str(key_type or "").strip()
                key_s = str(key or "").strip().lower()
                username_s = str(username or "").strip()
                path_obj = Path(str(path or "").strip())
                if not kind_s or not key_s:
                    continue
                if key_type_s == "md5":
                    self._md5_hits.setdefault(kind_s, {})[key_s] = path_obj
                elif key_type_s == "file_id":
                    self._file_id_hits.setdefault(kind_s, {}).setdefault(key_s, path_obj)
                    if username_s:
                        self._user_file_id_hits.setdefault(kind_s, {})[(username_s, key_s)] = path_obj

            for kind, md5, file_id, username in miss_rows:
                cache_key = self._normalize_cache_key(
                    kind=str(kind or ""),
                    md5=str(md5 or ""),
                    file_id=str(file_id or ""),
                    username=str(username or ""),
                )
                if not cache_key[0] or (not cache_key[1] and not cache_key[2]):
                    continue
                self._known_missing.add(cache_key)
                self._query_cache[cache_key] = None

            self.stats["resourceFiles"] = int(meta.get("resourceFiles") or 0)
            self.stats["hardlinkRows"] = int(meta.get("hardlinkRows") or 0)
            self.stats["scannedFiles"] = int(meta.get("scannedFiles") or 0)
            self.stats["md5Keys"] = sum(len(bucket) for bucket in self._md5_hits.values())
            self.stats["fileIdKeys"] = sum(len(bucket) for bucket in self._file_id_hits.values())
            self.stats["loadedEntries"] = len(entry_rows)
            self.stats["loadedMisses"] = len(miss_rows)
            self._loaded_from_cache = True
            return True
        except Exception:
            logger.exception("[media-index] load persisted failed account=%s", str(self.account_dir.name or ""))
            return False
        finally:
            conn.close()

    def _index_decrypted_resources(self) -> None:
        try:
            if not self.resource_dir.exists() or not self.resource_dir.is_dir():
                return
        except Exception:
            return

        for path in _iter_files_under(self.resource_dir):
            try:
                if not path.is_file():
                    continue
            except Exception:
                continue

            md5_values = _iter_md5_candidates_from_name(path.name)
            if not md5_values:
                continue

            suffix = str(path.suffix or "").lower()
            if suffix in _MEDIA_INDEX_VIDEO_STREAM_EXTS:
                kinds = ("video",)
            else:
                kinds = tuple(kind for kind in ("image", "emoji", "video_thumb") if self._wants(kind))
            if not kinds:
                continue

            for md5 in md5_values:
                for kind in kinds:
                    self._put_md5(kind, md5, path)
            self.stats["resourceFiles"] += 1

    def _load_hardlink_index(self) -> None:
        hardlink_db_path = self.account_dir / "hardlink.db"
        if not hardlink_db_path.exists():
            return

        try:
            conn = sqlite3.connect(str(hardlink_db_path))
            conn.row_factory = sqlite3.Row
        except Exception:
            return

        table_specs: list[tuple[str, tuple[str, ...]]] = []
        if self._wants("image") or self._wants("emoji"):
            table_specs.append(("image_hardlink_info", ("image", "emoji")))
        if self._wants("video") or self._wants("video_thumb"):
            table_specs.append(("video_hardlink_info", ("video", "video_thumb")))
        if self._wants("file"):
            table_specs.append(("file_hardlink_info", ("file",)))

        try:
            dir2id_map = _build_hardlink_dir2id_map(conn)
            for prefix, kinds in table_specs:
                table_name = _resolve_hardlink_table_name(conn, prefix)
                if not table_name:
                    continue

                quoted = _quote_ident(table_name)
                try:
                    rows = conn.execute(
                        f"SELECT md5, file_name, file_size, modify_time, dir1, dir2 FROM {quoted} "
                        "WHERE md5 IS NOT NULL AND md5 <> '' ORDER BY modify_time DESC, rowid DESC"
                    ).fetchall()
                except Exception:
                    continue

                for row in rows:
                    md5 = str(row["md5"] or "").strip().lower()
                    if not _EMOTICON_MD5_RE.fullmatch(md5):
                        continue

                    entry = _HardlinkEntry(
                        file_name=str(row["file_name"] or "").strip(),
                        file_size=int(row["file_size"] or 0),
                        modify_time=int(row["modify_time"] or 0),
                        dir1=int(row["dir1"] or 0),
                        dir2=int(row["dir2"] or 0),
                        dir_name=str(dir2id_map.get(int(row["dir2"] or 0)) or str(row["dir2"] or "")).strip(),
                    )

                    for kind in kinds:
                        bucket = self._hardlink_hits.setdefault(kind, {})
                        bucket.setdefault(md5, entry)

                self.stats["hardlinkRows"] += len(rows)
        finally:
            conn.close()

    def _scan_media_roots(self) -> None:
        if not self._roots:
            return

        if self._wants("image"):
            for username, directory in self._iter_attach_scan_dirs():
                self._scan_attach_dir(directory, username=username)

        if self._wants("video") or self._wants("video_thumb"):
            for directory in self._iter_video_scan_dirs():
                self._scan_video_dir(directory)

        if self._wants("file"):
            for directory in self._iter_file_scan_dirs():
                self._scan_file_dir(directory)

        if self._wants("emoji") or self._wants("video_thumb"):
            for directory in self._iter_cache_scan_dirs():
                self._scan_cache_dir(directory)

    def _iter_attach_scan_dirs(self) -> list[tuple[str, Path]]:
        result: list[tuple[str, Path]] = []
        usernames = self.usernames
        for root in self._roots:
            attach_root = root / "msg" / "attach"
            try:
                if not attach_root.exists() or not attach_root.is_dir():
                    continue
            except Exception:
                continue

            if usernames:
                for username in usernames:
                    chat_hash = hashlib.md5(username.encode()).hexdigest()
                    directory = attach_root / chat_hash
                    try:
                        if directory.exists() and directory.is_dir():
                            result.append((username, directory))
                    except Exception:
                        continue
            else:
                try:
                    for child in attach_root.iterdir():
                        try:
                            if child.is_dir():
                                result.append(("", child))
                        except Exception:
                            continue
                except Exception:
                    continue
        return result

    def _iter_video_scan_dirs(self) -> list[Path]:
        result: list[Path] = []
        for root in self._roots:
            candidates = [
                root / "msg" / "video",
                root / "video",
                root if str(root.name).lower() == "video" else None,
            ]
            for candidate in candidates:
                if not candidate:
                    continue
                try:
                    if candidate.exists() and candidate.is_dir() and candidate not in result:
                        result.append(candidate)
                except Exception:
                    continue
        return result

    def _iter_file_scan_dirs(self) -> list[Path]:
        result: list[Path] = []
        for root in self._roots:
            candidates = [
                root / "msg" / "file",
                root / "file",
                root if str(root.name).lower() == "file" else None,
            ]
            for candidate in candidates:
                if not candidate:
                    continue
                try:
                    if candidate.exists() and candidate.is_dir() and candidate not in result:
                        result.append(candidate)
                except Exception:
                    continue
        return result

    def _iter_cache_scan_dirs(self) -> list[Path]:
        result: list[Path] = []
        for root in self._roots:
            candidate = root / "cache"
            try:
                if candidate.exists() and candidate.is_dir() and candidate not in result:
                    result.append(candidate)
            except Exception:
                continue
        return result

    def _scan_attach_dir(self, directory: Path, *, username: str = "") -> None:
        for path in _iter_files_under(directory):
            suffix = str(path.suffix or "").lower()
            if suffix not in _MEDIA_INDEX_FILE_EXTS:
                continue
            self.stats["scannedFiles"] += 1
            if suffix in _MEDIA_INDEX_VIDEO_STREAM_EXTS:
                if self._wants("video"):
                    self._register_kind_path("video", path, username=username)
                continue
            if self._wants("image"):
                self._register_kind_path("image", path, username=username)

    def _scan_video_dir(self, directory: Path) -> None:
        for path in _iter_files_under(directory):
            suffix = str(path.suffix or "").lower()
            if suffix not in _MEDIA_INDEX_FILE_EXTS:
                continue
            self.stats["scannedFiles"] += 1
            if suffix in _MEDIA_INDEX_VIDEO_STREAM_EXTS:
                self._register_kind_path("video", path)
            elif suffix == ".dat":
                if self._wants("video"):
                    self._register_kind_path("video", path)
                if self._wants("video_thumb"):
                    self._register_kind_path("video_thumb", path)
            else:
                self._register_kind_path("video_thumb", path)

    def _scan_file_dir(self, directory: Path) -> None:
        for path in _iter_files_under(directory):
            self.stats["scannedFiles"] += 1
            self._register_kind_path("file", path)
            suffix = str(path.suffix or "").lower()
            if suffix in _MEDIA_INDEX_VIDEO_STREAM_EXTS and self._wants("video"):
                self._register_kind_path("video", path)

    def _scan_cache_dir(self, directory: Path) -> None:
        for path in _iter_files_under(directory):
            suffix = str(path.suffix or "").lower()
            if suffix not in _MEDIA_INDEX_FILE_EXTS:
                continue
            self.stats["scannedFiles"] += 1
            lowered_parts = {str(part or "").lower() for part in path.parts}
            if {"emoji", "emoticon"} & lowered_parts:
                self._register_kind_path("emoji", path)
                continue
            if suffix in _MEDIA_INDEX_VIDEO_STREAM_EXTS:
                self._register_kind_path("video", path)
                continue
            self._register_kind_path("video_thumb", path)

    def resolve(self, *, kind: str, md5: str = "", file_id: str = "", username: str = "") -> Optional[Path]:
        cache_key = self._normalize_cache_key(kind=kind, md5=md5, file_id=file_id, username=username)
        kind_key, md5_key, file_key, username_key = cache_key
        if cache_key in self._known_missing:
            self._query_cache[cache_key] = None
            return None
        if cache_key in self._query_cache:
            return self._query_cache[cache_key]
        if cache_key in self._negative_cache:
            return None

        path: Optional[Path] = None
        if md5_key and _EMOTICON_MD5_RE.fullmatch(md5_key):
            path = self._resolve_by_md5(kind_key, md5_key, username_key)
        if path is None and file_key:
            path = self._resolve_by_file_id(kind_key, file_key, username_key)

        if path is not None:
            self._query_cache[cache_key] = path
            return path

        self._negative_cache.add(cache_key)
        self._query_cache[cache_key] = None
        return None

    def _resolve_by_md5(self, kind: str, md5: str, username: str) -> Optional[Path]:
        preferred: list[str]
        if kind == "emoji":
            preferred = ["emoji", "image"]
        elif kind == "video_thumb":
            preferred = ["video_thumb", "image"]
        else:
            preferred = [kind]

        for candidate_kind in preferred:
            path = self._md5_hits.get(candidate_kind, {}).get(md5)
            if path is not None:
                try:
                    if path.exists() and path.is_file():
                        return path
                except Exception:
                    pass

        for candidate_kind in preferred:
            entry = self._hardlink_hits.get(candidate_kind, {}).get(md5)
            if entry is None or not self.wxid_dir:
                continue
            path = _resolve_hardlink_entry_path(
                kind=candidate_kind,
                entry=entry,
                wxid_dir=self.wxid_dir,
                username=username or None,
                extra_roots=self._roots[1:],
            )
            if path is None:
                continue
            self._register_kind_path(candidate_kind, path, username=username)
            return path

        if self.wxid_dir:
            hardlink_db_path = self.account_dir / "hardlink.db"
            for candidate_kind in preferred:
                path = _resolve_media_path_from_hardlink(
                    hardlink_db_path=hardlink_db_path,
                    wxid_dir=self.wxid_dir,
                    md5=md5,
                    kind=candidate_kind,
                    username=username or None,
                    extra_roots=self._roots[1:],
                )
                if path is None:
                    continue
                self._register_kind_path(candidate_kind, path, username=username)
                return path
        return None

    def _resolve_by_file_id(self, kind: str, file_id: str, username: str) -> Optional[Path]:
        keys = _iter_media_lookup_keys(file_id)
        if not keys:
            return None

        if username:
            user_bucket = self._user_file_id_hits.get(kind, {})
            for key in keys:
                path = user_bucket.get((username, key))
                if path is None:
                    continue
                try:
                    if path.exists() and path.is_file():
                        return path
                except Exception:
                    continue

        bucket = self._file_id_hits.get(kind, {})
        for key in keys:
            path = bucket.get(key)
            if path is None:
                continue
            try:
                if path.exists() and path.is_file():
                    return path
            except Exception:
                continue
        return None


def _resolve_media_path_from_hardlink(
    hardlink_db_path: Path,
    wxid_dir: Path,
    md5: str,
    kind: str,
    username: Optional[str],
    extra_roots: Optional[list[Path]] = None,
) -> Optional[Path]:
    if not hardlink_db_path.exists():
        return None

    kind_key = str(kind or "").lower().strip()
    prefixes: list[str]
    if kind_key == "image":
        prefixes = ["image_hardlink_info"]
    elif kind_key == "emoji":
        prefixes = [
            "emoji_hardlink_info",
            "emotion_hardlink_info",
            "image_hardlink_info",
        ]
    elif kind_key == "video" or kind_key == "video_thumb":
        prefixes = ["video_hardlink_info"]
    elif kind_key == "file":
        prefixes = ["file_hardlink_info"]
    else:
        return None

    conn = sqlite3.connect(str(hardlink_db_path))
    conn.row_factory = sqlite3.Row
    try:
        dir2id_map = _build_hardlink_dir2id_map(conn)
        for prefix in prefixes:
            table_name = _resolve_hardlink_table_name(conn, prefix)
            if not table_name:
                continue

            quoted = _quote_ident(table_name)
            try:
                row = conn.execute(
                    f"SELECT dir1, dir2, file_name, file_size, modify_time FROM {quoted} WHERE md5 = ? ORDER BY modify_time DESC, dir1 DESC, rowid DESC LIMIT 1",
                    (md5,),
                ).fetchone()
            except Exception:
                row = None
            if not row:
                continue

            entry = _HardlinkEntry(
                file_name=str(row["file_name"] or "").strip(),
                file_size=int(row["file_size"] or 0),
                modify_time=int(row["modify_time"] or 0),
                dir1=int(row["dir1"] or 0),
                dir2=int(row["dir2"] or 0),
                dir_name=str(dir2id_map.get(int(row["dir2"] or 0)) or str(row["dir2"] or "")).strip(),
            )
            resolved = _resolve_hardlink_entry_path(
                kind=kind_key,
                entry=entry,
                wxid_dir=wxid_dir,
                username=username,
                extra_roots=extra_roots,
            )
            if resolved is not None:
                return resolved

        return None
    finally:
        conn.close()


@lru_cache(maxsize=4096)
def _fallback_search_media_by_md5(weixin_root_str: str, md5: str, kind: str = "") -> Optional[str]:
    if not weixin_root_str or not md5:
        return None
    try:
        root = Path(weixin_root_str)
    except Exception:
        return None

    kind_key = str(kind or "").lower().strip()

    def _fast_find_emoji_in_cache() -> Optional[str]:
        md5_prefix = md5[:2] if len(md5) >= 2 else ""
        if not md5_prefix:
            return None
        cache_root = root / "cache"
        try:
            if not cache_root.exists() or not cache_root.is_dir():
                return None
        except Exception:
            return None

        exact_names = [
            f"{md5}_h.dat",
            f"{md5}_t.dat",
            f"{md5}.dat",
            f"{md5}.gif",
            f"{md5}.webp",
            f"{md5}.png",
            f"{md5}.jpg",
        ]
        buckets = ["Emoticon", "emoticon", "Emoji", "emoji"]

        candidates: list[Path] = []
        try:
            children = list(cache_root.iterdir())
        except Exception:
            children = []

        for child in children:
            try:
                if not child.is_dir():
                    continue
            except Exception:
                continue
            for bucket in buckets:
                candidates.append(child / bucket / md5_prefix)

        for bucket in buckets:
            candidates.append(cache_root / bucket / md5_prefix)

        seen: set[str] = set()
        uniq: list[Path] = []
        for c in candidates:
            try:
                rc = str(c.resolve())
            except Exception:
                rc = str(c)
            if rc in seen:
                continue
            seen.add(rc)
            uniq.append(c)

        for base in uniq:
            try:
                if not base.exists() or not base.is_dir():
                    continue
            except Exception:
                continue

            for name in exact_names:
                p = base / name
                try:
                    if p.exists() and p.is_file():
                        return str(p)
                except Exception:
                    continue

            try:
                for p in base.glob(f"{md5}*"):
                    try:
                        if p.is_file():
                            return str(p)
                    except Exception:
                        continue
            except Exception:
                continue
        return None

    # 根据类型选择搜索目录
    if kind_key == "file":
        search_dirs = [root / "msg" / "file"]
    elif kind_key == "emoji":
        hit_fast = _fast_find_emoji_in_cache()
        if hit_fast:
            return hit_fast
        search_dirs = [
            root / "msg" / "emoji",
            root / "msg" / "emoticon",
            root / "emoji",
            root / "emoticon",
            root / "msg" / "attach",
            root / "msg" / "file",
            root / "msg" / "video",
        ]
    else:
        search_dirs = [
            root / "msg" / "attach",
            root / "msg" / "file",
            root / "msg" / "video",
            root / "cache",
        ]

    # 根据类型选择搜索模式
    if kind_key == "file":
        patterns = [
            f"*{md5}*",
        ]
    elif kind_key == "emoji":
        patterns = [
            f"{md5}_h.dat",
            f"{md5}_t.dat",
            f"{md5}.dat",
            f"{md5}*.dat",
            f"{md5}*.gif",
            f"{md5}*.webp",
            f"{md5}*.png",
            f"{md5}*.jpg",
            f"*{md5}*",
        ]
    else:
        patterns = [
            f"{md5}_h.dat",
            f"{md5}_t.dat",
            f"{md5}.dat",
            f"{md5}*.dat",
            f"{md5}*.jpg",
            f"{md5}*.jpeg",
            f"{md5}*.m4v",
            f"{md5}*.mov",
            f"{md5}*.png",
            f"{md5}*.gif",
            f"{md5}*.webp",
            f"{md5}*.mp4",
        ]

    for d in search_dirs:
        try:
            if not d.exists() or not d.is_dir():
                continue
        except Exception:
            continue
        for pat in patterns:
            try:
                for p in d.rglob(pat):
                    try:
                        if p.is_file():
                            return str(p)
                    except Exception:
                        continue
            except Exception:
                continue
    return None


def _guess_media_type_by_path(path: Path, fallback: str = "application/octet-stream") -> str:
    try:
        mt = mimetypes.guess_type(str(path.name))[0]
        if mt:
            return mt
    except Exception:
        pass
    return fallback


def _try_xor_decrypt_by_magic(data: bytes) -> tuple[Optional[bytes], Optional[str]]:
    if not data:
        return None, None

    # (offset, magic, media_type)
    candidates: list[tuple[int, bytes, str]] = [
        (0, b"\x89PNG\r\n\x1a\n", "image/png"),
        (0, b"GIF87a", "image/gif"),
        (0, b"GIF89a", "image/gif"),
        (0, b"RIFF", "application/octet-stream"),
        (4, b"ftyp", "video/mp4"),
        (0, b"wxgf", "application/octet-stream"),
        (1, b"wxgf", "application/octet-stream"),
        (2, b"wxgf", "application/octet-stream"),
        (3, b"wxgf", "application/octet-stream"),
        (4, b"wxgf", "application/octet-stream"),
        (5, b"wxgf", "application/octet-stream"),
        (6, b"wxgf", "application/octet-stream"),
        (7, b"wxgf", "application/octet-stream"),
        (8, b"wxgf", "application/octet-stream"),
        (9, b"wxgf", "application/octet-stream"),
        (10, b"wxgf", "application/octet-stream"),
        (11, b"wxgf", "application/octet-stream"),
        (12, b"wxgf", "application/octet-stream"),
        (13, b"wxgf", "application/octet-stream"),
        (14, b"wxgf", "application/octet-stream"),
        (15, b"wxgf", "application/octet-stream"),
        # JPEG magic is short (3 bytes), keep it last to reduce false positives.
        (0, b"\xff\xd8\xff", "image/jpeg"),
    ]

    for offset, magic, mt in candidates:
        if len(data) < offset + len(magic):
            continue
        key = data[offset] ^ magic[0]
        ok = True
        for i in range(len(magic)):
            if (data[offset + i] ^ key) != magic[i]:
                ok = False
                break
        if not ok:
            continue

        decoded = bytes(b ^ key for b in data)

        if magic == b"wxgf":
            try:
                payload = decoded[offset:] if offset > 0 else decoded
                converted = _wxgf_to_image_bytes(payload)
                if converted:
                    mtw = _detect_image_media_type(converted[:32])
                    if mtw != "application/octet-stream":
                        return converted, mtw
            except Exception:
                pass
            continue

        if offset == 0 and magic == b"RIFF":
            if len(decoded) >= 12 and decoded[8:12] == b"WEBP":
                if _is_probably_valid_image(decoded, "image/webp"):
                    return decoded, "image/webp"
            continue

        if mt == "video/mp4":
            try:
                if len(decoded) >= 8 and decoded[4:8] == b"ftyp":
                    return decoded, "video/mp4"
            except Exception:
                pass
            continue

        mt2 = _detect_image_media_type(decoded[:32])
        if mt2 != mt:
            continue
        if not _is_probably_valid_image(decoded, mt2):
            continue
        return decoded, mt2

    preview_len = 8192
    try:
        preview_len = min(int(preview_len), int(len(data)))
    except Exception:
        preview_len = 8192

    if preview_len > 0:
        for key in range(256):
            try:
                pv = bytes(b ^ key for b in data[:preview_len])
            except Exception:
                continue
            try:
                scan = pv
                if (
                    (scan.find(b"wxgf") >= 0)
                    or (scan.find(b"\x89PNG\r\n\x1a\n") >= 0)
                    or (scan.find(b"\xff\xd8\xff") >= 0)
                    or (scan.find(b"GIF87a") >= 0)
                    or (scan.find(b"GIF89a") >= 0)
                    or (scan.find(b"RIFF") >= 0)
                    or (scan.find(b"ftyp") >= 0)
                ):
                    decoded = bytes(b ^ key for b in data)
                    dec2, mt2 = _try_strip_media_prefix(decoded)
                    if mt2 != "application/octet-stream":
                        if mt2.startswith("image/") and (not _is_probably_valid_image(dec2, mt2)):
                            continue
                        return dec2, mt2
            except Exception:
                continue

    return None, None


def _detect_wechat_dat_version(data: bytes) -> int:
    if not data or len(data) < 6:
        return -1
    sig = data[:6]
    if sig == b"\x07\x08V1\x08\x07":
        return 1
    if sig == b"\x07\x08V2\x08\x07":
        return 2
    return 0

@lru_cache(maxsize=4096)
def _fallback_search_media_by_file_id(
    weixin_root_str: str,
    file_id: str,
    kind: str = "",
    username: str = "",
) -> Optional[str]:
    """在微信数据目录里按文件名（file_id）兜底查找媒体文件。

    一些微信版本的图片消息不再直接提供 32 位 MD5，而是提供形如 `cdnthumburl` 的长串标识，
    本函数用于按文件名/前缀在 msg/attach、cache 等目录中定位对应的 .dat 资源文件。
    """
    if not weixin_root_str or not file_id:
        return None
    try:
        root = Path(weixin_root_str)
    except Exception:
        return None

    kind_key = str(kind or "").lower().strip()
    fid = str(file_id or "").strip()
    if not fid:
        return None

    # 优先在当前会话的 attach 子目录中查找（显著减少扫描范围）
    search_dirs: list[Path] = []
    if username:
        try:
            chat_hash = hashlib.md5(str(username).encode()).hexdigest()
            search_dirs.append(root / "msg" / "attach" / chat_hash)
        except Exception:
            pass

    if kind_key == "file":
        search_dirs.extend([root / "msg" / "file"])
    elif kind_key == "video" or kind_key == "video_thumb":
        search_dirs.extend([root / "msg" / "video", root / "cache"])
    else:
        search_dirs.extend([root / "msg" / "attach", root / "cache", root / "msg" / "file", root / "msg" / "video"])

    # de-dup while keeping order
    seen: set[str] = set()
    uniq_dirs: list[Path] = []
    for d in search_dirs:
        try:
            k = str(d.resolve())
        except Exception:
            k = str(d)
        if k in seen:
            continue
        seen.add(k)
        uniq_dirs.append(d)

    base = glob.escape(fid)
    has_suffix = bool(Path(fid).suffix)

    patterns: list[str] = []
    if has_suffix:
        patterns.append(base)
    else:
        patterns.extend(
            [
                f"{base}_h.dat",
                f"{base}_t.dat",
                f"{base}.dat",
                f"{base}*.dat",
                f"{base}.jpg",
                f"{base}.jpeg",
                f"{base}.png",
                f"{base}.gif",
                f"{base}.webp",
                f"{base}*",
            ]
        )

    for d in uniq_dirs:
        try:
            if not d.exists() or not d.is_dir():
                continue
        except Exception:
            continue
        for pat in patterns:
            try:
                for p in d.rglob(pat):
                    try:
                        if p.is_file():
                            return str(p)
                    except Exception:
                        continue
            except Exception:
                continue
    return None


def _save_media_keys(account_dir: Path, xor_key: int, aes_key16: Optional[bytes] = None) -> None:
    try:
        aes_str = ""
        if aes_key16:
            try:
                aes_str = aes_key16.decode("ascii", errors="ignore")[:16]
            except Exception:
                aes_str = ""
        payload = {
            "xor": int(xor_key),
            "aes": aes_str,
        }
        (account_dir / "_media_keys.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def _decrypt_wechat_dat_v3(data: bytes, xor_key: int) -> bytes:
    return bytes(b ^ xor_key for b in data)


def _decrypt_wechat_dat_v4(data: bytes, xor_key: int, aes_key: bytes) -> bytes:
    from Crypto.Cipher import AES
    from Crypto.Util import Padding

    header, rest = data[:0xF], data[0xF:]
    signature, aes_size, xor_size = struct.unpack("<6sLLx", header)
    aes_size += AES.block_size - aes_size % AES.block_size

    aes_data = rest[:aes_size]
    raw_data = rest[aes_size:]

    cipher = AES.new(aes_key[:16], AES.MODE_ECB)
    decrypted_data = Padding.unpad(cipher.decrypt(aes_data), AES.block_size)

    if xor_size > 0:
        raw_data = rest[aes_size:-xor_size]
        xor_data = rest[-xor_size:]
        xored_data = bytes(b ^ xor_key for b in xor_data)
    else:
        xored_data = b""

    return decrypted_data + raw_data + xored_data


def _load_media_keys(account_dir: Path) -> dict[str, Any]:
    p = account_dir / "_media_keys.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_resource_dir(account_dir: Path) -> Path:
    """获取解密资源输出目录"""
    return account_dir / "resource"


def _get_decrypted_resource_path(account_dir: Path, md5: str, ext: str = "") -> Path:
    """根据MD5获取解密后资源的路径"""
    resource_dir = _get_resource_dir(account_dir)
    # 使用MD5前2位作为子目录，避免单目录文件过多
    sub_dir = md5[:2] if len(md5) >= 2 else "00"
    if ext:
        return resource_dir / sub_dir / f"{md5}.{ext}"
    return resource_dir / sub_dir / md5


def _detect_image_extension(data: bytes) -> str:
    """根据图片数据检测文件扩展名"""
    if not data:
        return "dat"
    head = data[:32] if len(data) > 32 else data
    mt = _detect_image_media_type(head)
    if mt == "image/png":
        return "png"
    if mt == "image/jpeg":
        return "jpg"
    if mt == "image/gif":
        return "gif"
    if mt == "image/webp":
        return "webp"
    return "dat"


def _try_find_decrypted_resource(account_dir: Path, md5: str) -> Optional[Path]:
    """尝试在解密资源目录中查找已解密的资源"""
    if not md5:
        return None
    resource_dir = _get_resource_dir(account_dir)
    if not resource_dir.exists():
        return None
    sub_dir = md5[:2] if len(md5) >= 2 else "00"

    # Prefer the standard layout: resource/{md5-prefix}/{md5}.{ext}
    target_dir = resource_dir / sub_dir
    search_dirs = [target_dir]

    # Support wxdump flat media layout after it is imported as resource.
    # Typical files: resource/{md5}.jpg, resource/{md5}_t.jpg, or resource/{md5}.wxgf.
    if resource_dir not in search_dirs:
        search_dirs.append(resource_dir)

    exts = ["jpg", "png", "gif", "webp", "mp4", "dat", "wxgf", "wxgf.jpg"]
    suffixes = ["", "_t", "_b", "_h"]
    for directory in search_dirs:
        if not directory.exists():
            continue
        for suffix in suffixes:
            for ext in exts:
                candidate = directory / f"{md5}{suffix}.{ext}"
                if candidate.exists():
                    return candidate
    return None


def _read_and_maybe_decrypt_media(
    path: Path,
    account_dir: Optional[Path] = None,
    weixin_root: Optional[Path] = None,
) -> tuple[bytes, str]:
    # Fast path: already a normal image
    with open(path, "rb") as f:
        head = f.read(64)

    mt = _detect_image_media_type(head)
    if mt != "application/octet-stream":
        return path.read_bytes(), mt

    if head.startswith(b"wxgf"):
        data0 = path.read_bytes()
        converted0 = _wxgf_to_image_bytes(data0)
        if converted0:
            mt0 = _detect_image_media_type(converted0[:32])
            if mt0 != "application/octet-stream":
                return converted0, mt0

    try:
        idx = head.find(b"wxgf")
    except Exception:
        idx = -1
    if 0 < idx <= 4:
        try:
            data0 = path.read_bytes()
            payload0 = data0[idx:]
            converted0 = _wxgf_to_image_bytes(payload0)
            if converted0:
                mt0 = _detect_image_media_type(converted0[:32])
                if mt0 != "application/octet-stream":
                    return converted0, mt0
        except Exception:
            pass

    try:
        data_pref = path.read_bytes()
        # Only accept prefix stripping when it looks like a real image/video,
        # otherwise encrypted/random bytes may trigger false positives.
        stripped, mtp = _try_strip_media_prefix(data_pref)
        if mtp != "application/octet-stream":
            if mtp.startswith("image/") and (not _is_probably_valid_image(stripped, mtp)):
                pass
            else:
                return stripped, mtp
    except Exception:
        pass

    data = path.read_bytes()

    # Try WeChat .dat v1/v2 decrypt.
    version = _detect_wechat_dat_version(data)
    if version in (0, 1, 2):
        # 不在本项目内做任何密钥提取；仅使用用户保存的密钥（_media_keys.json）。
        xor_key: Optional[int] = None
        aes_key16 = b""
        if account_dir is not None:
            try:
                keys2 = _load_media_keys(account_dir)

                x2 = keys2.get("xor")
                if x2 is not None:
                    xor_key = int(x2)
                    if not (0 <= int(xor_key) <= 255):
                        xor_key = None
                    else:
                        logger.debug("使用 _media_keys.json 中保存的 xor key")

                aes_str = str(keys2.get("aes") or "").strip()
                if len(aes_str) >= 16:
                    aes_key16 = aes_str[:16].encode("ascii", errors="ignore")
            except Exception:
                xor_key = None
                aes_key16 = b""
        try:
            if version == 0 and xor_key is not None:
                out = _decrypt_wechat_dat_v3(data, xor_key)
                try:
                    out2, mtp2 = _try_strip_media_prefix(out)
                    if mtp2 != "application/octet-stream":
                        return out2, mtp2
                except Exception:
                    pass
                if out.startswith(b"wxgf"):
                    converted = _wxgf_to_image_bytes(out)
                    if converted:
                        out = converted
                        logger.info(f"wxgf->image: {path} -> {len(out)} bytes")
                    else:
                        logger.info(f"wxgf->image failed: {path}")
                mt0 = _detect_image_media_type(out[:32])
                if mt0 != "application/octet-stream":
                    return out, mt0
            elif version == 1 and xor_key is not None:
                out = _decrypt_wechat_dat_v4(data, xor_key, b"cfcd208495d565ef")
                try:
                    out2, mtp2 = _try_strip_media_prefix(out)
                    if mtp2 != "application/octet-stream":
                        return out2, mtp2
                except Exception:
                    pass
                if out.startswith(b"wxgf"):
                    converted = _wxgf_to_image_bytes(out)
                    if converted:
                        out = converted
                        logger.info(f"wxgf->image: {path} -> {len(out)} bytes")
                    else:
                        logger.info(f"wxgf->image failed: {path}")
                mt1 = _detect_image_media_type(out[:32])
                if mt1 != "application/octet-stream":
                    return out, mt1
            elif version == 2 and xor_key is not None and aes_key16:
                out = _decrypt_wechat_dat_v4(data, xor_key, aes_key16)
                try:
                    out2, mtp2 = _try_strip_media_prefix(out)
                    if mtp2 != "application/octet-stream":
                        return out2, mtp2
                except Exception:
                    pass
                if out.startswith(b"wxgf"):
                    converted = _wxgf_to_image_bytes(out)
                    if converted:
                        out = converted
                        logger.info(f"wxgf->image: {path} -> {len(out)} bytes")
                    else:
                        logger.info(f"wxgf->image failed: {path}")
                mt2b = _detect_image_media_type(out[:32])
                if mt2b != "application/octet-stream":
                    return out, mt2b
        except Exception:
            pass

    # Fallback: try guessing XOR key by magic (only after key-based decrypt attempts).
    # For V4 signature files, XOR guessing is not applicable and may be expensive.
    if version in (0, -1):
        dec, mt2 = _try_xor_decrypt_by_magic(data)
        if dec is not None and mt2:
            return dec, mt2

    # Fallback: return as-is.
    mt3 = _guess_media_type_by_path(path, fallback="application/octet-stream")
    if mt3.startswith("image/") and (not _is_probably_valid_image(data, mt3)):
        mt3 = "application/octet-stream"
    if mt3 == "video/mp4":
        try:
            if not (len(data) >= 8 and data[4:8] == b"ftyp"):
                mt3 = "application/octet-stream"
        except Exception:
            mt3 = "application/octet-stream"
    return data, mt3


def _ensure_decrypted_resource_for_md5(
    account_dir: Path,
    md5: str,
    source_path: Path,
    weixin_root: Optional[Path] = None,
) -> Optional[Path]:
    if not md5 or not source_path:
        return None

    md5_lower = str(md5).lower()
    existing = _try_find_decrypted_resource(account_dir, md5_lower)
    if existing:
        return existing

    try:
        if not source_path.exists() or not source_path.is_file():
            return None
    except Exception:
        return None

    data, mt0 = _read_and_maybe_decrypt_media(source_path, account_dir=account_dir, weixin_root=weixin_root)
    mt2 = str(mt0 or "").strip()
    if (not mt2) or mt2 == "application/octet-stream":
        mt2 = _detect_image_media_type(data[:32])
    if mt2 == "application/octet-stream":
        try:
            data2, mtp = _try_strip_media_prefix(data)
            if mtp != "application/octet-stream":
                data = data2
                mt2 = mtp
        except Exception:
            pass
    if mt2 == "application/octet-stream":
        try:
            if len(data) >= 8 and data[4:8] == b"ftyp":
                mt2 = "video/mp4"
        except Exception:
            pass
    if mt2 == "application/octet-stream":
        return None

    if str(mt2).startswith("image/"):
        ext = _detect_image_extension(data)
    elif str(mt2) == "video/mp4":
        ext = "mp4"
    else:
        ext = Path(str(source_path.name)).suffix.lstrip(".").lower() or "dat"
    output_path = _get_decrypted_resource_path(account_dir, md5_lower, ext)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not output_path.exists():
            output_path.write_bytes(data)
    except Exception:
        return None

    return output_path


def _collect_all_dat_files(wxid_dir: Path) -> list[tuple[Path, str]]:
    """收集所有需要解密的.dat文件，返回 (文件路径, md5) 列表"""
    results: list[tuple[Path, str]] = []
    if not wxid_dir or not wxid_dir.exists():
        return results

    # 搜索目录
    search_dirs = [
        wxid_dir / "msg" / "attach",
        wxid_dir / "cache",
    ]

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        try:
            for dat_file in search_dir.rglob("*.dat"):
                if not dat_file.is_file():
                    continue
                # 从文件名提取MD5
                stem = dat_file.stem
                # 文件名格式可能是: md5.dat, md5_t.dat, md5_h.dat 等
                md5 = stem.split("_")[0] if "_" in stem else stem
                # 验证是否是有效的MD5（32位十六进制）
                if len(md5) == 32 and all(c in "0123456789abcdefABCDEF" for c in md5):
                    results.append((dat_file, md5.lower()))
        except Exception as e:
            logger.warning(f"扫描目录失败 {search_dir}: {e}")

    return results


def _decrypt_and_save_resource(
    dat_path: Path,
    md5: str,
    account_dir: Path,
    xor_key: int,
    aes_key: Optional[bytes],
) -> tuple[bool, str]:
    """解密单个资源文件并保存到resource目录

    Returns:
        (success, message)
    """
    try:
        data = dat_path.read_bytes()
        if not data:
            return False, "文件为空"

        version = _detect_wechat_dat_version(data)
        decrypted: Optional[bytes] = None

        if version == 0:
            # V3: 纯XOR解密
            decrypted = _decrypt_wechat_dat_v3(data, xor_key)
        elif version == 1:
            # V4-V1: 使用固定AES密钥
            decrypted = _decrypt_wechat_dat_v4(data, xor_key, b"cfcd208495d565ef")
        elif version == 2:
            # V4-V2: 需要动态AES密钥
            if aes_key and len(aes_key) >= 16:
                decrypted = _decrypt_wechat_dat_v4(data, xor_key, aes_key[:16])
            else:
                return False, "V4-V2版本需要AES密钥"
        else:
            # 尝试简单XOR解密
            dec, mt = _try_xor_decrypt_by_magic(data)
            if dec:
                decrypted = dec
            else:
                return False, f"未知加密版本: {version}"

        if not decrypted:
            return False, "解密结果为空"

        if decrypted.startswith(b"wxgf"):
            converted = _wxgf_to_image_bytes(decrypted)
            if converted:
                decrypted = converted

        # 检测图片类型
        ext = _detect_image_extension(decrypted)
        mt = _detect_image_media_type(decrypted[:32])
        if mt == "application/octet-stream":
            # 解密可能失败，跳过
            return False, "解密后非有效图片"

        # 保存到resource目录
        output_path = _get_decrypted_resource_path(account_dir, md5, ext)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(decrypted)

        return True, str(output_path)
    except Exception as e:
        return False, str(e)


def _convert_silk_to_wav(silk_data: bytes) -> bytes:
    """Convert SILK audio data to WAV format for browser playback."""
    import tempfile

    try:
        import pilk
    except ImportError:
        # If pilk not installed, return original data
        return silk_data

    try:
        # pilk.silk_to_wav works with file paths, so use temp files
        with tempfile.NamedTemporaryFile(suffix=".silk", delete=False) as silk_file:
            silk_file.write(silk_data)
            silk_path = silk_file.name

        wav_path = silk_path.replace(".silk", ".wav")

        try:
            pilk.silk_to_wav(silk_path, wav_path, rate=24000)
            with open(wav_path, "rb") as wav_file:
                wav_data = wav_file.read()
            return wav_data
        finally:
            # Clean up temp files
            import os

            try:
                os.unlink(silk_path)
            except Exception:
                pass
            try:
                os.unlink(wav_path)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"SILK to WAV conversion failed: {e}")
        return silk_data


def _looks_like_mp3(data: bytes) -> bool:
    if not data:
        return False
    if data.startswith(b"ID3"):
        return True
    return len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0


@lru_cache(maxsize=1)
def _find_ffmpeg_executable() -> str:
    import shutil

    env_value = str(os.environ.get("WECHAT_TOOL_FFMPEG") or "").strip()
    if env_value:
        resolved = shutil.which(env_value)
        if resolved:
            return resolved
        candidate = Path(env_value).expanduser()
        if candidate.is_file():
            return str(candidate)

    return shutil.which("ffmpeg") or ""


def _convert_wav_to_mp3(wav_data: bytes) -> bytes:
    import subprocess
    import tempfile

    if not wav_data or not wav_data.startswith(b"RIFF"):
        return b""

    ffmpeg_exe = _find_ffmpeg_executable()
    if not ffmpeg_exe:
        return b""

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            wav_path = tmp_path / "voice.wav"
            mp3_path = tmp_path / "voice.mp3"
            wav_path.write_bytes(wav_data)

            proc = subprocess.run(
                [
                    ffmpeg_exe,
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(wav_path),
                    "-vn",
                    "-codec:a",
                    "libmp3lame",
                    "-q:a",
                    "4",
                    str(mp3_path),
                ],
                check=False,
                capture_output=True,
            )
            if proc.returncode != 0 or not mp3_path.exists():
                err = proc.stderr.decode("utf-8", errors="ignore").strip()
                if err:
                    logger.warning(f"WAV to MP3 conversion failed: {err}")
                return b""

            mp3_data = mp3_path.read_bytes()
            if _looks_like_mp3(mp3_data):
                return mp3_data
    except Exception as e:
        logger.warning(f"WAV to MP3 conversion failed: {e}")

    return b""


def _convert_silk_to_browser_audio(
    silk_data: bytes,
    *,
    preferred_format: str = "mp3",
) -> tuple[bytes, str, str]:
    """Convert SILK audio to a browser-friendly format.

    Returns `(payload, ext, media_type)`.
    Preference order:
      1) MP3 if ffmpeg is available
      2) WAV if SILK decoding succeeds
      3) original SILK bytes as a last-resort fallback
    """

    data = bytes(silk_data or b"")
    if not data:
        return b"", "silk", "audio/silk"

    if _looks_like_mp3(data):
        return data, "mp3", "audio/mpeg"

    wav_data = data if data.startswith(b"RIFF") else _convert_silk_to_wav(data)
    if wav_data.startswith(b"RIFF"):
        if str(preferred_format or "").strip().lower() == "mp3":
            mp3_data = _convert_wav_to_mp3(wav_data)
            if mp3_data:
                return mp3_data, "mp3", "audio/mpeg"
        return wav_data, "wav", "audio/wav"

    return data, "silk", "audio/silk"


def _resolve_media_path_for_kind(
    account_dir: Path,
    kind: str,
    md5: str,
    username: Optional[str],
    allow_fallback_scan: bool = True,
) -> Optional[Path]:
    if not md5:
        return None

    kind_key = str(kind or "").strip().lower()

    # 优先查找解密后的资源目录（图片、表情、视频缩略图）
    if kind_key in {"image", "emoji", "video_thumb"}:
        decrypted_path = _try_find_decrypted_resource(account_dir, md5.lower())
        if decrypted_path:
            logger.debug(f"找到解密资源: {decrypted_path}")
            return decrypted_path

    # 回退到原始逻辑：从微信数据目录查找
    wxid_dir = _resolve_account_wxid_dir(account_dir)
    hardlink_db_path = account_dir / "hardlink.db"
    db_storage_dir = _resolve_account_db_storage_dir(account_dir)

    roots: list[Path] = []
    if wxid_dir:
        roots.append(wxid_dir)
        roots.append(wxid_dir / "msg" / "attach")
        roots.append(wxid_dir / "msg" / "file")
        roots.append(wxid_dir / "msg" / "video")
        roots.append(wxid_dir / "cache")
    if db_storage_dir:
        roots.append(db_storage_dir)
    if not roots:
        return None

    p = _resolve_media_path_from_hardlink(
        hardlink_db_path,
        roots[0],
        md5=str(md5),
        kind=str(kind),
        username=username,
        extra_roots=roots[1:],
    )
    if (not p) and wxid_dir and allow_fallback_scan:
        hit = _fallback_search_media_by_md5(str(wxid_dir), str(md5), kind=kind_key)
        if hit:
            p = Path(hit)
    return p


def _pick_best_emoji_source_path(resolved: Path, md5: str) -> Optional[Path]:
    if not resolved:
        return None
    try:
        if resolved.exists() and resolved.is_file():
            return resolved
    except Exception:
        pass

    try:
        if not (resolved.exists() and resolved.is_dir()):
            return None
    except Exception:
        return None

    md5s = str(md5 or "").lower().strip()
    if not md5s:
        return None

    candidates = [
        f"{md5s}_h.dat",
        f"{md5s}_t.dat",
        f"{md5s}.dat",
    ]
    exts = ["gif", "webp", "png", "jpg", "jpeg"]
    for ext in exts:
        candidates.append(f"{md5s}.{ext}")

    for name in candidates:
        p = resolved / name
        try:
            if p.exists() and p.is_file():
                return p
        except Exception:
            continue

    patterns = [f"{md5s}*.dat", f"{md5s}*", f"*{md5s}*"]
    for pat in patterns:
        try:
            for p in resolved.glob(pat):
                try:
                    if p.is_file():
                        return p
                except Exception:
                    continue
        except Exception:
            continue
    return None


def _iter_emoji_source_candidates(resolved: Path, md5: str, limit: int = 20) -> list[Path]:
    md5s = str(md5 or "").lower().strip()
    if not md5s:
        return []

    best = _pick_best_emoji_source_path(resolved, md5s)
    out: list[Path] = []
    if best:
        out.append(best)

    try:
        if not (resolved.exists() and resolved.is_dir()):
            return out
    except Exception:
        return out

    try:
        files = [p for p in resolved.iterdir() if p.is_file()]
    except Exception:
        files = []

    def score(p: Path) -> tuple[int, int, int]:
        name = str(p.name).lower()
        contains = 1 if md5s in name else 0
        ext = str(p.suffix).lower().lstrip(".")
        ext_rank = 0
        if ext == "dat":
            ext_rank = 3
        elif ext in {"gif", "webp"}:
            ext_rank = 2
        elif ext in {"png", "jpg", "jpeg"}:
            ext_rank = 1
        try:
            sz = int(p.stat().st_size)
        except Exception:
            sz = 0
        return (contains, ext_rank, sz)

    files_sorted = sorted(files, key=score, reverse=True)
    for p in files_sorted:
        if p not in out:
            out.append(p)
        if len(out) >= int(limit):
            break
    return out
