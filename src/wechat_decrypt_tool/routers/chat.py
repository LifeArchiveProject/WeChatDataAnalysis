import os
import re
import sqlite3
import asyncio
import json
import time
import threading
from datetime import datetime, timedelta
from os import scandir
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from ..logging_config import get_logger
from ..chat_search_index import (
    get_chat_search_index_db_path,
    get_chat_search_index_status,
    start_chat_search_index_build,
)
from ..chat_helpers import (
    _build_avatar_url,
    _build_latest_message_preview,
    _build_fts_query,
    _decode_message_content,
    _decode_sqlite_text,
    _extract_md5_from_packed_info,
    _extract_sender_from_group_xml,
    _extract_xml_attr,
    _extract_xml_tag_or_attr,
    _extract_xml_tag_text,
    _format_session_time,
    _infer_last_message_brief,
    _infer_message_brief_by_local_type,
    _infer_transfer_status_text,
    _iter_message_db_paths,
    _list_decrypted_accounts,
    _make_search_tokens,
    _make_snippet,
    _match_tokens,
    _load_contact_rows,
    _load_group_nickname_map_from_contact_db,
    _load_usernames_by_display_names,
    _load_latest_message_previews,
    _build_group_sender_display_name_map,
    _normalize_session_preview_text,
    _extract_group_preview_sender_username,
    _replace_preview_sender_prefix,
    _lookup_resource_md5,
    _normalize_xml_url,
    _parse_app_message,
    _parse_system_message_content,
    _parse_pat_message,
    _pick_display_name,
    _query_head_image_usernames,
    _quote_ident,
    _resolve_account_dir,
    _resolve_msg_table_name,
    _resolve_msg_table_name_by_map,
    _row_to_search_hit,
    _resource_lookup_chat_id,
    _should_keep_session,
    _split_group_sender_prefix,
    _to_char_token_text,
)
from ..media_helpers import _resolve_account_db_storage_dir, _try_find_decrypted_resource
from .. import chat_edit_store
from ..path_fix import PathFixRoute
from ..session_last_message import (
    build_session_last_message_table,
    get_session_last_message_status,
    load_session_last_messages,
)
from ..wcdb_realtime import (
    WCDBRealtimeError,
    WCDB_REALTIME,
    exec_query as _wcdb_exec_query,
    get_avatar_urls as _wcdb_get_avatar_urls,
    get_display_names as _wcdb_get_display_names,
    get_group_members as _wcdb_get_group_members,
    get_group_nicknames as _wcdb_get_group_nicknames,
    get_messages as _wcdb_get_messages,
    get_sessions as _wcdb_get_sessions,
    update_message as _wcdb_update_message,
)

logger = get_logger(__name__)

_DEBUG_SESSIONS = os.environ.get("WECHAT_TOOL_DEBUG_SESSIONS", "0") == "1"

router = APIRouter(route_class=PathFixRoute)

_REALTIME_SYNC_MU = threading.Lock()
_REALTIME_SYNC_LOCKS: dict[tuple[str, str], threading.Lock] = {}
_REALTIME_SYNC_ALL_LOCKS: dict[str, threading.Lock] = {}


def _is_hex_md5(value: Any) -> bool:
    s = str(value or "").strip().lower()
    return len(s) == 32 and all(c in "0123456789abcdef" for c in s)


_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


def _hex_to_bytes(value: str) -> Optional[bytes]:
    s = str(value or "").strip()
    if not s.startswith("0x"):
        return None
    hex_part = s[2:]
    if (not hex_part) or (len(hex_part) % 2 != 0) or (_HEX_RE.match(hex_part) is None):
        return None
    try:
        return bytes.fromhex(hex_part)
    except Exception:
        return None


def _bytes_to_hex(value: bytes) -> str:
    return "0x" + value.hex()


def _is_mostly_printable_text(s: str) -> bool:
    if not s:
        return False
    sample = s[:600]
    if not sample:
        return False
    printable = sum(1 for ch in sample if ch.isprintable() or ch in {"\n", "\r", "\t"})
    return (printable / len(sample)) >= 0.85


def _jsonify_db_value(key: str, value: Any) -> Any:
    """Convert sqlite row values into JSON-friendly values (best-effort)."""
    if value is None:
        return None
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, (bytes, bytearray)):
        b = bytes(value)
        k = str(key or "").strip().lower()
        if k in {"compress_content", "packed_info_data", "packed_info", "packedinfo", "packedinfodata"} or k.endswith(
            "_data"
        ):
            return _bytes_to_hex(b)
        if not b:
            return ""
        try:
            s = b.decode("utf-8")
            if _is_mostly_printable_text(s):
                return s
        except Exception:
            pass
        return _bytes_to_hex(b)
    if isinstance(value, (int, float, bool, str)):
        return value
    try:
        return str(value)
    except Exception:
        return None


def _sql_literal(value: Any) -> str:
    """Build a SQLite literal for WCDB exec_query (no parameters supported)."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        try:
            return str(int(value))
        except Exception:
            return "0"
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, (bytes, bytearray)):
        b = bytes(value)
        return "X'" + b.hex() + "'"
    s = str(value)
    return "'" + s.replace("'", "''") + "'"


def _normalize_edit_value(col: str, value: Any, *, from_snapshot: bool = False) -> Any:
    c = str(col or "").strip().lower()
    if value is None:
        return None
    if isinstance(value, str):
        # Allow editing BLOBs via 0x... hex strings (unsafe only, enforced elsewhere).
        b = _hex_to_bytes(value)
        if b is not None:
            return b

        # Some WCDB exec_query snapshots return raw BLOBs as bare hex strings (without 0x prefix).
        # When restoring from snapshots (reset), convert them back to bytes so SQLite stores them as BLOB again.
        want_blob_hex = (
            c in {"packed_info_data", "packed_info", "packedinfo", "packedinfodata"}
            or c.endswith("_data")
            or c in {"source"}
            or (from_snapshot and c in {"message_content", "compress_content"})
        )
        if want_blob_hex:
            s = value.strip()
            # Heuristic for message_content: avoid converting legitimate short "hex-like" text messages.
            min_len = 0
            if c == "message_content":
                s_lower = s.lower()
                # zstd frame magic: 28 b5 2f fd
                if s_lower.startswith("28b52ffd"):
                    min_len = 16
                else:
                    min_len = 64
            if s and (len(s) >= min_len) and (len(s) % 2 == 0) and (_HEX_RE.fullmatch(s) is not None):
                try:
                    return bytes.fromhex(s)
                except Exception:
                    return value
        if c in {
            "local_id",
            "create_time",
            "server_id",
            "local_type",
            "sort_seq",
        } or c.startswith("wcdb_ct_"):
            s = value.strip()
            if s and re.fullmatch(r"-?\d+", s):
                try:
                    return int(s)
                except Exception:
                    return value
    return value


def _is_safe_edit_column(col: str, *, unsafe: bool) -> bool:
    if unsafe:
        return True
    c = str(col or "").strip().lower()
    if not c:
        return False
    if c == "local_id":
        return False
    if c.startswith("wcdb_ct_"):
        return False
    if c in {"compress_content", "packed_info_data", "packed_info"}:
        return False
    return True


def _pb_read_varint(buf: bytes, i: int) -> tuple[int, int]:
    """Read a protobuf varint from buf starting at i, returning (value, next_index)."""
    x = 0
    shift = 0
    while i < len(buf) and shift < 64:
        b = buf[i]
        i += 1
        x |= (b & 0x7F) << shift
        if (b & 0x80) == 0:
            return x, i
        shift += 7
    raise ValueError("Invalid varint.")


def _pb_write_varint(x: int) -> bytes:
    """Write a protobuf varint for a non-negative integer."""
    n = int(x or 0)
    if n < 0:
        raise ValueError("Negative varint.")
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def _swap_packed_info_from_to(packed: bytes | bytearray | memoryview) -> tuple[bytes, int, int]:
    """Swap protobuf field #1 and #2 varint values in packed_info_data.

    Empirically, WeChat uses packed_info_data as a tiny protobuf containing at least:
    - field 1: fromId (Name2Id rowid)
    - field 2: toId   (Name2Id rowid)

    Swapping these flips message direction in the WeChat client.
    Returns (new_bytes, old_field1, old_field2).
    """
    if isinstance(packed, memoryview):
        data = packed.tobytes()
    else:
        data = bytes(packed)
    if not data:
        raise ValueError("Empty packed_info_data.")

    # Pass 1: find the first occurrences of field 1/2 varints.
    i = 0
    v1: Optional[int] = None
    v2: Optional[int] = None
    while i < len(data):
        key, i = _pb_read_varint(data, i)
        field_num = key >> 3
        wire = key & 7
        if wire == 0:
            val, i = _pb_read_varint(data, i)
            if field_num == 1 and v1 is None:
                v1 = int(val)
            elif field_num == 2 and v2 is None:
                v2 = int(val)
            continue
        if wire == 1:
            i += 8
            continue
        if wire == 2:
            ln, i = _pb_read_varint(data, i)
            i += int(ln)
            continue
        if wire == 5:
            i += 4
            continue
        raise ValueError(f"Unsupported wire type: {wire}")

    if v1 is None or v2 is None:
        raise ValueError("packed_info_data does not contain field #1 and #2 varints.")

    # Pass 2: rebuild and swap values for all field 1/2 varints.
    i = 0
    out = bytearray()
    while i < len(data):
        key, i2 = _pb_read_varint(data, i)
        field_num = key >> 3
        wire = key & 7
        out += _pb_write_varint(key)
        i = i2

        if wire == 0:
            val, i = _pb_read_varint(data, i)
            if field_num == 1:
                val = int(v2)
            elif field_num == 2:
                val = int(v1)
            out += _pb_write_varint(int(val))
            continue
        if wire == 1:
            out += data[i : i + 8]
            i += 8
            continue
        if wire == 2:
            ln, i = _pb_read_varint(data, i)
            out += _pb_write_varint(int(ln))
            out += data[i : i + int(ln)]
            i += int(ln)
            continue
        if wire == 5:
            out += data[i : i + 4]
            i += 4
            continue
        raise ValueError(f"Unsupported wire type: {wire}")

    return bytes(out), int(v1), int(v2)


def _avatar_url_unified(
    *,
    account_dir: Path,
    username: str,
    local_avatar_usernames: set[str] | None = None,
) -> str:
    u = str(username or "").strip()
    if not u:
        return ""
    # Unified avatar entrypoint: backend decides local db vs remote fallback + cache.
    return _build_avatar_url(str(account_dir.name or ""), u)


def _load_group_nickname_map_from_wcdb(
    *,
    account_dir: Path,
    chatroom_id: str,
    sender_usernames: list[str],
    rt_conn=None,
) -> dict[str, str]:
    chatroom = str(chatroom_id or "").strip()
    if not chatroom.endswith("@chatroom"):
        return {}

    targets = list(dict.fromkeys([str(x or "").strip() for x in sender_usernames if str(x or "").strip()]))
    if not targets:
        return {}

    try:
        wcdb_conn = rt_conn or WCDB_REALTIME.ensure_connected(account_dir)
    except Exception:
        return {}

    target_set = set(targets)
    out: dict[str, str] = {}

    try:
        with wcdb_conn.lock:
            nickname_map = _wcdb_get_group_nicknames(wcdb_conn.handle, chatroom)
        for username, nickname in (nickname_map or {}).items():
            su = str(username or "").strip()
            nn = str(nickname or "").strip()
            if su and nn and su in target_set:
                out[su] = nn
    except Exception:
        pass

    unresolved = [u for u in targets if u not in out]
    if not unresolved:
        return out

    try:
        with wcdb_conn.lock:
            members = _wcdb_get_group_members(wcdb_conn.handle, chatroom)
    except Exception:
        return out

    if not members:
        return out

    unresolved_set = set(unresolved)
    for member in members:
        try:
            username = str(member.get("username") or "").strip()
        except Exception:
            username = ""
        if (not username) or (username not in unresolved_set):
            continue

        nickname = ""
        for key in ("nickname", "displayName", "remark", "originalName"):
            try:
                candidate = str(member.get(key) or "").strip()
            except Exception:
                candidate = ""
            if candidate:
                nickname = candidate
                break
        if nickname:
            out[username] = nickname

    return out


def _load_group_nickname_map(
    *,
    account_dir: Path,
    contact_db_path: Path,
    chatroom_id: str,
    sender_usernames: list[str],
    rt_conn=None,
) -> dict[str, str]:
    """Resolve group member nickname (group card) via WCDB and contact.db ext_buffer (best-effort)."""

    contact_map: dict[str, str] = {}
    try:
        contact_map = _load_group_nickname_map_from_contact_db(
            contact_db_path,
            chatroom_id,
            sender_usernames,
        )
    except Exception:
        contact_map = {}

    wcdb_map: dict[str, str] = {}
    try:
        wcdb_map = _load_group_nickname_map_from_wcdb(
            account_dir=account_dir,
            chatroom_id=chatroom_id,
            sender_usernames=sender_usernames,
            rt_conn=rt_conn,
        )
    except Exception:
        wcdb_map = {}

    if not contact_map and not wcdb_map:
        return {}

    # Merge: WCDB wins (newer DLLs may provide higher-quality group nicknames).
    merged: dict[str, str] = {}
    merged.update(contact_map)
    merged.update(wcdb_map)
    return merged


def _resolve_sender_display_name(
    *,
    sender_username: str,
    sender_contact_rows: dict[str, sqlite3.Row],
    wcdb_display_names: dict[str, str],
    group_nicknames: Optional[dict[str, str]] = None,
) -> str:
    su = str(sender_username or "").strip()
    if not su:
        return ""

    gn = str((group_nicknames or {}).get(su) or "").strip()
    if gn:
        return gn

    row = sender_contact_rows.get(su)
    display_name = _pick_display_name(row, su)
    if display_name == su:
        wd = str(wcdb_display_names.get(su) or "").strip()
        if wd and wd != su:
            display_name = wd
    return display_name


def _realtime_sync_lock(account: str, username: str) -> threading.Lock:
    key = (str(account or "").strip(), str(username or "").strip())
    with _REALTIME_SYNC_MU:
        lock = _REALTIME_SYNC_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _REALTIME_SYNC_LOCKS[key] = lock
        return lock


def _realtime_sync_all_lock(account: str) -> threading.Lock:
    key = str(account or "").strip()
    with _REALTIME_SYNC_MU:
        lock = _REALTIME_SYNC_ALL_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _REALTIME_SYNC_ALL_LOCKS[key] = lock
        return lock


def _normalize_chat_source(value: Optional[str]) -> str:
    v = str(value or "").strip().lower()
    if not v or v in {"decrypted", "local", "sqlite"}:
        return "decrypted"
    if v in {"realtime", "real-time", "wcdb"}:
        return "realtime"
    raise HTTPException(status_code=400, detail="Invalid source, use 'decrypted' or 'realtime'.")


def _lookup_contact_alias(
    conn: Optional[sqlite3.Connection],
    cache: dict[str, str],
    username: str,
) -> str:
    u = str(username or "").strip()
    if not u or conn is None:
        return ""
    if u in cache:
        return cache[u]

    alias = ""
    try:
        r = conn.execute("SELECT alias FROM contact WHERE username = ? LIMIT 1", (u,)).fetchone()
        if r is not None and r[0] is not None:
            alias = str(r[0] or "").strip()
        if not alias:
            r = conn.execute("SELECT alias FROM stranger WHERE username = ? LIMIT 1", (u,)).fetchone()
            if r is not None and r[0] is not None:
                alias = str(r[0] or "").strip()
    except Exception:
        alias = ""

    cache[u] = alias
    return alias


def _scan_db_storage_mtime_ns(db_storage_dir: Path) -> int:
    try:
        base = str(db_storage_dir)
    except Exception:
        return 0

    max_ns = 0
    try:
        for root, dirs, files in os.walk(base):
            # Most installs keep databases under these buckets.
            if root == base:
                allow = {"message", "session", "contact", "head_image", "bizchat", "sns", "general", "favorite"}
                dirs[:] = [d for d in dirs if str(d or "").lower() in allow]

            for fn in files:
                name = str(fn or "").lower()
                if not name.endswith((".db", ".db-wal", ".db-shm")):
                    continue
                if not (
                    ("message" in name)
                    or ("session" in name)
                    or ("contact" in name)
                    or ("name2id" in name)
                    or ("head_image" in name)
                ):
                    continue

                try:
                    st = os.stat(os.path.join(root, fn))
                    m_ns = int(getattr(st, "st_mtime_ns", 0) or 0)
                    if m_ns <= 0:
                        m_ns = int(float(getattr(st, "st_mtime", 0.0) or 0.0) * 1_000_000_000)
                    if m_ns > max_ns:
                        max_ns = m_ns
                except Exception:
                    continue
    except Exception:
        return 0

    return max_ns


@router.get("/api/chat/realtime/status", summary="实时模式状态")
async def get_chat_realtime_status(account: Optional[str] = None):
    """检查当前账号是否具备实时模式条件（dll/密钥/db_storage）以及是否已连接。"""
    account_dir = _resolve_account_dir(account)
    info = WCDB_REALTIME.get_status(account_dir)
    available = bool(info.get("dll_present") and info.get("key_present") and info.get("db_storage_dir"))
    return {
        "status": "success",
        "account": account_dir.name,
        "available": available,
        "realtime": info,
    }


@router.get("/api/chat/realtime/stream", summary="实时模式数据库变更事件（SSE）")
async def stream_chat_realtime_events(
    request: Request,
    account: Optional[str] = None,
    interval_ms: int = 500,
):
    """监听 db_storage 目录的变更，通过 SSE 推送事件（用于前端触发增量刷新）。"""
    if interval_ms < 100:
        interval_ms = 100
    if interval_ms > 5000:
        interval_ms = 5000

    account_dir = _resolve_account_dir(account)
    info = WCDB_REALTIME.get_status(account_dir)
    db_storage_dir = Path(str(info.get("db_storage_dir") or "").strip())
    if not db_storage_dir.exists() or not db_storage_dir.is_dir():
        raise HTTPException(status_code=400, detail="db_storage directory not found for this account.")

    logger.info(
        "[realtime] SSE stream open account=%s interval_ms=%s db_storage=%s",
        account_dir.name,
        int(interval_ms),
        str(db_storage_dir),
    )

    async def gen():
        last_mtime_ns = 0
        last_heartbeat = 0.0

        # initial snapshot
        initial = {
            "type": "ready",
            "account": account_dir.name,
            "dbStorageDir": str(db_storage_dir),
            "ts": int(time.time() * 1000),
        }
        yield f"data: {json.dumps(initial, ensure_ascii=False)}\n\n"

        try:
            while True:
                if await request.is_disconnected():
                    break

                # Avoid blocking the event loop on a potentially large directory walk.
                scan_t0 = time.perf_counter()
                try:
                    mtime_ns = await asyncio.to_thread(_scan_db_storage_mtime_ns, db_storage_dir)
                except Exception:
                    mtime_ns = 0
                scan_ms = (time.perf_counter() - scan_t0) * 1000.0
                if scan_ms > 1000:
                    logger.warning("[realtime] SSE scan slow account=%s ms=%.1f", account_dir.name, scan_ms)

                if mtime_ns and mtime_ns != last_mtime_ns:
                    last_mtime_ns = mtime_ns
                    payload = {
                        "type": "change",
                        "account": account_dir.name,
                        "mtimeNs": int(mtime_ns),
                        "ts": int(time.time() * 1000),
                    }
                    logger.info("[realtime] SSE change account=%s mtime_ns=%s", account_dir.name, int(mtime_ns))
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

                now = time.time()
                if now - last_heartbeat > 15:
                    last_heartbeat = now
                    yield ": ping\n\n"

                await asyncio.sleep(interval_ms / 1000.0)
        finally:
            logger.info("[realtime] SSE stream closed account=%s", account_dir.name)

    headers = {"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)


def _resolve_decrypted_message_table(account_dir: Path, username: str) -> Optional[tuple[Path, str]]:
    db_paths = _iter_message_db_paths(account_dir)
    if not db_paths:
        return None

    for db_path in db_paths:
        conn = sqlite3.connect(str(db_path))
        try:
            table_name = _resolve_msg_table_name(conn, username)
            if table_name:
                return db_path, table_name
        finally:
            conn.close()

    return None


def _local_month_range_epoch_seconds(*, year: int, month: int) -> tuple[int, int]:
    """Return [start, end) range as epoch seconds for local time month boundaries.

    Notes:
    - Uses local midnight boundaries (not +86400 * days) to stay DST-safe.
    - Returned timestamps are integers (seconds).
    """

    start = datetime(int(year), int(month), 1)
    if int(month) == 12:
        end = datetime(int(year) + 1, 1, 1)
    else:
        end = datetime(int(year), int(month) + 1, 1)
    return int(start.timestamp()), int(end.timestamp())


def _local_day_range_epoch_seconds(*, date_str: str) -> tuple[int, int, str]:
    """Return [start, end) range as epoch seconds for local date boundaries.

    Returns the normalized `YYYY-MM-DD` date string as the 3rd element.
    """

    d0 = datetime.strptime(str(date_str or "").strip(), "%Y-%m-%d")
    d1 = d0 + timedelta(days=1)
    return int(d0.timestamp()), int(d1.timestamp()), d0.strftime("%Y-%m-%d")


def _pick_message_db_for_new_table(account_dir: Path, username: str) -> Optional[Path]:
    """Pick a target decrypted sqlite db to place a new Msg_<md5> table.

    Some accounts have both `message_*.db` and `biz_message_*.db`. For normal users we prefer
    `message*.db`; for official accounts (`gh_`) we prefer `biz_message*.db`.
    """

    db_paths = _iter_message_db_paths(account_dir)
    if not db_paths:
        return None

    uname = str(username or "").strip()
    want_biz = bool(uname and uname.startswith("gh_"))

    msg_paths: list[Path] = []
    biz_paths: list[Path] = []
    other_paths: list[Path] = []
    for p in db_paths:
        ln = p.name.lower()
        if re.match(r"^message(_\d+)?\.db$", ln):
            msg_paths.append(p)
        elif re.match(r"^biz_message(_\d+)?\.db$", ln):
            biz_paths.append(p)
        else:
            other_paths.append(p)

    if want_biz and biz_paths:
        return biz_paths[0]
    if msg_paths:
        return msg_paths[0]
    if biz_paths:
        return biz_paths[0]
    return other_paths[0] if other_paths else db_paths[0]


def _ensure_decrypted_message_table(account_dir: Path, username: str) -> tuple[Path, str]:
    """Ensure the decrypted sqlite has a Msg_<md5(username)> table for this conversation.

    Why:
    - The decrypted snapshot can miss newly created sessions, so WCDB realtime can show messages
      while the decrypted message_*.db has no table -> `/api/chat/messages` returns empty.
    - Realtime sync should be able to create the missing conversation table and then insert rows.
    """

    uname = str(username or "").strip()
    if not uname:
        raise HTTPException(status_code=400, detail="Missing username.")

    resolved = _resolve_decrypted_message_table(account_dir, uname)
    if resolved:
        return resolved

    target_db = _pick_message_db_for_new_table(account_dir, uname)
    if target_db is None:
        raise HTTPException(status_code=404, detail="No message databases found for this account.")

    # Use the conventional WeChat naming (`Msg_<md5>`). Resolution is case-insensitive.
    import hashlib

    md5_hex = hashlib.md5(uname.encode("utf-8")).hexdigest()
    table_name = f"Msg_{md5_hex}"
    quoted_table = _quote_ident(table_name)

    conn = sqlite3.connect(str(target_db))
    try:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {quoted_table}(
                local_id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id INTEGER,
                local_type INTEGER,
                sort_seq INTEGER,
                real_sender_id INTEGER,
                create_time INTEGER,
                status INTEGER,
                upload_status INTEGER,
                download_status INTEGER,
                server_seq INTEGER,
                origin_source INTEGER,
                source TEXT,
                message_content TEXT,
                compress_content TEXT,
                packed_info_data BLOB,
                WCDB_CT_message_content INTEGER DEFAULT NULL,
                WCDB_CT_source INTEGER DEFAULT NULL
            )
            """
        )

        # Match the common indexes we observe on existing Msg_* tables for query performance.
        idx_sender = _quote_ident(f"{table_name}_SENDERID")
        idx_server = _quote_ident(f"{table_name}_SERVERID")
        idx_sort = _quote_ident(f"{table_name}_SORTSEQ")
        idx_type_seq = _quote_ident(f"{table_name}_TYPE_SEQ")
        conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_sender} ON {quoted_table}(real_sender_id)")
        conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_server} ON {quoted_table}(server_id)")
        conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_sort} ON {quoted_table}(sort_seq)")
        conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_type_seq} ON {quoted_table}(local_type, sort_seq)")

        conn.commit()
    finally:
        conn.close()

    return target_db, table_name


def _ensure_decrypted_message_tables(
    account_dir: Path, usernames: list[str]
) -> dict[str, tuple[Path, str]]:
    """Bulk resolver that also creates missing Msg_<md5> tables when needed."""

    table_map = _resolve_decrypted_message_tables(account_dir, usernames)
    for u in usernames:
        uname = str(u or "").strip()
        if not uname or uname in table_map:
            continue
        try:
            table_map[uname] = _ensure_decrypted_message_table(account_dir, uname)
        except Exception:
            # Best-effort: if we can't create the table, keep it missing and let callers skip.
            continue
    return table_map


def _resolve_decrypted_message_tables(
    account_dir: Path, usernames: list[str]
) -> dict[str, tuple[Path, str]]:
    uniq = list(dict.fromkeys([str(u or "").strip() for u in usernames if str(u or "").strip()]))
    if not uniq:
        return {}

    db_paths = _iter_message_db_paths(account_dir)
    if not db_paths:
        return {}

    remaining = {u for u in uniq if u}
    resolved: dict[str, tuple[Path, str]] = {}
    for db_path in db_paths:
        if not remaining:
            break
        try:
            conn = sqlite3.connect(str(db_path))
        except Exception:
            continue
        try:
            try:
                rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                names = [str(r[0]) for r in rows if r and r[0]]
                lower_to_actual = {n.lower(): n for n in names}
            except Exception:
                continue

            found: dict[str, str] = {}
            for u in list(remaining):
                try:
                    tn = _resolve_msg_table_name_by_map(lower_to_actual, u)
                except Exception:
                    tn = None
                if tn:
                    found[u] = tn
            for u, tn in found.items():
                resolved[u] = (db_path, tn)
                remaining.discard(u)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    return resolved


