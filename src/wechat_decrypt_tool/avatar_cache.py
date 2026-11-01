from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import time
from email.utils import formatdate
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

from .app_paths import get_output_dir
from .logging_config import get_logger

logger = get_logger(__name__)

AVATAR_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60


def is_avatar_cache_enabled() -> bool:
    v = str(os.environ.get("WECHAT_TOOL_AVATAR_CACHE_ENABLED", "1") or "").strip().lower()
    return v not in {"", "0", "false", "off", "no"}


def get_avatar_cache_root_dir() -> Path:
    return get_output_dir() / "avatar_cache"


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "_", str(value or "").strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "default"


def _account_layout(account: str) -> tuple[Path, Path, Path, Path]:
    account_dir = get_avatar_cache_root_dir() / _safe_segment(account)
    files_dir = account_dir / "files"
    tmp_dir = account_dir / "tmp"
    db_path = account_dir / "avatar_cache.db"
    return account_dir, files_dir, tmp_dir, db_path


def _ensure_account_layout(account: str) -> tuple[Path, Path, Path, Path]:
    account_dir, files_dir, tmp_dir, db_path = _account_layout(account)
    account_dir.mkdir(parents=True, exist_ok=True)
    files_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    return account_dir, files_dir, tmp_dir, db_path


def _connect(account: str) -> sqlite3.Connection:
    _, _, _, db_path = _ensure_account_layout(account)
    conn = sqlite3.connect(str(db_path), timeout=5)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS avatar_cache_entries (
            account TEXT NOT NULL,
            cache_key TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            username TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            source_md5 TEXT NOT NULL DEFAULT '',
            source_update_time INTEGER NOT NULL DEFAULT 0,
            rel_path TEXT NOT NULL DEFAULT '',
            media_type TEXT NOT NULL DEFAULT 'application/octet-stream',
            size_bytes INTEGER NOT NULL DEFAULT 0,
            etag TEXT NOT NULL DEFAULT '',
            last_modified TEXT NOT NULL DEFAULT '',
            fetched_at INTEGER NOT NULL DEFAULT 0,
            checked_at INTEGER NOT NULL DEFAULT 0,
            expires_at INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (account, cache_key)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_avatar_cache_entries_account_username ON avatar_cache_entries(account, username)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_avatar_cache_entries_account_source ON avatar_cache_entries(account, source_kind, source_url)"
    )
    conn.commit()


def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    out: dict[str, Any] = {}
    for k in row.keys():
        out[str(k)] = row[k]
    return out


def normalize_avatar_source_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        p = urlsplit(raw)
    except Exception:
        return raw
    scheme = str(p.scheme or "").lower()
    host = str(p.hostname or "").lower()
    if not scheme or not host:
        return raw
    netloc = host
    if p.port:
        netloc = f"{host}:{int(p.port)}"
    path = p.path or "/"
    return urlunsplit((scheme, netloc, path, p.query or "", ""))


def cache_key_for_avatar_user(username: str) -> str:
    u = str(username or "").strip()
    return hashlib.sha1(f"user:{u}".encode("utf-8", errors="ignore")).hexdigest()


def cache_key_for_avatar_url(url: str) -> str:
    u = normalize_avatar_source_url(url)
    return hashlib.sha1(f"url:{u}".encode("utf-8", errors="ignore")).hexdigest()


def get_avatar_cache_entry(account: str, cache_key: str) -> Optional[dict[str, Any]]:
    if (not is_avatar_cache_enabled()) or (not cache_key):
        return None
    try:
        conn = _connect(account)
    except Exception:
        return None
    try:
        row = conn.execute(
            "SELECT * FROM avatar_cache_entries WHERE account = ? AND cache_key = ? LIMIT 1",
            (str(account or ""), str(cache_key or "")),
        ).fetchone()
        return _row_to_dict(row)
    except Exception:
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_avatar_cache_user_entry(account: str, username: str) -> Optional[dict[str, Any]]:
    if not username:
        return None
    return get_avatar_cache_entry(account, cache_key_for_avatar_user(username))


def get_avatar_cache_url_entry(account: str, source_url: str) -> Optional[dict[str, Any]]:
    if not source_url:
        return None
    return get_avatar_cache_entry(account, cache_key_for_avatar_url(source_url))


def resolve_avatar_cache_entry_path(account: str, entry: Optional[dict[str, Any]]) -> Optional[Path]:
    if not entry:
        return None
    rel = str(entry.get("rel_path") or "").strip().replace("\\", "/")
    if not rel:
        return None
    account_dir, _, _, _ = _account_layout(account)
    p = account_dir / rel
    try:
        account_dir_resolved = account_dir.resolve()
        p_resolved = p.resolve()
        if p_resolved != account_dir_resolved and account_dir_resolved not in p_resolved.parents:
            return None
        return p_resolved
    except Exception:
        return p


def avatar_cache_entry_file_exists(account: str, entry: Optional[dict[str, Any]]) -> Optional[Path]:
    p = resolve_avatar_cache_entry_path(account, entry)
    if not p:
        return None
    try:
        if p.exists() and p.is_file():
            return p
    except Exception:
        return None
    return None


def avatar_cache_entry_is_fresh(entry: Optional[dict[str, Any]], now_ts: Optional[int] = None) -> bool:
    if not entry:
        return False
    try:
        expires = int(entry.get("expires_at") or 0)
    except Exception:
        expires = 0
    if expires <= 0:
        return False
    now0 = int(now_ts or time.time())
    return expires > now0


def _guess_ext(media_type: str) -> str:
    mt = str(media_type or "").strip().lower()
    if mt == "image/jpeg":
        return "jpg"
    if mt == "image/png":
        return "png"
    if mt == "image/gif":
        return "gif"
    if mt == "image/webp":
        return "webp"
    if mt == "image/bmp":
        return "bmp"
    if mt == "image/svg+xml":
        return "svg"
    if mt == "image/avif":
        return "avif"
    if mt.startswith("image/"):
        return mt.split("/", 1)[1].split("+", 1)[0].split(";", 1)[0] or "img"
    return "dat"


def _http_date_from_ts(ts: Optional[int]) -> str:
    try:
        t = int(ts or 0)
    except Exception:
        t = 0
    if t <= 0:
        return ""
    try:
        return formatdate(timeval=float(t), usegmt=True)
    except Exception:
        return ""