def _ensure_session_last_message_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session_last_message (
            username TEXT PRIMARY KEY,
            sort_seq INTEGER NOT NULL DEFAULT 0,
            local_id INTEGER NOT NULL DEFAULT 0,
            create_time INTEGER NOT NULL DEFAULT 0,
            local_type INTEGER NOT NULL DEFAULT 0,
            sender_username TEXT NOT NULL DEFAULT '',
            preview TEXT NOT NULL DEFAULT '',
            db_stem TEXT NOT NULL DEFAULT '',
            table_name TEXT NOT NULL DEFAULT '',
            built_at INTEGER NOT NULL DEFAULT 0
        )
        """
    )


def _get_session_table_columns(conn: sqlite3.Connection) -> set[str]:
    try:
        rows = conn.execute("PRAGMA table_info(SessionTable)").fetchall()
        # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
        cols = {str(r[1]) for r in rows if r and r[1]}
        return cols
    except Exception:
        return set()


def _upsert_session_table_rows(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    """Best-effort upsert of WCDB Session rows into decrypted session.db::SessionTable.

    Why:
    - WCDB realtime can observe newly created sessions (e.g., new friends) immediately.
    - The decrypted snapshot's session.db can become stale and miss those sessions entirely, causing
      the left sidebar list to differ after a refresh (when the UI falls back to decrypted).

    This upsert intentionally avoids depending on message tables; it only keeps SessionTable fresh.
    """

    if not rows:
        return

    # Ensure SessionTable exists; if not, silently skip (older/partial accounts).
    try:
        conn.execute("SELECT 1 FROM SessionTable LIMIT 1").fetchone()
    except Exception:
        return

    cols = _get_session_table_columns(conn)
    if "username" not in cols:
        return

    uniq_usernames: list[str] = []
    for r in rows:
        u = str((r or {}).get("username") or "").strip()
        if not u:
            continue
        uniq_usernames.append(u)
    uniq_usernames = list(dict.fromkeys(uniq_usernames))
    if not uniq_usernames:
        return

    # Insert missing rows first so UPDATE always has a target.
    try:
        conn.executemany(
            "INSERT OR IGNORE INTO SessionTable(username) VALUES (?)",
            [(u,) for u in uniq_usernames],
        )
    except Exception:
        # If the schema is unusual, don't fail the whole sync.
        return

    # Only update columns that exist in this account's schema.
    # Keep the order stable so executemany parameters line up.
    desired_cols = [
        "unread_count",
        "is_hidden",
        "summary",
        "draft",
        "last_timestamp",
        "sort_timestamp",
        "last_msg_locald_id",
        "last_msg_type",
        "last_msg_sub_type",
        "last_msg_sender",
        "last_sender_display_name",
    ]
    update_cols = [c for c in desired_cols if c in cols]
    if not update_cols:
        return

    def _int(v: Any) -> int:
        try:
            return int(v or 0)
        except Exception:
            return 0

    def _text(v: Any) -> str:
        try:
            return str(v or "")
        except Exception:
            return ""

    params: list[tuple[Any, ...]] = []
    for r in rows:
        u = str((r or {}).get("username") or "").strip()
        if not u:
            continue
        values: list[Any] = []
        for c in update_cols:
            if c in {
                "unread_count",
                "is_hidden",
                "last_timestamp",
                "sort_timestamp",
                "last_msg_locald_id",
                "last_msg_type",
                "last_msg_sub_type",
            }:
                values.append(_int((r or {}).get(c)))
            else:
                values.append(_text((r or {}).get(c)))
        values.append(u)
        params.append(tuple(values))

    if not params:
        return

    set_expr = ", ".join([f"{c} = ?" for c in update_cols])
    conn.executemany(f"UPDATE SessionTable SET {set_expr} WHERE username = ?", params)


def _load_session_last_message_times(conn: sqlite3.Connection, usernames: list[str]) -> dict[str, int]:
    """Load last synced message create_time per conversation from session.db::session_last_message.

    Note: This is used as the *sync watermark* for realtime -> decrypted, because SessionTable timestamps may be
    updated from WCDB session rows for UI consistency.
    """

    uniq = list(dict.fromkeys([str(u or "").strip() for u in usernames if str(u or "").strip()]))
    if not uniq:
        return {}

    out: dict[str, int] = {}
    chunk_size = 900
    for i in range(0, len(uniq), chunk_size):
        chunk = uniq[i : i + chunk_size]
        placeholders = ",".join(["?"] * len(chunk))
        try:
            rows = conn.execute(
                f"SELECT username, create_time FROM session_last_message WHERE username IN ({placeholders})",
                chunk,
            ).fetchall()
        except Exception:
            continue
        for r in rows:
            u = str((r["username"] if isinstance(r, sqlite3.Row) else r[0]) or "").strip()
            if not u:
                continue
            try:
                ts = int((r["create_time"] if isinstance(r, sqlite3.Row) else r[1]) or 0)
            except Exception:
                ts = 0
            out[u] = int(ts or 0)
    return out


def _session_row_get(row: Any, key: str, default: Any = None) -> Any:
    try:
        if isinstance(row, sqlite3.Row):
            return row[key]
    except Exception:
        return default
    try:
        return row.get(key, default)
    except Exception:
        return default


def _contact_flag_is_top(flag_value: Any) -> bool:
    try:
        flag_int = int(flag_value)
    except Exception:
        return False
    if flag_int < 0:
        flag_int &= (1 << 64) - 1
    return bool((flag_int >> 11) & 1)


def _load_contact_top_flags(contact_db_path: Path, usernames: list[str]) -> dict[str, bool]:
    uniq = list(dict.fromkeys([str(u or "").strip() for u in usernames if str(u or "").strip()]))
    if not uniq:
        return {}
    if not contact_db_path.exists():
        return {}

    out: dict[str, bool] = {}
    conn = sqlite3.connect(str(contact_db_path))
    conn.row_factory = sqlite3.Row
    try:
        def has_flag_column(table: str) -> bool:
            try:
                rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
            except Exception:
                return False
            cols: set[str] = set()
            for r in rows:
                try:
                    cols.add(str(r["name"] if isinstance(r, sqlite3.Row) else r[1]).strip().lower())
                except Exception:
                    continue
            return ("username" in cols) and ("flag" in cols)

        chunk_size = 900
        for table in ("contact", "stranger"):
            if not has_flag_column(table):
                continue

            for i in range(0, len(uniq), chunk_size):
                chunk = uniq[i : i + chunk_size]
                placeholders = ",".join(["?"] * len(chunk))
                try:
                    rows = conn.execute(
                        f"SELECT username, flag FROM {table} WHERE username IN ({placeholders})",
                        chunk,
                    ).fetchall()
                except Exception:
                    continue

                for r in rows:
                    username = str(_session_row_get(r, "username", "") or "").strip()
                    if not username:
                        continue
                    is_top = _contact_flag_is_top(_session_row_get(r, "flag", 0))
                    if is_top:
                        out[username] = True
                    else:
                        out.setdefault(username, False)
        return out
    finally:
        conn.close()


@router.post("/api/chat/realtime/sync", summary="实时消息同步到解密库（按会话增量）")
def sync_chat_realtime_messages(
    request: Request,
    username: str,
    account: Optional[str] = None,
    max_scan: int = 600,
    backfill_limit: int = 200,
):
    """
    设计目的：实时模式只用来“同步增量”到 output/databases 下的解密库，前端始终从解密库读取显示，
    避免 WCDB realtime 返回格式差异（如 compress_content/message_content 的 hex 编码）直接影响渲染。

    同步策略：从 WCDB 获取最新消息（从新到旧），直到遇到解密库中已存在的最大 local_id 为止。

    backfill_limit：同步过程中额外“回填”旧消息的 packed_info_data 的最大行数（用于修复旧库缺失字段）。
    - 设为 0 可显著降低每次同步的扫描/写入开销（更适合前端实时轮询/推送触发的高频增量同步）。
    """
    if not username:
        raise HTTPException(status_code=400, detail="Missing username.")
    if max_scan < 50:
        max_scan = 50
    if max_scan > 5000:
        max_scan = 5000
    if backfill_limit < 0:
        backfill_limit = 0
    if backfill_limit > 5000:
        backfill_limit = 5000

    account_dir = _resolve_account_dir(account)
    trace_id = f"rt-sync-{int(time.time() * 1000)}-{threading.get_ident()}"
    logger.info(
        "[%s] realtime sync start account=%s username=%s max_scan=%s",
        trace_id,
        account_dir.name,
        username,
        int(max_scan),
    )

    # Lock per (account, username) to avoid concurrent writes to the same sqlite tables.
    logger.info("[%s] acquiring per-session lock account=%s username=%s", trace_id, account_dir.name, username)
    with _realtime_sync_lock(account_dir.name, username):
        logger.info("[%s] per-session lock acquired account=%s username=%s", trace_id, account_dir.name, username)
        try:
            logger.info("[%s] ensure wcdb connected account=%s", trace_id, account_dir.name)
            rt_conn = WCDB_REALTIME.ensure_connected(account_dir)
            logger.info("[%s] wcdb connected account=%s handle=%s", trace_id, account_dir.name, int(rt_conn.handle))
        except WCDBRealtimeError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Some sessions may not exist in the decrypted snapshot yet; create the missing Msg_<md5> table
        # so we can insert the realtime rows and make `/api/chat/messages` work after switching off realtime.
        msg_db_path, table_name = _ensure_decrypted_message_table(account_dir, username)
        logger.info(
            "[%s] resolved decrypted table account=%s username=%s db=%s table=%s",
            trace_id,
            account_dir.name,
            username,
            str(msg_db_path),
            table_name,
        )

        msg_conn = sqlite3.connect(str(msg_db_path))
        msg_conn.row_factory = sqlite3.Row
        try:
            quoted_table = _quote_ident(table_name)
            row = msg_conn.execute(f"SELECT MAX(local_id) AS mx FROM {quoted_table}").fetchone()
            try:
                max_local_id = int((row["mx"] if row is not None else 0) or 0)
            except Exception:
                max_local_id = 0

            # Build a minimal insert statement based on existing columns (different WeChat versions vary).
            cols = msg_conn.execute(f"PRAGMA table_info({quoted_table})").fetchall()
            available_cols = {str(c[1] or "") for c in cols}
            base_cols = [
                "local_id",
                "server_id",
                "local_type",
                "sort_seq",
                "real_sender_id",
                "create_time",
                "message_content",
                "compress_content",
                "packed_info_data",
            ]
            insert_cols = [c for c in base_cols if c in available_cols]
            if "local_id" not in insert_cols:
                raise HTTPException(status_code=500, detail="Invalid message table schema (missing local_id).")

            placeholders = ",".join(["?"] * len(insert_cols))
            insert_sql = f"INSERT OR IGNORE INTO {quoted_table} ({','.join(insert_cols)}) VALUES ({placeholders})"

            def pick(item: dict[str, Any], *keys: str) -> Any:
                for k in keys:
                    if k in item and item[k] is not None:
                        return item[k]
                    lk = k.lower()
                    for kk in item.keys():
                        if str(kk).lower() == lk and item[kk] is not None:
                            return item[kk]
                return None

            def normalize_blob(value: Any) -> Optional[bytes]:
                if value is None:
                    return None
                if isinstance(value, memoryview):
                    return value.tobytes()
                if isinstance(value, (bytes, bytearray)):
                    return bytes(value)
                if isinstance(value, str):
                    s = value.strip()
                    if s.lower().startswith("0x"):
                        s = s[2:]
                    if s and re.fullmatch(r"[0-9a-fA-F]+", s) and (len(s) % 2 == 0):
                        try:
                            return bytes.fromhex(s)
                        except Exception:
                            return None
                    return s.encode("utf-8", errors="ignore")
                return None

            def normalize(item: dict[str, Any]) -> dict[str, Any]:
                return {
                    "local_id": int(pick(item, "local_id", "localId") or 0),
                    "server_id": int(pick(item, "server_id", "serverId", "MsgSvrID") or 0),
                    "local_type": int(pick(item, "local_type", "localType", "Type", "type") or 0),
                    "sort_seq": int(pick(item, "sort_seq", "sortSeq", "SortSeq") or 0),
                    "real_sender_id": int(pick(item, "real_sender_id", "realSenderId") or 0),
                    "create_time": int(pick(item, "create_time", "createTime", "CreateTime") or 0),
                    "message_content": pick(item, "message_content", "messageContent", "MessageContent") or "",
                    "compress_content": pick(item, "compress_content", "compressContent", "CompressContent"),
                    "packed_info_data": normalize_blob(pick(item, "packed_info_data", "packedInfoData")),
                    "sender_username": str(
                        pick(item, "sender_username", "senderUsername", "sender", "SenderUsername") or ""
                    ).strip(),
                }

            batch_size = 200
            scanned = 0
            offset = 0
            new_rows: list[dict[str, Any]] = []
            backfill_rows: list[dict[str, Any]] = []
            reached_existing = False
            stop = False

            while scanned < int(max_scan):
                take = min(batch_size, int(max_scan) - scanned)
                logger.info(
                    "[%s] wcdb_get_messages account=%s username=%s take=%s offset=%s",
                    trace_id,
                    account_dir.name,
                    username,
                    int(take),
                    int(offset),
                )
                wcdb_t0 = time.perf_counter()
                with rt_conn.lock:
                    raw_rows = _wcdb_get_messages(rt_conn.handle, username, limit=take, offset=offset)
                wcdb_ms = (time.perf_counter() - wcdb_t0) * 1000.0
                logger.info(
                    "[%s] wcdb_get_messages done account=%s username=%s rows=%s ms=%.1f",
                    trace_id,
                    account_dir.name,
                    username,
                    len(raw_rows or []),
                    wcdb_ms,
                )
                if wcdb_ms > 2000:
                    logger.warning(
                        "[%s] wcdb_get_messages slow account=%s username=%s ms=%.1f",
                        trace_id,
                        account_dir.name,
                        username,
                        wcdb_ms,
                    )
                if not raw_rows:
                    break

                scanned += len(raw_rows)
                offset += len(raw_rows)

                for item in raw_rows:
                    if not isinstance(item, dict):
                        continue
                    norm = normalize(item)
                    lid = int(norm.get("local_id") or 0)
                    if lid <= 0:
                        continue
                    if (not reached_existing) and lid > max_local_id:
                        new_rows.append(norm)
                        continue

                    reached_existing = True
                    if int(backfill_limit) <= 0:
                        stop = True
                        break
                    backfill_rows.append(norm)
                    if len(backfill_rows) >= int(backfill_limit):
                        stop = True
                        break

                if stop or len(raw_rows) < take:
                    break

            inserted = 0
            backfilled = 0
            if new_rows:
                # Best-effort: keep Name2Id updated so decrypted queries can resolve sender usernames.
                # Rowid mapping is important (message.real_sender_id joins Name2Id.rowid).
                try:
                    has_name2id = bool(
                        msg_conn.execute(
                            "SELECT name FROM sqlite_master WHERE type='table' AND lower(name)=lower('Name2Id') LIMIT 1"
                        ).fetchone()
                    )
                except Exception:
                    has_name2id = False

                if has_name2id:
                    try:
                        msg_conn.execute(
                            "INSERT OR IGNORE INTO Name2Id(user_name, is_session) VALUES (?, ?)",
                            (str(account_dir.name), 1),
                        )
                    except Exception:
                        pass

                    for r in new_rows:
                        try:
                            rid = int(r.get("real_sender_id") or 0)
                        except Exception:
                            rid = 0
                        su = str(r.get("sender_username") or "").strip()
                        if rid <= 0 or not su:
                            continue
                        try:
                            msg_conn.execute(
                                "INSERT OR IGNORE INTO Name2Id(rowid, user_name, is_session) VALUES (?, ?, ?)",
                                (rid, su, 1),
                            )
                        except Exception:
                            continue

                # Insert older -> newer to keep sqlite btree locality similar to existing data.
                values = [tuple(r.get(c) for c in insert_cols) for r in reversed(new_rows)]
                insert_t0 = time.perf_counter()
                msg_conn.executemany(insert_sql, values)
                msg_conn.commit()
                insert_ms = (time.perf_counter() - insert_t0) * 1000.0
                inserted = len(new_rows)
                logger.info(
                    "[%s] sqlite insert done account=%s username=%s inserted=%s ms=%.1f",
                    trace_id,
                    account_dir.name,
                    username,
                    int(inserted),
                    insert_ms,
                )
                if insert_ms > 1000:
                    logger.warning(
                        "[%s] sqlite insert slow account=%s username=%s ms=%.1f",
                        trace_id,
                        account_dir.name,
                        username,
                        insert_ms,
                    )

            if ("packed_info_data" in insert_cols) and backfill_rows:
                update_values = []
                for r in backfill_rows:
                    pdata = r.get("packed_info_data")
                    if not pdata:
                        continue
                    update_values.append((pdata, int(r.get("local_id") or 0)))
                if update_values:
                    before_changes = msg_conn.total_changes
                    update_t0 = time.perf_counter()
                    msg_conn.executemany(
                        f"UPDATE {quoted_table} SET packed_info_data = ? WHERE local_id = ? AND (packed_info_data IS NULL OR length(packed_info_data) = 0)",
                        update_values,
                    )
                    msg_conn.commit()
                    update_ms = (time.perf_counter() - update_t0) * 1000.0
                    backfilled = int(msg_conn.total_changes - before_changes)
                    logger.info(
                        "[%s] sqlite backfill done account=%s username=%s rows=%s ms=%.1f",
                        trace_id,
                        account_dir.name,
                        username,
                        int(backfilled),
                        update_ms,
                    )
                    if update_ms > 1000:
                        logger.warning(
                            "[%s] sqlite backfill slow account=%s username=%s ms=%.1f",
                            trace_id,
                            account_dir.name,
                            username,
                            update_ms,
                        )

            # Update session.db so left sidebar ordering/time can follow new messages.
            newest = new_rows[0] if new_rows else None
            preview = ""
            newest_ts = 0
            newest_local_id = 0
            newest_type = 0
            newest_sort_seq = 0
            newest_sender = ""
            newest_sub_type = 0

            if newest:
                newest_ts = int(newest.get("create_time") or 0)
                newest_local_id = int(newest.get("local_id") or 0)
                newest_type = int(newest.get("local_type") or 0)
                newest_sort_seq = int(newest.get("sort_seq") or 0)
                newest_sender = str(newest.get("sender_username") or "").strip()

                raw_text = _decode_message_content(newest.get("compress_content"), newest.get("message_content")).strip()
                is_group = bool(username.endswith("@chatroom"))
                preview = _build_latest_message_preview(
                    username=username,
                    local_type=newest_type,
                    raw_text=raw_text,
                    is_group=is_group,
                    sender_username=newest_sender,
                )

                if newest_type == 49 and raw_text:
                    try:
                        newest_sub_type = int(str(_extract_xml_tag_text(raw_text, "type") or "0").strip() or "0")
                    except Exception:
                        newest_sub_type = 0

            if inserted and newest_ts:
                session_db_path = account_dir / "session.db"
                sconn = sqlite3.connect(str(session_db_path))
                try:
                    sconn.execute("INSERT OR IGNORE INTO SessionTable(username) VALUES (?)", (username,))
                    sconn.execute(
                        """
                        UPDATE SessionTable
                        SET
                            last_timestamp = CASE WHEN COALESCE(last_timestamp, 0) < ? THEN ? ELSE last_timestamp END,
                            sort_timestamp = CASE WHEN COALESCE(sort_timestamp, 0) < ? THEN ? ELSE sort_timestamp END,
                            last_msg_locald_id = ?,
                            last_msg_type = ?,
                            last_msg_sub_type = ?,
                            last_msg_sender = ?,
                            summary = ?
                        WHERE username = ?
                        """,
                        (
                            newest_ts,
                            newest_ts,
                            newest_ts,
                            newest_ts,
                            newest_local_id,
                            newest_type,
                            newest_sub_type,
                            newest_sender,
                            preview or "",
                            username,
                        ),
                    )

                    _ensure_session_last_message_table(sconn)
                    sconn.execute(
                        """
                        INSERT OR REPLACE INTO session_last_message (
                            username, sort_seq, local_id, create_time, local_type, sender_username,
                            preview, db_stem, table_name, built_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            username,
                            newest_sort_seq,
                            newest_local_id,
                            newest_ts,
                            newest_type,
                            newest_sender,
                            preview or "",
                            str(msg_db_path.stem),
                            str(table_name),
                            int(time.time()),
                        ),
                    )
                    sconn.commit()
                finally:
                    sconn.close()

            logger.info(
                "[%s] realtime sync done account=%s username=%s scanned=%s inserted=%s backfilled=%s maxLocalIdBefore=%s",
                trace_id,
                account_dir.name,
                username,
                int(scanned),
                int(inserted),
                int(backfilled),
                int(max_local_id),
            )
            return {
                "status": "success",
                "account": account_dir.name,
                "username": username,
                "scanned": int(scanned),
                "maxLocalIdBefore": int(max_local_id),
                "inserted": int(inserted),
                "backfilled": int(backfilled),
                "preview": preview or "",
            }
        finally:
            msg_conn.close()