def upsert_avatar_cache_entry(
    account: str,
    *,
    cache_key: str,
    source_kind: str,
    username: str = "",
    source_url: str = "",
    source_md5: str = "",
    source_update_time: int = 0,
    rel_path: str = "",
    media_type: str = "application/octet-stream",
    size_bytes: int = 0,
    etag: str = "",
    last_modified: str = "",
    fetched_at: Optional[int] = None,
    checked_at: Optional[int] = None,
    expires_at: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    if (not is_avatar_cache_enabled()) or (not cache_key):
        return None

    acct = str(account or "").strip()
    ck = str(cache_key or "").strip()
    sk = str(source_kind or "").strip().lower()
    if not acct or not ck or not sk:
        return None

    source_url_norm = normalize_avatar_source_url(source_url) if source_url else ""

    now_ts = int(time.time())
    fetched = int(fetched_at if fetched_at is not None else now_ts)
    checked = int(checked_at if checked_at is not None else now_ts)
    expire_ts = int(expires_at if expires_at is not None else (checked + AVATAR_CACHE_TTL_SECONDS))

    try:
        conn = _connect(acct)
    except Exception as e:
        logger.warning(f"[avatar_cache_error] open db failed account={acct} err={e}")
        return None
    try:
        conn.execute(
            """
            INSERT INTO avatar_cache_entries (
                account, cache_key, source_kind, username, source_url,
                source_md5, source_update_time, rel_path, media_type, size_bytes,
                etag, last_modified, fetched_at, checked_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account, cache_key) DO UPDATE SET
                source_kind=excluded.source_kind,
                username=excluded.username,
                source_url=excluded.source_url,
                source_md5=excluded.source_md5,
                source_update_time=excluded.source_update_time,
                rel_path=excluded.rel_path,
                media_type=excluded.media_type,
                size_bytes=excluded.size_bytes,
                etag=excluded.etag,
                last_modified=excluded.last_modified,
                fetched_at=excluded.fetched_at,
                checked_at=excluded.checked_at,
                expires_at=excluded.expires_at
            """,
            (
                acct,
                ck,
                sk,
                str(username or "").strip(),
                source_url_norm,
                str(source_md5 or "").strip().lower(),
                int(source_update_time or 0),
                str(rel_path or "").strip().replace("\\", "/"),
                str(media_type or "application/octet-stream").strip() or "application/octet-stream",
                int(size_bytes or 0),
                str(etag or "").strip(),
                str(last_modified or "").strip(),
                fetched,
                checked,
                expire_ts,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM avatar_cache_entries WHERE account = ? AND cache_key = ? LIMIT 1",
            (acct, ck),
        ).fetchone()
        return _row_to_dict(row)
    except Exception as e:
        logger.warning(f"[avatar_cache_error] upsert failed account={acct} cache_key={ck} err={e}")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def touch_avatar_cache_entry(account: str, cache_key: str, *, ttl_seconds: int = AVATAR_CACHE_TTL_SECONDS) -> bool:
    if (not is_avatar_cache_enabled()) or (not cache_key):
        return False
    now_ts = int(time.time())
    try:
        conn = _connect(account)
    except Exception:
        return False
    try:
        conn.execute(
            "UPDATE avatar_cache_entries SET checked_at = ?, expires_at = ? WHERE account = ? AND cache_key = ?",
            (now_ts, now_ts + max(60, int(ttl_seconds or AVATAR_CACHE_TTL_SECONDS)), str(account or ""), str(cache_key or "")),
        )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def write_avatar_cache_payload(
    account: str,
    *,
    source_kind: str,
    username: str = "",
    source_url: str = "",
    payload: bytes,
    media_type: str,
    source_md5: str = "",
    source_update_time: int = 0,
    etag: str = "",
    last_modified: str = "",
    ttl_seconds: int = AVATAR_CACHE_TTL_SECONDS,
) -> tuple[Optional[dict[str, Any]], Optional[Path]]:
    if (not is_avatar_cache_enabled()) or (not payload):
        return None, None

    acct = str(account or "").strip()
    sk = str(source_kind or "").strip().lower()
    if not acct or sk not in {"user", "url"}:
        return None, None

    source_url_norm = normalize_avatar_source_url(source_url) if source_url else ""
    if sk == "user":
        cache_key = cache_key_for_avatar_user(username)
    else:
        cache_key = cache_key_for_avatar_url(source_url_norm)

    digest = hashlib.sha1(bytes(payload)).hexdigest()
    ext = _guess_ext(media_type)
    rel_path = f"files/{digest[:2]}/{digest}.{ext}"

    try:
        account_dir, _, tmp_dir, _ = _ensure_account_layout(acct)
    except Exception as e:
        logger.warning(f"[avatar_cache_error] ensure dirs failed account={acct} err={e}")
        return None, None

    abs_path = account_dir / rel_path
    try:
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        if (not abs_path.exists()) or (int(abs_path.stat().st_size) != len(payload)):
            tmp_path = tmp_dir / f"{digest}.{time.time_ns()}.tmp"
            tmp_path.write_bytes(payload)
            os.replace(str(tmp_path), str(abs_path))
    except Exception as e:
        logger.warning(f"[avatar_cache_error] write file failed account={acct} path={abs_path} err={e}")
        return None, None

    if (not etag) and digest:
        etag = f'"{digest}"'
    if (not last_modified) and source_update_time:
        last_modified = _http_date_from_ts(source_update_time)
    if not last_modified:
        last_modified = _http_date_from_ts(int(time.time()))

    entry = upsert_avatar_cache_entry(
        acct,
        cache_key=cache_key,
        source_kind=sk,
        username=username,
        source_url=source_url_norm,
        source_md5=source_md5,
        source_update_time=int(source_update_time or 0),
        rel_path=rel_path,
        media_type=media_type,
        size_bytes=len(payload),
        etag=etag,
        last_modified=last_modified,
        fetched_at=int(time.time()),
        checked_at=int(time.time()),
        expires_at=int(time.time()) + max(60, int(ttl_seconds or AVATAR_CACHE_TTL_SECONDS)),
    )
    if not entry:
        return None, None
    return entry, abs_path


def build_avatar_cache_response_headers(
    entry: Optional[dict[str, Any]], *, max_age: int = AVATAR_CACHE_TTL_SECONDS
) -> dict[str, str]:
    headers: dict[str, str] = {
        "Cache-Control": f"public, max-age={int(max_age)}",
    }
    if not entry:
        return headers
    etag = str(entry.get("etag") or "").strip()
    last_modified = str(entry.get("last_modified") or "").strip()
    if etag:
        headers["ETag"] = etag
    if last_modified:
        headers["Last-Modified"] = last_modified
    return headers