def _sync_chat_realtime_messages_for_table(
    *,
    account_dir: Path,
    rt_conn: Any,
    username: str,
    msg_db_path: Path,
    table_name: str,
    max_scan: int,
    backfill_limit: int = 200,
) -> dict[str, Any]:
    if max_scan < 50:
        max_scan = 50
    if max_scan > 5000:
        max_scan = 5000
    if backfill_limit < 0:
        backfill_limit = 0
    if backfill_limit > 5000:
        backfill_limit = 5000
    if backfill_limit > max_scan:
        backfill_limit = max_scan

    msg_conn = sqlite3.connect(str(msg_db_path))
    msg_conn.row_factory = sqlite3.Row
    try:
        quoted_table = _quote_ident(table_name)
        row = msg_conn.execute(f"SELECT MAX(local_id) AS mx FROM {quoted_table}").fetchone()
        try:
            max_local_id = int((row["mx"] if row is not None else 0) or 0)
        except Exception:
            max_local_id = 0

        cols = msg_conn.execute(f"PRAGMA table_info({quoted_table})").fetchall()
        available_cols = {str(c[1] or "") for c in cols}
        base_cols = [
            "local_id",
            "server_id",
            "local_type",
            "sort_seq",
            "real_sender_id",
            "create_time",
            "message_content",
            "compress_content",
            "packed_info_data",
        ]
        insert_cols = [c for c in base_cols if c in available_cols]
        if "local_id" not in insert_cols:
            raise HTTPException(status_code=500, detail="Invalid message table schema (missing local_id).")

        placeholders = ",".join(["?"] * len(insert_cols))
        insert_sql = f"INSERT OR IGNORE INTO {quoted_table} ({','.join(insert_cols)}) VALUES ({placeholders})"

        def pick(item: dict[str, Any], *keys: str) -> Any:
            for k in keys:
                if k in item and item[k] is not None:
                    return item[k]
                lk = k.lower()
                for kk in item.keys():
                    if str(kk).lower() == lk and item[kk] is not None:
                        return item[kk]
            return None

        def normalize_blob(value: Any) -> Optional[bytes]:
            if value is None:
                return None
            if isinstance(value, memoryview):
                return value.tobytes()
            if isinstance(value, (bytes, bytearray)):
                return bytes(value)
            if isinstance(value, str):
                s = value.strip()
                if s.lower().startswith("0x"):
                    s = s[2:]
                if s and re.fullmatch(r"[0-9a-fA-F]+", s) and (len(s) % 2 == 0):
                    try:
                        return bytes.fromhex(s)
                    except Exception:
                        return None
                return s.encode("utf-8", errors="ignore")
            return None

        def normalize(item: dict[str, Any]) -> dict[str, Any]:
            return {
                "local_id": int(pick(item, "local_id", "localId") or 0),
                "server_id": int(pick(item, "server_id", "serverId", "MsgSvrID") or 0),
                "local_type": int(pick(item, "local_type", "localType", "Type", "type") or 0),
                "sort_seq": int(pick(item, "sort_seq", "sortSeq", "SortSeq") or 0),
                "real_sender_id": int(pick(item, "real_sender_id", "realSenderId") or 0),
                "create_time": int(pick(item, "create_time", "createTime", "CreateTime") or 0),
                "message_content": pick(item, "message_content", "messageContent", "MessageContent") or "",
                "compress_content": pick(item, "compress_content", "compressContent", "CompressContent"),
                "packed_info_data": normalize_blob(pick(item, "packed_info_data", "packedInfoData")),
                "sender_username": str(
                    pick(item, "sender_username", "senderUsername", "sender", "SenderUsername") or ""
                ).strip(),
            }

        batch_size = 200
        scanned = 0
        offset = 0
        new_rows: list[dict[str, Any]] = []
        backfill_rows: list[dict[str, Any]] = []
        reached_existing = False
        stop = False

        while scanned < int(max_scan):
            take = min(batch_size, int(max_scan) - scanned)
            logger.debug(
                "[realtime] wcdb_get_messages account=%s username=%s take=%s offset=%s",
                account_dir.name,
                username,
                int(take),
                int(offset),
            )
            wcdb_t0 = time.perf_counter()
            with rt_conn.lock:
                raw_rows = _wcdb_get_messages(rt_conn.handle, username, limit=take, offset=offset)
            wcdb_ms = (time.perf_counter() - wcdb_t0) * 1000.0
            logger.debug(
                "[realtime] wcdb_get_messages done account=%s username=%s rows=%s ms=%.1f",
                account_dir.name,
                username,
                len(raw_rows or []),
                wcdb_ms,
            )
            if wcdb_ms > 2000:
                logger.warning(
                    "[realtime] wcdb_get_messages slow account=%s username=%s ms=%.1f",
                    account_dir.name,
                    username,
                    wcdb_ms,
                )
            if not raw_rows:
                break

            scanned += len(raw_rows)
            offset += len(raw_rows)

            for item in raw_rows:
                if not isinstance(item, dict):
                    continue
                norm = normalize(item)
                lid = int(norm.get("local_id") or 0)
                if lid <= 0:
                    continue
                if (not reached_existing) and lid > max_local_id:
                    new_rows.append(norm)
                    continue

                reached_existing = True
                if int(backfill_limit) <= 0:
                    stop = True
                    break
                backfill_rows.append(norm)
                if len(backfill_rows) >= int(backfill_limit):
                    stop = True
                    break

            if stop or len(raw_rows) < take:
                break

        inserted = 0
        backfilled = 0
        if new_rows:
            try:
                has_name2id = bool(
                    msg_conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND lower(name)=lower('Name2Id') LIMIT 1"
                    ).fetchone()
                )
            except Exception:
                has_name2id = False

            if has_name2id:
                try:
                    msg_conn.execute(
                        "INSERT OR IGNORE INTO Name2Id(user_name, is_session) VALUES (?, ?)",
                        (str(account_dir.name), 1),
                    )
                except Exception:
                    pass

                for r in new_rows:
                    try:
                        rid = int(r.get("real_sender_id") or 0)
                    except Exception:
                        rid = 0
                    su = str(r.get("sender_username") or "").strip()
                    if rid <= 0 or not su:
                        continue
                    try:
                        msg_conn.execute(
                            "INSERT OR IGNORE INTO Name2Id(rowid, user_name, is_session) VALUES (?, ?, ?)",
                            (rid, su, 1),
                        )
                    except Exception:
                        continue

            values = [tuple(r.get(c) for c in insert_cols) for r in reversed(new_rows)]
            insert_t0 = time.perf_counter()
            msg_conn.executemany(insert_sql, values)
            msg_conn.commit()
            insert_ms = (time.perf_counter() - insert_t0) * 1000.0
            inserted = len(new_rows)
            logger.info(
                "[realtime] sqlite insert done account=%s username=%s inserted=%s ms=%.1f",
                account_dir.name,
                username,
                int(inserted),
                insert_ms,
            )
            if insert_ms > 1000:
                logger.warning(
                    "[realtime] sqlite insert slow account=%s username=%s ms=%.1f",
                    account_dir.name,
                    username,
                    insert_ms,
                )

        if ("packed_info_data" in insert_cols) and backfill_rows:
            update_values = []
            for r in backfill_rows:
                pdata = r.get("packed_info_data")
                if not pdata:
                    continue
                update_values.append((pdata, int(r.get("local_id") or 0)))
            if update_values:
                before_changes = msg_conn.total_changes
                update_t0 = time.perf_counter()
                msg_conn.executemany(
                    f"UPDATE {quoted_table} SET packed_info_data = ? WHERE local_id = ? AND (packed_info_data IS NULL OR length(packed_info_data) = 0)",
                    update_values,
                )
                msg_conn.commit()
                update_ms = (time.perf_counter() - update_t0) * 1000.0
                backfilled = int(msg_conn.total_changes - before_changes)
                logger.info(
                    "[realtime] sqlite backfill done account=%s username=%s rows=%s ms=%.1f",
                    account_dir.name,
                    username,
                    int(backfilled),
                    update_ms,
                )
                if update_ms > 1000:
                    logger.warning(
                        "[realtime] sqlite backfill slow account=%s username=%s ms=%.1f",
                        account_dir.name,
                        username,
                        update_ms,
                    )

        newest = new_rows[0] if new_rows else None
        preview = ""
        newest_ts = 0
        newest_local_id = 0
        newest_type = 0
        newest_sort_seq = 0
        newest_sender = ""
        newest_sub_type = 0

        if newest:
            newest_ts = int(newest.get("create_time") or 0)
            newest_local_id = int(newest.get("local_id") or 0)
            newest_type = int(newest.get("local_type") or 0)
            newest_sort_seq = int(newest.get("sort_seq") or 0)
            newest_sender = str(newest.get("sender_username") or "").strip()

            raw_text = _decode_message_content(newest.get("compress_content"), newest.get("message_content")).strip()
            is_group = bool(username.endswith("@chatroom"))
            preview = _build_latest_message_preview(
                username=username,
                local_type=newest_type,
                raw_text=raw_text,
                is_group=is_group,
                sender_username=newest_sender,
            )

            if newest_type == 49 and raw_text:
                try:
                    newest_sub_type = int(str(_extract_xml_tag_text(raw_text, "type") or "0").strip() or "0")
                except Exception:
                    newest_sub_type = 0

        if inserted and newest_ts:
            session_db_path = account_dir / "session.db"
            sconn = sqlite3.connect(str(session_db_path))
            try:
                sconn.execute("INSERT OR IGNORE INTO SessionTable(username) VALUES (?)", (username,))
                sconn.execute(
                    """
                    UPDATE SessionTable
                    SET
                        last_timestamp = CASE WHEN COALESCE(last_timestamp, 0) < ? THEN ? ELSE last_timestamp END,
                        sort_timestamp = CASE WHEN COALESCE(sort_timestamp, 0) < ? THEN ? ELSE sort_timestamp END,
                        last_msg_locald_id = ?,
                        last_msg_type = ?,
                        last_msg_sub_type = ?,
                        last_msg_sender = ?,
                        summary = ?
                    WHERE username = ?
                    """,
                    (
                        newest_ts,
                        newest_ts,
                        newest_ts,
                        newest_ts,
                        newest_local_id,
                        newest_type,
                        newest_sub_type,
                        newest_sender,
                        preview or "",
                        username,
                    ),
                )

                _ensure_session_last_message_table(sconn)
                sconn.execute(
                    """
                    INSERT OR REPLACE INTO session_last_message (
                        username, sort_seq, local_id, create_time, local_type, sender_username,
                        preview, db_stem, table_name, built_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        username,
                        newest_sort_seq,
                        newest_local_id,
                        newest_ts,
                        newest_type,
                        newest_sender,
                        preview or "",
                        str(msg_db_path.stem),
                        str(table_name),
                        int(time.time()),
                    ),
                )
                sconn.commit()
            finally:
                sconn.close()

        return {
            "username": username,
            "scanned": int(scanned),
            "maxLocalIdBefore": int(max_local_id),
            "inserted": int(inserted),
            "backfilled": int(backfilled),
            "preview": preview or "",
        }
    finally:
        msg_conn.close()


@router.post("/api/chat/realtime/sync_all", summary="实时消息同步到解密库（全会话增量）")
def sync_chat_realtime_messages_all(
    request: Request,
    account: Optional[str] = None,
    max_scan: int = 200,
    priority_username: Optional[str] = None,
    priority_max_scan: int = 600,
    include_hidden: bool = True,
    include_official: bool = True,
    backfill_limit: int = 200,
):
    """
    全量会话同步（增量）：遍历会话列表，对每个会话调用与 /realtime/sync 相同的“遇到已同步 local_id 即停止”逻辑。

    说明：这是增量同步，不会每次全表扫描；priority_username 会优先同步并可设置更大的 priority_max_scan。
    """
    account_dir = _resolve_account_dir(account)
    trace_id = f"rt-syncall-{int(time.time() * 1000)}-{threading.get_ident()}"
    logger.info(
        "[%s] realtime sync_all start account=%s max_scan=%s priority=%s include_hidden=%s include_official=%s",
        trace_id,
        account_dir.name,
        int(max_scan),
        str(priority_username or "").strip(),
        bool(include_hidden),
        bool(include_official),
    )

    if max_scan < 20:
        max_scan = 20
    if max_scan > 5000:
        max_scan = 5000
    if priority_max_scan < max_scan:
        priority_max_scan = max_scan
    if priority_max_scan > 5000:
        priority_max_scan = 5000
    if backfill_limit < 0:
        backfill_limit = 0
    if backfill_limit > 5000:
        backfill_limit = 5000
    if backfill_limit > max_scan:
        backfill_limit = max_scan

    priority = str(priority_username or "").strip()
    started = time.time()

    logger.info("[%s] acquiring global sync lock account=%s", trace_id, account_dir.name)
    with _realtime_sync_all_lock(account_dir.name):
        logger.info("[%s] global sync lock acquired account=%s", trace_id, account_dir.name)
        try:
            logger.info("[%s] ensure wcdb connected account=%s", trace_id, account_dir.name)
            rt_conn = WCDB_REALTIME.ensure_connected(account_dir)
            logger.info("[%s] wcdb connected account=%s handle=%s", trace_id, account_dir.name, int(rt_conn.handle))
        except WCDBRealtimeError as e:
            raise HTTPException(status_code=400, detail=str(e))

        try:
            logger.info("[%s] wcdb_get_sessions account=%s", trace_id, account_dir.name)
            wcdb_t0 = time.perf_counter()
            with rt_conn.lock:
                raw_sessions = _wcdb_get_sessions(rt_conn.handle)
            wcdb_ms = (time.perf_counter() - wcdb_t0) * 1000.0
            logger.info(
                "[%s] wcdb_get_sessions done account=%s sessions=%s ms=%.1f",
                trace_id,
                account_dir.name,
                len(raw_sessions or []),
                wcdb_ms,
            )
        except Exception:
            raw_sessions = []

        sessions: list[tuple[int, str]] = []
        realtime_rows_by_user: dict[str, dict[str, Any]] = {}
        for item in raw_sessions:
            if not isinstance(item, dict):
                continue
            uname = str(item.get("username") or item.get("user_name") or item.get("UserName") or "").strip()
            if not uname:
                continue

            try:
                hidden_val = int(item.get("is_hidden", item.get("isHidden", 0)) or 0)
            except Exception:
                hidden_val = 0
            if not include_hidden and hidden_val == 1:
                continue
            if not _should_keep_session(uname, include_official=include_official):
                continue

            ts = 0
            for k in ("sort_timestamp", "sortTimestamp", "last_timestamp", "lastTimestamp"):
                try:
                    ts = int(item.get(k, 0) or 0)
                except Exception:
                    ts = 0
                if ts:
                    break
            sessions.append((ts, uname))

            # Keep a normalized SessionTable row for upserting into decrypted session.db.
            norm_row = {
                "username": uname,
                "unread_count": item.get("unread_count", item.get("unreadCount", 0)),
                "is_hidden": item.get("is_hidden", item.get("isHidden", 0)),
                "summary": item.get("summary", ""),
                "draft": item.get("draft", ""),
                "last_timestamp": item.get("last_timestamp", item.get("lastTimestamp", 0)),
                "sort_timestamp": item.get(
                    "sort_timestamp",
                    item.get("sortTimestamp", item.get("last_timestamp", item.get("lastTimestamp", 0))),
                ),
                "last_msg_locald_id": item.get(
                    "last_msg_locald_id",
                    item.get("lastMsgLocaldId", item.get("lastMsgLocalId", 0)),
                ),
                "last_msg_type": item.get("last_msg_type", item.get("lastMsgType", 0)),
                "last_msg_sub_type": item.get("last_msg_sub_type", item.get("lastMsgSubType", 0)),
                "last_msg_sender": item.get("last_msg_sender", item.get("lastMsgSender", "")),
                "last_sender_display_name": item.get(
                    "last_sender_display_name",
                    item.get("lastSenderDisplayName", ""),
                ),
            }
            # Prefer the row with the newer sort timestamp for the same username.
            prev = realtime_rows_by_user.get(uname)
            try:
                prev_sort = int((prev or {}).get("sort_timestamp") or 0)
            except Exception:
                prev_sort = 0
            try:
                cur_sort = int(norm_row.get("sort_timestamp") or 0)
            except Exception:
                cur_sort = 0
            if prev is None or cur_sort >= prev_sort:
                realtime_rows_by_user[uname] = norm_row

        def _dedupe(items: list[tuple[int, str]]) -> list[tuple[int, str]]:
            seen = set()
            out: list[tuple[int, str]] = []
            for ts, u in items:
                if not u or u in seen:
                    continue
                seen.add(u)
                out.append((ts, u))
            return out

        sessions = _dedupe(sessions)
        sessions.sort(key=lambda x: int(x[0] or 0), reverse=True)
        all_usernames = [u for _, u in sessions if u]
        logger.info(
            "[%s] sessions prepared account=%s raw=%s filtered=%s",
            trace_id,
            account_dir.name,
            len(raw_sessions or []),
            len(all_usernames),
        )

        # Keep SessionTable fresh for UI consistency, and use session_last_message.create_time as the
        # "sync watermark" (instead of SessionTable timestamps) to decide whether a session needs syncing.
        decrypted_ts_by_user: dict[str, int] = {}
        if all_usernames:
            try:
                session_db_path = account_dir / "session.db"
                sconn = sqlite3.connect(str(session_db_path))
                sconn.row_factory = sqlite3.Row
                try:
                    _ensure_session_last_message_table(sconn)

                    # If the cache table exists but is empty (older accounts), attempt a one-time build so we
                    # don't keep treating every session as "needs_sync".
                    try:
                        cnt = int(sconn.execute("SELECT COUNT(1) FROM session_last_message").fetchone()[0] or 0)
                    except Exception:
                        cnt = 0
                    if cnt <= 0:
                        try:
                            sconn.close()
                        except Exception:
                            pass
                        try:
                            build_session_last_message_table(
                                account_dir,
                                rebuild=False,
                                include_hidden=True,
                                include_official=True,
                            )
                        except Exception:
                            pass
                        sconn = sqlite3.connect(str(session_db_path))
                        sconn.row_factory = sqlite3.Row
                        _ensure_session_last_message_table(sconn)

                    # Upsert latest WCDB sessions into decrypted SessionTable so the sidebar list remains stable
                    # after switching off realtime (or refreshing the page).
                    try:
                        _upsert_session_table_rows(sconn, list(realtime_rows_by_user.values()))
                        sconn.commit()
                    except Exception:
                        try:
                            sconn.rollback()
                        except Exception:
                            pass

                    decrypted_ts_by_user = _load_session_last_message_times(sconn, all_usernames)
                finally:
                    try:
                        sconn.close()
                    except Exception:
                        pass
            except Exception:
                decrypted_ts_by_user = {}

        sync_usernames: list[str] = []
        skipped_up_to_date = 0
        for ts, u in sessions:
            if not u:
                continue
            local_ts = int(decrypted_ts_by_user.get(u) or 0)
            if ts and local_ts and local_ts >= int(ts):
                skipped_up_to_date += 1
                continue
            sync_usernames.append(u)

        logger.info(
            "[%s] sessions need_sync account=%s need_sync=%s skipped_up_to_date=%s",
            trace_id,
            account_dir.name,
            len(sync_usernames),
            int(skipped_up_to_date),
        )

        if priority and priority in sync_usernames:
            sync_usernames = [priority] + [u for u in sync_usernames if u != priority]

        table_map = _ensure_decrypted_message_tables(account_dir, sync_usernames)
        logger.info(
            "[%s] resolved decrypted tables account=%s resolved=%s need_sync=%s",
            trace_id,
            account_dir.name,
            len(table_map),
            len(sync_usernames),
        )

        scanned_total = 0
        inserted_total = 0
        synced = 0
        skipped_missing_table = 0
        updated_sessions = 0
        errors: list[str] = []

        for uname in sync_usernames:
            resolved = table_map.get(uname)
            if not resolved:
                skipped_missing_table += 1
                continue
            msg_db_path, table_name = resolved
            cur_scan = priority_max_scan if (priority and uname == priority) else max_scan

            try:
                with _realtime_sync_lock(account_dir.name, uname):
                    result = _sync_chat_realtime_messages_for_table(
                        account_dir=account_dir,
                        rt_conn=rt_conn,
                        username=uname,
                        msg_db_path=msg_db_path,
                        table_name=table_name,
                        max_scan=int(cur_scan),
                        backfill_limit=int(backfill_limit),
                    )
                synced += 1
                scanned_total += int(result.get("scanned") or 0)
                ins = int(result.get("inserted") or 0)
                inserted_total += ins
                if ins:
                    updated_sessions += 1
                    logger.info(
                        "[%s] synced session account=%s username=%s inserted=%s scanned=%s",
                        trace_id,
                        account_dir.name,
                        uname,
                        ins,
                        int(result.get("scanned") or 0),
                    )
            except HTTPException as e:
                errors.append(f"{uname}: {str(e.detail or '')}".strip())
                logger.warning(
                    "[%s] sync session failed account=%s username=%s err=%s",
                    trace_id,
                    account_dir.name,
                    uname,
                    str(e.detail or "").strip(),
                )
                continue
            except Exception as e:
                errors.append(f"{uname}: {str(e)}".strip())
                logger.exception(
                    "[%s] sync session crashed account=%s username=%s",
                    trace_id,
                    account_dir.name,
                    uname,
                )
                continue

        elapsed_ms = int((time.time() - started) * 1000)
        if len(errors) > 20:
            errors = errors[:20] + [f"... and {len(errors) - 20} more"]

        logger.info(
            "[%s] realtime sync_all done account=%s sessions_total=%s need_sync=%s synced=%s updated=%s inserted_total=%s elapsed_ms=%s errors=%s",
            trace_id,
            account_dir.name,
            len(all_usernames),
            len(sync_usernames),
            int(synced),
            int(updated_sessions),
            int(inserted_total),
            int(elapsed_ms),
            len(errors),
        )
        return {
            "status": "success",
            "account": account_dir.name,
            "priorityUsername": priority,
            "sessionsTotal": len(all_usernames),
            "sessionsNeedSync": len(sync_usernames),
            "sessionsSkippedUpToDate": int(skipped_up_to_date),
            "sessionsResolved": len(table_map),
            "sessionsSynced": int(synced),
            "sessionsUpdated": int(updated_sessions),
            "sessionsSkippedMissingTable": int(skipped_missing_table),
            "scannedTotal": int(scanned_total),
            "insertedTotal": int(inserted_total),
            "elapsedMs": int(elapsed_ms),
            "errors": errors,
        }

def _normalize_session_type(value: Optional[str]) -> Optional[str]:
    v = str(value or "").strip().lower()
    if not v or v in {"all", "any", "none", "null", "0"}:
        return None
    if v in {"group", "groups", "chatroom", "chatrooms"}:
        return "group"
    if v in {"single", "singles", "person", "people", "user", "users", "contact", "contacts"}:
        return "single"
    raise HTTPException(status_code=400, detail="Invalid session_type, use 'group' or 'single'.")


def _normalize_render_type_key(value: Any) -> str:
    v = str(value or "").strip()
    if not v:
        return ""
    if v == "redPacket":
        return "redpacket"
    lower = v.lower()
    if lower in {"redpacket", "red_packet", "red-packet", "redenvelope", "red_envelope"}:
        return "redpacket"
    return lower


@router.get("/api/chat/search-index/status", summary="消息搜索索引状态")
async def chat_search_index_status(account: Optional[str] = None):
    account_dir = _resolve_account_dir(account)
    return get_chat_search_index_status(account_dir)


@router.post("/api/chat/search-index/build", summary="构建/重建消息搜索索引")
async def chat_search_index_build(account: Optional[str] = None, rebuild: bool = False):
    account_dir = _resolve_account_dir(account)
    return start_chat_search_index_build(account_dir, rebuild=bool(rebuild))


@router.get("/api/chat/session-last-message/status", summary="会话最后一条消息缓存表状态")
async def session_last_message_status(account: Optional[str] = None):
    account_dir = _resolve_account_dir(account)
    return get_session_last_message_status(account_dir)


@router.post("/api/chat/session-last-message/build", summary="构建/重建会话最后一条消息缓存表")
async def session_last_message_build(
    account: Optional[str] = None,
    rebuild: bool = False,
    include_hidden: bool = True,
    include_official: bool = True,
):
    account_dir = _resolve_account_dir(account)
    return build_session_last_message_table(
        account_dir,
        rebuild=bool(rebuild),
        include_hidden=bool(include_hidden),
        include_official=bool(include_official),
    )


@router.get("/api/chat/search-index/senders", summary="消息搜索索引发送者列表")
async def chat_search_index_senders(
    account: Optional[str] = None,
    username: Optional[str] = None,
    session_type: Optional[str] = None,
    message_q: Optional[str] = None,
    limit: int = 200,
    q: Optional[str] = None,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    render_types: Optional[str] = None,
    include_hidden: bool = False,
    include_official: bool = False,
):
    if limit <= 0:
        limit = 200
    if limit > 2000:
        limit = 2000

    username = str(username or "").strip()
    if not username:
        username = None

    session_type_norm = _normalize_session_type(session_type)

    message_q = str(message_q or "").strip()
    if not message_q:
        message_q = None

    q = str(q or "").strip()
    if not q:
        q = None

    account_dir = _resolve_account_dir(account)
    contact_db_path = account_dir / "contact.db"

    index_status = get_chat_search_index_status(account_dir)
    index = dict(index_status.get("index") or {})
    build = dict(index.get("build") or {})

    index_exists = bool(index.get("exists"))
    index_ready = bool(index.get("ready"))
    build_status = str(build.get("status") or "").strip()

    if (not index_ready) and build_status not in {"building", "error"}:
        start_chat_search_index_build(account_dir, rebuild=bool(index_exists))
        index_status = get_chat_search_index_status(account_dir)
        index = dict(index_status.get("index") or {})
        build = dict(index.get("build") or {})
        build_status = str(build.get("status") or "").strip()
        index_exists = bool(index.get("exists"))
        index_ready = bool(index.get("ready"))

    if build_status == "error":
        return {
            "status": "index_error",
            "account": account_dir.name,
            "username": username,
            "scope": "conversation" if username else "global",
            "senders": [],
            "index": index,
            "message": str(build.get("error") or "Search index build failed."),
        }

    if not index_ready:
        return {
            "status": "index_building",
            "account": account_dir.name,
            "username": username,
            "scope": "conversation" if username else "global",
            "senders": [],
            "index": index,
            "message": "Search index is building. Please retry in a moment.",
        }

    if username is None and message_q is None:
        return {
            "status": "success",
            "account": account_dir.name,
            "username": None,
            "scope": "global",
            "senders": [],
            "index": index,
            "message": "Provide message_q to list global senders.",
        }

    index_db_path = get_chat_search_index_db_path(account_dir)
    conn = sqlite3.connect(str(index_db_path))
    conn.row_factory = sqlite3.Row
    try:
        where_parts: list[str] = ["sender_username <> ''"]
        params: list[Any] = []

        if message_q is not None:
            fts_query = _build_fts_query(message_q)
            if fts_query:
                where_parts.insert(0, "message_fts MATCH ?")
                params.append(fts_query)

        if username is not None:
            where_parts.append("username = ?")
            params.append(username)
        elif session_type_norm == "group":
            where_parts.append("username LIKE ?")
            params.append("%@chatroom")
        elif session_type_norm == "single":
            where_parts.append("username NOT LIKE ?")
            params.append("%@chatroom")

        if q is not None:
            where_parts.append("sender_username LIKE ?")
            params.append(f"%{q}%")

        want_types: Optional[set[str]] = None
        if render_types is not None:
            parts = [p.strip() for p in str(render_types or "").split(",") if p.strip()]
            want_types = {p for p in parts if p}
            if not want_types:
                want_types = None

        if want_types is not None:
            types_sorted = sorted(want_types)
            placeholders = ",".join(["?"] * len(types_sorted))
            where_parts.append(f"render_type IN ({placeholders})")
            params.extend(types_sorted)

        start_ts = int(start_time) if start_time is not None else None
        end_ts = int(end_time) if end_time is not None else None
        if start_ts is not None and start_ts < 0:
            start_ts = 0
        if end_ts is not None and end_ts < 0:
            end_ts = 0

        if start_ts is not None:
            where_parts.append("CAST(create_time AS INTEGER) >= ?")
            params.append(int(start_ts))
        if end_ts is not None:
            where_parts.append("CAST(create_time AS INTEGER) <= ?")
            params.append(int(end_ts))

        if not include_hidden:
            where_parts.append("CAST(is_hidden AS INTEGER) = 0")
        if not include_official:
            where_parts.append("CAST(is_official AS INTEGER) = 0")

        where_sql = " AND ".join(where_parts)
        rows = conn.execute(
            f"""
            SELECT
                sender_username AS sender_username,
                COUNT(*) AS c
            FROM message_fts
            WHERE {where_sql}
            GROUP BY sender_username
            ORDER BY c DESC, sender_username ASC
            LIMIT ?
            """,
            params + [int(limit)],
        ).fetchall()
    finally:
        conn.close()

    sender_usernames = [str(r["sender_username"] or "").strip() for r in rows if r and r["sender_username"]]
    sender_usernames = [u for u in sender_usernames if u]
    contact_rows = _load_contact_rows(contact_db_path, sender_usernames)
    head_image_db_path = account_dir / "head_image.db"
    local_sender_avatars = _query_head_image_usernames(head_image_db_path, sender_usernames)

    senders: list[dict[str, Any]] = []
    for r in rows:
        su = str(r["sender_username"] or "").strip()
        if not su:
            continue
        cnt = int(r["c"] or 0)
        row = contact_rows.get(su)
        avatar_url = _avatar_url_unified(
            account_dir=account_dir,
            username=su,
            local_avatar_usernames=local_sender_avatars,
        )
        senders.append(
            {
                "username": su,
                "displayName": _pick_display_name(row, su) if row is not None else su,
                "avatar": avatar_url,
                "count": cnt,
            }
        )

    return {
        "status": "success",
        "account": account_dir.name,
        "username": username,
        "scope": "conversation" if username else "global",
        "senders": senders,
        "index": index,
    }


def _append_full_messages_from_rows(
    *,
    merged: list[dict[str, Any]],
    sender_usernames: list[str],
    quote_usernames: list[str],
    pat_usernames: set[str],
    rows: list[sqlite3.Row],
    db_path: Path,
    table_name: str,
    username: str,
    account_dir: Path,
    is_group: bool,
    my_rowid: Optional[int],
    resource_conn: Optional[sqlite3.Connection],
    resource_chat_id: Optional[int],
) -> None:
    contact_conn: Optional[sqlite3.Connection] = None
    alias_cache: dict[str, str] = {}
    if is_group:
        try:
            contact_db_path = account_dir / "contact.db"
            if contact_db_path.exists():
                contact_conn = sqlite3.connect(str(contact_db_path))
        except Exception:
            contact_conn = None

    for r in rows:
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
        else:
            # Realtime WCDB DLL may already compute this field.
            for k in (
                "computed_is_send",
                "computed_is_sent",
                "computed_isSend",
                "is_send",
                "isSent",
            ):
                try:
                    v = r[k]
                except Exception:
                    v = None
                if v is None:
                    continue
                try:
                    is_sent = bool(int(v))
                except Exception:
                    is_sent = bool(v)
                break

            if not is_sent:
                # Fallback: some builds include the resolved "my rowid" for debugging.
                try:
                    my_debug = None
                    for k2 in ("debug_my_rowid", "debugMyRowid", "my_rowid", "myRowid"):
                        try:
                            my_debug = r[k2]
                            break
                        except Exception:
                            continue
                    if my_debug is not None and int(my_debug or 0) > 0:
                        is_sent = int(r["real_sender_id"] or 0) == int(my_debug)
                except Exception:
                    pass

            if not is_sent:
                try:
                    su = str(sender_username or "").strip().lower()
                    me = str(account_dir.name or "").strip().lower()
                    if su and me and su == me:
                        is_sent = True
                except Exception:
                    pass

        raw_text = _decode_message_content(r["compress_content"], r["message_content"])
        raw_text = raw_text.strip()

        sender_prefix = ""
        if is_group and raw_text and (not raw_text.startswith("<")) and (not raw_text.startswith('"<')):
            sender_alias = ""
            sep = raw_text.find(":\n")
            if sep > 0:
                prefix = raw_text[:sep].strip()
                if prefix and sender_username and prefix != sender_username:
                    strong_hint = prefix.startswith("wxid_") or prefix.endswith("@chatroom") or "@" in prefix
                    if not strong_hint:
                        body_probe = raw_text[sep + 2 :].lstrip("\n").lstrip()
                        body_is_xml = body_probe.startswith("<") or body_probe.startswith('"<')
                        if not body_is_xml:
                            sender_alias = _lookup_contact_alias(contact_conn, alias_cache, sender_username)
            sender_prefix, raw_text = _split_group_sender_prefix(raw_text, sender_username, sender_alias)

        if is_group and sender_prefix and (not sender_username):
            sender_username = sender_prefix

        if is_group and (not sender_username) and (raw_text.startswith("<") or raw_text.startswith('"<')):
            xml_sender = _extract_sender_from_group_xml(raw_text)
            if xml_sender:
                sender_username = xml_sender

        if is_sent:
            sender_username = account_dir.name
        elif (not is_group) and (not sender_username):
            sender_username = username

        if sender_username:
            sender_usernames.append(sender_username)

        render_type = "text"
        content_text = raw_text
        title = ""
        url = ""
        from_name = ""
        from_username = ""
        record_item = ""
        image_md5 = ""
        emoji_md5 = ""
        emoji_url = ""
        thumb_url = ""
        image_url = ""
        image_file_id = ""
        video_md5 = ""
        video_thumb_md5 = ""
        video_file_id = ""
        video_thumb_file_id = ""
        video_url = ""
        video_thumb_url = ""
        voice_length = ""
        quote_username = ""
        quote_title = ""
        quote_content = ""
        quote_thumb_url = ""
        link_type = ""
        link_style = ""
        quote_server_id = ""
        quote_type = ""
        quote_voice_length = ""
        amount = ""
        cover_url = ""
        file_size = ""
        pay_sub_type = ""
        transfer_status = ""
        file_md5 = ""
        transfer_id = ""
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
            from_name = str(parsed.get("from") or "")
            from_username = str(parsed.get("fromUsername") or "")
            record_item = str(parsed.get("recordItem") or "")
            quote_title = str(parsed.get("quoteTitle") or "")
            quote_content = str(parsed.get("quoteContent") or "")
            quote_thumb_url = str(parsed.get("quoteThumbUrl") or "")
            link_type = str(parsed.get("linkType") or "")
            link_style = str(parsed.get("linkStyle") or "")
            quote_username = str(parsed.get("quoteUsername") or "")
            quote_server_id = str(parsed.get("quoteServerId") or "")
            quote_type = str(parsed.get("quoteType") or "")
            quote_voice_length = str(parsed.get("quoteVoiceLength") or "")
            amount = str(parsed.get("amount") or "")
            cover_url = str(parsed.get("coverUrl") or "")
            thumb_url = str(parsed.get("thumbUrl") or "")
            file_size = str(parsed.get("size") or "")
            pay_sub_type = str(parsed.get("paySubType") or "")
            file_md5 = str(parsed.get("fileMd5") or "")
            transfer_id = str(parsed.get("transferId") or "")

            if render_type == "transfer":
                # 直接从原始 XML 提取 transferid（可能在 wcpayinfo 内）
                if not transfer_id:
                    transfer_id = _extract_xml_tag_or_attr(raw_text, "transferid") or ""
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
            template = _extract_xml_tag_text(raw_text, "template")
            if template:
                pat_usernames.update(
                    {m.group(1) for m in re.finditer(r"\$\{([^}]+)\}", template) if m.group(1)}
                )
                content_text = "[拍一拍]"
            else:
                content_text = "[拍一拍]"
        elif local_type == 244813135921:
            render_type = "quote"
            parsed = _parse_app_message(raw_text)
            content_text = str(parsed.get("content") or "[引用消息]")
            quote_title = str(parsed.get("quoteTitle") or "")
            quote_content = str(parsed.get("quoteContent") or "")
            quote_thumb_url = str(parsed.get("quoteThumbUrl") or "")
            link_type = str(parsed.get("linkType") or "")
            link_style = str(parsed.get("linkStyle") or "")
            quote_username = str(parsed.get("quoteUsername") or "")
            quote_server_id = str(parsed.get("quoteServerId") or "")
            quote_type = str(parsed.get("quoteType") or "")
            quote_voice_length = str(parsed.get("quoteVoiceLength") or "")
        elif local_type == 3:
            render_type = "image"
            # 先尝试从 XML 中提取 md5（不同版本字段可能不同）
            image_md5 = _extract_xml_attr(raw_text, "md5") or _extract_xml_tag_text(raw_text, "md5")
            if not image_md5:
                for k in [
                    "cdnthumbmd5",
                    "cdnthumd5",
                    "cdnmidimgmd5",
                    "cdnbigimgmd5",
                    "hdmd5",
                    "hevc_mid_md5",
                    "hevc_md5",
                    "imgmd5",
                    "filemd5",
                ]:
                    image_md5 = _extract_xml_attr(raw_text, k) or _extract_xml_tag_text(raw_text, k)
                    if image_md5:
                        break

            # Prefer message_resource.db md5 for local files: XML md5 frequently differs from the on-disk *.dat basename
            # (especially for *_t.dat thumbnails), causing the media endpoint to 404.
            if resource_conn is not None:
                try:
                    resource_md5 = _lookup_resource_md5(
                        resource_conn,
                        resource_chat_id,
                        message_local_type=local_type,
                        server_id=int(r["server_id"] or 0),
                        local_id=local_id,
                        create_time=create_time,
                    )
                except Exception:
                    resource_md5 = ""
                resource_md5 = str(resource_md5 or "").strip().lower()
                if len(resource_md5) == 32 and all(c in "0123456789abcdef" for c in resource_md5):
                    image_md5 = resource_md5

            try:
                packed_val = r["packed_info_data"]
            except Exception:
                try:
                    packed_val = r.get("packed_info_data")  # type: ignore[attr-defined]
                except Exception:
                    packed_val = None
            packed_md5 = _extract_md5_from_packed_info(packed_val)
            if packed_md5:
                image_md5 = packed_md5

            # Extract CDN URL (some versions store a non-HTTP "file id" string here)
            _cdn_url_or_id = (
                _extract_xml_attr(raw_text, "cdnthumburl")
                or _extract_xml_attr(raw_text, "cdnthumurl")
                or _extract_xml_attr(raw_text, "cdnmidimgurl")
                or _extract_xml_attr(raw_text, "cdnbigimgurl")
                or _extract_xml_tag_text(raw_text, "cdnthumburl")
                or _extract_xml_tag_text(raw_text, "cdnthumurl")
                or _extract_xml_tag_text(raw_text, "cdnmidimgurl")
                or _extract_xml_tag_text(raw_text, "cdnbigimgurl")
            )
            _cdn_url_or_id = _normalize_xml_url(_cdn_url_or_id)
            image_url = (
                _cdn_url_or_id if str(_cdn_url_or_id).lower().startswith(("http://", "https://")) else ""
            )
            if (not image_url) and _cdn_url_or_id:
                image_file_id = _cdn_url_or_id

            content_text = "[图片]"
        elif local_type == 34:
            render_type = "voice"
            duration = _extract_xml_attr(raw_text, "voicelength")
            voice_length = duration
            content_text = f"[语音 {duration}秒]" if duration else "[语音]"
        elif local_type == 43 or local_type == 62:
            render_type = "video"
            video_md5 = _extract_xml_attr(raw_text, "md5")
            video_thumb_md5 = _extract_xml_attr(raw_text, "cdnthumbmd5")
            video_thumb_url_or_id = _extract_xml_attr(raw_text, "cdnthumburl") or _extract_xml_tag_text(
                raw_text, "cdnthumburl"
            )
            video_url_or_id = _extract_xml_attr(raw_text, "cdnvideourl") or _extract_xml_tag_text(
                raw_text, "cdnvideourl"
            )

            video_thumb_url_or_id = _normalize_xml_url(video_thumb_url_or_id)
            video_url_or_id = _normalize_xml_url(video_url_or_id)

            video_thumb_url = (
                video_thumb_url_or_id
                if str(video_thumb_url_or_id or "").strip().lower().startswith(("http://", "https://"))
                else ""
            )
            video_url = (
                video_url_or_id
                if str(video_url_or_id or "").strip().lower().startswith(("http://", "https://"))
                else ""
            )
            video_thumb_file_id = "" if video_thumb_url else (str(video_thumb_url_or_id or "").strip() or "")
            video_file_id = "" if video_url else (str(video_url_or_id or "").strip() or "")
            if (not video_thumb_md5) and resource_conn is not None:
                video_thumb_md5 = _lookup_resource_md5(
                    resource_conn,
                    resource_chat_id,
                    message_local_type=local_type,
                    server_id=int(r["server_id"] or 0),
                    local_id=local_id,
                    create_time=create_time,
                )

            # Some WeChat builds store the on-disk thumbnail basename (32-hex) in packed_info_data (protobuf),
            # while the message XML only carries a long cdnthumburl file_id. Prefer packed_info_data when present.
            if not _is_hex_md5(video_thumb_md5):
                try:
                    packed_val = r["packed_info_data"]
                except Exception:
                    try:
                        packed_val = r.get("packed_info_data")  # type: ignore[attr-defined]
                    except Exception:
                        packed_val = None
                packed_md5 = _extract_md5_from_packed_info(packed_val)
                if packed_md5:
                    video_thumb_md5 = packed_md5
            content_text = "[视频]"
        elif local_type == 47:
            render_type = "emoji"
            emoji_md5 = _extract_xml_attr(raw_text, "md5")
            if not emoji_md5:
                emoji_md5 = _extract_xml_tag_text(raw_text, "md5")
            emoji_url = _extract_xml_attr(raw_text, "cdnurl")
            if not emoji_url:
                emoji_url = _extract_xml_tag_text(raw_text, "cdn_url")
            emoji_url = _normalize_xml_url(emoji_url)
            if (not emoji_md5) and resource_conn is not None:
                emoji_md5 = _lookup_resource_md5(
                    resource_conn,
                    resource_chat_id,
                    message_local_type=local_type,
                    server_id=int(r["server_id"] or 0),
                    local_id=local_id,
                    create_time=create_time,
                )
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
                    parsed_special = False
                    if "<appmsg" in content_text.lower():
                        parsed = _parse_app_message(content_text)
                        rt = str(parsed.get("renderType") or "")
                        if rt and rt != "text":
                            parsed_special = True
                            render_type = rt
                            content_text = str(parsed.get("content") or content_text)
                            title = str(parsed.get("title") or title)
                            url = str(parsed.get("url") or url)
                            record_item = str(parsed.get("recordItem") or record_item)
                            quote_title = str(parsed.get("quoteTitle") or quote_title)
                            quote_content = str(parsed.get("quoteContent") or quote_content)
                            quote_thumb_url = str(parsed.get("quoteThumbUrl") or quote_thumb_url)
                            link_type = str(parsed.get("linkType") or link_type)
                            link_style = str(parsed.get("linkStyle") or link_style)
                            amount = str(parsed.get("amount") or amount)
                            cover_url = str(parsed.get("coverUrl") or cover_url)
                            thumb_url = str(parsed.get("thumbUrl") or thumb_url)
                            from_name = str(parsed.get("from") or from_name)
                            file_size = str(parsed.get("size") or file_size)
                            pay_sub_type = str(parsed.get("paySubType") or pay_sub_type)
                            file_md5 = str(parsed.get("fileMd5") or file_md5)
                            transfer_id = str(parsed.get("transferId") or transfer_id)

                            if render_type == "transfer":
                                # 如果 transferId 仍为空，尝试从原始 XML 提取
                                if not transfer_id:
                                    transfer_id = _extract_xml_tag_or_attr(content_text, "transferid") or ""
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

                    if not parsed_special:
                        t = _extract_xml_tag_text(content_text, "title")
                        d = _extract_xml_tag_text(content_text, "des")
                        content_text = t or d or _infer_message_brief_by_local_type(local_type)

        if not content_text:
            content_text = _infer_message_brief_by_local_type(local_type)

        if quote_username:
            quote_usernames.append(str(quote_username).strip())

        merged.append(
            {
                "id": f"{db_path.stem}:{table_name}:{local_id}",
                "localId": local_id,
                "serverId": int(r["server_id"] or 0),
                "serverIdStr": str(int(r["server_id"] or 0)) if int(r["server_id"] or 0) else "",
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
                "from": from_name,
                "fromUsername": from_username,
                "recordItem": record_item,
                "imageMd5": image_md5,
                "imageFileId": image_file_id,
                "emojiMd5": emoji_md5,
                "emojiUrl": emoji_url,
                "thumbUrl": thumb_url,
                "imageUrl": image_url,
                "videoMd5": video_md5,
                "videoThumbMd5": video_thumb_md5,
                "videoFileId": video_file_id,
                "videoThumbFileId": video_thumb_file_id,
                "videoUrl": video_url,
                "videoThumbUrl": video_thumb_url,
                "voiceLength": voice_length,
                "voipType": voip_type,
                "quoteUsername": str(quote_username).strip(),
                "quoteServerId": str(quote_server_id).strip(),
                "quoteType": str(quote_type).strip(),
                "quoteVoiceLength": str(quote_voice_length).strip(),
                "quoteTitle": quote_title,
                "quoteContent": quote_content,
                "quoteThumbUrl": quote_thumb_url,
                "amount": amount,
                "coverUrl": cover_url,
                "fileSize": file_size,
                "fileMd5": file_md5,
                "paySubType": pay_sub_type,
                "transferStatus": transfer_status,
                "transferId": transfer_id,
                "_rawText": raw_text if local_type == 266287972401 else "",
            }
        )

    if contact_conn is not None:
        try:
            contact_conn.close()
        except Exception:
            pass


def _postprocess_transfer_messages(merged: list[dict[str, Any]]) -> None:
    # 后处理：关联转账消息的最终状态
    # 策略：优先使用 transferId 精确匹配，回退到金额+时间窗口匹配
    # paysubtype 含义：1=不明确 3=已收款 4=对方退回给你 8=发起转账 9=被对方退回 10=已过期
    #
    # Windows 微信在部分场景会为同一笔转账记录两条消息：
    # - paysubtype=1/8：发起/待收款（这里回填为“已被接收”）
    # - paysubtype=3：收款确认（展示为“已收款”）
    #
    # 这两条消息的 isSent 并不能稳定表示“付款方/收款方视角”，因此这里以 transferId 关联结果为准：
    # - 将原始转账消息（1/8）回填为“已被接收”
    # - 若同一 transferId 同时存在原始消息与 paysubtype=3 消息，则将 paysubtype=3 的那条校正为“已收款”

    def _is_transfer_expired_system_message(text: Any) -> bool:
        content = str(text or "").strip()
        if not content:
            return False
        if "转账" not in content or "过期" not in content:
            return False
        if "未接收" in content and ("24小时" in content or "二十四小时" in content):
            return True
        return "已过期" in content and ("收款方" in content or "转账" in content)

    def _mark_pending_transfers_expired_by_system_messages() -> set[str]:
        expired_system_times: list[int] = []
        pending_candidates: list[tuple[int, int]] = []  # (index, createTime)

        for idx, msg in enumerate(merged):
            rt = str(msg.get("renderType") or "").strip()
            if rt == "system":
                if _is_transfer_expired_system_message(msg.get("content")):
                    try:
                        ts = int(msg.get("createTime") or 0)
                    except Exception:
                        ts = 0
                    if ts > 0:
                        expired_system_times.append(ts)
                continue

            if rt != "transfer":
                continue

            pst = str(msg.get("paySubType") or "").strip()
            if pst not in ("1", "8"):
                continue

            try:
                ts = int(msg.get("createTime") or 0)
            except Exception:
                ts = 0
            if ts <= 0:
                continue

            pending_candidates.append((idx, ts))

        if not expired_system_times or not pending_candidates:
            return set()

        used_pending_indexes: set[int] = set()
        expired_transfer_ids: set[str] = set()

        # 过期系统提示通常出现在转账发起约 24 小时后。
        # 为避免误匹配，要求时间差落在 [22h, 26h] 范围内，并选择最接近 24h 的待收款消息。
        for sys_ts in sorted(expired_system_times):
            best_index = -1
            best_distance = 10**9

            for idx, transfer_ts in pending_candidates:
                if idx in used_pending_indexes:
                    continue
                delta = sys_ts - transfer_ts
                if delta < 0:
                    continue
                if delta < 22 * 3600 or delta > 26 * 3600:
                    continue

                distance = abs(delta - 24 * 3600)
                if distance < best_distance:
                    best_distance = distance
                    best_index = idx

            if best_index < 0:
                continue

            used_pending_indexes.add(best_index)
            transfer_msg = merged[best_index]
            transfer_msg["paySubType"] = "10"
            transfer_msg["transferStatus"] = "已过期"

            tid = str(transfer_msg.get("transferId") or "").strip()
            if tid:
                expired_transfer_ids.add(tid)

        return expired_transfer_ids

    expired_transfer_ids = _mark_pending_transfers_expired_by_system_messages()

    returned_transfer_ids: set[str] = set()  # 退还状态的 transferId
    received_transfer_ids: set[str] = set()  # 已收款状态的 transferId
    returned_amounts_with_time: list[tuple[str, int]] = []  # (金额, 时间戳) 用于退还回退匹配
    received_amounts_with_time: list[tuple[str, int]] = []  # (金额, 时间戳) 用于收款回退匹配
    pending_transfer_ids: set[str] = set()  # (paysubtype=1/8) 的 transferId，用于识别“收款确认”消息

    for m in merged:
        if m.get("renderType") != "transfer":
            continue

        pst = str(m.get("paySubType") or "")
        tid = str(m.get("transferId") or "").strip()
        amt = str(m.get("amount") or "")
        ts = int(m.get("createTime") or 0)

        if tid and pst in ("1", "8"):
            pending_transfer_ids.add(tid)

        if pst in ("4", "9"):  # 退还状态
            if tid:
                returned_transfer_ids.add(tid)
            if amt:
                returned_amounts_with_time.append((amt, ts))
        elif pst == "3":  # 已收款状态
            if tid:
                received_transfer_ids.add(tid)
            if amt:
                received_amounts_with_time.append((amt, ts))

    backfilled_message_ids: set[str] = set()

    for m in merged:
        if m.get("renderType") != "transfer":
            continue

        pst = str(m.get("paySubType") or "")
        if pst not in ("1", "8"):
            continue

        tid = str(m.get("transferId") or "").strip()
        amt = str(m.get("amount") or "")
        ts = int(m.get("createTime") or 0)

        should_mark_returned = False
        should_mark_received = False

        # 策略1：精确 transferId 匹配
        if tid:
            if tid in returned_transfer_ids:
                should_mark_returned = True
            elif tid in received_transfer_ids:
                should_mark_received = True

        # 策略2：回退到金额+时间窗口匹配（24小时内同金额）
        if not should_mark_returned and not should_mark_received and amt:
            for ret_amt, ret_ts in returned_amounts_with_time:
                if ret_amt == amt and abs(ret_ts - ts) <= 86400:
                    should_mark_returned = True
                    break
            if not should_mark_returned:
                for rec_amt, rec_ts in received_amounts_with_time:
                    if rec_amt == amt and abs(rec_ts - ts) <= 86400:
                        should_mark_received = True
                        break

        if should_mark_returned:
            m["paySubType"] = "9"
            m["transferStatus"] = "已被退还"
        elif should_mark_received:
            m["paySubType"] = "3"
            m["transferStatus"] = "已被接收"
            mid = str(m.get("id") or "").strip()
            if mid:
                backfilled_message_ids.add(mid)

    # 修正收款确认消息：当同一 transferId 同时存在原始转账消息（1/8）与收款消息（3）时，
    # paysubtype=3 的那条通常是收款确认消息，状态文案应为“已收款”。
    for m in merged:
        if m.get("renderType") != "transfer":
            continue
        pst = str(m.get("paySubType") or "")
        if pst != "3":
            continue
        tid = str(m.get("transferId") or "").strip()
        if not tid or tid not in pending_transfer_ids:
            continue
        if tid in expired_transfer_ids:
            continue
        mid = str(m.get("id") or "").strip()
        if mid and mid in backfilled_message_ids:
            continue
        m["transferStatus"] = "已收款"


def _postprocess_full_messages(
    *,
    merged: list[dict[str, Any]],
    sender_usernames: list[str],
    quote_usernames: list[str],
    pat_usernames: set[str],
    account_dir: Path,
    username: str,
    base_url: str,
    contact_db_path: Path,
    head_image_db_path: Path,
) -> None:
    _postprocess_transfer_messages(merged)

    # Some appmsg payloads provide only `from` (sourcedisplayname) but not `fromUsername` (sourceusername).
    # Recover `fromUsername` via contact.db so the frontend can render the publisher avatar.
    missing_from_names = [
        str(m.get("from") or "").strip()
        for m in merged
        if str(m.get("renderType") or "").strip() == "link"
        and str(m.get("from") or "").strip()
        and not str(m.get("fromUsername") or "").strip()
    ]
    if missing_from_names:
        name_to_username = _load_usernames_by_display_names(contact_db_path, missing_from_names)
        if name_to_username:
            for m in merged:
                if str(m.get("fromUsername") or "").strip():
                    continue
                if str(m.get("renderType") or "").strip() != "link":
                    continue
                fn = str(m.get("from") or "").strip()
                if fn and fn in name_to_username:
                    m["fromUsername"] = name_to_username[fn]

    from_usernames = [str(m.get("fromUsername") or "").strip() for m in merged]
    uniq_senders = list(
        dict.fromkeys([u for u in (sender_usernames + list(pat_usernames) + quote_usernames + from_usernames) if u])
    )
    sender_contact_rows = _load_contact_rows(contact_db_path, uniq_senders)
    local_sender_avatars = _query_head_image_usernames(head_image_db_path, uniq_senders)

    # contact.db may not include enterprise/openim contacts (or group chatroom records). WCDB has a more complete
    # view of display names + avatar URLs, so we use it as a best-effort fallback.
    wcdb_display_names: dict[str, str] = {}
    wcdb_avatar_urls: dict[str, str] = {}
    try:
        need_display: list[str] = []
        need_avatar: list[str] = []
        for u in uniq_senders:
            if not u:
                continue
            row = sender_contact_rows.get(u)
            if _pick_display_name(row, u) == u:
                need_display.append(u)
            if u not in local_sender_avatars:
                need_avatar.append(u)

        need_display = list(dict.fromkeys(need_display))
        need_avatar = list(dict.fromkeys(need_avatar))
        if need_display or need_avatar:
            wcdb_conn = WCDB_REALTIME.ensure_connected(account_dir)
            with wcdb_conn.lock:
                if need_display:
                    wcdb_display_names = _wcdb_get_display_names(wcdb_conn.handle, need_display)
                if need_avatar:
                    wcdb_avatar_urls = _wcdb_get_avatar_urls(wcdb_conn.handle, need_avatar)
    except Exception:
        wcdb_display_names = {}
        wcdb_avatar_urls = {}

    group_nicknames = _load_group_nickname_map(
        account_dir=account_dir,
        contact_db_path=contact_db_path,
        chatroom_id=username,
        sender_usernames=uniq_senders,
    )

    for m in merged:
        # If appmsg doesn't provide sourcedisplayname, try mapping sourceusername to display name.
        if (not str(m.get("from") or "").strip()) and str(m.get("fromUsername") or "").strip():
            fu = str(m.get("fromUsername") or "").strip()
            frow = sender_contact_rows.get(fu)
            if frow is not None:
                m["from"] = _pick_display_name(frow, fu)
            else:
                wd = str(wcdb_display_names.get(fu) or "").strip()
                if wd:
                    m["from"] = wd

        su = str(m.get("senderUsername") or "")
        if not su:
            continue
        m["senderDisplayName"] = _resolve_sender_display_name(
            sender_username=su,
            sender_contact_rows=sender_contact_rows,
            wcdb_display_names=wcdb_display_names,
            group_nicknames=group_nicknames,
        )
        avatar_url = base_url + _avatar_url_unified(
            account_dir=account_dir,
            username=su,
            local_avatar_usernames=local_sender_avatars,
        )
        m["senderAvatar"] = avatar_url

        qu = str(m.get("quoteUsername") or "").strip()
        if qu:
            qrow = sender_contact_rows.get(qu)
            qt = str(m.get("quoteTitle") or "").strip()
            if qrow is not None:
                remark = ""
                try:
                    remark = str(qrow["remark"] or "").strip()
                except Exception:
                    remark = ""
                if remark:
                    m["quoteTitle"] = remark
                elif not qt:
                    title = _pick_display_name(qrow, qu)
                    if title == qu:
                        wd = str(wcdb_display_names.get(qu) or "").strip()
                        if wd and wd != qu:
                            title = wd
                    m["quoteTitle"] = title
            elif not qt:
                wd = str(wcdb_display_names.get(qu) or "").strip()
                m["quoteTitle"] = wd or qu

        # Media URL fallback: if CDN URLs missing, use local media endpoints.
        try:
            rt = str(m.get("renderType") or "")
            if rt == "image":
                if not str(m.get("imageUrl") or ""):
                    md5 = str(m.get("imageMd5") or "").strip()
                    file_id = str(m.get("imageFileId") or "").strip()
                    if md5:
                        m["imageUrl"] = (
                            base_url
                            + f"/api/chat/media/image?account={quote(account_dir.name)}&md5={quote(md5)}&username={quote(username)}"
                        )
                    elif file_id:
                        m["imageUrl"] = (
                            base_url
                            + f"/api/chat/media/image?account={quote(account_dir.name)}&file_id={quote(file_id)}&username={quote(username)}"
                        )
            elif rt == "emoji":
                md5 = str(m.get("emojiMd5") or "")
                if md5:
                    existing_local: Optional[Path] = None
                    try:
                        existing_local = _try_find_decrypted_resource(account_dir, str(md5).lower())
                    except Exception:
                        existing_local = None

                    if existing_local:
                        try:
                            cur = str(m.get("emojiUrl") or "")
                            if cur and re.match(r"^https?://", cur, flags=re.I) and (
                                "/api/chat/media/emoji" not in cur
                            ):
                                m["emojiRemoteUrl"] = cur
                        except Exception:
                            pass

                        m["emojiUrl"] = (
                            base_url
                            + f"/api/chat/media/emoji?account={quote(account_dir.name)}&md5={quote(md5)}&username={quote(username)}"
                        )
                    elif (not str(m.get("emojiUrl") or "")):
                        m["emojiUrl"] = (
                            base_url
                            + f"/api/chat/media/emoji?account={quote(account_dir.name)}&md5={quote(md5)}&username={quote(username)}"
                        )
            elif rt == "video":
                video_thumb_url = str(m.get("videoThumbUrl") or "").strip()
                video_thumb_md5 = str(m.get("videoThumbMd5") or "").strip()
                video_thumb_file_id = str(m.get("videoThumbFileId") or "").strip()
                if (not video_thumb_url) or (
                    not video_thumb_url.lower().startswith(("http://", "https://"))
                ):
                    if video_thumb_md5:
                        m["videoThumbUrl"] = (
                            base_url
                            + f"/api/chat/media/video_thumb?account={quote(account_dir.name)}&md5={quote(video_thumb_md5)}&username={quote(username)}"
                        )
                    elif video_thumb_file_id:
                        m["videoThumbUrl"] = (
                            base_url
                            + f"/api/chat/media/video_thumb?account={quote(account_dir.name)}&file_id={quote(video_thumb_file_id)}&username={quote(username)}"
                        )

                video_url = str(m.get("videoUrl") or "").strip()
                video_md5 = str(m.get("videoMd5") or "").strip()
                video_file_id = str(m.get("videoFileId") or "").strip()
                if (not video_url) or (not video_url.lower().startswith(("http://", "https://"))):
                    if video_md5:
                        m["videoUrl"] = (
                            base_url
                            + f"/api/chat/media/video?account={quote(account_dir.name)}&md5={quote(video_md5)}&username={quote(username)}"
                        )
                    elif video_file_id:
                        m["videoUrl"] = (
                            base_url
                            + f"/api/chat/media/video?account={quote(account_dir.name)}&file_id={quote(video_file_id)}&username={quote(username)}"
                        )
            elif rt == "link":
                # Some appmsg link cards (notably Bilibili shares) carry a non-HTTP `<thumburl>` payload
                # (often an ASN.1-ish hex blob). The actual preview image is typically saved as:
                #   msg/attach/{md5(conv_username)}/.../Img/{local_id}_{create_time}_t.dat
                # Expose it via the existing image endpoint using file_id.
                thumb_url = str(m.get("thumbUrl") or "").strip()
                if thumb_url and (not thumb_url.lower().startswith(("http://", "https://"))):
                    try:
                        lid = int(m.get("localId") or 0)
                    except Exception:
                        lid = 0
                    try:
                        ct = int(m.get("createTime") or 0)
                    except Exception:
                        ct = 0
                    if lid > 0 and ct > 0:
                        file_id = f"{lid}_{ct}"
                        m["thumbUrl"] = (
                            base_url
                            + f"/api/chat/media/image?account={quote(account_dir.name)}&file_id={quote(file_id)}&username={quote(username)}"
                        )
            elif rt == "voice":
                if str(m.get("serverId") or ""):
                    sid = int(m.get("serverId") or 0)
                    if sid:
                        m["voiceUrl"] = base_url + f"/api/chat/media/voice?account={quote(account_dir.name)}&server_id={sid}"
        except Exception:
            pass

        if int(m.get("type") or 0) == 266287972401:
            raw = str(m.get("_rawText") or "")
            if raw:
                m["content"] = _parse_pat_message(raw, sender_contact_rows)

        if "_rawText" in m:
            m.pop("_rawText", None)


@router.get("/api/chat/accounts", summary="列出已解密账号")
async def list_chat_accounts():
    """列出 output/databases 下可用于聊天预览的账号目录"""
    accounts = _list_decrypted_accounts()
    if not accounts:
        return {
            "status": "error",
            "accounts": [],
            "default_account": None,
            "message": "No decrypted databases found. Please decrypt first.",
        }

    return {
        "status": "success",
        "accounts": accounts,
        "default_account": accounts[0],
    }


@router.get("/api/chat/sessions", summary="获取会话列表（聊天左侧列表）")
def list_chat_sessions(
    request: Request,
    account: Optional[str] = None,
    limit: int = 400,
    include_hidden: bool = False,
    include_official: bool = False,
    preview: str = "latest",
    source: Optional[str] = None,
):
    """从 session.db + contact.db 读取会话列表，用于前端聊天界面动态渲染联系人"""
    if limit <= 0:
        raise HTTPException(status_code=400, detail="Invalid limit.")
    if limit > 2000:
        limit = 2000

    source_norm = _normalize_chat_source(source)
    account_dir = _resolve_account_dir(account)
    contact_db_path = account_dir / "contact.db"
    head_image_db_path = account_dir / "head_image.db"
    base_url = str(request.base_url).rstrip("/")

    rt_conn = None
    rows: list[Any]
    if source_norm == "realtime":
        trace_id = f"rt-sessions-{int(time.time() * 1000)}-{threading.get_ident()}"
        logger.info(
            "[%s] list_sessions realtime start account=%s limit=%s include_hidden=%s include_official=%s preview=%s",
            trace_id,
            account_dir.name,
            int(limit),
            bool(include_hidden),
            bool(include_official),
            str(preview or ""),
        )
        try:
            logger.info("[%s] ensure wcdb connected account=%s", trace_id, account_dir.name)
            conn = WCDB_REALTIME.ensure_connected(account_dir)
            rt_conn = conn
            logger.info("[%s] wcdb connected account=%s handle=%s", trace_id, account_dir.name, int(conn.handle))
            logger.info("[%s] wcdb_get_sessions account=%s", trace_id, account_dir.name)
            wcdb_t0 = time.perf_counter()
            with conn.lock:
                raw = _wcdb_get_sessions(conn.handle)
            wcdb_ms = (time.perf_counter() - wcdb_t0) * 1000.0
            logger.info(
                "[%s] wcdb_get_sessions done account=%s sessions=%s ms=%.1f",
                trace_id,
                account_dir.name,
                len(raw or []),
                wcdb_ms,
            )
        except WCDBRealtimeError as e:
            raise HTTPException(status_code=400, detail=str(e))

        norm: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            uname = str(item.get("username") or item.get("user_name") or item.get("UserName") or "").strip()
            if not uname:
                continue
            norm.append(
                {
                    "username": uname,
                    "unread_count": item.get("unread_count", item.get("unreadCount", 0)),
                    "is_hidden": item.get("is_hidden", item.get("isHidden", 0)),
                    "summary": item.get("summary", ""),
                    "draft": item.get("draft", ""),
                    "last_timestamp": item.get("last_timestamp", item.get("lastTimestamp", 0)),
                    "sort_timestamp": item.get("sort_timestamp", item.get("sortTimestamp", item.get("last_timestamp", 0))),
                    "last_msg_type": item.get("last_msg_type", item.get("lastMsgType", 0)),
                    "last_msg_sub_type": item.get("last_msg_sub_type", item.get("lastMsgSubType", 0)),
                    # Keep these fields so group session previews can render "sender: content" without
                    # crashing (realtime rows are dicts, not sqlite Rows).
                    "last_msg_sender": item.get("last_msg_sender", item.get("lastMsgSender", "")),
                    "last_sender_display_name": item.get(
                        "last_sender_display_name",
                        item.get("lastSenderDisplayName", ""),
                    ),
                    "last_msg_locald_id": item.get(
                        "last_msg_locald_id",
                        item.get("lastMsgLocaldId", item.get("lastMsgLocalId", 0)),
                    ),
                }
            )

        def _ts(v: Any) -> int:
            try:
                return int(v or 0)
            except Exception:
                return 0

        norm.sort(key=lambda r: _ts(r.get("sort_timestamp")), reverse=True)
        rows = norm
        logger.info("[%s] list_sessions realtime normalized account=%s rows=%s", trace_id, account_dir.name, len(rows))
    else:
        session_db_path = account_dir / "session.db"
        sconn = sqlite3.connect(str(session_db_path))
        sconn.row_factory = sqlite3.Row
        try:
            try:
                rows = sconn.execute(
                    """
                    SELECT
                        username,
                        unread_count,
                        is_hidden,
                        summary,
                        draft,
                        last_timestamp,
                        sort_timestamp,
                        last_msg_locald_id,
                        last_msg_type,
                        last_msg_sub_type,
                        last_msg_sender,
                        last_sender_display_name
                    FROM SessionTable
                    ORDER BY sort_timestamp DESC
                    LIMIT ?
                    """,
                    (int(limit),),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = sconn.execute(
                    """
                    SELECT
                        username,
                        unread_count,
                        is_hidden,
                        summary,
                        draft,
                        last_timestamp,
                        sort_timestamp,
                        last_msg_type,
                        last_msg_sub_type
                    FROM SessionTable
                    ORDER BY sort_timestamp DESC
                    LIMIT ?
                    """,
                    (int(limit),),
                ).fetchall()
        finally:
            sconn.close()

    filtered: list[Any] = []
    for r in rows:
        username = _session_row_get(r, "username", "") or ""
        if not username:
            continue
        if not include_hidden and int((_session_row_get(r, "is_hidden", 0) or 0)) == 1:
            continue
        if not _should_keep_session(username, include_official=include_official):
            continue
        filtered.append(r)

    raw_usernames = [str(_session_row_get(r, "username", "") or "").strip() for r in filtered]
    top_flags = _load_contact_top_flags(contact_db_path, raw_usernames)

    def _to_int(v: Any) -> int:
        try:
            return int(v or 0)
        except Exception:
            return 0

    def _session_sort_key(row: Any) -> tuple[int, int, int]:
        username = str(_session_row_get(row, "username", "") or "").strip()
        sort_ts = _to_int(_session_row_get(row, "sort_timestamp", 0))
        last_ts = _to_int(_session_row_get(row, "last_timestamp", 0))
        return (
            1 if bool(top_flags.get(username, False)) else 0,
            sort_ts,
            last_ts,
        )

    filtered.sort(key=_session_sort_key, reverse=True)
    if len(filtered) > int(limit):
        filtered = filtered[: int(limit)]

    usernames: list[str] = []
    for r in filtered:
        username = str(_session_row_get(r, "username", "") or "").strip()
        if username:
            usernames.append(username)

    contact_rows = _load_contact_rows(contact_db_path, usernames)
    local_avatar_usernames = _query_head_image_usernames(head_image_db_path, usernames)

    # Some sessions (notably enterprise groups / openim-related IDs) may be missing from decrypted contact.db
    # (or lack nickname/avatar columns). In that case, fall back to WCDB APIs (same as WeFlow) to resolve
    # display names + avatar URLs.
    wcdb_display_names: dict[str, str] = {}
    wcdb_avatar_urls: dict[str, str] = {}
    try:
        need_display: list[str] = []
        need_avatar: list[str] = []
        if source_norm == "realtime":
            # In realtime mode, always ask WCDB for display names: decrypted contact.db can be stale.
            need_display = [str(u or "").strip() for u in usernames if str(u or "").strip()]
        for u in usernames:
            if not u:
                continue
            if source_norm != "realtime":
                row = contact_rows.get(u)
                if _pick_display_name(row, u) == u:
                    need_display.append(u)
            if source_norm == "realtime":
                # In realtime mode, prefer WCDB-resolved avatar URLs (contact.db can be stale).
                if u not in local_avatar_usernames:
                    need_avatar.append(u)
            else:
                if u not in local_avatar_usernames:
                    need_avatar.append(u)

        need_display = list(dict.fromkeys(need_display))
        need_avatar = list(dict.fromkeys(need_avatar))
        if need_display or need_avatar:
            wcdb_conn = rt_conn
            if wcdb_conn is None:
                status = WCDB_REALTIME.get_status(account_dir)
                can_connect = bool(status.get("dll_present")) and bool(status.get("key_present")) and bool(
                    status.get("session_db_path")
                )
                if can_connect:
                    wcdb_conn = WCDB_REALTIME.ensure_connected(account_dir)
            if wcdb_conn is not None:
                with wcdb_conn.lock:
                    if need_display:
                        wcdb_display_names = _wcdb_get_display_names(wcdb_conn.handle, need_display)
                    if need_avatar:
                        wcdb_avatar_urls = _wcdb_get_avatar_urls(wcdb_conn.handle, need_avatar)
    except Exception:
        wcdb_display_names = {}
        wcdb_avatar_urls = {}

    preview_mode = str(preview or "").strip().lower()
    if preview_mode not in {"latest", "index", "session", "db", "none"}:
        preview_mode = "latest"
    if preview_mode == "index":
        preview_mode = "latest"
    if source_norm == "realtime" and preview_mode in {"latest", "db"}:
        # Decrypted caches may be stale; prefer session summary in realtime mode.
        preview_mode = "session"

    last_previews: dict[str, str] = {}
    if preview_mode == "latest":
        try:
            last_previews = load_session_last_messages(account_dir, usernames)
            # Backward-compatible: old decrypted accounts may not have built the cache table yet.
            if (not last_previews) and usernames:
                build_session_last_message_table(
                    account_dir,
                    rebuild=False,
                    include_hidden=True,
                    include_official=True,
                )
                last_previews = load_session_last_messages(account_dir, usernames)
        except Exception:
            last_previews = {}

    if preview_mode in {"latest", "db"}:
        targets = usernames if preview_mode == "db" else [u for u in usernames if u and (u not in last_previews)]
        if targets:
            legacy = _load_latest_message_previews(account_dir, targets)
            for u, v in legacy.items():
                if v:
                    last_previews[u] = v

    group_sender_display_names: dict[str, str] = _build_group_sender_display_name_map(
        contact_db_path,
        last_previews,
    )
    unresolved = []
    for conv_username, preview_text in last_previews.items():
        if not str(conv_username or "").endswith("@chatroom"):
            continue
        sender_username = _extract_group_preview_sender_username(preview_text)
        if sender_username and sender_username not in group_sender_display_names:
            unresolved.append(sender_username)
    unresolved = list(dict.fromkeys(unresolved))
    if unresolved:
        try:
            wcdb_conn = rt_conn or WCDB_REALTIME.ensure_connected(account_dir)
            with wcdb_conn.lock:
                wcdb_names = _wcdb_get_display_names(wcdb_conn.handle, unresolved)
            for sender_username in unresolved:
                wcdb_name = str(wcdb_names.get(sender_username) or "").strip()
                if wcdb_name and wcdb_name != sender_username:
                    group_sender_display_names[sender_username] = wcdb_name
        except Exception:
            pass

    sessions: list[dict[str, Any]] = []
    for r in filtered:
        username = r["username"]
        c_row = contact_rows.get(username)

        display_name = _pick_display_name(c_row, username)
        wd = str(wcdb_display_names.get(username) or "").strip()
        if source_norm == "realtime" and wd and wd != username:
            display_name = wd
        elif display_name == username:
            if wd and wd != username:
                display_name = wd

        # Prefer local head_image avatars when available: decrypted contact.db URLs can be stale
        # (or hotlink-protected for browsers). WCDB realtime (when available) is the next best.
        avatar_url = base_url + _avatar_url_unified(
            account_dir=account_dir,
            username=username,
            local_avatar_usernames=local_avatar_usernames,
        )

        last_message = ""
        if preview_mode == "session":
            draft_text = _decode_sqlite_text(r["draft"]).strip()
            if draft_text:
                draft_text = re.sub(r"\s+", " ", draft_text).strip()
                last_message = f"[草稿] {draft_text}" if draft_text else "[草稿]"
            else:
                summary_text = _decode_sqlite_text(r["summary"]).strip()
                summary_text = re.sub(r"\s+", " ", summary_text).strip()
                if summary_text:
                    last_message = summary_text
                else:
                    last_message = _infer_last_message_brief(r["last_msg_type"], r["last_msg_sub_type"])
        elif preview_mode in {"latest", "db"}:
            if str(last_previews.get(username) or "").strip():
                last_message = str(last_previews.get(username) or "").strip()
            elif preview_mode != "none":
                summary_text = _decode_sqlite_text(r["summary"]).strip()
                summary_text = re.sub(r"\s+", " ", summary_text).strip()
                if summary_text:
                    last_message = summary_text
                else:
                    last_message = _infer_last_message_brief(r["last_msg_type"], r["last_msg_sub_type"])
        elif preview_mode != "none":
            summary_text = _decode_sqlite_text(r["summary"]).strip()
            summary_text = re.sub(r"\s+", " ", summary_text).strip()
            if summary_text:
                last_message = summary_text
            else:
                last_message = _infer_last_message_brief(r["last_msg_type"], r["last_msg_sub_type"])

        # 合并转发聊天记录：左侧会话列表统一显示为 [聊天记录]
        if preview_mode != "none" and not str(last_message or "").startswith("[草稿]"):
            try:
                last_msg_type = int(r["last_msg_type"] or 0)
            except Exception:
                last_msg_type = 0
            try:
                last_msg_sub_type = int(r["last_msg_sub_type"] or 0)
            except Exception:
                last_msg_sub_type = 0
            if last_msg_type == 81604378673 or (last_msg_type == 49 and last_msg_sub_type == 19):
                last_message = "[聊天记录]"

        last_message = _normalize_session_preview_text(
            last_message,
            is_group=bool(str(username or "").endswith("@chatroom")),
            sender_display_names=group_sender_display_names,
        )
        if str(username or "").endswith("@chatroom") and str(last_message or "") and not str(last_message).startswith("[草稿]"):
            # Prefer group card nickname when available. In realtime mode, WCDB session rows can provide
            # `last_sender_display_name`, but we may still get a summary that doesn't include "sender:".
            # Also guard against URL schemes like "https://..." being mis-parsed as "https: //...".
            raw_sender_display = ""
            try:
                raw_sender_display = r["last_sender_display_name"]
            except Exception:
                try:
                    raw_sender_display = r.get("last_sender_display_name", "")
                except Exception:
                    raw_sender_display = ""
            sender_display = _decode_sqlite_text(raw_sender_display).strip()
            if sender_display:
                text = re.sub(r"\s+", " ", str(last_message or "").strip()).strip()
                match = re.match(r"^([^:\n]{1,128}):\s*(.+)$", text)
                if match:
                    prefix = str(match.group(1) or "").strip()
                    body = re.sub(r"\s+", " ", str(match.group(2) or "").strip()).strip()
                    if prefix.lower() in {"http", "https"} and body.startswith("//"):
                        last_message = f"{sender_display}: {text}"
                    else:
                        last_message = f"{sender_display}: {body}"
                else:
                    last_message = f"{sender_display}: {text}"

        last_time = _format_session_time(r["sort_timestamp"] or r["last_timestamp"])

        sessions.append(
            {
                "id": username,
                "username": username,
                "name": display_name,
                "avatar": avatar_url,
                "lastMessage": last_message,
                "lastMessageTime": last_time,
                "unreadCount": int(r["unread_count"] or 0),
                "isGroup": bool(username.endswith("@chatroom")),
                "isTop": bool(top_flags.get(str(username or "").strip(), False)),
            }
        )

    return {
        "status": "success",
        "account": account_dir.name,
        "total": len(sessions),
        "sessions": sessions,
    }


def _collect_chat_messages(
    *,
    username: str,
    account_dir: Path,
    db_paths: list[Path],
    resource_conn: Optional[sqlite3.Connection],
    resource_chat_id: Optional[int],
    take: int,
    want_types: Optional[set[str]],
) -> tuple[list[dict[str, Any]], bool, list[str], list[str], set[str]]:
    is_group = bool(username.endswith("@chatroom"))
    take = int(take)
    if take < 0:
        take = 0
    take_probe = take + 1

    merged: list[dict[str, Any]] = []
    sender_usernames: list[str] = []
    quote_usernames: list[str] = []
    pat_usernames: set[str] = set()
    has_more_any = False

    contact_conn: Optional[sqlite3.Connection] = None
    alias_cache: dict[str, str] = {}
    if is_group:
        try:
            contact_db_path = account_dir / "contact.db"
            if contact_db_path.exists():
                contact_conn = sqlite3.connect(str(contact_db_path))
        except Exception:
            contact_conn = None

    for db_path in db_paths:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            table_name = _resolve_msg_table_name(conn, username)
            if not table_name:
                continue

            my_wxid = account_dir.name
            my_rowid = None
            try:
                r = conn.execute(
                    "SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1",
                    (my_wxid,),
                ).fetchone()
                if r is not None:
                    my_rowid = int(r[0])
            except Exception:
                my_rowid = None

            quoted_table = _quote_ident(table_name)
            has_packed_info_data = False
            try:
                cols = conn.execute(f"PRAGMA table_info({quoted_table})").fetchall()
                has_packed_info_data = any(str(c[1] or "").strip().lower() == "packed_info_data" for c in cols)
            except Exception:
                has_packed_info_data = False

            packed_select = (
                "m.packed_info_data AS packed_info_data, " if has_packed_info_data else "NULL AS packed_info_data, "
            )
            sql_with_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, "
                + packed_select
                + "n.user_name AS sender_username "
                f"FROM {quoted_table} m "
                "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
                "ORDER BY m.create_time DESC, m.sort_seq DESC, m.local_id DESC "
                "LIMIT ?"
            )
            sql_no_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, "
                + packed_select
                + "'' AS sender_username "
                f"FROM {quoted_table} m "
                "ORDER BY m.create_time DESC, m.sort_seq DESC, m.local_id DESC "
                "LIMIT ?"
            )

            # Force sqlite3 to return TEXT as raw bytes for this query, so we can zstd-decompress
            # compress_content reliably.
            conn.text_factory = bytes

            try:
                rows = conn.execute(sql_with_join, (take_probe,)).fetchall()
            except Exception:
                rows = conn.execute(sql_no_join, (take_probe,)).fetchall()
            if len(rows) > take:
                has_more_any = True
                rows = rows[:take]

            for r in rows:
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

                raw_text = _decode_message_content(r["compress_content"], r["message_content"])
                raw_text = raw_text.strip()

                sender_prefix = ""
                if is_group and raw_text and (not raw_text.startswith("<")) and (not raw_text.startswith('"<')):
                    sender_alias = ""
                    sep = raw_text.find(":\n")
                    if sep > 0:
                        prefix = raw_text[:sep].strip()
                        if prefix and sender_username and prefix != sender_username:
                            strong_hint = prefix.startswith("wxid_") or prefix.endswith("@chatroom") or "@" in prefix
                            if not strong_hint:
                                body_probe = raw_text[sep + 2 :].lstrip("\n").lstrip()
                                body_is_xml = body_probe.startswith("<") or body_probe.startswith('"<')
                                if not body_is_xml:
                                    sender_alias = _lookup_contact_alias(contact_conn, alias_cache, sender_username)
                    sender_prefix, raw_text = _split_group_sender_prefix(raw_text, sender_username, sender_alias)

                if is_group and sender_prefix and (not sender_username):
                    sender_username = sender_prefix

                if is_group and (not sender_username) and (raw_text.startswith("<") or raw_text.startswith('"<')):
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
                from_name = ""
                from_username = ""
                record_item = ""
                image_md5 = ""
                emoji_md5 = ""
                emoji_url = ""
                thumb_url = ""
                image_url = ""
                image_file_id = ""
                video_md5 = ""
                video_thumb_md5 = ""
                video_file_id = ""
                video_thumb_file_id = ""
                video_url = ""
                video_thumb_url = ""
                voice_length = ""
                quote_username = ""
                quote_title = ""
                quote_content = ""
                quote_thumb_url = ""
                link_type = ""
                link_style = ""
                quote_server_id = ""
                quote_type = ""
                quote_voice_length = ""
                amount = ""
                cover_url = ""
                file_size = ""
                pay_sub_type = ""
                transfer_status = ""
                file_md5 = ""
                transfer_id = ""
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
                    from_name = str(parsed.get("from") or "")
                    from_username = str(parsed.get("fromUsername") or "")
                    record_item = str(parsed.get("recordItem") or "")
                    quote_title = str(parsed.get("quoteTitle") or "")
                    quote_content = str(parsed.get("quoteContent") or "")
                    quote_thumb_url = str(parsed.get("quoteThumbUrl") or "")
                    link_type = str(parsed.get("linkType") or "")
                    link_style = str(parsed.get("linkStyle") or "")
                    quote_username = str(parsed.get("quoteUsername") or "")
                    quote_server_id = str(parsed.get("quoteServerId") or "")
                    quote_type = str(parsed.get("quoteType") or "")
                    quote_voice_length = str(parsed.get("quoteVoiceLength") or "")
                    amount = str(parsed.get("amount") or "")
                    cover_url = str(parsed.get("coverUrl") or "")
                    thumb_url = str(parsed.get("thumbUrl") or "")
                    file_size = str(parsed.get("size") or "")
                    pay_sub_type = str(parsed.get("paySubType") or "")
                    file_md5 = str(parsed.get("fileMd5") or "")
                    transfer_id = str(parsed.get("transferId") or "")

                    if render_type == "transfer":
                        # 直接从原始 XML 提取 transferid（可能在 wcpayinfo 内）
                        if not transfer_id:
                            transfer_id = _extract_xml_tag_or_attr(raw_text, "transferid") or ""
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
                    template = _extract_xml_tag_text(raw_text, "template")
                    if template:
                        # import re
                        pat_usernames.update({m.group(1) for m in re.finditer(r"\$\{([^}]+)\}", template) if m.group(1)})
                        content_text = "[拍一拍]"
                    else:
                        content_text = "[拍一拍]"
                elif local_type == 244813135921:
                    render_type = "quote"
                    parsed = _parse_app_message(raw_text)
                    content_text = str(parsed.get("content") or "[引用消息]")
                    quote_title = str(parsed.get("quoteTitle") or "")
                    quote_content = str(parsed.get("quoteContent") or "")
                    quote_thumb_url = str(parsed.get("quoteThumbUrl") or "")
                    link_type = str(parsed.get("linkType") or "")
                    link_style = str(parsed.get("linkStyle") or "")
                    quote_username = str(parsed.get("quoteUsername") or "")
                    quote_server_id = str(parsed.get("quoteServerId") or "")
                    quote_type = str(parsed.get("quoteType") or "")
                    quote_voice_length = str(parsed.get("quoteVoiceLength") or "")
                elif local_type == 3:
                    render_type = "image"
                    # 先尝试从 XML 中提取 md5（不同版本字段可能不同）
                    image_md5 = _extract_xml_attr(raw_text, "md5") or _extract_xml_tag_text(raw_text, "md5")
                    if not image_md5:
                        for k in [
                            "cdnthumbmd5",
                            "cdnthumd5",
                            "cdnmidimgmd5",
                            "cdnbigimgmd5",
                            "hdmd5",
                            "hevc_mid_md5",
                            "hevc_md5",
                            "imgmd5",
                            "filemd5",
                        ]:
                            image_md5 = _extract_xml_attr(raw_text, k) or _extract_xml_tag_text(raw_text, k)
                            if image_md5:
                                break

                    # Prefer message_resource.db md5 for local files: XML md5 frequently differs from the on-disk *.dat basename
                    # (especially for *_t.dat thumbnails), causing the media endpoint to 404.
                    if resource_conn is not None:
                        try:
                            resource_md5 = _lookup_resource_md5(
                                resource_conn,
                                resource_chat_id,
                                message_local_type=local_type,
                                server_id=int(r["server_id"] or 0),
                                local_id=local_id,
                                create_time=create_time,
                            )
                        except Exception:
                            resource_md5 = ""
                        resource_md5 = str(resource_md5 or "").strip().lower()
                        if len(resource_md5) == 32 and all(c in "0123456789abcdef" for c in resource_md5):
                            image_md5 = resource_md5

                    packed_md5 = _extract_md5_from_packed_info(r["packed_info_data"])
                    if packed_md5:
                        image_md5 = packed_md5

                    # Extract CDN URL (some versions store a non-HTTP "file id" string here)
                    _cdn_url_or_id = (
                        _extract_xml_attr(raw_text, "cdnthumburl")
                        or _extract_xml_attr(raw_text, "cdnthumurl")
                        or _extract_xml_attr(raw_text, "cdnmidimgurl")
                        or _extract_xml_attr(raw_text, "cdnbigimgurl")
                        or _extract_xml_tag_text(raw_text, "cdnthumburl")
                        or _extract_xml_tag_text(raw_text, "cdnthumurl")
                        or _extract_xml_tag_text(raw_text, "cdnmidimgurl")
                        or _extract_xml_tag_text(raw_text, "cdnbigimgurl")
                    )
                    _cdn_url_or_id = str(_cdn_url_or_id or "").strip()
                    image_url = _cdn_url_or_id if _cdn_url_or_id.startswith(("http://", "https://")) else ""
                    if (not image_url) and _cdn_url_or_id:
                        image_file_id = _cdn_url_or_id
                    content_text = "[图片]"
                elif local_type == 34:
                    render_type = "voice"
                    duration = _extract_xml_attr(raw_text, "voicelength")
                    voice_length = duration
                    content_text = f"[语音 {duration}秒]" if duration else "[语音]"
                elif local_type == 43 or local_type == 62:
                    render_type = "video"
                    video_md5 = _extract_xml_attr(raw_text, "md5")
                    video_thumb_md5 = _extract_xml_attr(raw_text, "cdnthumbmd5")
                    video_thumb_url_or_id = _extract_xml_attr(raw_text, "cdnthumburl") or _extract_xml_tag_text(
                        raw_text, "cdnthumburl"
                    )
                    video_url_or_id = _extract_xml_attr(raw_text, "cdnvideourl") or _extract_xml_tag_text(
                        raw_text, "cdnvideourl"
                    )

                    video_thumb_url = (
                        video_thumb_url_or_id
                        if str(video_thumb_url_or_id or "").strip().lower().startswith(("http://", "https://"))
                        else ""
                    )
                    video_url = (
                        video_url_or_id
                        if str(video_url_or_id or "").strip().lower().startswith(("http://", "https://"))
                        else ""
                    )
                    video_thumb_file_id = "" if video_thumb_url else (str(video_thumb_url_or_id or "").strip() or "")
                    video_file_id = "" if video_url else (str(video_url_or_id or "").strip() or "")
                    if (not video_thumb_md5) and resource_conn is not None:
                        video_thumb_md5 = _lookup_resource_md5(
                            resource_conn,
                            resource_chat_id,
                            message_local_type=local_type,
                            server_id=int(r["server_id"] or 0),
                            local_id=local_id,
                            create_time=create_time,
                        )

                    if not _is_hex_md5(video_thumb_md5):
                        packed_md5 = _extract_md5_from_packed_info(r["packed_info_data"])
                        if packed_md5:
                            video_thumb_md5 = packed_md5
                    content_text = "[视频]"
                elif local_type == 47:
                    render_type = "emoji"
                    emoji_md5 = _extract_xml_attr(raw_text, "md5")
                    if not emoji_md5:
                        emoji_md5 = _extract_xml_tag_text(raw_text, "md5")
                    emoji_url = _extract_xml_attr(raw_text, "cdnurl")
                    if not emoji_url:
                        emoji_url = _extract_xml_tag_text(raw_text, "cdn_url")
                    if (not emoji_md5) and resource_conn is not None:
                        emoji_md5 = _lookup_resource_md5(
                            resource_conn,
                            resource_chat_id,
                            message_local_type=local_type,
                            server_id=int(r["server_id"] or 0),
                            local_id=local_id,
                            create_time=create_time,
                        )
                    content_text = "[表情]"
                elif local_type == 50:
                    render_type = "voip"
                    try:
                        # import re
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
                            parsed_special = False
                            if "<appmsg" in content_text.lower():
                                parsed = _parse_app_message(content_text)
                                rt = str(parsed.get("renderType") or "")
                                if rt and rt != "text":
                                    parsed_special = True
                                    render_type = rt
                                    content_text = str(parsed.get("content") or content_text)
                                    title = str(parsed.get("title") or title)
                                    url = str(parsed.get("url") or url)
                                    from_name = str(parsed.get("from") or from_name)
                                    record_item = str(parsed.get("recordItem") or record_item)
                                    quote_title = str(parsed.get("quoteTitle") or quote_title)
                                    quote_content = str(parsed.get("quoteContent") or quote_content)
                                    quote_thumb_url = str(parsed.get("quoteThumbUrl") or quote_thumb_url)
                                    link_type = str(parsed.get("linkType") or link_type)
                                    link_style = str(parsed.get("linkStyle") or link_style)
                                    amount = str(parsed.get("amount") or amount)
                                    cover_url = str(parsed.get("coverUrl") or cover_url)
                                    thumb_url = str(parsed.get("thumbUrl") or thumb_url)
                                    file_size = str(parsed.get("size") or file_size)
                                    pay_sub_type = str(parsed.get("paySubType") or pay_sub_type)
                                    file_md5 = str(parsed.get("fileMd5") or file_md5)
                                    transfer_id = str(parsed.get("transferId") or transfer_id)

                                    if render_type == "transfer":
                                        # 如果 transferId 仍为空，尝试从原始 XML 提取
                                        if not transfer_id:
                                            transfer_id = _extract_xml_tag_or_attr(content_text, "transferid") or ""
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

                            if not parsed_special:
                                t = _extract_xml_tag_text(content_text, "title")
                                d = _extract_xml_tag_text(content_text, "des")
                                content_text = t or d or _infer_message_brief_by_local_type(local_type)

                if not content_text:
                    content_text = _infer_message_brief_by_local_type(local_type)

                if want_types is not None:
                    rt_key = _normalize_render_type_key(render_type)
                    if rt_key not in want_types:
                        continue

                if sender_username:
                    sender_usernames.append(sender_username)
                if quote_username:
                    quote_usernames.append(str(quote_username).strip())

                merged.append(
                    {
                        "id": f"{db_path.stem}:{table_name}:{local_id}",
                        "localId": local_id,
                        "serverId": int(r["server_id"] or 0),
                        "serverIdStr": str(int(r["server_id"] or 0)) if int(r["server_id"] or 0) else "",
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
                        "from": from_name,
                        "fromUsername": from_username,
                        "recordItem": record_item,
                        "imageMd5": image_md5,
                        "imageFileId": image_file_id,
                        "emojiMd5": emoji_md5,
                        "emojiUrl": emoji_url,
                        "thumbUrl": thumb_url,
                        "imageUrl": image_url,
                        "videoMd5": video_md5,
                        "videoThumbMd5": video_thumb_md5,
                        "videoFileId": video_file_id,
                        "videoThumbFileId": video_thumb_file_id,
                        "videoUrl": video_url,
                        "videoThumbUrl": video_thumb_url,
                        "voiceLength": voice_length,
                        "voipType": voip_type,
                        "quoteUsername": str(quote_username).strip(),
                        "quoteServerId": str(quote_server_id).strip(),
                        "quoteType": str(quote_type).strip(),
                        "quoteVoiceLength": str(quote_voice_length).strip(),
                        "quoteTitle": quote_title,
                        "quoteContent": quote_content,
                        "quoteThumbUrl": quote_thumb_url,
                        "amount": amount,
                        "coverUrl": cover_url,
                        "fileSize": file_size,
                        "fileMd5": file_md5,
                        "paySubType": pay_sub_type,
                        "transferStatus": transfer_status,
                        "transferId": transfer_id,
                        "_rawText": raw_text if local_type == 266287972401 else "",
                    }
                )
        finally:
            conn.close()

    if contact_conn is not None:
        try:
            contact_conn.close()
        except Exception:
            pass

    return merged, has_more_any, sender_usernames, quote_usernames, pat_usernames


@router.get("/api/chat/messages/daily_counts", summary="获取某月每日消息数（热力图）")
def get_chat_message_daily_counts(
    username: str,
    year: int,
    month: int,
    account: Optional[str] = None,
):
    username = str(username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="Missing username.")
    try:
        y = int(year)
        m = int(month)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid year or month.")
    if m < 1 or m > 12:
        raise HTTPException(status_code=400, detail="Invalid month.")

    try:
        start_ts, end_ts = _local_month_range_epoch_seconds(year=y, month=m)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid year or month.")

    account_dir = _resolve_account_dir(account)
    db_paths = _iter_message_db_paths(account_dir)

    counts: dict[str, int] = {}

    for db_path in db_paths:
        conn = sqlite3.connect(str(db_path))
        try:
            try:
                table_name = _resolve_msg_table_name(conn, username)
                if not table_name:
                    continue
                quoted_table = _quote_ident(table_name)
                rows = conn.execute(
                    "SELECT strftime('%Y-%m-%d', CAST(create_time AS INTEGER), 'unixepoch', 'localtime') AS day, "
                    "COUNT(*) AS c "
                    f"FROM {quoted_table} "
                    "WHERE CAST(create_time AS INTEGER) >= ? AND CAST(create_time AS INTEGER) < ? "
                    "GROUP BY day",
                    (int(start_ts), int(end_ts)),
                ).fetchall()
                for day, c in rows:
                    k = str(day or "").strip()
                    if not k:
                        continue
                    try:
                        vv = int(c or 0)
                    except Exception:
                        vv = 0
                    if vv <= 0:
                        continue
                    counts[k] = int(counts.get(k, 0)) + vv
            except Exception:
                continue
        finally:
            conn.close()

    total = int(sum(int(v) for v in counts.values())) if counts else 0
    max_count = int(max(counts.values())) if counts else 0

    return {
        "status": "success",
        "account": account_dir.name,
        "username": username,
        "year": int(y),
        "month": int(m),
        "counts": counts,
        "total": total,
        "max": max_count,
    }


@router.get("/api/chat/messages/anchor", summary="获取定位锚点（某日第一条/会话顶部）")
def get_chat_message_anchor(
    username: str,
    kind: str,
    account: Optional[str] = None,
    date: Optional[str] = None,
):
    username = str(username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="Missing username.")

    kind_norm = str(kind or "").strip().lower()
    if kind_norm not in {"day", "first"}:
        raise HTTPException(status_code=400, detail="Invalid kind.")

    date_norm: Optional[str] = None
    start_ts: Optional[int] = None
    end_ts: Optional[int] = None
    if kind_norm == "day":
        if not date:
            raise HTTPException(status_code=400, detail="Missing date.")
        try:
            start_ts, end_ts, date_norm = _local_day_range_epoch_seconds(date_str=str(date))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid date.")

    account_dir = _resolve_account_dir(account)
    db_paths = _iter_message_db_paths(account_dir)

    best_key: Optional[tuple[int, int, int]] = None
    best_anchor_id = ""
    best_create_time = 0

    for db_path in db_paths:
        conn = sqlite3.connect(str(db_path))
        try:
            try:
                table_name = _resolve_msg_table_name(conn, username)
                if not table_name:
                    continue
                quoted_table = _quote_ident(table_name)

                if kind_norm == "first":
                    row = conn.execute(
                        "SELECT local_id, CAST(create_time AS INTEGER) AS create_time, "
                        "COALESCE(CAST(sort_seq AS INTEGER), 0) AS sort_seq "
                        f"FROM {quoted_table} "
                        "ORDER BY CAST(create_time AS INTEGER) ASC, COALESCE(CAST(sort_seq AS INTEGER), 0) ASC, local_id ASC "
                        "LIMIT 1"
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT local_id, CAST(create_time AS INTEGER) AS create_time, "
                        "COALESCE(CAST(sort_seq AS INTEGER), 0) AS sort_seq "
                        f"FROM {quoted_table} "
                        "WHERE CAST(create_time AS INTEGER) >= ? AND CAST(create_time AS INTEGER) < ? "
                        "ORDER BY CAST(create_time AS INTEGER) ASC, COALESCE(CAST(sort_seq AS INTEGER), 0) ASC, local_id ASC "
                        "LIMIT 1",
                        (int(start_ts or 0), int(end_ts or 0)),
                    ).fetchone()

                if not row:
                    continue
                try:
                    local_id = int(row[0] or 0)
                    create_time = int(row[1] or 0)
                    sort_seq = int(row[2] or 0)
                except Exception:
                    continue
                if local_id <= 0:
                    continue

                key = (int(create_time), int(sort_seq), int(local_id))
                if (best_key is None) or (key < best_key):
                    best_key = key
                    best_create_time = int(create_time)
                    best_anchor_id = f"{db_path.stem}:{table_name}:{local_id}"
            except Exception:
                continue
        finally:
            conn.close()

    if not best_anchor_id:
        return {
            "status": "empty",
            "anchorId": "",
        }

    resp: dict[str, Any] = {
        "status": "success",
        "account": account_dir.name,
        "username": username,
        "kind": kind_norm,
        "anchorId": best_anchor_id,
        "createTime": int(best_create_time),
    }
    if date_norm is not None:
        resp["date"] = date_norm
    return resp


@router.get("/api/chat/messages", summary="获取会话消息列表")
def list_chat_messages(
    request: Request,
    username: str,
    account: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    order: str = "asc",
    render_types: Optional[str] = None,
    source: Optional[str] = None,
):
    if not username:
        raise HTTPException(status_code=400, detail="Missing username.")
    if limit <= 0:
        raise HTTPException(status_code=400, detail="Invalid limit.")
    if limit > 500:
        limit = 500
    if offset < 0:
        offset = 0

    source_norm = _normalize_chat_source(source)
    account_dir = _resolve_account_dir(account)
    contact_db_path = account_dir / "contact.db"
    head_image_db_path = account_dir / "head_image.db"
    message_resource_db_path = account_dir / "message_resource.db"
    base_url = str(request.base_url).rstrip("/")

    db_paths: list[Path] = []
    if source_norm != "realtime":
        db_paths = _iter_message_db_paths(account_dir)
        if not db_paths:
            return {
                "status": "error",
                "account": account_dir.name,
                "username": username,
                "total": 0,
                "messages": [],
                "message": "No message databases found for this account.",
            }

    resource_conn: Optional[sqlite3.Connection] = None
    resource_chat_id: Optional[int] = None
    try:
        if message_resource_db_path.exists():
            resource_conn = sqlite3.connect(str(message_resource_db_path))
            resource_conn.row_factory = sqlite3.Row
            resource_chat_id = _resource_lookup_chat_id(resource_conn, username)
    except Exception:
        if resource_conn is not None:
            try:
                resource_conn.close()
            except Exception:
                pass
        resource_conn = None
        resource_chat_id = None

    want_asc = str(order or "").lower() != "desc"

    want_types: Optional[set[str]] = None
    if render_types is not None:
        parts = [p.strip() for p in str(render_types or "").split(",") if p.strip()]
        want = {_normalize_render_type_key(p) for p in parts}
        want.discard("")
        if want and not ({"all", "any", "none"} & want):
            want_types = want

    scan_take = int(limit) + int(offset)
    if scan_take < 0:
        scan_take = 0

    merged: list[dict[str, Any]] = []
    sender_usernames: list[str] = []
    quote_usernames: list[str] = []
    pat_usernames: set[str] = set()
    has_more_any = False

    if source_norm == "realtime":
        try:
            rt_conn = WCDB_REALTIME.ensure_connected(account_dir)
        except WCDBRealtimeError as e:
            raise HTTPException(status_code=400, detail=str(e))

        def _normalize_wcdb_message_row(item: dict[str, Any]) -> dict[str, Any]:
            def pick(*keys: str) -> Any:
                for k in keys:
                    if k in item and item[k] is not None:
                        return item[k]
                    lk = k.lower()
                    for kk in item.keys():
                        if str(kk).lower() == lk:
                            v = item.get(kk)
                            if v is not None:
                                return v
                return None

            return {
                "local_id": pick("local_id", "localId") or 0,
                "server_id": pick("server_id", "serverId", "MsgSvrID") or 0,
                "local_type": pick("local_type", "localType", "Type", "type") or 0,
                "sort_seq": pick("sort_seq", "sortSeq", "SortSeq") or 0,
                "real_sender_id": pick("real_sender_id", "realSenderId") or 0,
                "create_time": pick("create_time", "createTime", "CreateTime") or 0,
                "message_content": pick("message_content", "messageContent", "MessageContent") or "",
                "compress_content": pick("compress_content", "compressContent", "CompressContent") or None,
                "packed_info_data": pick("packed_info_data", "packedInfoData") or None,
                "sender_username": pick("sender_username", "senderUsername", "sender", "SenderUsername") or "",
                "computed_is_send": pick("computed_is_send", "computed_isSend", "computed_is_sent", "is_send", "isSent"),
                "debug_my_rowid": pick("debug_my_rowid", "debugMyRowid", "my_rowid", "myRowid"),
            }

        # Realtime mode: fetch from newest (offset handled after render_type filtering).
        import hashlib

        table_name = f"msg_{hashlib.md5(username.encode('utf-8')).hexdigest()}"
        rt_db_path = Path(f"realtime_{account_dir.name}.db")

        while True:
            probe = int(scan_take) + 1
            if probe <= 0:
                probe = 1
            if probe > 50000:
                probe = 50000

            with rt_conn.lock:
                raw_rows = _wcdb_get_messages(rt_conn.handle, username, limit=probe, offset=0)
            has_more_any = len(raw_rows) > int(scan_take)
            raw_rows = raw_rows[: int(scan_take)] if int(scan_take) > 0 else []

            merged = []
            sender_usernames = []
            quote_usernames = []
            pat_usernames = set()

            norm_rows = [_normalize_wcdb_message_row(r) for r in raw_rows if isinstance(r, dict)]
            _append_full_messages_from_rows(
                merged=merged,
                sender_usernames=sender_usernames,
                quote_usernames=quote_usernames,
                pat_usernames=pat_usernames,
                rows=norm_rows,
                db_path=rt_db_path,
                table_name=table_name,
                username=username,
                account_dir=account_dir,
                is_group=bool(username.endswith("@chatroom")),
                my_rowid=None,
                resource_conn=resource_conn,
                resource_chat_id=resource_chat_id,
            )

            if want_types is not None:
                merged = [m for m in merged if _normalize_render_type_key(m.get("renderType")) in want_types]

            if want_types is None:
                break
            if (len(merged) >= (int(offset) + int(limit))) or (not has_more_any):
                break

            next_take = scan_take * 2 if scan_take > 0 else (int(limit) + int(offset))
            if next_take <= scan_take:
                break
            if next_take > 50000:
                next_take = 50000
            scan_take = next_take

    else:
        while True:
            (
                merged,
                has_more_any,
                sender_usernames,
                quote_usernames,
                pat_usernames,
            ) = _collect_chat_messages(
                username=username,
                account_dir=account_dir,
                db_paths=db_paths,
                resource_conn=resource_conn,
                resource_chat_id=resource_chat_id,
                take=scan_take,
                want_types=want_types,
            )

            if want_types is None:
                break

            if (len(merged) >= (int(offset) + int(limit))) or (not has_more_any):
                break

            next_take = scan_take * 2 if scan_take > 0 else (int(limit) + int(offset))
            if next_take <= scan_take:
                break
            scan_take = next_take

    # Self-heal (default source only): if the decrypted snapshot has no conversation table yet (new session),
    # do a one-shot realtime->decrypted sync and re-query once. This avoids "暂无聊天记录" after turning off realtime.
    if (
        source_norm != "realtime"
        and (source is None or not str(source).strip())
        and (not merged)
        and int(offset) == 0
    ):
        missing_table = False
        try:
            missing_table = _resolve_decrypted_message_table(account_dir, username) is None
        except Exception:
            missing_table = True

        if missing_table:
            rt_conn2 = None
            try:
                rt_conn2 = WCDB_REALTIME.ensure_connected(account_dir)
            except WCDBRealtimeError:
                rt_conn2 = None
            except Exception:
                rt_conn2 = None

            if rt_conn2 is not None:
                try:
                    with _realtime_sync_lock(account_dir.name, username):
                        msg_db_path2, table_name2 = _ensure_decrypted_message_table(account_dir, username)
                        _sync_chat_realtime_messages_for_table(
                            account_dir=account_dir,
                            rt_conn=rt_conn2,
                            username=username,
                            msg_db_path=msg_db_path2,
                            table_name=table_name2,
                            max_scan=max(200, int(limit) + 50),
                            backfill_limit=0,
                        )
                except Exception:
                    pass

                (
                    merged,
                    has_more_any,
                    sender_usernames,
                    quote_usernames,
                    pat_usernames,
                ) = _collect_chat_messages(
                    username=username,
                    account_dir=account_dir,
                    db_paths=db_paths,
                    resource_conn=resource_conn,
                    resource_chat_id=resource_chat_id,
                    take=scan_take,
                    want_types=want_types,
                )
                if want_types is not None:
                    merged = [m for m in merged if _normalize_render_type_key(m.get("renderType")) in want_types]

    r"""
    take = int(limit) + int(offset)
    take_probe = take + 1
    merged: list[dict[str, Any]] = []
    sender_usernames: list[str] = []
    quote_usernames: list[str] = []
    pat_usernames: set[str] = set()
    is_group = bool(username.endswith("@chatroom"))
    has_more_any = False

    for db_path in db_paths:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            table_name = _resolve_msg_table_name(conn, username)
            if not table_name:
                continue

            my_wxid = account_dir.name
            my_rowid = None
            try:
                r = conn.execute(
                    "SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1",
                    (my_wxid,),
                ).fetchone()
                if r is not None:
                    my_rowid = int(r[0])
            except Exception:
                my_rowid = None

            quoted_table = _quote_ident(table_name)
            sql_with_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, n.user_name AS sender_username "
                f"FROM {quoted_table} m "
                "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
                "ORDER BY m.create_time DESC, m.sort_seq DESC, m.local_id DESC "
                "LIMIT ?"
            )
            sql_no_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, '' AS sender_username "
                f"FROM {quoted_table} m "
                "ORDER BY m.create_time DESC, m.sort_seq DESC, m.local_id DESC "
                "LIMIT ?"
            )

            # Force sqlite3 to return TEXT as raw bytes for this query, so we can zstd-decompress
            # compress_content reliably.
            conn.text_factory = bytes

            try:
                rows = conn.execute(sql_with_join, (take_probe,)).fetchall()
            except Exception:
                rows = conn.execute(sql_no_join, (take_probe,)).fetchall()
            if len(rows) > take:
                has_more_any = True
                rows = rows[:take]

            for r in rows:
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

                raw_text = _decode_message_content(r["compress_content"], r["message_content"])
                raw_text = raw_text.strip()

                sender_prefix = ""
                if is_group and not raw_text.startswith("<") and not raw_text.startswith('"<'):
                    sender_prefix, raw_text = _split_group_sender_prefix(raw_text)

                if is_group and sender_prefix:
                    sender_username = sender_prefix

                if is_group and (not sender_username) and (raw_text.startswith("<") or raw_text.startswith('"<')):
                    xml_sender = _extract_sender_from_group_xml(raw_text)
                    if xml_sender:
                        sender_username = xml_sender

                if is_sent:
                    sender_username = account_dir.name
                elif (not is_group) and (not sender_username):
                    sender_username = username

                if sender_username:
                    sender_usernames.append(sender_username)

                render_type = "text"
                content_text = raw_text
                title = ""
                url = ""
                from_name = ""
                from_username = ""
                record_item = ""
                image_md5 = ""
                emoji_md5 = ""
                emoji_url = ""
                thumb_url = ""
                image_url = ""
                image_file_id = ""
                video_md5 = ""
                video_thumb_md5 = ""
                video_file_id = ""
                video_thumb_file_id = ""
                video_url = ""
                video_thumb_url = ""
                voice_length = ""
                quote_username = ""
                quote_title = ""
                quote_content = ""
                quote_thumb_url = ""
                link_type = ""
                link_style = ""
                quote_server_id = ""
                quote_type = ""
                quote_voice_length = ""
                amount = ""
                cover_url = ""
                file_size = ""
                pay_sub_type = ""
                transfer_status = ""
                file_md5 = ""
                transfer_id = ""
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
                    from_name = str(parsed.get("from") or "")
                    from_username = str(parsed.get("fromUsername") or "")
                    record_item = str(parsed.get("recordItem") or "")
                    quote_title = str(parsed.get("quoteTitle") or "")
                    quote_content = str(parsed.get("quoteContent") or "")
                    quote_thumb_url = str(parsed.get("quoteThumbUrl") or "")
                    link_type = str(parsed.get("linkType") or "")
                    link_style = str(parsed.get("linkStyle") or "")
                    quote_username = str(parsed.get("quoteUsername") or "")
                    quote_server_id = str(parsed.get("quoteServerId") or "")
                    quote_type = str(parsed.get("quoteType") or "")
                    quote_voice_length = str(parsed.get("quoteVoiceLength") or "")
                    amount = str(parsed.get("amount") or "")
                    cover_url = str(parsed.get("coverUrl") or "")
                    thumb_url = str(parsed.get("thumbUrl") or "")
                    file_size = str(parsed.get("size") or "")
                    pay_sub_type = str(parsed.get("paySubType") or "")
                    file_md5 = str(parsed.get("fileMd5") or "")
                    transfer_id = str(parsed.get("transferId") or "")

                    if render_type == "transfer":
                        # 直接从原始 XML 提取 transferid（可能在 wcpayinfo 内）
                        if not transfer_id:
                            transfer_id = _extract_xml_tag_or_attr(raw_text, "transferid") or ""
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
                    template = _extract_xml_tag_text(raw_text, "template")
                    if template:
                        # import re

                        pat_usernames.update({m.group(1) for m in re.finditer(r"\$\{([^}]+)\}", template) if m.group(1)})
                        content_text = "[拍一拍]"
                    else:
                        content_text = "[拍一拍]"
                elif local_type == 244813135921:
                    render_type = "quote"
                    parsed = _parse_app_message(raw_text)
                    content_text = str(parsed.get("content") or "[引用消息]")
                    quote_title = str(parsed.get("quoteTitle") or "")
                    quote_content = str(parsed.get("quoteContent") or "")
                    quote_thumb_url = str(parsed.get("quoteThumbUrl") or "")
                    link_type = str(parsed.get("linkType") or "")
                    link_style = str(parsed.get("linkStyle") or "")
                    quote_username = str(parsed.get("quoteUsername") or "")
                    quote_server_id = str(parsed.get("quoteServerId") or "")
                    quote_type = str(parsed.get("quoteType") or "")
                    quote_voice_length = str(parsed.get("quoteVoiceLength") or "")
                elif local_type == 3:
                    render_type = "image"
                    # 先尝试从 XML 中提取 md5（不同版本字段可能不同）
                    image_md5 = _extract_xml_attr(raw_text, "md5") or _extract_xml_tag_text(raw_text, "md5")
                    if not image_md5:
                        for k in [
                            "cdnthumbmd5",
                            "cdnthumd5",
                            "cdnmidimgmd5",
                            "cdnbigimgmd5",
                            "hdmd5",
                            "hevc_mid_md5",
                            "hevc_md5",
                            "imgmd5",
                            "filemd5",
                        ]:
                            image_md5 = _extract_xml_attr(raw_text, k) or _extract_xml_tag_text(raw_text, k)
                            if image_md5:
                                break

                    # Prefer message_resource.db md5 for local files: XML md5 frequently differs from the on-disk *.dat basename
                    # (especially for *_t.dat thumbnails), causing the media endpoint to 404.
                    if resource_conn is not None:
                        try:
                            resource_md5 = _lookup_resource_md5(
                                resource_conn,
                                resource_chat_id,
                                message_local_type=local_type,
                                server_id=int(r["server_id"] or 0),
                                local_id=local_id,
                                create_time=create_time,
                            )
                        except Exception:
                            resource_md5 = ""
                        resource_md5 = str(resource_md5 or "").strip().lower()
                        if len(resource_md5) == 32 and all(c in "0123456789abcdef" for c in resource_md5):
                            image_md5 = resource_md5

                    # Extract CDN URL (some versions store a non-HTTP "file id" string here)
                    _cdn_url_or_id = (
                        _extract_xml_attr(raw_text, "cdnthumburl")
                        or _extract_xml_attr(raw_text, "cdnthumurl")
                        or _extract_xml_attr(raw_text, "cdnmidimgurl")
                        or _extract_xml_attr(raw_text, "cdnbigimgurl")
                        or _extract_xml_tag_text(raw_text, "cdnthumburl")
                        or _extract_xml_tag_text(raw_text, "cdnthumurl")
                        or _extract_xml_tag_text(raw_text, "cdnmidimgurl")
                        or _extract_xml_tag_text(raw_text, "cdnbigimgurl")
                    )
                    _cdn_url_or_id = str(_cdn_url_or_id or "").strip()
                    image_url = _cdn_url_or_id if _cdn_url_or_id.startswith(("http://", "https://")) else ""
                    if (not image_url) and _cdn_url_or_id:
                        image_file_id = _cdn_url_or_id
                    content_text = "[图片]"
                elif local_type == 34:
                    render_type = "voice"
                    duration = _extract_xml_attr(raw_text, "voicelength")
                    voice_length = duration
                    content_text = f"[语音 {duration}秒]" if duration else "[语音]"
                elif local_type == 43 or local_type == 62:
                    render_type = "video"
                    video_md5 = _extract_xml_attr(raw_text, "md5")
                    video_thumb_md5 = _extract_xml_attr(raw_text, "cdnthumbmd5")
                    video_thumb_url_or_id = _extract_xml_attr(raw_text, "cdnthumburl") or _extract_xml_tag_text(
                        raw_text, "cdnthumburl"
                    )
                    video_url_or_id = _extract_xml_attr(raw_text, "cdnvideourl") or _extract_xml_tag_text(
                        raw_text, "cdnvideourl"
                    )

                    video_thumb_url = (
                        video_thumb_url_or_id
                        if str(video_thumb_url_or_id or "").strip().lower().startswith(("http://", "https://"))
                        else ""
                    )
                    video_url = (
                        video_url_or_id
                        if str(video_url_or_id or "").strip().lower().startswith(("http://", "https://"))
                        else ""
                    )
                    video_thumb_file_id = "" if video_thumb_url else (str(video_thumb_url_or_id or "").strip() or "")
                    video_file_id = "" if video_url else (str(video_url_or_id or "").strip() or "")
                    if (not video_thumb_md5) and resource_conn is not None:
                        video_thumb_md5 = _lookup_resource_md5(
                            resource_conn,
                            resource_chat_id,
                            message_local_type=local_type,
                            server_id=int(r["server_id"] or 0),
                            local_id=local_id,
                            create_time=create_time,
                        )
                    content_text = "[视频]"
                elif local_type == 47:
                    render_type = "emoji"
                    emoji_md5 = _extract_xml_attr(raw_text, "md5")
                    if not emoji_md5:
                        emoji_md5 = _extract_xml_tag_text(raw_text, "md5")
                    emoji_url = _extract_xml_attr(raw_text, "cdnurl")
                    if not emoji_url:
                        emoji_url = _extract_xml_tag_text(raw_text, "cdn_url")
                    if (not emoji_md5) and resource_conn is not None:
                        emoji_md5 = _lookup_resource_md5(
                            resource_conn,
                            resource_chat_id,
                            message_local_type=local_type,
                            server_id=int(r["server_id"] or 0),
                            local_id=local_id,
                            create_time=create_time,
                        )
                    content_text = "[表情]"
                elif local_type == 50:
                    render_type = "voip"
                    try:
                        # import re

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
                            parsed_special = False
                            if "<appmsg" in content_text.lower():
                                parsed = _parse_app_message(content_text)
                                rt = str(parsed.get("renderType") or "")
                                if rt and rt != "text":
                                    parsed_special = True
                                    render_type = rt
                                    content_text = str(parsed.get("content") or content_text)
                                    title = str(parsed.get("title") or title)
                                    url = str(parsed.get("url") or url)
                                    from_name = str(parsed.get("from") or from_name)
                                    record_item = str(parsed.get("recordItem") or record_item)
                                    quote_title = str(parsed.get("quoteTitle") or quote_title)
                                    quote_content = str(parsed.get("quoteContent") or quote_content)
                                    quote_thumb_url = str(parsed.get("quoteThumbUrl") or quote_thumb_url)
                                    link_type = str(parsed.get("linkType") or link_type)
                                    link_style = str(parsed.get("linkStyle") or link_style)
                                    amount = str(parsed.get("amount") or amount)
                                    cover_url = str(parsed.get("coverUrl") or cover_url)
                                    thumb_url = str(parsed.get("thumbUrl") or thumb_url)
                                    file_size = str(parsed.get("size") or file_size)
                                    pay_sub_type = str(parsed.get("paySubType") or pay_sub_type)
                                    file_md5 = str(parsed.get("fileMd5") or file_md5)
                                    transfer_id = str(parsed.get("transferId") or transfer_id)

                                    if render_type == "transfer":
                                        # 如果 transferId 仍为空，尝试从原始 XML 提取
                                        if not transfer_id:
                                            transfer_id = _extract_xml_tag_or_attr(content_text, "transferid") or ""
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

                            if not parsed_special:
                                t = _extract_xml_tag_text(content_text, "title")
                                d = _extract_xml_tag_text(content_text, "des")
                                content_text = t or d or _infer_message_brief_by_local_type(local_type)

                if not content_text:
                    content_text = _infer_message_brief_by_local_type(local_type)

                if quote_username:
                    quote_usernames.append(str(quote_username).strip())

                merged.append(
                    {
                        "id": f"{db_path.stem}:{table_name}:{local_id}",
                        "localId": local_id,
                        "serverId": int(r["server_id"] or 0),
                        "serverIdStr": str(int(r["server_id"] or 0)) if int(r["server_id"] or 0) else "",
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
                        "from": from_name,
                        "fromUsername": from_username,
                        "recordItem": record_item,
                        "imageMd5": image_md5,
                        "imageFileId": image_file_id,
                        "emojiMd5": emoji_md5,
                        "emojiUrl": emoji_url,
                        "thumbUrl": thumb_url,
                        "imageUrl": image_url,
                        "videoMd5": video_md5,
                        "videoThumbMd5": video_thumb_md5,
                        "videoFileId": video_file_id,
                        "videoThumbFileId": video_thumb_file_id,
                        "videoUrl": video_url,
                        "videoThumbUrl": video_thumb_url,
                        "voiceLength": voice_length,
                        "voipType": voip_type,
                        "quoteUsername": str(quote_username).strip(),
                        "quoteServerId": str(quote_server_id).strip(),
                        "quoteType": str(quote_type).strip(),
                        "quoteVoiceLength": str(quote_voice_length).strip(),
                        "quoteTitle": quote_title,
                        "quoteContent": quote_content,
                        "quoteThumbUrl": quote_thumb_url,
                        "amount": amount,
                        "coverUrl": cover_url,
                        "fileSize": file_size,
                        "fileMd5": file_md5,
                        "paySubType": pay_sub_type,
                        "transferStatus": transfer_status,
                        "transferId": transfer_id,
                        "_rawText": raw_text if local_type == 266287972401 else "",
                    }
                )
        finally:
            conn.close()

    """
    if resource_conn is not None:
        try:
            resource_conn.close()
        except Exception:
            pass

    # Guard against duplicate message ids (observed in realtime mode).
    # Duplicate ids break Vue list rendering (duplicate keys) and can cause incorrect message display.
    if merged:
        seen_ids: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for m in merged:
            mid = str(m.get("id") or "")
            if not mid:
                deduped.append(m)
                continue
            if mid in seen_ids:
                continue
            seen_ids.add(mid)
            deduped.append(m)
        merged = deduped

    _postprocess_transfer_messages(merged)

    def sort_key(m: dict[str, Any]) -> tuple[int, int, int]:
        sseq = int(m.get("sortSeq") or 0)
        cts = int(m.get("createTime") or 0)
        lid = int(m.get("localId") or 0)
        return (cts, sseq, lid)

    merged.sort(key=sort_key, reverse=True)
    has_more_global = bool(has_more_any or (len(merged) > (int(offset) + int(limit))))
    page = merged[int(offset) : int(offset) + int(limit)]
    if want_asc:
        page = list(reversed(page))

    # Hot path optimization: only enrich the page we return.
    if not page:
        return {
            "status": "success",
            "account": account_dir.name,
            "username": username,
            "total": int(offset) + (1 if has_more_global else 0),
            "hasMore": bool(has_more_global),
            "messages": [],
        }

    messages_window = page

    # Some appmsg payloads provide only `from` (sourcedisplayname) but not `fromUsername` (sourceusername).
    # Recover `fromUsername` via contact.db so the frontend can render the publisher avatar.
    missing_from_names = [
        str(m.get("from") or "").strip()
        for m in messages_window
        if str(m.get("renderType") or "").strip() == "link"
        and str(m.get("from") or "").strip()
        and not str(m.get("fromUsername") or "").strip()
    ]
    if missing_from_names:
        name_to_username = _load_usernames_by_display_names(contact_db_path, missing_from_names)
        if name_to_username:
            for m in messages_window:
                if str(m.get("fromUsername") or "").strip():
                    continue
                if str(m.get("renderType") or "").strip() != "link":
                    continue
                fn = str(m.get("from") or "").strip()
                if fn and fn in name_to_username:
                    m["fromUsername"] = name_to_username[fn]

    pat_usernames_in_page: set[str] = set()
    for m in messages_window:
        if int(m.get("type") or 0) != 266287972401:
            continue
        raw = str(m.get("_rawText") or "")
        if not raw:
            continue
        template = _extract_xml_tag_text(raw, "template")
        if not template:
            continue
        pat_usernames_in_page.update({mm.group(1) for mm in re.finditer(r"\$\{([^}]+)\}", template) if mm.group(1)})

    from_usernames = [str(m.get("fromUsername") or "").strip() for m in messages_window]
    sender_usernames_in_page = [str(m.get("senderUsername") or "").strip() for m in messages_window]
    quote_usernames_in_page = [str(m.get("quoteUsername") or "").strip() for m in messages_window]
    uniq_senders = list(
        dict.fromkeys(
            [
                u
                for u in (
                    sender_usernames_in_page
                    + list(pat_usernames_in_page)
                    + quote_usernames_in_page
                    + from_usernames
                )
                if u
            ]
        )
    )
    sender_contact_rows = _load_contact_rows(contact_db_path, uniq_senders)
    local_sender_avatars = _query_head_image_usernames(head_image_db_path, uniq_senders)

    # contact.db may not include enterprise/openim contacts (or group chatroom records). WCDB has a more complete
    # view of display names + avatar URLs, so we use it as a best-effort fallback.
    wcdb_display_names: dict[str, str] = {}
    wcdb_avatar_urls: dict[str, str] = {}
    try:
        need_display: list[str] = []
        need_avatar: list[str] = []
        for u in uniq_senders:
            if not u:
                continue
            row = sender_contact_rows.get(u)
            if _pick_display_name(row, u) == u:
                need_display.append(u)
            if u not in local_sender_avatars:
                need_avatar.append(u)

        need_display = list(dict.fromkeys(need_display))
        need_avatar = list(dict.fromkeys(need_avatar))
        if need_display or need_avatar:
            wcdb_conn = WCDB_REALTIME.ensure_connected(account_dir)
            with wcdb_conn.lock:
                if need_display:
                    wcdb_display_names = _wcdb_get_display_names(wcdb_conn.handle, need_display)
                if need_avatar:
                    wcdb_avatar_urls = _wcdb_get_avatar_urls(wcdb_conn.handle, need_avatar)
    except Exception:
        wcdb_display_names = {}
        wcdb_avatar_urls = {}

    group_nicknames = _load_group_nickname_map(
        account_dir=account_dir,
        contact_db_path=contact_db_path,
        chatroom_id=username,
        sender_usernames=uniq_senders,
    )

    for m in messages_window:
        # If appmsg doesn't provide sourcedisplayname, try mapping sourceusername to display name.
        if (not str(m.get("from") or "").strip()) and str(m.get("fromUsername") or "").strip():
            fu = str(m.get("fromUsername") or "").strip()
            frow = sender_contact_rows.get(fu)
            if frow is not None:
                m["from"] = _pick_display_name(frow, fu)
            else:
                wd = str(wcdb_display_names.get(fu) or "").strip()
                if wd:
                    m["from"] = wd

        su = str(m.get("senderUsername") or "")
        if not su:
            continue
        m["senderDisplayName"] = _resolve_sender_display_name(
            sender_username=su,
            sender_contact_rows=sender_contact_rows,
            wcdb_display_names=wcdb_display_names,
            group_nicknames=group_nicknames,
        )
        avatar_url = base_url + _avatar_url_unified(
            account_dir=account_dir,
            username=su,
            local_avatar_usernames=local_sender_avatars,
        )
        m["senderAvatar"] = avatar_url

        qu = str(m.get("quoteUsername") or "").strip()
        if qu:
            qrow = sender_contact_rows.get(qu)
            qt = str(m.get("quoteTitle") or "").strip()
            if qrow is not None:
                remark = ""
                try:
                    remark = str(qrow["remark"] or "").strip()
                except Exception:
                    remark = ""
                if remark:
                    m["quoteTitle"] = remark
                elif not qt:
                    title = _pick_display_name(qrow, qu)
                    if title == qu:
                        wd = str(wcdb_display_names.get(qu) or "").strip()
                        if wd and wd != qu:
                            title = wd
                    m["quoteTitle"] = title
            elif not qt:
                wd = str(wcdb_display_names.get(qu) or "").strip()
                m["quoteTitle"] = wd or qu

        # Media URL fallback: if CDN URLs missing, use local media endpoints.
        try:
            rt = str(m.get("renderType") or "")
            if rt == "image":
                if not str(m.get("imageUrl") or ""):
                    md5 = str(m.get("imageMd5") or "").strip()
                    file_id = str(m.get("imageFileId") or "").strip()
                    if md5:
                        m["imageUrl"] = (
                            base_url
                            + f"/api/chat/media/image?account={quote(account_dir.name)}&md5={quote(md5)}&username={quote(username)}"
                        )
                    elif file_id:
                        m["imageUrl"] = (
                            base_url
                            + f"/api/chat/media/image?account={quote(account_dir.name)}&file_id={quote(file_id)}&username={quote(username)}"
                        )
            elif rt == "emoji":
                md5 = str(m.get("emojiMd5") or "")
                if md5:
                    existing_local: Optional[Path] = None
                    try:
                        existing_local = _try_find_decrypted_resource(account_dir, str(md5).lower())
                    except Exception:
                        existing_local = None

                    if existing_local:
                        try:
                            # import re
                            cur = str(m.get("emojiUrl") or "")
                            if cur and re.match(r"^https?://", cur, flags=re.I) and ("/api/chat/media/emoji" not in cur):
                                m["emojiRemoteUrl"] = cur
                        except Exception:
                            pass

                        m["emojiUrl"] = (
                            base_url
                            + f"/api/chat/media/emoji?account={quote(account_dir.name)}&md5={quote(md5)}&username={quote(username)}"
                        )
                    elif (not str(m.get("emojiUrl") or "")):
                        m["emojiUrl"] = (
                            base_url
                            + f"/api/chat/media/emoji?account={quote(account_dir.name)}&md5={quote(md5)}&username={quote(username)}"
                        )
            elif rt == "video":
                video_thumb_url = str(m.get("videoThumbUrl") or "").strip()
                video_thumb_md5 = str(m.get("videoThumbMd5") or "").strip()
                video_thumb_file_id = str(m.get("videoThumbFileId") or "").strip()
                if (not video_thumb_url) or (
                    not video_thumb_url.lower().startswith(("http://", "https://"))
                ):
                    if video_thumb_md5:
                        m["videoThumbUrl"] = (
                            base_url
                            + f"/api/chat/media/video_thumb?account={quote(account_dir.name)}&md5={quote(video_thumb_md5)}&username={quote(username)}"
                        )
                    elif video_thumb_file_id:
                        m["videoThumbUrl"] = (
                            base_url
                            + f"/api/chat/media/video_thumb?account={quote(account_dir.name)}&file_id={quote(video_thumb_file_id)}&username={quote(username)}"
                        )

                video_url = str(m.get("videoUrl") or "").strip()
                video_md5 = str(m.get("videoMd5") or "").strip()
                video_file_id = str(m.get("videoFileId") or "").strip()
                if (not video_url) or (not video_url.lower().startswith(("http://", "https://"))):
                    if video_md5:
                        m["videoUrl"] = (
                            base_url
                            + f"/api/chat/media/video?account={quote(account_dir.name)}&md5={quote(video_md5)}&username={quote(username)}"
                        )
                    elif video_file_id:
                        m["videoUrl"] = (
                            base_url
                            + f"/api/chat/media/video?account={quote(account_dir.name)}&file_id={quote(video_file_id)}&username={quote(username)}"
                        )
            elif rt == "link":
                thumb_url = str(m.get("thumbUrl") or "").strip()
                if thumb_url and (not thumb_url.lower().startswith(("http://", "https://"))):
                    try:
                        lid = int(m.get("localId") or 0)
                    except Exception:
                        lid = 0
                    try:
                        ct = int(m.get("createTime") or 0)
                    except Exception:
                        ct = 0
                    if lid > 0 and ct > 0:
                        file_id = f"{lid}_{ct}"
                        m["thumbUrl"] = (
                            base_url
                            + f"/api/chat/media/image?account={quote(account_dir.name)}&file_id={quote(file_id)}&username={quote(username)}"
                        )
            elif rt == "voice":
                if str(m.get("serverId") or ""):
                    sid = int(m.get("serverId") or 0)
                    if sid:
                        m["voiceUrl"] = base_url + f"/api/chat/media/voice?account={quote(account_dir.name)}&server_id={sid}"
        except Exception:
            pass

        if int(m.get("type") or 0) == 266287972401:
            raw = str(m.get("_rawText") or "")
            if raw:
                m["content"] = _parse_pat_message(raw, sender_contact_rows)

        if "_rawText" in m:
            m.pop("_rawText", None)

    return {
        "status": "success",
        "account": account_dir.name,
        "username": username,
        "total": int(offset) + len(page) + (1 if has_more_global else 0),
        "hasMore": bool(has_more_global),
        "messages": page,
    }


async def _search_chat_messages_via_fts(
    request: Request,
    *,
    q: str,
    account: Optional[str],
    username: Optional[str],
    sender: Optional[str],
    session_type: Optional[str],
    limit: int,
    offset: int,
    start_time: Optional[int],
    end_time: Optional[int],
    render_types: Optional[str],
    include_hidden: bool,
    include_official: bool,
) -> dict[str, Any]:
    tokens = _make_search_tokens(q)
    if not tokens:
        raise HTTPException(status_code=400, detail="Missing q.")

    if limit <= 0:
        raise HTTPException(status_code=400, detail="Invalid limit.")
    if limit > 200:
        limit = 200
    if offset < 0:
        offset = 0

    start_ts = int(start_time) if start_time is not None else None
    end_ts = int(end_time) if end_time is not None else None
    if start_ts is not None and start_ts < 0:
        start_ts = 0
    if end_ts is not None and end_ts < 0:
        end_ts = 0

    want_types: Optional[set[str]] = None
    if render_types is not None:
        parts = [p.strip() for p in str(render_types or "").split(",") if p.strip()]
        want_types = {p for p in parts if p}
        if not want_types:
            want_types = None

    username = str(username).strip() if username else None
    if not username:
        username = None

    sender = str(sender).strip() if sender else None
    if not sender:
        sender = None

    session_type_norm = _normalize_session_type(session_type)

    account_dir = _resolve_account_dir(account)
    contact_db_path = account_dir / "contact.db"
    head_image_db_path = account_dir / "head_image.db"
    base_url = str(request.base_url).rstrip("/")

    index_status = get_chat_search_index_status(account_dir)
    index = dict(index_status.get("index") or {})
    build = dict(index.get("build") or {})

    index_exists = bool(index.get("exists"))
    index_ready = bool(index.get("ready"))
    build_status = str(build.get("status") or "").strip()

    if (not index_ready) and build_status not in {"building", "error"}:
        start_chat_search_index_build(account_dir, rebuild=bool(index_exists))
        index_status = get_chat_search_index_status(account_dir)
        index = dict(index_status.get("index") or {})
        build = dict(index.get("build") or {})
        build_status = str(build.get("status") or "").strip()
        index_exists = bool(index.get("exists"))
        index_ready = bool(index.get("ready"))

    if build_status == "error":
        return {
            "status": "index_error",
            "account": account_dir.name,
            "q": q,
            "tokens": tokens,
            "scope": "conversation" if username else "global",
            "username": username,
            "offset": int(offset),
            "limit": int(limit),
            "baseUrl": base_url,
            "total": 0,
            "hasMore": False,
            "hits": [],
            "index": index,
            "message": str(build.get("error") or "Search index build failed."),
        }

    if not index_ready:
        return {
            "status": "index_building",
            "account": account_dir.name,
            "q": q,
            "tokens": tokens,
            "scope": "conversation" if username else "global",
            "username": username,
            "offset": int(offset),
            "limit": int(limit),
            "baseUrl": base_url,
            "total": 0,
            "hasMore": False,
            "hits": [],
            "index": index,
            "message": "Search index is building. Please retry in a moment.",
        }

    fts_query = _build_fts_query(q)
    if not fts_query:
        raise HTTPException(status_code=400, detail="Missing q.")

    index_db_path = get_chat_search_index_db_path(account_dir)
    conn = sqlite3.connect(str(index_db_path))
    conn.row_factory = sqlite3.Row
    try:
        try:
            where_parts: list[str] = ["message_fts MATCH ?"]
            params: list[Any] = [fts_query]

            if username:
                where_parts.append("username = ?")
                params.append(str(username))
            elif session_type_norm == "group":
                where_parts.append("username LIKE ?")
                params.append("%@chatroom")
            elif session_type_norm == "single":
                where_parts.append("username NOT LIKE ?")
                params.append("%@chatroom")

            if sender:
                where_parts.append("sender_username = ?")
                params.append(str(sender))

            if want_types is not None:
                types_sorted = sorted(want_types)
                placeholders = ",".join(["?"] * len(types_sorted))
                where_parts.append(f"render_type IN ({placeholders})")
                params.extend(types_sorted)

            if start_ts is not None:
                where_parts.append("CAST(create_time AS INTEGER) >= ?")
                params.append(int(start_ts))
            if end_ts is not None:
                where_parts.append("CAST(create_time AS INTEGER) <= ?")
                params.append(int(end_ts))

            if not include_hidden:
                where_parts.append("CAST(is_hidden AS INTEGER) = 0")
            if not include_official:
                where_parts.append("CAST(is_official AS INTEGER) = 0")

            where_sql = " AND ".join(where_parts)
            total_row = conn.execute(f"SELECT COUNT(*) AS c FROM message_fts WHERE {where_sql}", params).fetchone()
            total = int(total_row[0] or 0) if total_row is not None else 0

            rows = conn.execute(
                f"""
                SELECT
                    username,
                    db_stem,
                    table_name,
                    local_id
                FROM message_fts
                WHERE {where_sql}
                ORDER BY
                    CAST(create_time AS INTEGER) DESC,
                    CAST(sort_seq AS INTEGER) DESC,
                    CAST(local_id AS INTEGER) DESC
                LIMIT ? OFFSET ?
                """,
                params + [int(limit), int(offset)],
            ).fetchall()
        except Exception as e:
            logger.exception("Chat search index query failed")
            return {
                "status": "index_error",
                "account": account_dir.name,
                "q": q,
                "tokens": tokens,
                "scope": "conversation" if username else "global",
                "username": username,
                "offset": int(offset),
                "limit": int(limit),
                "baseUrl": base_url,
                "total": 0,
                "hasMore": False,
                "hits": [],
                "index": index,
                "message": str(e),
            }
    finally:
        conn.close()

    db_paths = _iter_message_db_paths(account_dir)
    stem_to_path = {p.stem: p for p in db_paths}

    groups: dict[tuple[Path, str, str], list[int]] = {}
    ordered_keys: list[tuple[Path, str, str, int]] = []
    for r in rows:
        conv_username = str(r["username"] or "").strip()
        db_stem = str(r["db_stem"] or "").strip()
        table_name = str(r["table_name"] or "").strip()
        local_id = int(r["local_id"] or 0)
        if not conv_username or not db_stem or not table_name or local_id <= 0:
            continue
        db_path = stem_to_path.get(db_stem)
        if db_path is None:
            continue
        groups.setdefault((db_path, table_name, conv_username), []).append(local_id)
        ordered_keys.append((db_path, table_name, conv_username, local_id))

    hit_by_key: dict[tuple[Path, str, str, int], dict[str, Any]] = {}

    for (db_path, table_name, conv_username), local_ids in groups.items():
        uniq_local_ids = list(dict.fromkeys([int(x) for x in local_ids if int(x) > 0]))
        if not uniq_local_ids:
            continue

        msg_conn = sqlite3.connect(str(db_path))
        msg_conn.row_factory = sqlite3.Row
        msg_conn.text_factory = bytes
        try:
            my_rowid = None
            try:
                r2 = msg_conn.execute(
                    "SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1",
                    (account_dir.name,),
                ).fetchone()
                if r2 is not None and r2[0] is not None:
                    my_rowid = int(r2[0])
            except Exception:
                my_rowid = None

            placeholders = ",".join(["?"] * len(uniq_local_ids))
            quoted_table = _quote_ident(table_name)

            sql_with_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, n.user_name AS sender_username "
                f"FROM {quoted_table} m "
                "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
                f"WHERE m.local_id IN ({placeholders})"
            )
            sql_no_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, '' AS sender_username "
                f"FROM {quoted_table} m "
                f"WHERE m.local_id IN ({placeholders})"
            )

            try:
                try:
                    msg_rows = msg_conn.execute(sql_with_join, uniq_local_ids).fetchall()
                except Exception:
                    msg_rows = msg_conn.execute(sql_no_join, uniq_local_ids).fetchall()
            except Exception:
                continue

            is_group = bool(conv_username.endswith("@chatroom"))
            for rr in msg_rows:
                local_id = int(rr["local_id"] or 0)
                if local_id <= 0:
                    continue
                try:
                    hit = _row_to_search_hit(
                        rr,
                        db_path=db_path,
                        table_name=table_name,
                        username=conv_username,
                        account_dir=account_dir,
                        is_group=is_group,
                        my_rowid=my_rowid,
                    )
                except Exception:
                    continue

                hay_items = [
                    str(hit.get("content") or ""),
                    str(hit.get("title") or ""),
                    str(hit.get("url") or ""),
                    str(hit.get("quoteTitle") or ""),
                    str(hit.get("quoteContent") or ""),
                    str(hit.get("amount") or ""),
                ]
                haystack = "\n".join([x for x in hay_items if x.strip()])
                snippet_src = (
                    str(hit.get("content") or "").strip()
                    or str(hit.get("title") or "").strip()
                    or haystack
                )
                hit["snippet"] = _make_snippet(snippet_src, tokens)
                hit_by_key[(db_path, table_name, conv_username, local_id)] = hit
        finally:
            msg_conn.close()

    hits: list[dict[str, Any]] = []
    for k in ordered_keys:
        h = hit_by_key.get(k)
        if h is not None:
            hits.append(h)

    scope = "conversation" if username else "global"

    if username:
        uniq_usernames = list(dict.fromkeys([username] + [str(x.get("senderUsername") or "") for x in hits]))
        contact_rows = _load_contact_rows(contact_db_path, uniq_usernames)
        local_avatar_usernames = _query_head_image_usernames(head_image_db_path, uniq_usernames)

        wcdb_display_names: dict[str, str] = {}
        wcdb_avatar_urls: dict[str, str] = {}
        try:
            need_display: list[str] = []
            need_avatar: list[str] = []
            for u in uniq_usernames:
                uu = str(u or "").strip()
                if not uu:
                    continue
                row = contact_rows.get(uu)
                if _pick_display_name(row, uu) == uu:
                    need_display.append(uu)
                if uu not in local_avatar_usernames:
                    need_avatar.append(uu)

            need_display = list(dict.fromkeys(need_display))
            need_avatar = list(dict.fromkeys(need_avatar))
            if need_display or need_avatar:
                wcdb_conn = WCDB_REALTIME.ensure_connected(account_dir)
                with wcdb_conn.lock:
                    if need_display:
                        wcdb_display_names = _wcdb_get_display_names(wcdb_conn.handle, need_display)
                    if need_avatar:
                        wcdb_avatar_urls = _wcdb_get_avatar_urls(wcdb_conn.handle, need_avatar)
        except Exception:
            wcdb_display_names = {}
            wcdb_avatar_urls = {}

        conv_row = contact_rows.get(username)
        conv_name = _pick_display_name(conv_row, username)
        if conv_name == username:
            wd = str(wcdb_display_names.get(username) or "").strip()
            if wd and wd != username:
                conv_name = wd
        conv_avatar = base_url + _avatar_url_unified(
            account_dir=account_dir,
            username=username,
            local_avatar_usernames=local_avatar_usernames,
        )
        group_nicknames = _load_group_nickname_map(
            account_dir=account_dir,
            contact_db_path=contact_db_path,
            chatroom_id=username,
            sender_usernames=[str(x.get("senderUsername") or "") for x in hits],
        )

        for h in hits:
            su = str(h.get("senderUsername") or "").strip()
            h["conversationName"] = conv_name
            h["conversationAvatar"] = conv_avatar
            if su:
                h["senderDisplayName"] = _resolve_sender_display_name(
                    sender_username=su,
                    sender_contact_rows=contact_rows,
                    wcdb_display_names=wcdb_display_names,
                    group_nicknames=group_nicknames,
                )
                avatar_url = base_url + _avatar_url_unified(
                    account_dir=account_dir,
                    username=su,
                    local_avatar_usernames=local_avatar_usernames,
                )
                h["senderAvatar"] = avatar_url
    else:
        uniq_contacts = list(
            dict.fromkeys(
                [str(x.get("username") or "") for x in hits] + [str(x.get("senderUsername") or "") for x in hits]
            )
        )
        contact_rows = _load_contact_rows(contact_db_path, uniq_contacts)
        local_avatar_usernames = _query_head_image_usernames(head_image_db_path, uniq_contacts)

        wcdb_display_names: dict[str, str] = {}
        wcdb_avatar_urls: dict[str, str] = {}
        try:
            need_display: list[str] = []
            need_avatar: list[str] = []
            for u in uniq_contacts:
                uu = str(u or "").strip()
                if not uu:
                    continue
                row = contact_rows.get(uu)
                if _pick_display_name(row, uu) == uu:
                    need_display.append(uu)
                if uu not in local_avatar_usernames:
                    need_avatar.append(uu)

            need_display = list(dict.fromkeys(need_display))
            need_avatar = list(dict.fromkeys(need_avatar))
            if need_display or need_avatar:
                wcdb_conn = WCDB_REALTIME.ensure_connected(account_dir)
                with wcdb_conn.lock:
                    if need_display:
                        wcdb_display_names = _wcdb_get_display_names(wcdb_conn.handle, need_display)
                    if need_avatar:
                        wcdb_avatar_urls = _wcdb_get_avatar_urls(wcdb_conn.handle, need_avatar)
        except Exception:
            wcdb_display_names = {}
            wcdb_avatar_urls = {}

        group_senders_by_room: dict[str, list[str]] = {}
        for h in hits:
            cu = str(h.get("username") or "").strip()
            su = str(h.get("senderUsername") or "").strip()
            if (not cu.endswith("@chatroom")) or (not su):
                continue
            group_senders_by_room.setdefault(cu, []).append(su)

        group_nickname_cache: dict[str, dict[str, str]] = {}
        for cu, senders in group_senders_by_room.items():
            group_nickname_cache[cu] = _load_group_nickname_map(
                account_dir=account_dir,
                contact_db_path=contact_db_path,
                chatroom_id=cu,
                sender_usernames=senders,
            )

        for h in hits:
            cu = str(h.get("username") or "").strip()
            su = str(h.get("senderUsername") or "").strip()
            crow = contact_rows.get(cu)
            conv_name = _pick_display_name(crow, cu) if cu else ""
            if cu and (conv_name == cu):
                wd = str(wcdb_display_names.get(cu) or "").strip()
                if wd and wd != cu:
                    conv_name = wd
            h["conversationName"] = conv_name or cu
            conv_avatar = base_url + _avatar_url_unified(
                account_dir=account_dir,
                username=cu,
                local_avatar_usernames=local_avatar_usernames,
            )
            h["conversationAvatar"] = conv_avatar
            if su:
                h["senderDisplayName"] = _resolve_sender_display_name(
                    sender_username=su,
                    sender_contact_rows=contact_rows,
                    wcdb_display_names=wcdb_display_names,
                    group_nicknames=group_nickname_cache.get(cu, {}),
                )
                avatar_url = base_url + _avatar_url_unified(
                    account_dir=account_dir,
                    username=su,
                    local_avatar_usernames=local_avatar_usernames,
                )
                h["senderAvatar"] = avatar_url

    return {
        "status": "success",
        "account": account_dir.name,
        "scope": scope,
        "username": username,
        "q": q,
        "tokens": tokens,
        "offset": int(offset),
        "limit": int(limit),
        "baseUrl": base_url,
        "total": int(total),
        "hasMore": bool(int(offset) + int(limit) < int(total)),
        "index": index,
        "hits": hits,
    }


@router.get("/api/chat/search", summary="搜索聊天记录（消息）")
async def search_chat_messages(
    request: Request,
    q: str,
    account: Optional[str] = None,
    username: Optional[str] = None,
    sender: Optional[str] = None,
    session_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    render_types: Optional[str] = None,
    include_hidden: bool = False,
    include_official: bool = False,
    session_limit: int = 200,
    per_chat_scan: int = 200,
    scan_limit: int = 20000,
):
    return await _search_chat_messages_via_fts(
        request,
        q=q,
        account=account,
        username=username,
        sender=sender,
        session_type=session_type,
        limit=limit,
        offset=offset,
        start_time=start_time,
        end_time=end_time,
        render_types=render_types,
        include_hidden=include_hidden,
        include_official=include_official,
    )

    tokens = _make_search_tokens(q)
    if not tokens:
        raise HTTPException(status_code=400, detail="Missing q.")

    if limit <= 0:
        raise HTTPException(status_code=400, detail="Invalid limit.")
    if limit > 200:
        limit = 200
    if offset < 0:
        offset = 0

    if session_limit <= 0:
        session_limit = 200
    if session_limit > 2000:
        session_limit = 2000

    if per_chat_scan <= 0:
        per_chat_scan = 200
    if per_chat_scan > 5000:
        per_chat_scan = 5000

    if scan_limit <= 0:
        scan_limit = 20000
    if scan_limit > 200000:
        scan_limit = 200000

    start_ts = int(start_time) if start_time is not None else None
    end_ts = int(end_time) if end_time is not None else None
    if start_ts is not None and start_ts < 0:
        start_ts = 0
    if end_ts is not None and end_ts < 0:
        end_ts = 0

    want_types: Optional[set[str]] = None
    if render_types is not None:
        parts = [p.strip() for p in str(render_types or "").split(",") if p.strip()]
        want_types = {p for p in parts if p}
        if not want_types:
            want_types = None

    account_dir = _resolve_account_dir(account)
    db_paths = _iter_message_db_paths(account_dir)
    contact_db_path = account_dir / "contact.db"
    session_db_path = account_dir / "session.db"

    if not db_paths:
        return {
            "status": "error",
            "account": account_dir.name,
            "q": q,
            "hits": [],
            "hasMore": False,
            "scanLimited": False,
            "scannedMessages": 0,
            "message": "No message databases found for this account.",
        }

    def build_haystack(hit: dict[str, Any]) -> str:
        items = [
            str(hit.get("content") or ""),
            str(hit.get("title") or ""),
            str(hit.get("url") or ""),
            str(hit.get("quoteTitle") or ""),
            str(hit.get("quoteContent") or ""),
            str(hit.get("amount") or ""),
        ]
        return "\n".join([x for x in items if x.strip()])

    def scan_conversation(conv_username: str, *, per_db_limit: int, max_hits: Optional[int] = None) -> tuple[list[dict[str, Any]], int, bool]:
        is_group = bool(conv_username.endswith("@chatroom"))
        scanned = 0
        truncated = False
        hits: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for db_path in db_paths:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            try:
                table_name = _resolve_msg_table_name(conn, conv_username)
                if not table_name:
                    continue

                my_wxid = account_dir.name
                my_rowid = None
                try:
                    r2 = conn.execute(
                        "SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1",
                        (my_wxid,),
                    ).fetchone()
                    if r2 is not None:
                        my_rowid = int(r2[0])
                except Exception:
                    my_rowid = None

                where_parts: list[str] = []
                params: list[Any] = []
                if start_ts is not None:
                    where_parts.append("m.create_time >= ?")
                    params.append(int(start_ts))
                if end_ts is not None:
                    where_parts.append("m.create_time <= ?")
                    params.append(int(end_ts))

                where_sql = ""
                if where_parts:
                    where_sql = "WHERE " + " AND ".join(where_parts)

                quoted_table = _quote_ident(table_name)
                sql_with_join = (
                    "SELECT "
                    "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                    "m.message_content, m.compress_content, n.user_name AS sender_username "
                    f"FROM {quoted_table} m "
                    "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
                    f"{where_sql} "
                    "ORDER BY m.create_time DESC, m.sort_seq DESC, m.local_id DESC "
                    "LIMIT ?"
                )
                sql_no_join = (
                    "SELECT "
                    "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                    "m.message_content, m.compress_content, '' AS sender_username "
                    f"FROM {quoted_table} m "
                    f"{where_sql} "
                    "ORDER BY m.create_time DESC, m.sort_seq DESC, m.local_id DESC "
                    "LIMIT ?"
                )

                conn.text_factory = bytes

                per_db_probe = int(per_db_limit) + 1
                params_probe = list(params) + [per_db_probe]
                try:
                    rows = conn.execute(sql_with_join, params_probe).fetchall()
                except Exception:
                    rows = conn.execute(sql_no_join, params_probe).fetchall()

                if len(rows) > per_db_limit:
                    truncated = True
                    rows = rows[:per_db_limit]

                scanned += len(rows)

                for rr in rows:
                    hit = _row_to_search_hit(
                        rr,
                        db_path=db_path,
                        table_name=table_name,
                        username=conv_username,
                        account_dir=account_dir,
                        is_group=is_group,
                        my_rowid=my_rowid,
                    )
                    if want_types is not None and str(hit.get("renderType") or "") not in want_types:
                        continue

                    haystack = build_haystack(hit)
                    if not _match_tokens(haystack, tokens):
                        continue

                    mid = str(hit.get("id") or "")
                    if not mid or mid in seen_ids:
                        continue
                    seen_ids.add(mid)

                    snippet_src = str(hit.get("content") or "").strip() or str(hit.get("title") or "").strip() or haystack
                    hit["snippet"] = _make_snippet(snippet_src, tokens)
                    hits.append(hit)

                    if max_hits is not None and len(hits) >= int(max_hits):
                        return hits, scanned, True
            finally:
                conn.close()

        return hits, scanned, truncated

    base_url = str(request.base_url).rstrip("/")

    hits: list[dict[str, Any]] = []
    scanned_messages = 0
    scan_limited = False

    if username:
        conv_hits, scanned, truncated = scan_conversation(username, per_db_limit=scan_limit)
        scanned_messages = scanned
        scan_limited = bool(truncated)

        conv_hits.sort(
            key=lambda h: (
                int(h.get("createTime") or 0),
                int(h.get("sortSeq") or 0),
                int(h.get("localId") or 0),
            ),
            reverse=True,
        )
        total_in_scan = len(conv_hits)
        page = conv_hits[int(offset) : int(offset) + int(limit)]

        uniq_usernames = list(dict.fromkeys([username] + [str(x.get("senderUsername") or "") for x in page]))
        contact_rows = _load_contact_rows(contact_db_path, uniq_usernames)
        conv_row = contact_rows.get(username)
        conv_name = _pick_display_name(conv_row, username)
        group_nicknames = _load_group_nickname_map(
            account_dir=account_dir,
            contact_db_path=contact_db_path,
            chatroom_id=username,
            sender_usernames=[str(x.get("senderUsername") or "") for x in page],
        )

        for h in page:
            su = str(h.get("senderUsername") or "").strip()
            h["conversationName"] = conv_name
            if su:
                h["senderDisplayName"] = _resolve_sender_display_name(
                    sender_username=su,
                    sender_contact_rows=contact_rows,
                    wcdb_display_names={},
                    group_nicknames=group_nicknames,
                )

        return {
            "status": "success",
            "account": account_dir.name,
            "scope": "conversation",
            "username": username,
            "q": q,
            "tokens": tokens,
            "offset": int(offset),
            "limit": int(limit),
            "totalInScan": total_in_scan,
            "hasMore": bool((int(offset) + int(limit) < total_in_scan) or scan_limited),
            "scanLimited": bool(scan_limited),
            "scannedMessages": int(scanned_messages),
            "hits": page,
        }

    # Global: scan recent conversations (session.db), then keep only top K newest hits within the scanned window.
    if not session_db_path.exists():
        raise HTTPException(status_code=404, detail="session.db not found for this account.")

    sconn = sqlite3.connect(str(session_db_path))
    sconn.row_factory = sqlite3.Row
    try:
        rows = sconn.execute(
            """
            SELECT
                username,
                is_hidden,
                sort_timestamp,
                last_timestamp
            FROM SessionTable
            ORDER BY sort_timestamp DESC
            LIMIT ?
            """,
            (int(session_limit),),
        ).fetchall()
    finally:
        sconn.close()

    conv_usernames: list[str] = []
    for r in rows:
        u = str(r["username"] or "").strip()
        if not u:
            continue
        if not include_hidden and int(r["is_hidden"] or 0) == 1:
            continue
        if not _should_keep_session(u, include_official=include_official):
            continue
        conv_usernames.append(u)

    top_k = min(5000, int(offset) + int(limit) + 2000)
    heap: list[tuple[tuple[int, int, int], dict[str, Any]]] = []

    for conv in conv_usernames:
        conv_hits, scanned, truncated = scan_conversation(conv, per_db_limit=per_chat_scan, max_hits=50)
        scanned_messages += int(scanned)
        if truncated:
            scan_limited = True
        for h in conv_hits:
            k = (
                int(h.get("createTime") or 0),
                int(h.get("sortSeq") or 0),
                int(h.get("localId") or 0),
            )
            heapq.heappush(heap, (k, h))
            if len(heap) > top_k:
                heapq.heappop(heap)

    heap.sort(key=lambda x: x[0], reverse=True)
    hits_all = [x[1] for x in heap]
    total_in_scan = len(hits_all)
    page = hits_all[int(offset) : int(offset) + int(limit)]

    uniq_contacts = list(
        dict.fromkeys(
            [str(x.get("username") or "") for x in page] + [str(x.get("senderUsername") or "") for x in page]
        )
    )
    contact_rows = _load_contact_rows(contact_db_path, uniq_contacts)

    group_senders_by_room: dict[str, list[str]] = {}
    for h in page:
        cu = str(h.get("username") or "").strip()
        su = str(h.get("senderUsername") or "").strip()
        if (not cu.endswith("@chatroom")) or (not su):
            continue
        group_senders_by_room.setdefault(cu, []).append(su)

    group_nickname_cache: dict[str, dict[str, str]] = {}
    for cu, senders in group_senders_by_room.items():
        group_nickname_cache[cu] = _load_group_nickname_map(
            account_dir=account_dir,
            contact_db_path=contact_db_path,
            chatroom_id=cu,
            sender_usernames=senders,
        )

    for h in page:
        cu = str(h.get("username") or "").strip()
        su = str(h.get("senderUsername") or "").strip()
        crow = contact_rows.get(cu)
        conv_name = _pick_display_name(crow, cu) if cu else ""
        h["conversationName"] = conv_name or cu
        if su:
            h["senderDisplayName"] = _resolve_sender_display_name(
                sender_username=su,
                sender_contact_rows=contact_rows,
                wcdb_display_names={},
                group_nicknames=group_nickname_cache.get(cu, {}),
            )

    return {
        "status": "success",
        "account": account_dir.name,
        "scope": "global",
        "q": q,
        "tokens": tokens,
        "offset": int(offset),
        "limit": int(limit),
        "baseUrl": base_url,
        "totalInScan": total_in_scan,
        "hasMore": bool((int(offset) + int(limit) < total_in_scan) or scan_limited or (total_in_scan >= top_k)),
        "scanLimited": bool(scan_limited),
        "scannedMessages": int(scanned_messages),
        "conversationsScanned": len(conv_usernames),
        "hits": page,
    }


@router.get("/api/chat/messages/around", summary="定位到某条消息并返回上下文")
async def get_chat_messages_around(
    request: Request,
    username: str,
    anchor_id: str,
    account: Optional[str] = None,
    before: int = 20,
    after: int = 20,
):
    if not username:
        raise HTTPException(status_code=400, detail="Missing username.")
    if not anchor_id:
        raise HTTPException(status_code=400, detail="Missing anchor_id.")

    if before < 0:
        before = 0
    if after < 0:
        after = 0
    if before > 200:
        before = 200
    if after > 200:
        after = 200

    parts = str(anchor_id).split(":", 2)
    if len(parts) != 3:
        raise HTTPException(status_code=400, detail="Invalid anchor_id.")
    anchor_db_stem, anchor_table_name_in, anchor_local_id_str = parts
    try:
        anchor_local_id = int(anchor_local_id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid anchor_id.")

    account_dir = _resolve_account_dir(account)
    db_paths = _iter_message_db_paths(account_dir)
    contact_db_path = account_dir / "contact.db"
    head_image_db_path = account_dir / "head_image.db"
    message_resource_db_path = account_dir / "message_resource.db"
    base_url = str(request.base_url).rstrip("/")

    anchor_db_path: Optional[Path] = None
    for p in db_paths:
        if p.stem == anchor_db_stem:
            anchor_db_path = p
            break
    if anchor_db_path is None:
        raise HTTPException(status_code=404, detail="Anchor database not found.")

    # Open resource DB once (optional), and reuse for all message DBs.
    resource_conn: Optional[sqlite3.Connection] = None
    resource_chat_id: Optional[int] = None
    try:
        if message_resource_db_path.exists():
            resource_conn = sqlite3.connect(str(message_resource_db_path))
            resource_conn.row_factory = sqlite3.Row
            resource_chat_id = _resource_lookup_chat_id(resource_conn, username)
    except Exception:
        if resource_conn is not None:
            try:
                resource_conn.close()
            except Exception:
                pass
        resource_conn = None
        resource_chat_id = None

    # Resolve anchor message tuple from its DB.
    anchor_ct = 0
    anchor_ss = 0
    anchor_table_name = str(anchor_table_name_in or "").strip()
    anchor_row: Optional[sqlite3.Row] = None
    anchor_packed_select = "NULL AS packed_info_data, "
    try:
        conn_a = sqlite3.connect(str(anchor_db_path))
        conn_a.row_factory = sqlite3.Row
        try:
            if not anchor_table_name:
                try:
                    anchor_table_name = _resolve_msg_table_name(conn_a, username) or ""
                except Exception:
                    anchor_table_name = ""
            if not anchor_table_name:
                raise HTTPException(status_code=404, detail="Anchor table not found.")

            # Normalize table name casing if needed
            try:
                trows = conn_a.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                lower_to_actual = {str(x[0]).lower(): str(x[0]) for x in trows if x and x[0]}
                anchor_table_name = lower_to_actual.get(anchor_table_name.lower(), anchor_table_name)
            except Exception:
                pass

            quoted_table_a = _quote_ident(anchor_table_name)
            has_packed_info_data = False
            try:
                cols = conn_a.execute(f"PRAGMA table_info({quoted_table_a})").fetchall()
                has_packed_info_data = any(str(c[1] or "").strip().lower() == "packed_info_data" for c in cols)
            except Exception:
                has_packed_info_data = False
            anchor_packed_select = (
                "m.packed_info_data AS packed_info_data, " if has_packed_info_data else "NULL AS packed_info_data, "
            )

            sql_anchor_with_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, "
                + anchor_packed_select
                + "n.user_name AS sender_username "
                f"FROM {quoted_table_a} m "
                "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
                "WHERE m.local_id = ? "
                "LIMIT 1"
            )
            sql_anchor_no_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, "
                + anchor_packed_select
                + "'' AS sender_username "
                f"FROM {quoted_table_a} m "
                "WHERE m.local_id = ? "
                "LIMIT 1"
            )

            conn_a.text_factory = bytes
            try:
                anchor_row = conn_a.execute(sql_anchor_with_join, (anchor_local_id,)).fetchone()
            except Exception:
                anchor_row = conn_a.execute(sql_anchor_no_join, (anchor_local_id,)).fetchone()

            if anchor_row is None:
                raise HTTPException(status_code=404, detail="Anchor message not found.")

            anchor_ct = int(anchor_row["create_time"] or 0)
            anchor_ss = int(anchor_row["sort_seq"] or 0) if anchor_row["sort_seq"] is not None else 0
        finally:
            conn_a.close()
    finally:
        pass

    anchor_id_canon = f"{anchor_db_stem}:{anchor_table_name}:{anchor_local_id}"

    merged: list[dict[str, Any]] = []
    sender_usernames_all: list[str] = []
    quote_usernames_all: list[str] = []
    pat_usernames_all: set[str] = set()
    is_group = bool(username.endswith("@chatroom"))

    for db_path in db_paths:
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row

            table_name = ""
            if db_path.stem == anchor_db_stem:
                table_name = anchor_table_name
            else:
                try:
                    table_name = _resolve_msg_table_name(conn, username) or ""
                except Exception:
                    table_name = ""
            if not table_name:
                continue

            my_wxid = account_dir.name
            my_rowid = None
            try:
                r2 = conn.execute(
                    "SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1",
                    (my_wxid,),
                ).fetchone()
                if r2 is not None:
                    my_rowid = int(r2[0])
            except Exception:
                my_rowid = None

            quoted_table = _quote_ident(table_name)
            has_packed_info_data = False
            try:
                cols = conn.execute(f"PRAGMA table_info({quoted_table})").fetchall()
                has_packed_info_data = any(str(c[1] or "").strip().lower() == "packed_info_data" for c in cols)
            except Exception:
                has_packed_info_data = False
            packed_select = (
                "m.packed_info_data AS packed_info_data, " if has_packed_info_data else "NULL AS packed_info_data, "
            )

            # Stable cross-db ordering: (create_time, sort_seq, db_stem, local_id)
            stem = db_path.stem
            if stem < anchor_db_stem:
                tie_before = "1"
                tie_before_params: tuple[Any, ...] = ()
                tie_after = "0"
                tie_after_params: tuple[Any, ...] = ()
            elif stem > anchor_db_stem:
                tie_before = "0"
                tie_before_params = ()
                tie_after = "1"
                tie_after_params = ()
            else:
                tie_before = "m.local_id < ?"
                tie_before_params = (int(anchor_local_id),)
                tie_after = "m.local_id > ?"
                tie_after_params = (int(anchor_local_id),)

            where_before = (
                "WHERE ("
                "m.create_time < ? "
                "OR (m.create_time = ? AND COALESCE(m.sort_seq, 0) < ?) "
                f"OR (m.create_time = ? AND COALESCE(m.sort_seq, 0) = ? AND {tie_before})"
                ")"
            )
            where_after = (
                "WHERE ("
                "m.create_time > ? "
                "OR (m.create_time = ? AND COALESCE(m.sort_seq, 0) > ?) "
                f"OR (m.create_time = ? AND COALESCE(m.sort_seq, 0) = ? AND {tie_after})"
                ")"
            )

            sql_before_with_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, "
                + packed_select
                + "n.user_name AS sender_username "
                f"FROM {quoted_table} m "
                "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
                f"{where_before} "
                "ORDER BY m.create_time DESC, COALESCE(m.sort_seq, 0) DESC, m.local_id DESC "
                "LIMIT ?"
            )
            sql_before_no_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, "
                + packed_select
                + "'' AS sender_username "
                f"FROM {quoted_table} m "
                f"{where_before} "
                "ORDER BY m.create_time DESC, COALESCE(m.sort_seq, 0) DESC, m.local_id DESC "
                "LIMIT ?"
            )

            sql_after_with_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, "
                + packed_select
                + "n.user_name AS sender_username "
                f"FROM {quoted_table} m "
                "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
                f"{where_after} "
                "ORDER BY m.create_time ASC, COALESCE(m.sort_seq, 0) ASC, m.local_id ASC "
                "LIMIT ?"
            )
            sql_after_no_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, "
                + packed_select
                + "'' AS sender_username "
                f"FROM {quoted_table} m "
                f"{where_after} "
                "ORDER BY m.create_time ASC, COALESCE(m.sort_seq, 0) ASC, m.local_id ASC "
                "LIMIT ?"
            )

            # Always fetch anchor row from anchor DB, but don't include anchor itself in before/after queries.
            anchor_rows: list[sqlite3.Row] = []
            if db_path.stem == anchor_db_stem:
                if anchor_row is None:
                    raise HTTPException(status_code=404, detail="Anchor message not found.")
                anchor_rows = [anchor_row]

            conn.text_factory = bytes

            before_rows: list[sqlite3.Row] = []
            if int(before) > 0:
                params_before = (
                    int(anchor_ct),
                    int(anchor_ct),
                    int(anchor_ss),
                    int(anchor_ct),
                    int(anchor_ss),
                    *tie_before_params,
                    int(before) + 1,
                )
                try:
                    before_rows = conn.execute(sql_before_with_join, params_before).fetchall()
                except Exception:
                    before_rows = conn.execute(sql_before_no_join, params_before).fetchall()

            after_rows: list[sqlite3.Row] = []
            if int(after) > 0:
                params_after = (
                    int(anchor_ct),
                    int(anchor_ct),
                    int(anchor_ss),
                    int(anchor_ct),
                    int(anchor_ss),
                    *tie_after_params,
                    int(after) + 1,
                )
                try:
                    after_rows = conn.execute(sql_after_with_join, params_after).fetchall()
                except Exception:
                    after_rows = conn.execute(sql_after_no_join, params_after).fetchall()

            # Dedup rows by message id within this DB.
            seen_ids: set[str] = set()
            combined: list[sqlite3.Row] = []
            for rr in list(before_rows) + list(anchor_rows) + list(after_rows):
                lid = int(rr["local_id"] or 0)
                mid = f"{db_path.stem}:{table_name}:{lid}"
                if mid in seen_ids:
                    continue
                seen_ids.add(mid)
                combined.append(rr)

            if not combined:
                continue

            _append_full_messages_from_rows(
                merged=merged,
                sender_usernames=sender_usernames_all,
                quote_usernames=quote_usernames_all,
                pat_usernames=pat_usernames_all,
                rows=combined,
                db_path=db_path,
                table_name=table_name,
                username=username,
                account_dir=account_dir,
                is_group=is_group,
                my_rowid=my_rowid,
                resource_conn=resource_conn,
                resource_chat_id=resource_chat_id,
            )
        except HTTPException:
            raise
        except Exception:
            # Skip broken DBs / missing tables gracefully.
            continue
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    if resource_conn is not None:
        try:
            resource_conn.close()
        except Exception:
            pass

    # Global dedupe + sort.
    if merged:
        seen_ids2: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for m in merged:
            mid = str(m.get("id") or "").strip()
            if mid and mid in seen_ids2:
                continue
            if mid:
                seen_ids2.add(mid)
            deduped.append(m)
        merged = deduped

    def sort_key_global(m: dict[str, Any]) -> tuple[int, int, str, int]:
        cts = int(m.get("createTime") or 0)
        sseq = int(m.get("sortSeq") or 0)
        lid = int(m.get("localId") or 0)
        mid = str(m.get("id") or "")
        stem2 = ""
        try:
            stem2 = mid.split(":", 1)[0] if ":" in mid else ""
        except Exception:
            stem2 = ""
        return (cts, sseq, stem2, lid)

    merged.sort(key=sort_key_global, reverse=False)

    anchor_index_all = -1
    for i, m in enumerate(merged):
        if str(m.get("id") or "") == str(anchor_id_canon):
            anchor_index_all = i
            break
    if anchor_index_all < 0:
        # Fallback: ignore table casing differences when matching anchor.
        for i, m in enumerate(merged):
            mid = str(m.get("id") or "")
            p2 = mid.split(":", 2)
            if len(p2) != 3:
                continue
            if p2[0] != anchor_db_stem:
                continue
            try:
                if int(p2[2] or 0) == int(anchor_local_id):
                    anchor_index_all = i
                    break
            except Exception:
                continue

    if anchor_index_all < 0:
        # Should not happen because we always include the anchor row, but keep defensive.
        anchor_index_all = 0

    start = max(0, int(anchor_index_all) - int(before))
    end = min(len(merged), int(anchor_index_all) + int(after) + 1)
    return_messages = merged[start:end]
    anchor_index = int(anchor_index_all) - start if 0 <= anchor_index_all < len(merged) else -1

    # Postprocess only the returned window to keep it fast.
    sender_usernames_win = [str(m.get("senderUsername") or "").strip() for m in return_messages if str(m.get("senderUsername") or "").strip()]
    quote_usernames_win = [str(m.get("quoteUsername") or "").strip() for m in return_messages if str(m.get("quoteUsername") or "").strip()]
    pat_usernames_win: set[str] = set()
    try:
        for m in return_messages:
            if int(m.get("type") or 0) != 266287972401:
                continue
            raw = str(m.get("_rawText") or "")
            if not raw:
                continue
            template = _extract_xml_tag_text(raw, "template")
            if not template:
                continue
            pat_usernames_win.update({mm.group(1) for mm in re.finditer(r"\$\{([^}]+)\}", template) if mm.group(1)})
    except Exception:
        pat_usernames_win = set()

    _postprocess_full_messages(
        merged=return_messages,
        sender_usernames=sender_usernames_win,
        quote_usernames=quote_usernames_win,
        pat_usernames=pat_usernames_win,
        account_dir=account_dir,
        username=username,
        base_url=base_url,
        contact_db_path=contact_db_path,
        head_image_db_path=head_image_db_path,
    )

    return {
        "status": "success",
        "account": account_dir.name,
        "username": username,
        "anchorId": anchor_id_canon,
        "anchorIndex": anchor_index,
        "messages": return_messages,
    }


@router.get("/api/chat/chat_history/resolve", summary="解析嵌套合并转发聊天记录（通过 server_id）")
async def resolve_nested_chat_history(
    request: Request,
    server_id: int,
    account: Optional[str] = None,
):
    """Resolve a nested merged-forward chat history item (datatype=17) to its full recordItem XML.

    Some nested records inside a merged-forward recordItem only carry pointers like `fromnewmsgid` (server_id),
    while the full recordItem exists in the original app message (local_type=49, appmsg type=19) stored elsewhere.
    WeChat can open it by looking up the original message; we do the same here.
    """
    if not server_id:
        raise HTTPException(status_code=400, detail="Missing server_id.")

    account_dir = _resolve_account_dir(account)
    db_paths = _iter_message_db_paths(account_dir)
    base_url = str(request.base_url).rstrip("/")
    found_appmsg = False

    for db_path in db_paths:
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            conn.text_factory = bytes

            try:
                table_rows = conn.execute(
                    # Some DBs use `Msg_...` (capital M). Use LOWER() to keep matching even if
                    # `PRAGMA case_sensitive_like=ON` is set.
                    "SELECT name FROM sqlite_master WHERE type='table' AND lower(name) LIKE 'msg_%'"
                ).fetchall()
            except Exception:
                table_rows = []

            # With `conn.text_factory = bytes`, sqlite_master.name comes back as bytes.
            # Decode it to the real table name, otherwise we'd end up querying a non-existent
            # table like "b'Msg_...'" and never find the message.
            table_names = [_decode_sqlite_text(r[0]).strip() for r in table_rows if r and r[0]]
            for table_name in table_names:
                quoted = _quote_ident(table_name)
                try:
                    row = conn.execute(
                        f"""
                        SELECT local_id, server_id, local_type, create_time, message_content, compress_content
                        FROM {quoted}
                        -- WeChat v4 can pack appmsg subtype into the high 32 bits of local_type:
                        --   local_type = base_type + (app_subtype << 32)
                        -- so a chatHistory appmsg can be 49 + (19<<32), not exactly 49.
                        WHERE server_id = ? AND (local_type & 4294967295) = 49
                        LIMIT 1
                        """,
                        (int(server_id),),
                    ).fetchone()
                except Exception:
                    row = None

                if row is None:
                    continue

                found_appmsg = True
                raw_text = _decode_message_content(row["compress_content"], row["message_content"]).strip()
                if not raw_text:
                    continue

                # If the stored payload is a zstd frame but we couldn't decode it into XML, it's
                # almost always because the optional `zstandard` dependency isn't installed.
                try:
                    blob = row["message_content"]
                    if isinstance(blob, memoryview):
                        blob = blob.tobytes()
                    if isinstance(blob, (bytes, bytearray)) and bytes(blob).startswith(b"\x28\xb5\x2f\xfd"):
                        lower = raw_text.lower()
                        if "<appmsg" not in lower and "<msg" not in lower:
                            raise HTTPException(
                                status_code=500,
                                detail="Failed to decode zstd-compressed message_content. Please install `zstandard` and restart the backend.",
                            )
                except HTTPException:
                    raise
                except Exception:
                    pass

                parsed = _parse_app_message(raw_text)
                if not isinstance(parsed, dict):
                    continue

                if str(parsed.get("renderType") or "") != "chatHistory":
                    # Found an app message, but not a merged-forward chat history.
                    continue

                record_item = str(parsed.get("recordItem") or "").strip()
                if not record_item:
                    continue

                return {
                    "status": "success",
                    "serverId": int(server_id),
                    "title": str(parsed.get("title") or "").strip(),
                    "content": str(parsed.get("content") or "").strip(),
                    "recordItem": record_item,
                    "baseUrl": base_url,
                }
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    if found_appmsg:
        raise HTTPException(status_code=404, detail="Target message is not a chat history.")
    raise HTTPException(status_code=404, detail="Message not found for server_id.")


@router.get("/api/chat/appmsg/resolve", summary="解析卡片/小程序等 App 消息（通过 server_id）")
async def resolve_app_message(
    request: Request,
    server_id: int,
    account: Optional[str] = None,
):
    """Resolve an app message (base local_type=49) by server_id.

    This is mainly used by merged-forward recordItem dataitems that only contain pointers like
    `fromnewmsgid` (server_id). WeChat can open the original card by looking up the appmsg in
    message DBs; we do the same and return the parsed appmsg fields.
    """
    if not server_id:
        raise HTTPException(status_code=400, detail="Missing server_id.")

    account_dir = _resolve_account_dir(account)
    db_paths = _iter_message_db_paths(account_dir)
    base_url = str(request.base_url).rstrip("/")

    found_appmsg = False
    for db_path in db_paths:
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            conn.text_factory = bytes

            try:
                table_rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND lower(name) LIKE 'msg_%'"
                ).fetchall()
            except Exception:
                table_rows = []

            table_names = [_decode_sqlite_text(r[0]).strip() for r in table_rows if r and r[0]]
            for table_name in table_names:
                quoted = _quote_ident(table_name)
                try:
                    row = conn.execute(
                        f"""
                        SELECT local_id, server_id, local_type, create_time, message_content, compress_content
                        FROM {quoted}
                        WHERE server_id = ? AND (local_type & 4294967295) = 49
                        LIMIT 1
                        """,
                        (int(server_id),),
                    ).fetchone()
                except Exception:
                    row = None

                if row is None:
                    continue

                found_appmsg = True
                raw_text = _decode_message_content(row["compress_content"], row["message_content"]).strip()
                if not raw_text:
                    continue

                # Same zstd guard as chat_history/resolve.
                try:
                    blob = row["message_content"]
                    if isinstance(blob, memoryview):
                        blob = blob.tobytes()
                    if isinstance(blob, (bytes, bytearray)) and bytes(blob).startswith(b"\x28\xb5\x2f\xfd"):
                        lower = raw_text.lower()
                        if "<appmsg" not in lower and "<msg" not in lower:
                            raise HTTPException(
                                status_code=500,
                                detail="Failed to decode zstd-compressed message_content. Please install `zstandard` and restart the backend.",
                            )
                except HTTPException:
                    raise
                except Exception:
                    pass

                parsed = _parse_app_message(raw_text)
                if not isinstance(parsed, dict):
                    continue

                # Return a stable, explicit shape for the frontend.
                return {
                    "status": "success",
                    "serverId": int(server_id),
                    "renderType": str(parsed.get("renderType") or "text"),
                    "title": str(parsed.get("title") or "").strip(),
                    "content": str(parsed.get("content") or "").strip(),
                    "url": str(parsed.get("url") or "").strip(),
                    "thumbUrl": str(parsed.get("thumbUrl") or "").strip(),
                    "coverUrl": str(parsed.get("coverUrl") or "").strip(),
                    "from": str(parsed.get("from") or "").strip(),
                    "fromUsername": str(parsed.get("fromUsername") or "").strip(),
                    "linkType": str(parsed.get("linkType") or "").strip(),
                    "linkStyle": str(parsed.get("linkStyle") or "").strip(),
                    "size": str(parsed.get("size") or "").strip(),
                    "baseUrl": base_url,
                }
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    if found_appmsg:
        raise HTTPException(status_code=404, detail="App message decode failed.")
    raise HTTPException(status_code=404, detail="Message not found for server_id.")


def _normalize_table_name_case(conn: sqlite3.Connection, table_name: str) -> str:
    t = str(table_name or "").strip()
    if not t:
        return ""
    try:
        r = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND lower(name)=lower(?) LIMIT 1",
            (t,),
        ).fetchone()
        if r is not None and r[0]:
            # With `conn.text_factory = bytes`, sqlite_master.name can be returned as bytes.
            # Decode it to avoid querying a non-existent table like "b'Msg_...'".
            return _decode_sqlite_text(r[0]).strip()
    except Exception:
        pass
    return t


def _table_info_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    t = str(table_name or "").strip()
    if not t:
        return set()
    quoted = _quote_ident(t)
    try:
        cols = conn.execute(f"PRAGMA table_info({quoted})").fetchall()
    except Exception:
        return set()
    out: set[str] = set()
    for c in cols:
        try:
            name = _decode_sqlite_text(c[1]).strip()
        except Exception:
            continue
        if name:
            out.add(name)
    return out


def _has_column(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    want = str(column_name or "").strip().lower()
    if not want:
        return False
    for c in _table_info_columns(conn, table_name):
        if str(c or "").strip().lower() == want:
            return True
    return False


def _lookup_output_my_rowid(conn: sqlite3.Connection, my_wxid: str) -> Optional[int]:
    try:
        r = conn.execute(
            "SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1",
            (str(my_wxid or "").strip(),),
        ).fetchone()
        if r is None:
            return None
        return int(r[0])
    except Exception:
        return None


def _lookup_output_username_by_rowid(conn: sqlite3.Connection, rowid: int) -> str:
    try:
        r = conn.execute(
            "SELECT user_name FROM Name2Id WHERE rowid = ? LIMIT 1",
            (int(rowid or 0),),
        ).fetchone()
        if r is None:
            return ""
        return _decode_sqlite_text(r[0]).strip()
    except Exception:
        return ""


def _select_output_message_row(conn: sqlite3.Connection, *, table_name: str, local_id: int) -> Optional[sqlite3.Row]:
    t = _normalize_table_name_case(conn, table_name)
    if not t:
        return None
    quoted_table = _quote_ident(t)
    has_packed_info_data = _has_column(conn, t, "packed_info_data")
    packed_select = "m.packed_info_data AS packed_info_data, " if has_packed_info_data else "NULL AS packed_info_data, "
    sql_with_join = (
        "SELECT "
        "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
        "m.message_content, m.compress_content, "
        + packed_select
        + "n.user_name AS sender_username "
        f"FROM {quoted_table} m "
        "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
        "WHERE m.local_id = ? "
        "LIMIT 1"
    )
    sql_no_join = (
        "SELECT "
        "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
        "m.message_content, m.compress_content, "
        + packed_select
        + "'' AS sender_username "
        f"FROM {quoted_table} m "
        "WHERE m.local_id = ? "
        "LIMIT 1"
    )
    try:
        return conn.execute(sql_with_join, (int(local_id),)).fetchone()
    except Exception:
        try:
            return conn.execute(sql_no_join, (int(local_id),)).fetchone()
        except Exception:
            return None


def _resolve_db_storage_message_paths(account_dir: Path, db_stem: str) -> tuple[Path, Path]:
    db_storage_dir = _resolve_account_db_storage_dir(account_dir)
    if db_storage_dir is None:
        raise HTTPException(status_code=400, detail="Cannot resolve db_storage directory for this account.")
    db_name = str(db_stem or "").strip()
    if not db_name:
        raise HTTPException(status_code=400, detail="Invalid message_id.")
    msg_db_path = db_storage_dir / "message" / f"{db_name}.db"
    res_db_path = db_storage_dir / "message" / "message_resource.db"
    return msg_db_path, res_db_path


def _build_wcdb_update_sql(*, table_name: str, updates: dict[str, Any], where_local_id: int) -> str:
    t = str(table_name or "").strip()
    if not t:
        raise HTTPException(status_code=400, detail="Missing table_name.")
    if not updates:
        raise HTTPException(status_code=400, detail="Missing edits.")
    parts: list[str] = []
    for k, v in updates.items():
        col = str(k or "").strip()
        if not col:
            continue
        parts.append(f"{_quote_ident(col)} = {_sql_literal(v)}")
    if not parts:
        raise HTTPException(status_code=400, detail="Missing edits.")
    return f"UPDATE {_quote_ident(t)} SET " + ", ".join(parts) + f" WHERE local_id = {int(where_local_id)}"


def _build_sqlite_update_sql(*, table_name: str, updates: dict[str, Any], where_local_id: int) -> tuple[str, list[Any]]:
    t = str(table_name or "").strip()
    if not t:
        raise HTTPException(status_code=400, detail="Missing table_name.")
    if not updates:
        raise HTTPException(status_code=400, detail="Missing edits.")
    cols: list[str] = []
    params: list[Any] = []
    for k, v in updates.items():
        col = str(k or "").strip()
        if not col:
            continue
        cols.append(f"{_quote_ident(col)} = ?")
        params.append(v)
    if not cols:
        raise HTTPException(status_code=400, detail="Missing edits.")
    sql = f"UPDATE {_quote_ident(t)} SET " + ", ".join(cols) + " WHERE local_id = ?"
    params.append(int(where_local_id))
    return sql, params


@router.get("/api/chat/messages/raw", summary="获取单条消息原始字段（output 解密库）")
def get_chat_message_raw(
    *,
    account: Optional[str] = None,
    username: str,
    message_id: str,
) -> dict[str, Any]:
    if not username:
        raise HTTPException(status_code=400, detail="Missing username.")
    if not message_id:
        raise HTTPException(status_code=400, detail="Missing message_id.")

    account_dir = _resolve_account_dir(account)
    try:
        db_stem, table_name_in, local_id = chat_edit_store.parse_message_id(message_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid message_id.")

    db_path = account_dir / f"{db_stem}.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="Message database not found.")

    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.text_factory = bytes
        table_name = _normalize_table_name_case(conn, table_name_in)
        if not table_name:
            raise HTTPException(status_code=404, detail="Message table not found.")

        quoted_table = _quote_ident(table_name)
        row = conn.execute(f"SELECT * FROM {quoted_table} WHERE local_id = ? LIMIT 1", (int(local_id),)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Message not found.")

        out_row: dict[str, Any] = {}
        for k in row.keys():
            out_row[str(k)] = _jsonify_db_value(str(k), row[k])

        return {
            "status": "success",
            "account": account_dir.name,
            "username": username,
            "messageId": f"{db_stem}:{table_name}:{int(local_id)}",
            "row": out_row,
        }
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.post("/api/chat/messages/edit", summary="编辑/修改消息（写入真实库 db_storage 并同步 output）")
async def edit_chat_message(request: Request) -> dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload.")

    account = str(payload.get("account") or "").strip() or None
    session_id = str(payload.get("session_id") or payload.get("username") or payload.get("sessionId") or "").strip()
    message_id_in = str(payload.get("message_id") or payload.get("messageId") or "").strip()
    edits_in = payload.get("edits")
    unsafe = bool(payload.get("unsafe") or False)

    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id.")
    if not message_id_in:
        raise HTTPException(status_code=400, detail="Missing message_id.")
    if not isinstance(edits_in, dict) or not edits_in:
        raise HTTPException(status_code=400, detail="Missing edits.")

    account_dir = _resolve_account_dir(account)
    base_url = str(request.base_url).rstrip("/")

    try:
        db_stem, table_name_in, local_id_old = chat_edit_store.parse_message_id(message_id_in)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid message_id.")

    msg_db_path_out = account_dir / f"{db_stem}.db"
    if not msg_db_path_out.exists():
        raise HTTPException(status_code=404, detail="Message database not found.")

    msg_db_path_real, res_db_path_real = _resolve_db_storage_message_paths(account_dir, db_stem)
    if not msg_db_path_real.exists():
        raise HTTPException(status_code=404, detail="Real message database not found in db_storage.")

    # Validate edits against output schema and normalize table name casing.
    table_name = table_name_in
    edits: dict[str, Any] = {}
    explicit_keys: set[str] = set()
    conn_schema: Optional[sqlite3.Connection] = None
    try:
        conn_schema = sqlite3.connect(str(msg_db_path_out))
        conn_schema.row_factory = sqlite3.Row
        table_name = _normalize_table_name_case(conn_schema, table_name_in)
        if not table_name:
            raise HTTPException(status_code=404, detail="Message table not found.")
        cols = _table_info_columns(conn_schema, table_name)
        if not cols:
            raise HTTPException(status_code=404, detail="Message table not found.")

        for k, v in edits_in.items():
            col = str(k or "").strip()
            if not col:
                continue
            if col not in cols:
                raise HTTPException(status_code=400, detail=f"Unknown column: {col}")
            if not _is_safe_edit_column(col, unsafe=unsafe):
                raise HTTPException(status_code=400, detail=f"Unsafe column requires unsafe=true: {col}")
            explicit_keys.add(col)
            edits[col] = _normalize_edit_value(col, v)
        if not edits:
            raise HTTPException(status_code=400, detail="Missing edits.")
    finally:
        if conn_schema is not None:
            try:
                conn_schema.close()
            except Exception:
                pass

    message_id = f"{db_stem}:{table_name}:{int(local_id_old)}"

    # Decide update strategy for real db_storage.
    only_message_content = (set(edits.keys()) == {"message_content"}) and ("compress_content" not in explicit_keys)

    # Default behavior: clear compress_content when message_content changes, unless explicitly provided.
    output_edits = dict(edits)
    if "message_content" in edits and ("compress_content" not in explicit_keys):
        output_edits.setdefault("compress_content", None)

    new_local_id = int(edits.get("local_id") or 0) if "local_id" in edits else int(local_id_old)
    if new_local_id <= 0:
        new_local_id = int(local_id_old)

    # Resource sync mapping when Msg fields change.
    resource_sync_map: dict[str, str] = {
        "local_type": "message_local_type",
        "create_time": "message_create_time",
        "server_id": "message_svr_id",
        "origin_source": "message_origin_source",
    }
    if unsafe:
        resource_sync_map["local_id"] = "message_local_id"

    warnings: list[str] = []

    with _realtime_sync_lock(account_dir.name, session_id):
        # Ensure WCDB realtime connection.
        try:
            wcdb_conn = WCDB_REALTIME.ensure_connected(account_dir)
        except WCDBRealtimeError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Read original row from real db_storage (snapshot).
        original_row: Optional[dict[str, Any]] = None
        original_create_time = 0
        try:
            select_sql = f"SELECT * FROM {_quote_ident(table_name)} WHERE local_id = {int(local_id_old)} LIMIT 1"
            with wcdb_conn.lock:
                rows = _wcdb_exec_query(
                    wcdb_conn.handle,
                    kind="message",
                    path=str(msg_db_path_real),
                    sql=select_sql,
                )
            if rows and isinstance(rows[0], dict):
                original_row = rows[0]
                try:
                    original_create_time = int(original_row.get("create_time") or 0)
                except Exception:
                    original_create_time = 0
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read original message row: {e}")
        if not original_row:
            raise HTTPException(status_code=404, detail="Message not found in real db_storage.")

        # Read original resource row from real db_storage (optional).
        original_resource_row: Optional[dict[str, Any]] = None
        try:
            if res_db_path_real.exists() and original_create_time > 0:
                res_sql = (
                    "SELECT * FROM MessageResourceInfo "
                    f"WHERE message_local_id = {int(local_id_old)} AND message_create_time = {int(original_create_time)} "
                    "ORDER BY message_id DESC "
                    "LIMIT 1"
                )
                with wcdb_conn.lock:
                    res_rows = _wcdb_exec_query(
                        wcdb_conn.handle,
                        kind="message",
                        path=str(res_db_path_real),
                        sql=res_sql,
                    )
                if res_rows and isinstance(res_rows[0], dict):
                    original_resource_row = res_rows[0]
        except Exception:
            original_resource_row = None

        # Create snapshot record only if this message hasn't been edited via this tool.
        created_record = False
        existing_record = chat_edit_store.get_message_edit(account_dir.name, session_id, message_id)
        if existing_record is None:
            try:
                chat_edit_store.upsert_original_once(
                    account=account_dir.name,
                    session_id=session_id,
                    db=db_stem,
                    table_name=table_name,
                    local_id=int(local_id_old),
                    original_msg=original_row,
                    original_resource=original_resource_row,
                    now_ms=int(time.time() * 1000),
                )
                created_record = True
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to write edit snapshot: {e}")

        # Read current output row (for rollback if real update fails).
        out_before: dict[str, Any] = {}
        conn_out: Optional[sqlite3.Connection] = None
        try:
            conn_out = sqlite3.connect(str(msg_db_path_out), timeout=5)
            conn_out.row_factory = sqlite3.Row
            table_name_out = _normalize_table_name_case(conn_out, table_name)
            if not table_name_out:
                raise HTTPException(status_code=404, detail="Message table not found.")
            quoted = _quote_ident(table_name_out)
            row_before = conn_out.execute(
                f"SELECT * FROM {quoted} WHERE local_id = ? LIMIT 1",
                (int(local_id_old),),
            ).fetchone()
            if row_before is None:
                if created_record:
                    try:
                        chat_edit_store.delete_message_edit(account_dir.name, session_id, message_id)
                    except Exception:
                        pass
                raise HTTPException(status_code=404, detail="Message not found in output database.")
            for k in row_before.keys():
                out_before[str(k)] = row_before[k]

            # Apply edits to output decrypted db first; if this fails, do not touch the real db_storage.
            sql_out, params_out = _build_sqlite_update_sql(
                table_name=table_name_out,
                updates=output_edits,
                where_local_id=int(local_id_old),
            )
            cur_out = conn_out.execute(sql_out, params_out)
            conn_out.commit()
            if int(getattr(cur_out, "rowcount", 0) or 0) <= 0:
                if created_record:
                    try:
                        chat_edit_store.delete_message_edit(account_dir.name, session_id, message_id)
                    except Exception:
                        pass
                raise HTTPException(status_code=404, detail="Message not found in output database.")
        except HTTPException:
            raise
        except Exception as e:
            if created_record:
                try:
                    chat_edit_store.delete_message_edit(account_dir.name, session_id, message_id)
                except Exception:
                    pass
            raise HTTPException(status_code=500, detail=f"Failed to update output database: {e}")

        # Apply edits to real db_storage. If it fails, rollback output changes.
        try:
            if only_message_content:
                new_content = edits.get("message_content")
                if isinstance(new_content, (bytes, bytearray, memoryview)):
                    try:
                        new_content = bytes(new_content).decode("utf-8", errors="replace")
                    except Exception:
                        new_content = ""
                _wcdb_update_message(
                    wcdb_conn.handle,
                    session_id=session_id,
                    local_id=int(local_id_old),
                    create_time=int(original_create_time),
                    new_content=str(new_content or ""),
                )
            else:
                real_edits = dict(edits)
                if "message_content" in edits and ("compress_content" not in explicit_keys):
                    real_edits.setdefault("compress_content", None)
                sql_real = _build_wcdb_update_sql(
                    table_name=table_name,
                    updates=real_edits,
                    where_local_id=int(local_id_old),
                )
                with wcdb_conn.lock:
                    _wcdb_exec_query(
                        wcdb_conn.handle,
                        kind="message",
                        path=str(msg_db_path_real),
                        sql=sql_real,
                    )
        except Exception as e:
            # Roll back output changes.
            try:
                where_lid = int(new_local_id) if ("local_id" in edits) else int(local_id_old)
                cols_now = _table_info_columns(conn_out, table_name_out)
                rollback_updates = {k: v for k, v in out_before.items() if str(k or "") in cols_now}
                sql_rb, params_rb = _build_sqlite_update_sql(
                    table_name=table_name_out,
                    updates=rollback_updates,
                    where_local_id=where_lid,
                )
                conn_out.execute(sql_rb, params_rb)
                conn_out.commit()
            except Exception:
                pass
            # Remove newly-created snapshot record (real db was not touched successfully).
            if created_record:
                try:
                    chat_edit_store.delete_message_edit(account_dir.name, session_id, message_id)
                except Exception:
                    pass
            raise HTTPException(status_code=500, detail=f"Failed to update real db_storage: {e}")
        finally:
            if conn_out is not None:
                try:
                    conn_out.close()
                except Exception:
                    pass

        # Sync message_resource key fields (best-effort).
        try:
            msg_to_res_updates: dict[str, Any] = {}
            for msg_col, res_col in resource_sync_map.items():
                if msg_col in edits:
                    msg_to_res_updates[res_col] = _normalize_edit_value(res_col, edits[msg_col])
            if msg_to_res_updates:
                res_message_id = 0
                if original_resource_row is not None:
                    try:
                        res_message_id = int(original_resource_row.get("message_id") or 0)
                    except Exception:
                        res_message_id = 0
                if res_message_id > 0:
                    # real db_storage
                    if res_db_path_real.exists():
                        parts = [f"{_quote_ident(k)} = {_sql_literal(v)}" for k, v in msg_to_res_updates.items()]
                        sql_res_real = (
                            "UPDATE MessageResourceInfo SET "
                            + ", ".join(parts)
                            + f" WHERE message_id = {int(res_message_id)}"
                        )
                        with wcdb_conn.lock:
                            _wcdb_exec_query(
                                wcdb_conn.handle,
                                kind="message",
                                path=str(res_db_path_real),
                                sql=sql_res_real,
                            )

                    # output decrypted
                    out_res_db_path = account_dir / "message_resource.db"
                    if out_res_db_path.exists():
                        conn_res = sqlite3.connect(str(out_res_db_path), timeout=5)
                        try:
                            set_cols = ", ".join([f"{_quote_ident(k)} = ?" for k in msg_to_res_updates.keys()])
                            params = list(msg_to_res_updates.values()) + [int(res_message_id)]
                            conn_res.execute(
                                f"UPDATE MessageResourceInfo SET {set_cols} WHERE message_id = ?",
                                params,
                            )
                            conn_res.commit()
                        finally:
                            conn_res.close()
                else:
                    warnings.append("message_resource row not found; skipped resource sync.")
        except Exception as e:
            warnings.append(f"Failed to sync message_resource: {e}")

        # If local_id changed (unsafe), move the edit record key so future reset works.
        edit_record_local_id = int(local_id_old)
        if "local_id" in edits and int(new_local_id) != int(local_id_old):
            ok = chat_edit_store.update_message_edit_local_id(
                account=account_dir.name,
                session_id=session_id,
                db=db_stem,
                table_name=table_name,
                old_local_id=int(local_id_old),
                new_local_id=int(new_local_id),
            )
            if not ok:
                warnings.append("Failed to update edit record key after local_id change.")
            else:
                edit_record_local_id = int(new_local_id)

        # If this was an already-tracked message, bump edit metadata.
        if existing_record is not None:
            try:
                chat_edit_store.upsert_original_once(
                    account=account_dir.name,
                    session_id=session_id,
                    db=db_stem,
                    table_name=table_name,
                    local_id=int(edit_record_local_id),
                    original_msg={},
                    original_resource=None,
                    now_ms=int(time.time() * 1000),
                )
            except Exception:
                pass

        # Track which columns were actually modified so reset can restore only those fields.
        try:
            chat_edit_store.merge_edited_columns(
                account=account_dir.name,
                session_id=session_id,
                db=db_stem,
                table_name=table_name,
                local_id=int(edit_record_local_id),
                columns=list(output_edits.keys()),
            )
        except Exception:
            pass

    # Build updated message object (best-effort, from output).
    updated_message: Optional[dict[str, Any]] = None
    try:
        conn_msg = sqlite3.connect(str(msg_db_path_out))
        conn_msg.row_factory = sqlite3.Row
        conn_msg.text_factory = bytes
        row = _select_output_message_row(conn_msg, table_name=table_name, local_id=int(new_local_id))
        if row is not None:
            my_rowid = _lookup_output_my_rowid(conn_msg, account_dir.name)
            out_res_db_path2 = account_dir / "message_resource.db"
            resource_conn: Optional[sqlite3.Connection] = None
            resource_chat_id: Optional[int] = None
            try:
                if out_res_db_path2.exists():
                    resource_conn = sqlite3.connect(str(out_res_db_path2))
                    resource_conn.row_factory = sqlite3.Row
                    resource_chat_id = _resource_lookup_chat_id(resource_conn, session_id)
            except Exception:
                if resource_conn is not None:
                    try:
                        resource_conn.close()
                    except Exception:
                        pass
                resource_conn = None
                resource_chat_id = None

            merged: list[dict[str, Any]] = []
            sender_usernames: list[str] = []
            quote_usernames: list[str] = []
            pat_usernames: set[str] = set()
            _append_full_messages_from_rows(
                merged=merged,
                sender_usernames=sender_usernames,
                quote_usernames=quote_usernames,
                pat_usernames=pat_usernames,
                rows=[row],
                db_path=msg_db_path_out,
                table_name=table_name,
                username=session_id,
                account_dir=account_dir,
                is_group=bool(session_id.endswith("@chatroom")),
                my_rowid=my_rowid,
                resource_conn=resource_conn,
                resource_chat_id=resource_chat_id,
            )
            _postprocess_full_messages(
                merged=merged,
                sender_usernames=sender_usernames,
                quote_usernames=quote_usernames,
                pat_usernames=pat_usernames,
                account_dir=account_dir,
                username=session_id,
                base_url=base_url,
                contact_db_path=account_dir / "contact.db",
                head_image_db_path=account_dir / "head_image.db",
            )
            if merged:
                updated_message = merged[0]
            if resource_conn is not None:
                try:
                    resource_conn.close()
                except Exception:
                    pass
        conn_msg.close()
    except Exception:
        updated_message = None

    resp: dict[str, Any] = {
        "status": "success",
        "account": account_dir.name,
        "session_id": session_id,
        "messageId": f"{db_stem}:{table_name}:{int(new_local_id)}",
    }
    if warnings:
        resp["warnings"] = warnings
    if updated_message is not None:
        resp["updated_message"] = updated_message
    return resp


@router.get("/api/chat/edits/sessions", summary="获取有修改记录的会话列表")
def list_chat_edited_sessions(request: Request, account: Optional[str] = None) -> dict[str, Any]:
    account_dir = _resolve_account_dir(account)
    base_url = str(request.base_url).rstrip("/")

    stats = chat_edit_store.list_sessions(account_dir.name)
    session_ids = [str(s.get("session_id") or "").strip() for s in stats if str(s.get("session_id") or "").strip()]
    contact_db_path = account_dir / "contact.db"
    contact_rows = _load_contact_rows(contact_db_path, session_ids)

    sessions: list[dict[str, Any]] = []
    for s in stats:
        uname = str(s.get("session_id") or "").strip()
        if not uname:
            continue
        row = contact_rows.get(uname)
        name = _pick_display_name(row, uname) if row is not None else uname
        avatar = base_url + _avatar_url_unified(account_dir=account_dir, username=uname)
        sessions.append(
            {
                "username": uname,
                "name": name,
                "avatar": avatar,
                "isGroup": bool(uname.endswith("@chatroom")),
                "editedCount": int(s.get("msg_count") or 0),
                "lastEditedAt": int(s.get("last_edited_at") or 0),
            }
        )

    return {
        "status": "success",
        "account": account_dir.name,
        "sessions": sessions,
    }


@router.get("/api/chat/edits/messages", summary="获取某会话下所有被修改过的消息（原/现对比）")
def list_chat_edited_messages(
    request: Request,
    username: str,
    account: Optional[str] = None,
) -> dict[str, Any]:
    if not username:
        raise HTTPException(status_code=400, detail="Missing username.")
    account_dir = _resolve_account_dir(account)
    base_url = str(request.base_url).rstrip("/")

    edits = chat_edit_store.list_messages(account_dir.name, username)
    if not edits:
        return {"status": "success", "account": account_dir.name, "username": username, "items": []}

    # Open resource DB once (optional).
    resource_conn: Optional[sqlite3.Connection] = None
    resource_chat_id: Optional[int] = None
    out_res_db_path = account_dir / "message_resource.db"
    try:
        if out_res_db_path.exists():
            resource_conn = sqlite3.connect(str(out_res_db_path))
            resource_conn.row_factory = sqlite3.Row
            resource_chat_id = _resource_lookup_chat_id(resource_conn, username)
    except Exception:
        if resource_conn is not None:
            try:
                resource_conn.close()
            except Exception:
                pass

        resource_conn = None
        resource_chat_id = None

    is_group = bool(username.endswith("@chatroom"))

    msg_conns: dict[str, sqlite3.Connection] = {}
    my_rowids: dict[str, Optional[int]] = {}

    merged_current: list[dict[str, Any]] = []
    sender_usernames_current: list[str] = []
    quote_usernames_current: list[str] = []
    pat_usernames_current: set[str] = set()

    merged_original: list[dict[str, Any]] = []
    sender_usernames_original: list[str] = []
    quote_usernames_original: list[str] = []
    pat_usernames_original: set[str] = set()

    current_raw_by_id: dict[str, dict[str, Any]] = {}
    original_raw_by_id: dict[str, Any] = {}

    try:
        for rec in edits:
            db_stem = str(rec.get("db") or "").strip()
            table_name = str(rec.get("table_name") or "").strip()
            try:
                local_id = int(rec.get("local_id") or 0)
            except Exception:
                local_id = 0
            if not db_stem or not table_name or local_id <= 0:
                continue

            message_id = str(rec.get("message_id") or "").strip() or f"{db_stem}:{table_name}:{int(local_id)}"

            conn_msg = msg_conns.get(db_stem)
            if conn_msg is None:
                db_path_out = account_dir / f"{db_stem}.db"
                if not db_path_out.exists():
                    continue
                conn_msg = sqlite3.connect(str(db_path_out))
                conn_msg.row_factory = sqlite3.Row
                conn_msg.text_factory = bytes
                msg_conns[db_stem] = conn_msg
                my_rowids[db_stem] = _lookup_output_my_rowid(conn_msg, account_dir.name)

            row_cur = _select_output_message_row(conn_msg, table_name=table_name, local_id=local_id)
            if row_cur is not None:
                _append_full_messages_from_rows(
                    merged=merged_current,
                    sender_usernames=sender_usernames_current,
                    quote_usernames=quote_usernames_current,
                    pat_usernames=pat_usernames_current,
                    rows=[row_cur],
                    db_path=account_dir / f"{db_stem}.db",
                    table_name=table_name,
                    username=username,
                    account_dir=account_dir,
                    is_group=is_group,
                    my_rowid=my_rowids.get(db_stem),
                    resource_conn=resource_conn,
                    resource_chat_id=resource_chat_id,
                )
                cur_raw: dict[str, Any] = {}
                for k in row_cur.keys():
                    cur_raw[str(k)] = _jsonify_db_value(str(k), row_cur[k])
                current_raw_by_id[message_id] = cur_raw

            # Original raw snapshot (for UI raw display)
            try:
                original_raw_by_id[message_id] = json.loads(str(rec.get("original_msg_json") or "") or "null")
            except Exception:
                original_raw_by_id[message_id] = None

            # Original row for rendering
            try:
                orig_row = chat_edit_store.loads_json_with_blobs(str(rec.get("original_msg_json") or "") or "")
            except Exception:
                orig_row = None
            if isinstance(orig_row, dict):
                try:
                    rsid = int(orig_row.get("real_sender_id") or 0)
                except Exception:
                    rsid = 0
                sender_username = _lookup_output_username_by_rowid(conn_msg, rsid) if rsid > 0 else ""
                orig_row["sender_username"] = sender_username
                orig_row.setdefault("packed_info_data", None)
                _append_full_messages_from_rows(
                    merged=merged_original,
                    sender_usernames=sender_usernames_original,
                    quote_usernames=quote_usernames_original,
                    pat_usernames=pat_usernames_original,
                    rows=[orig_row],
                    db_path=account_dir / f"{db_stem}.db",
                    table_name=table_name,
                    username=username,
                    account_dir=account_dir,
                    is_group=is_group,
                    my_rowid=my_rowids.get(db_stem),
                    resource_conn=resource_conn,
                    resource_chat_id=resource_chat_id,
                )

        if merged_current:
            _postprocess_full_messages(
                merged=merged_current,
                sender_usernames=sender_usernames_current,
                quote_usernames=quote_usernames_current,
                pat_usernames=pat_usernames_current,
                account_dir=account_dir,
                username=username,
                base_url=base_url,
                contact_db_path=account_dir / "contact.db",
                head_image_db_path=account_dir / "head_image.db",
            )
        if merged_original:
            _postprocess_full_messages(
                merged=merged_original,
                sender_usernames=sender_usernames_original,
                quote_usernames=quote_usernames_original,
                pat_usernames=pat_usernames_original,
                account_dir=account_dir,
                username=username,
                base_url=base_url,
                contact_db_path=account_dir / "contact.db",
                head_image_db_path=account_dir / "head_image.db",
            )

        current_by_id = {str(m.get("id") or ""): m for m in merged_current if str(m.get("id") or "").strip()}
        original_by_id = {str(m.get("id") or ""): m for m in merged_original if str(m.get("id") or "").strip()}

        items: list[dict[str, Any]] = []
        for rec in edits:
            mid = str(rec.get("message_id") or "").strip()
            if not mid:
                try:
                    mid = chat_edit_store.format_message_id(
                        rec.get("db") or "",
                        rec.get("table_name") or "",
                        int(rec.get("local_id") or 0),
                    )
                except Exception:
                    mid = ""
            if not mid:
                continue
            items.append(
                {
                    "messageId": mid,
                    "firstEditedAt": int(rec.get("first_edited_at") or 0),
                    "lastEditedAt": int(rec.get("last_edited_at") or 0),
                    "editCount": int(rec.get("edit_count") or 0),
                    "original": original_by_id.get(mid),
                    "current": current_by_id.get(mid),
                    "originalRaw": original_raw_by_id.get(mid),
                    "currentRaw": current_raw_by_id.get(mid),
                }
            )

        items.sort(key=lambda x: int(((x.get("current") or x.get("original") or {}) or {}).get("createTime") or 0))
        return {
            "status": "success",
            "account": account_dir.name,
            "username": username,
            "items": items,
        }
    finally:
        for c in msg_conns.values():
            try:
                c.close()
            except Exception:
                pass
        if resource_conn is not None:
            try:
                resource_conn.close()
            except Exception:
                pass


@router.get("/api/chat/edits/message_status", summary="某条消息是否被本工具修改过")
def get_chat_edit_status(*, account: Optional[str] = None, username: str, message_id: str) -> dict[str, Any]:
    if not username:
        raise HTTPException(status_code=400, detail="Missing username.")
    if not message_id:
        raise HTTPException(status_code=400, detail="Missing message_id.")
    account_dir = _resolve_account_dir(account)
    item = chat_edit_store.get_message_edit(account_dir.name, username, message_id)
    if not item:
        return {"modified": False}
    return {
        "modified": True,
        "firstEditedAt": int(item.get("first_edited_at") or 0),
        "lastEditedAt": int(item.get("last_edited_at") or 0),
        "editCount": int(item.get("edit_count") or 0),
    }


@router.post("/api/chat/messages/repair_sender", summary="修复某条消息的发送者（real_sender_id）")
async def repair_chat_message_sender(request: Request) -> dict[str, Any]:
    """Repair message sender for cases where an incorrect reset wrote wrong metadata.

    Currently this supports forcing the message to be treated as "sent by me" by setting
    `real_sender_id` to the account's Name2Id rowid, in both db_storage and output DB.
    """
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload.")

    account = str(payload.get("account") or "").strip() or None
    session_id = str(payload.get("session_id") or payload.get("username") or payload.get("sessionId") or "").strip()
    message_id = str(payload.get("message_id") or payload.get("messageId") or "").strip()
    mode = str(payload.get("mode") or "me").strip().lower()

    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id.")
    if not message_id:
        raise HTTPException(status_code=400, detail="Missing message_id.")
    if mode not in {"me"}:
        raise HTTPException(status_code=400, detail="Unsupported mode.")

    account_dir = _resolve_account_dir(account)
    try:
        db_stem, table_name_in, local_id = chat_edit_store.parse_message_id(message_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid message_id.")

    msg_db_path_out = account_dir / f"{db_stem}.db"
    if not msg_db_path_out.exists():
        raise HTTPException(status_code=404, detail="Message database not found.")

    msg_db_path_real, _res_db_path_real = _resolve_db_storage_message_paths(account_dir, db_stem)
    if not msg_db_path_real.exists():
        raise HTTPException(status_code=404, detail="Real message database not found in db_storage.")

    # Resolve output table name casing and the "my" rowid for this message DB.
    table_name_out = ""
    my_rowid_out: Optional[int] = None
    conn_probe: Optional[sqlite3.Connection] = None
    try:
        conn_probe = sqlite3.connect(str(msg_db_path_out), timeout=5)
        conn_probe.row_factory = sqlite3.Row
        table_name_out = _normalize_table_name_case(conn_probe, table_name_in) or ""
        if not table_name_out:
            raise HTTPException(status_code=404, detail="Message table not found.")

        r = conn_probe.execute(
            "SELECT rowid FROM Name2Id WHERE user_name = ? ORDER BY rowid ASC LIMIT 1",
            (account_dir.name,),
        ).fetchone()
        if r is not None:
            try:
                my_rowid_out = int(r[0])
            except Exception:
                my_rowid_out = None
    finally:
        if conn_probe is not None:
            try:
                conn_probe.close()
            except Exception:
                pass

    if my_rowid_out is None or my_rowid_out <= 0:
        raise HTTPException(status_code=404, detail="Name2Id row not found for account in output db.")

    with _realtime_sync_lock(account_dir.name, session_id):
        try:
            wcdb_conn = WCDB_REALTIME.ensure_connected(account_dir)
        except WCDBRealtimeError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Resolve "my" rowid from the live db_storage message DB.
        sql_my = (
            "SELECT rowid FROM Name2Id WHERE user_name = "
            + _sql_literal(account_dir.name)
            + " ORDER BY rowid ASC LIMIT 1"
        )
        with wcdb_conn.lock:
            rows = _wcdb_exec_query(wcdb_conn.handle, kind="message", path=str(msg_db_path_real), sql=sql_my)

        my_rowid_real = 0
        if rows and isinstance(rows[0], dict):
            for k, v in rows[0].items():
                if str(k or "").strip().lower() == "rowid":
                    try:
                        my_rowid_real = int(v or 0)
                    except Exception:
                        my_rowid_real = 0
                    break

        if my_rowid_real <= 0:
            raise HTTPException(status_code=404, detail="Name2Id row not found for account in real db_storage.")

        # 1) Update real db_storage (source of truth).
        try:
            sql_real = _build_wcdb_update_sql(
                table_name=table_name_in,
                updates={"real_sender_id": int(my_rowid_real)},
                where_local_id=int(local_id),
            )
            with wcdb_conn.lock:
                _wcdb_exec_query(wcdb_conn.handle, kind="message", path=str(msg_db_path_real), sql=sql_real)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to update real db_storage: {e}")

        # 2) Sync output decrypted DB so UI reflects the change immediately.
        try:
            conn_out = sqlite3.connect(str(msg_db_path_out), timeout=5)
            try:
                sql_out, params_out = _build_sqlite_update_sql(
                    table_name=table_name_out,
                    updates={"real_sender_id": int(my_rowid_out)},
                    where_local_id=int(local_id),
                )
                conn_out.execute(sql_out, params_out)
                conn_out.commit()
            finally:
                conn_out.close()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to update output db: {e}")

    return {
        "status": "success",
        "account": account_dir.name,
        "sessionId": session_id,
        "messageId": f"{db_stem}:{table_name_out or table_name_in}:{int(local_id)}",
        "mode": mode,
    }


@router.post("/api/chat/messages/flip_direction", summary="反转某条消息在微信客户端的左右位置（packed_info_data）")
async def flip_chat_message_direction(request: Request) -> dict[str, Any]:
    """Flip a message's bubble side in the *WeChat client* by swapping from/to in packed_info_data.

    Note: this intentionally edits `packed_info_data` (a protobuf-like BLOB). It is risky.
    A snapshot is recorded so users can undo via `/api/chat/edits/reset_message`.
    """

    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload.")

    account = str(payload.get("account") or "").strip() or None
    session_id = str(payload.get("session_id") or payload.get("username") or payload.get("sessionId") or "").strip()
    message_id_in = str(payload.get("message_id") or payload.get("messageId") or "").strip()

    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id.")
    if not message_id_in:
        raise HTTPException(status_code=400, detail="Missing message_id.")

    account_dir = _resolve_account_dir(account)
    try:
        db_stem, table_name_in, local_id = chat_edit_store.parse_message_id(message_id_in)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid message_id.")

    msg_db_path_out = account_dir / f"{db_stem}.db"
    if not msg_db_path_out.exists():
        raise HTTPException(status_code=404, detail="Message database not found.")

    msg_db_path_real, _res_db_path_real = _resolve_db_storage_message_paths(account_dir, db_stem)
    if not msg_db_path_real.exists():
        raise HTTPException(status_code=404, detail="Real message database not found in db_storage.")

    def _coerce_packed_bytes(value: Any) -> Optional[bytes]:
        if value is None:
            return None
        if isinstance(value, memoryview):
            value = value.tobytes()
        if isinstance(value, bytearray):
            value = bytes(value)
        if isinstance(value, bytes):
            # If a past bug stored the blob as TEXT hex, sqlite may return ASCII bytes here.
            try:
                s = value.decode("ascii").strip()
            except Exception:
                return value
            if not s:
                return b""
            b = _hex_to_bytes(s)
            if b is not None:
                return b
            if (len(s) % 2 == 0) and (_HEX_RE.fullmatch(s) is not None):
                try:
                    return bytes.fromhex(s)
                except Exception:
                    return value
            return value
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return b""
            b = _hex_to_bytes(s)
            if b is not None:
                return b
            if (len(s) % 2 == 0) and (_HEX_RE.fullmatch(s) is not None):
                try:
                    return bytes.fromhex(s)
                except Exception:
                    return None
            return s.encode("utf-8", errors="replace")
        return None

    # Resolve output table name casing and read packed_info_data bytes from output DB.
    table_name_out = ""
    packed_before: Optional[bytes] = None
    conn_out_probe: Optional[sqlite3.Connection] = None
    try:
        conn_out_probe = sqlite3.connect(str(msg_db_path_out), timeout=5)
        conn_out_probe.row_factory = sqlite3.Row
        conn_out_probe.text_factory = bytes
        table_name_out = _normalize_table_name_case(conn_out_probe, table_name_in) or ""
        if not table_name_out:
            raise HTTPException(status_code=404, detail="Message table not found.")
        cols = _table_info_columns(conn_out_probe, table_name_out)
        if not cols or ("packed_info_data" not in cols):
            raise HTTPException(status_code=400, detail="packed_info_data column not found.")
        quoted = _quote_ident(table_name_out)
        row = conn_out_probe.execute(
            f"SELECT packed_info_data FROM {quoted} WHERE local_id = ? LIMIT 1",
            (int(local_id),),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Message not found in output database.")
        packed_before = _coerce_packed_bytes(row["packed_info_data"])
    finally:
        if conn_out_probe is not None:
            try:
                conn_out_probe.close()
            except Exception:
                pass

    if not packed_before:
        raise HTTPException(status_code=400, detail="packed_info_data is empty; cannot flip direction.")

    try:
        packed_after, old_from_id, old_to_id = _swap_packed_info_from_to(packed_before)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot flip packed_info_data: {e}")

    # Apply to output DB first, then real db_storage. Record snapshot so users can undo.
    message_id = f"{db_stem}:{table_name_out or table_name_in}:{int(local_id)}"
    created_record = False

    with _realtime_sync_lock(account_dir.name, session_id):
        try:
            wcdb_conn = WCDB_REALTIME.ensure_connected(account_dir)
        except WCDBRealtimeError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Snapshot original row from real db_storage (only once).
        existing_record = chat_edit_store.get_message_edit(account_dir.name, session_id, message_id)
        if existing_record is None:
            try:
                select_sql = f"SELECT * FROM {_quote_ident(table_name_in)} WHERE local_id = {int(local_id)} LIMIT 1"
                with wcdb_conn.lock:
                    rows = _wcdb_exec_query(
                        wcdb_conn.handle,
                        kind="message",
                        path=str(msg_db_path_real),
                        sql=select_sql,
                    )
                if not rows or not isinstance(rows[0], dict):
                    raise HTTPException(status_code=404, detail="Message not found in real db_storage.")
                original_row = rows[0]

                chat_edit_store.upsert_original_once(
                    account=account_dir.name,
                    session_id=session_id,
                    db=db_stem,
                    table_name=table_name_out or table_name_in,
                    local_id=int(local_id),
                    original_msg=original_row,
                    original_resource=None,
                    now_ms=int(time.time() * 1000),
                )
                created_record = True
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to write edit snapshot: {e}")

        # 1) Update output decrypted DB (so UI can show it in raw view).
        try:
            conn_out = sqlite3.connect(str(msg_db_path_out), timeout=5)
            try:
                sql_out, params_out = _build_sqlite_update_sql(
                    table_name=table_name_out,
                    updates={"packed_info_data": packed_after},
                    where_local_id=int(local_id),
                )
                cur = conn_out.execute(sql_out, params_out)
                conn_out.commit()
                if int(getattr(cur, "rowcount", 0) or 0) <= 0:
                    raise HTTPException(status_code=404, detail="Message not found in output database.")
            finally:
                conn_out.close()
        except HTTPException:
            if created_record:
                try:
                    chat_edit_store.delete_message_edit(account_dir.name, session_id, message_id)
                except Exception:
                    pass
            raise
        except Exception as e:
            if created_record:
                try:
                    chat_edit_store.delete_message_edit(account_dir.name, session_id, message_id)
                except Exception:
                    pass
            raise HTTPException(status_code=500, detail=f"Failed to update output database: {e}")

        # 2) Update real db_storage (source of truth). Rollback output on failure.
        try:
            sql_real = _build_wcdb_update_sql(
                table_name=table_name_in,
                updates={"packed_info_data": packed_after},
                where_local_id=int(local_id),
            )
            with wcdb_conn.lock:
                _wcdb_exec_query(wcdb_conn.handle, kind="message", path=str(msg_db_path_real), sql=sql_real)
        except Exception as e:
            # Roll back output changes.
            try:
                conn_rb = sqlite3.connect(str(msg_db_path_out), timeout=5)
                try:
                    sql_rb, params_rb = _build_sqlite_update_sql(
                        table_name=table_name_out,
                        updates={"packed_info_data": packed_before},
                        where_local_id=int(local_id),
                    )
                    conn_rb.execute(sql_rb, params_rb)
                    conn_rb.commit()
                finally:
                    conn_rb.close()
            except Exception:
                pass

            if created_record:
                try:
                    chat_edit_store.delete_message_edit(account_dir.name, session_id, message_id)
                except Exception:
                    pass
            raise HTTPException(status_code=500, detail=f"Failed to update real db_storage: {e}")

        # Track which columns were modified so reset restores only those.
        try:
            chat_edit_store.merge_edited_columns(
                account=account_dir.name,
                session_id=session_id,
                db=db_stem,
                table_name=table_name_out or table_name_in,
                local_id=int(local_id),
                columns=["packed_info_data"],
            )
        except Exception:
            pass

        # Bump edit metadata for already-tracked messages.
        if existing_record is not None:
            try:
                chat_edit_store.upsert_original_once(
                    account=account_dir.name,
                    session_id=session_id,
                    db=db_stem,
                    table_name=table_name_out or table_name_in,
                    local_id=int(local_id),
                    original_msg={},
                    original_resource=None,
                    now_ms=int(time.time() * 1000),
                )
            except Exception:
                pass

    return {
        "status": "success",
        "account": account_dir.name,
        "sessionId": session_id,
        "messageId": message_id,
        "before": {
            "packed_info_data": _bytes_to_hex(packed_before),
            "fromId": int(old_from_id),
            "toId": int(old_to_id),
        },
        "after": {
            "packed_info_data": _bytes_to_hex(packed_after),
            "fromId": int(old_to_id),
            "toId": int(old_from_id),
        },
    }


def _restore_message_from_snapshot(
    *,
    account_dir: Path,
    session_id: str,
    message_id: str,
    record: dict[str, Any],
    wcdb_conn,
) -> None:
    db_stem, table_name, local_id_current = chat_edit_store.parse_message_id(message_id)
    msg_db_path_out = account_dir / f"{db_stem}.db"
    if not msg_db_path_out.exists():
        raise HTTPException(status_code=404, detail="Message database not found.")

    msg_db_path_real, res_db_path_real = _resolve_db_storage_message_paths(account_dir, db_stem)
    if not msg_db_path_real.exists():
        raise HTTPException(status_code=404, detail="Real message database not found in db_storage.")

    original_msg = chat_edit_store.loads_json_with_blobs(str(record.get("original_msg_json") or "") or "")
    if not isinstance(original_msg, dict):
        raise HTTPException(status_code=500, detail="Invalid original snapshot.")

    original_resource = None
    if str(record.get("original_resource_json") or ""):
        try:
            original_resource = chat_edit_store.loads_json_with_blobs(str(record.get("original_resource_json") or "") or "")
        except Exception:
            original_resource = None

    edited_cols: set[str] = set()
    try:
        raw = str(record.get("edited_cols_json") or "").strip()
        if raw:
            v = json.loads(raw)
            if isinstance(v, list):
                edited_cols = {str(x or "").strip().lower() for x in v if str(x or "").strip()}
    except Exception:
        edited_cols = set()

    # Backward compatible default: older records didn't track edited columns.
    if not edited_cols:
        edited_cols = {"message_content", "compress_content"}

    # Editing content implicitly clears compress_content unless explicitly provided.
    if "message_content" in edited_cols:
        edited_cols.add("compress_content")

    orig_key_map = {str(k or "").strip().lower(): str(k) for k in original_msg.keys()}

    # Read current create_time from real db to call wcdb_update_message reliably.
    cur_create_time = 0
    try:
        sql_ct = f"SELECT create_time FROM {_quote_ident(table_name)} WHERE local_id = {int(local_id_current)} LIMIT 1"
        with wcdb_conn.lock:
            rows = _wcdb_exec_query(wcdb_conn.handle, kind="message", path=str(msg_db_path_real), sql=sql_ct)
        if rows and isinstance(rows[0], dict):
            cur_create_time = int(rows[0].get("create_time") or 0)
    except Exception:
        cur_create_time = 0
    if cur_create_time <= 0:
        raise HTTPException(status_code=404, detail="Message not found in real db_storage.")

    # Restore message_content via wcdb_update_message (best-effort).
    # Some builds store message_content as an encrypted/compressed BLOB; WCDB exec_query may return it as bare hex.
    # In that case, don't call update_message with the hex string; restoring the raw column bytes below is safer.
    if "message_content" in edited_cols and "message_content" in orig_key_map:
        try:
            content = original_msg.get(orig_key_map["message_content"])
            if isinstance(content, str):
                s = content.strip()
                if s and (len(s) % 2 == 0) and (_HEX_RE.fullmatch(s) is not None):
                    s_lower = s.lower()
                    if (len(s) >= 64) or (s_lower.startswith("28b52ffd") and len(s) >= 16):
                        content = None
            if isinstance(content, (bytes, bytearray, memoryview)):
                try:
                    content = bytes(content).decode("utf-8", errors="replace")
                except Exception:
                    content = ""
            if content is not None:
                _wcdb_update_message(
                    wcdb_conn.handle,
                    session_id=session_id,
                    local_id=int(local_id_current),
                    create_time=int(cur_create_time),
                    new_content=str(content or ""),
                )
        except Exception:
            pass

    # Restore only columns that were actually edited by the tool.
    try:
        restore_updates: dict[str, Any] = {}
        for col_lc in sorted(edited_cols):
            k = orig_key_map.get(col_lc)
            if not k:
                continue
            restore_updates[k] = _normalize_edit_value(k, original_msg.get(k), from_snapshot=True)

        if restore_updates:
            sql_real = _build_wcdb_update_sql(
                table_name=table_name,
                updates=restore_updates,
                where_local_id=int(local_id_current),
            )
            with wcdb_conn.lock:
                _wcdb_exec_query(wcdb_conn.handle, kind="message", path=str(msg_db_path_real), sql=sql_real)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restore real db_storage: {e}")

    # Restore output decrypted Msg_*.
    try:
        conn_out = sqlite3.connect(str(msg_db_path_out), timeout=5)
        try:
            tnorm = _normalize_table_name_case(conn_out, table_name)
            if not tnorm:
                raise HTTPException(status_code=404, detail="Message table not found.")
            cols = _table_info_columns(conn_out, tnorm)
            col_map = {str(c or "").strip().lower(): str(c) for c in cols if str(c or "").strip()}
            restore_out: dict[str, Any] = {}
            for col_lc in sorted(edited_cols):
                col = col_map.get(col_lc)
                k = orig_key_map.get(col_lc)
                if not col or not k:
                    continue
                restore_out[col] = _normalize_edit_value(col, original_msg.get(k), from_snapshot=True)

            if restore_out:
                sql_out, params = _build_sqlite_update_sql(
                    table_name=tnorm,
                    updates=restore_out,
                    where_local_id=int(local_id_current),
                )
                conn_out.execute(sql_out, params)
                conn_out.commit()
        finally:
            conn_out.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restore output database: {e}")

    # Restore message_resource key fields (best-effort, by message_id).
    need_restore_resource = any(
        k in edited_cols for k in {"local_type", "create_time", "server_id", "origin_source", "local_id"}
    )
    if need_restore_resource and isinstance(original_resource, dict):
        try:
            res_message_id = int(original_resource.get("message_id") or 0)
        except Exception:
            res_message_id = 0
        if res_message_id > 0:
            restore_res: dict[str, Any] = {}
            msg_to_res = {
                "local_type": "message_local_type",
                "create_time": "message_create_time",
                "server_id": "message_svr_id",
                "origin_source": "message_origin_source",
                "local_id": "message_local_id",
            }
            for msg_col, res_col in msg_to_res.items():
                if msg_col not in edited_cols:
                    continue
                if res_col in original_resource:
                    restore_res[res_col] = _normalize_edit_value(res_col, original_resource.get(res_col), from_snapshot=True)
            if restore_res:
                try:
                    parts = [f"{_quote_ident(k)} = {_sql_literal(v)}" for k, v in restore_res.items()]
                    sql_res_real = (
                        "UPDATE MessageResourceInfo SET " + ", ".join(parts) + f" WHERE message_id = {int(res_message_id)}"
                    )
                    if res_db_path_real.exists():
                        with wcdb_conn.lock:
                            _wcdb_exec_query(
                                wcdb_conn.handle,
                                kind="message",
                                path=str(res_db_path_real),
                                sql=sql_res_real,
                            )
                except Exception:
                    pass

                try:
                    out_res_db_path = account_dir / "message_resource.db"
                    if out_res_db_path.exists():
                        conn_res = sqlite3.connect(str(out_res_db_path), timeout=5)
                        try:
                            set_cols = ", ".join([f"{_quote_ident(k)} = ?" for k in restore_res.keys()])
                            params = list(restore_res.values()) + [int(res_message_id)]
                            conn_res.execute(f"UPDATE MessageResourceInfo SET {set_cols} WHERE message_id = ?", params)
                            conn_res.commit()
                        finally:
                            conn_res.close()
                except Exception:
                    pass


@router.post("/api/chat/edits/reset_message", summary="恢复某条消息到首次快照，并删除修改记录")
async def reset_chat_edited_message(request: Request) -> dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload.")

    account = str(payload.get("account") or "").strip() or None
    session_id = str(payload.get("session_id") or payload.get("username") or payload.get("sessionId") or "").strip()
    message_id = str(payload.get("message_id") or payload.get("messageId") or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id.")
    if not message_id:
        raise HTTPException(status_code=400, detail="Missing message_id.")

    account_dir = _resolve_account_dir(account)
    record = chat_edit_store.get_message_edit(account_dir.name, session_id, message_id)
    if not record:
        raise HTTPException(status_code=404, detail="Edit record not found.")

    with _realtime_sync_lock(account_dir.name, session_id):
        try:
            wcdb_conn = WCDB_REALTIME.ensure_connected(account_dir)
        except WCDBRealtimeError as e:
            raise HTTPException(status_code=400, detail=str(e))

        _restore_message_from_snapshot(
            account_dir=account_dir,
            session_id=session_id,
            message_id=message_id,
            record=record,
            wcdb_conn=wcdb_conn,
        )

        try:
            chat_edit_store.delete_message_edit(account_dir.name, session_id, message_id)
        except Exception:
            pass

    return {"status": "success"}


@router.post("/api/chat/edits/reset_session", summary="一键恢复某会话下全部修改记录")
async def reset_chat_edited_session(request: Request) -> dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload.")

    account = str(payload.get("account") or "").strip() or None
    session_id = str(payload.get("session_id") or payload.get("username") or payload.get("sessionId") or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id.")

    account_dir = _resolve_account_dir(account)
    records = chat_edit_store.list_messages(account_dir.name, session_id)
    if not records:
        return {"status": "success", "restored": 0, "failed": 0, "failures": []}

    restored = 0
    failures: list[dict[str, Any]] = []

    with _realtime_sync_lock(account_dir.name, session_id):
        try:
            wcdb_conn = WCDB_REALTIME.ensure_connected(account_dir)
        except WCDBRealtimeError as e:
            raise HTTPException(status_code=400, detail=str(e))

        for rec in records:
            mid = str(rec.get("message_id") or "").strip()
            if not mid:
                try:
                    mid = chat_edit_store.format_message_id(
                        rec.get("db") or "",
                        rec.get("table_name") or "",
                        int(rec.get("local_id") or 0),
                    )
                except Exception:
                    mid = ""
            if not mid:
                continue
            try:
                _restore_message_from_snapshot(
                    account_dir=account_dir,
                    session_id=session_id,
                    message_id=mid,
                    record=rec,
                    wcdb_conn=wcdb_conn,
                )
                try:
                    chat_edit_store.delete_message_edit(account_dir.name, session_id, mid)
                except Exception:
                    pass
                restored += 1
            except Exception as e:
                failures.append({"messageId": mid, "error": str(e)})

    return {"status": "success", "restored": int(restored), "failed": int(len(failures)), "failures": failures}
