import os
import re
import sqlite3
import asyncio
import json
import time
import threading
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
    _load_usernames_by_display_names,
    _load_latest_message_previews,
    _lookup_resource_md5,
    _normalize_xml_url,
    _parse_app_message,
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
from ..media_helpers import _try_find_decrypted_resource
from ..path_fix import PathFixRoute
from ..session_last_message import (
    build_session_last_message_table,
    get_session_last_message_status,
    load_session_last_messages,
)
from ..wcdb_realtime import (
    WCDBRealtimeError,
    WCDB_REALTIME,
    get_avatar_urls as _wcdb_get_avatar_urls,
    get_display_names as _wcdb_get_display_names,
    get_messages as _wcdb_get_messages,
    get_sessions as _wcdb_get_sessions,
)

logger = get_logger(__name__)

_DEBUG_SESSIONS = os.environ.get("WECHAT_TOOL_DEBUG_SESSIONS", "0") == "1"

router = APIRouter(route_class=PathFixRoute)

_REALTIME_SYNC_MU = threading.Lock()
_REALTIME_SYNC_LOCKS: dict[tuple[str, str], threading.Lock] = {}
_REALTIME_SYNC_ALL_LOCKS: dict[str, threading.Lock] = {}


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
        "last_msg_type",
        "last_msg_sub_type",
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
            if c in {"unread_count", "is_hidden", "last_timestamp", "sort_timestamp", "last_msg_type", "last_msg_sub_type"}:
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
                "last_msg_type": item.get("last_msg_type", item.get("lastMsgType", 0)),
                "last_msg_sub_type": item.get("last_msg_sub_type", item.get("lastMsgSubType", 0)),
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

        if is_group and (raw_text.startswith("<") or raw_text.startswith('"<')):
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
            if "revokemsg" in raw_text:
                content_text = "撤回了一条消息"
            else:
                content_text = re.sub(r"</?[_a-zA-Z0-9]+[^>]*>", "", raw_text)
                content_text = re.sub(r"\s+", " ", content_text).strip() or "[系统消息]"
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
    # 后处理：关联转账消息的最终状态
    # 策略：优先使用 transferId 精确匹配，回退到金额+时间窗口匹配
    # paysubtype 含义：1=不明确 3=已收款 4=对方退回给你 8=发起转账 9=被对方退回 10=已过期

    # 收集已退还和已收款的转账ID和金额
    returned_transfer_ids: set[str] = set()  # 退还状态的 transferId
    received_transfer_ids: set[str] = set()  # 已收款状态的 transferId
    returned_amounts_with_time: list[tuple[str, int]] = []  # (金额, 时间戳) 用于退还回退匹配
    received_amounts_with_time: list[tuple[str, int]] = []  # (金额, 时间戳) 用于收款回退匹配

    for m in merged:
        if m.get("renderType") == "transfer":
            pst = str(m.get("paySubType") or "")
            tid = str(m.get("transferId") or "").strip()
            amt = str(m.get("amount") or "")
            ts = int(m.get("createTime") or 0)

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

    # 更新原始转账消息的状态
    for m in merged:
        if m.get("renderType") == "transfer":
            pst = str(m.get("paySubType") or "")
            # 只更新未确定状态的原始转账消息（paysubtype=1 或 8）
            if pst in ("1", "8"):
                tid = str(m.get("transferId") or "").strip()
                amt = str(m.get("amount") or "")
                ts = int(m.get("createTime") or 0)

                # 优先检查退还状态（退还优先于收款）
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
                    # 根据 isSent 判断：发起方显示"已收款"，收款方显示"已被接收"
                    is_sent = m.get("isSent", False)
                    m["transferStatus"] = "已收款" if is_sent else "已被接收"

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
        row = sender_contact_rows.get(su)
        display_name = _pick_display_name(row, su)
        if display_name == su:
            wd = str(wcdb_display_names.get(su) or "").strip()
            if wd and wd != su:
                display_name = wd
        m["senderDisplayName"] = display_name
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

    filtered: list[sqlite3.Row] = []
    usernames: list[str] = []
    for r in rows:
        username = r["username"] or ""
        if not username:
            continue
        if not include_hidden and int(r["is_hidden"] or 0) == 1:
            continue
        if not _should_keep_session(username, include_official=include_official):
            continue
        filtered.append(r)
        usernames.append(username)
        if len(filtered) >= int(limit):
            break

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
        for u in usernames:
            if not u:
                continue
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
            wcdb_conn = rt_conn or WCDB_REALTIME.ensure_connected(account_dir)
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

    sessions: list[dict[str, Any]] = []
    for r in filtered:
        username = r["username"]
        c_row = contact_rows.get(username)

        display_name = _pick_display_name(c_row, username)
        if display_name == username:
            wd = str(wcdb_display_names.get(username) or "").strip()
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

                if is_group and (raw_text.startswith("<") or raw_text.startswith('"<')):
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
                    if "revokemsg" in raw_text:
                        content_text = "撤回了一条消息"
                    else:
                        import re

                        content_text = re.sub(r"</?[_a-zA-Z0-9]+[^>]*>", "", raw_text)
                        content_text = re.sub(r"\s+", " ", content_text).strip() or "[系统消息]"
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
                        import re

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
                        import re

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

                if is_group and (raw_text.startswith("<") or raw_text.startswith('"<')):
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
                    if "revokemsg" in raw_text:
                        content_text = "撤回了一条消息"
                    else:
                        import re

                        content_text = re.sub(r"</?[_a-zA-Z0-9]+[^>]*>", "", raw_text)
                        content_text = re.sub(r"\s+", " ", content_text).strip() or "[系统消息]"
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
                        import re

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
                        import re

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

    # 后处理：关联转账消息的最终状态
    # 策略：优先使用 transferId 精确匹配，回退到金额+时间窗口匹配
    # paysubtype 含义：1=不明确 3=已收款 4=对方退回给你 8=发起转账 9=被对方退回 10=已过期

    # 收集已退还和已收款的转账ID和金额
    returned_transfer_ids: set[str] = set()  # 退还状态的 transferId
    received_transfer_ids: set[str] = set()  # 已收款状态的 transferId
    returned_amounts_with_time: list[tuple[str, int]] = []  # (金额, 时间戳) 用于退还回退匹配
    received_amounts_with_time: list[tuple[str, int]] = []  # (金额, 时间戳) 用于收款回退匹配

    for m in merged:
        if m.get("renderType") == "transfer":
            pst = str(m.get("paySubType") or "")
            tid = str(m.get("transferId") or "").strip()
            amt = str(m.get("amount") or "")
            ts = int(m.get("createTime") or 0)

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

    # 更新原始转账消息的状态
    for m in merged:
        if m.get("renderType") == "transfer":
            pst = str(m.get("paySubType") or "")
            # 只更新未确定状态的原始转账消息（paysubtype=1 或 8）
            if pst in ("1", "8"):
                tid = str(m.get("transferId") or "").strip()
                amt = str(m.get("amount") or "")
                ts = int(m.get("createTime") or 0)

                # 优先检查退还状态（退还优先于收款）
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
                    # 根据 isSent 判断：发起方显示"已收款"，收款方显示"已被接收"
                    is_sent = m.get("isSent", False)
                    m["transferStatus"] = "已收款" if is_sent else "已被接收"

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
        dict.fromkeys(
            [u for u in (sender_usernames + list(pat_usernames) + quote_usernames + from_usernames) if u]
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
        row = sender_contact_rows.get(su)
        display_name = _pick_display_name(row, su)
        if display_name == su:
            wd = str(wcdb_display_names.get(su) or "").strip()
            if wd and wd != su:
                display_name = wd
        m["senderDisplayName"] = display_name
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
                            import re

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

        for h in hits:
            su = str(h.get("senderUsername") or "").strip()
            h["conversationName"] = conv_name
            h["conversationAvatar"] = conv_avatar
            if su:
                row = contact_rows.get(su)
                display_name = _pick_display_name(row, su) if row is not None else (conv_name if su == username else su)
                if display_name == su:
                    wd = str(wcdb_display_names.get(su) or "").strip()
                    if wd and wd != su:
                        display_name = wd
                h["senderDisplayName"] = display_name
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
                row = contact_rows.get(su)
                display_name = _pick_display_name(row, su) if row is not None else (conv_name if su == cu else su)
                if display_name == su:
                    wd = str(wcdb_display_names.get(su) or "").strip()
                    if wd and wd != su:
                        display_name = wd
                h["senderDisplayName"] = display_name
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

        for h in page:
            su = str(h.get("senderUsername") or "").strip()
            h["conversationName"] = conv_name
            if su:
                row = contact_rows.get(su)
                h["senderDisplayName"] = _pick_display_name(row, su) if row is not None else (conv_name if su == username else su)

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

    for h in page:
        cu = str(h.get("username") or "").strip()
        su = str(h.get("senderUsername") or "").strip()
        crow = contact_rows.get(cu)
        conv_name = _pick_display_name(crow, cu) if cu else ""
        h["conversationName"] = conv_name or cu
        if su:
            row = contact_rows.get(su)
            h["senderDisplayName"] = _pick_display_name(row, su) if row is not None else (conv_name if su == cu else su)

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
    anchor_db_stem, anchor_table_name, anchor_local_id_str = parts
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

    target_db: Optional[Path] = None
    for p in db_paths:
        if p.stem == anchor_db_stem:
            target_db = p
            break
    if target_db is None:
        raise HTTPException(status_code=404, detail="Anchor database not found.")

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

    conn = sqlite3.connect(str(target_db))
    conn.row_factory = sqlite3.Row
    try:
        table_name = str(anchor_table_name).strip()
        if not table_name:
            raise HTTPException(status_code=404, detail="Anchor table not found.")

        # Normalize table name casing if needed
        try:
            trows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            lower_to_actual = {str(x[0]).lower(): str(x[0]) for x in trows if x and x[0]}
            table_name = lower_to_actual.get(table_name.lower(), table_name)
        except Exception:
            pass

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
        sql_anchor_with_join = (
            "SELECT "
            "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
            "m.message_content, m.compress_content, n.user_name AS sender_username "
            f"FROM {quoted_table} m "
            "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
            "WHERE m.local_id = ? "
            "LIMIT 1"
        )
        sql_anchor_no_join = (
            "SELECT "
            "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
            "m.message_content, m.compress_content, '' AS sender_username "
            f"FROM {quoted_table} m "
            "WHERE m.local_id = ? "
            "LIMIT 1"
        )

        conn.text_factory = bytes

        try:
            anchor_row = conn.execute(sql_anchor_with_join, (anchor_local_id,)).fetchone()
        except Exception:
            anchor_row = conn.execute(sql_anchor_no_join, (anchor_local_id,)).fetchone()

        if anchor_row is None:
            raise HTTPException(status_code=404, detail="Anchor message not found.")

        anchor_ct = int(anchor_row["create_time"] or 0)
        anchor_ss = int(anchor_row["sort_seq"] or 0) if anchor_row["sort_seq"] is not None else 0

        where_before = (
            "WHERE ("
            "m.create_time < ? "
            "OR (m.create_time = ? AND COALESCE(m.sort_seq, 0) < ?) "
            "OR (m.create_time = ? AND COALESCE(m.sort_seq, 0) = ? AND m.local_id <= ?)"
            ")"
        )
        where_after = (
            "WHERE ("
            "m.create_time > ? "
            "OR (m.create_time = ? AND COALESCE(m.sort_seq, 0) > ?) "
            "OR (m.create_time = ? AND COALESCE(m.sort_seq, 0) = ? AND m.local_id >= ?)"
            ")"
        )

        sql_before_with_join = (
            "SELECT "
            "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
            "m.message_content, m.compress_content, n.user_name AS sender_username "
            f"FROM {quoted_table} m "
            "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
            f"{where_before} "
            "ORDER BY m.create_time DESC, COALESCE(m.sort_seq, 0) DESC, m.local_id DESC "
            "LIMIT ?"
        )
        sql_before_no_join = (
            "SELECT "
            "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
            "m.message_content, m.compress_content, '' AS sender_username "
            f"FROM {quoted_table} m "
            f"{where_before} "
            "ORDER BY m.create_time DESC, COALESCE(m.sort_seq, 0) DESC, m.local_id DESC "
            "LIMIT ?"
        )

        sql_after_with_join = (
            "SELECT "
            "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
            "m.message_content, m.compress_content, n.user_name AS sender_username "
            f"FROM {quoted_table} m "
            "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
            f"{where_after} "
            "ORDER BY m.create_time ASC, COALESCE(m.sort_seq, 0) ASC, m.local_id ASC "
            "LIMIT ?"
        )
        sql_after_no_join = (
            "SELECT "
            "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
            "m.message_content, m.compress_content, '' AS sender_username "
            f"FROM {quoted_table} m "
            f"{where_after} "
            "ORDER BY m.create_time ASC, COALESCE(m.sort_seq, 0) ASC, m.local_id ASC "
            "LIMIT ?"
        )

        params_before = (anchor_ct, anchor_ct, anchor_ss, anchor_ct, anchor_ss, anchor_local_id, int(before) + 1)
        params_after = (anchor_ct, anchor_ct, anchor_ss, anchor_ct, anchor_ss, anchor_local_id, int(after) + 1)

        try:
            before_rows = conn.execute(sql_before_with_join, params_before).fetchall()
        except Exception:
            before_rows = conn.execute(sql_before_no_join, params_before).fetchall()

        try:
            after_rows = conn.execute(sql_after_with_join, params_after).fetchall()
        except Exception:
            after_rows = conn.execute(sql_after_no_join, params_after).fetchall()

        seen_ids: set[str] = set()
        combined: list[sqlite3.Row] = []
        for rr in list(before_rows) + list(after_rows):
            lid = int(rr["local_id"] or 0)
            mid = f"{target_db.stem}:{table_name}:{lid}"
            if mid in seen_ids:
                continue
            seen_ids.add(mid)
            combined.append(rr)

        merged: list[dict[str, Any]] = []
        sender_usernames: list[str] = []
        quote_usernames: list[str] = []
        pat_usernames: set[str] = set()
        is_group = bool(username.endswith("@chatroom"))

        _append_full_messages_from_rows(
            merged=merged,
            sender_usernames=sender_usernames,
            quote_usernames=quote_usernames,
            pat_usernames=pat_usernames,
            rows=combined,
            db_path=target_db,
            table_name=table_name,
            username=username,
            account_dir=account_dir,
            is_group=is_group,
            my_rowid=my_rowid,
            resource_conn=resource_conn,
            resource_chat_id=resource_chat_id,
        )

        return_messages = merged
    finally:
        conn.close()
        if resource_conn is not None:
            try:
                resource_conn.close()
            except Exception:
                pass

    _postprocess_full_messages(
        merged=return_messages,
        sender_usernames=sender_usernames,
        quote_usernames=quote_usernames,
        pat_usernames=pat_usernames,
        account_dir=account_dir,
        username=username,
        base_url=base_url,
        contact_db_path=contact_db_path,
        head_image_db_path=head_image_db_path,
    )

    def sort_key(m: dict[str, Any]) -> tuple[int, int, int]:
        sseq = int(m.get("sortSeq") or 0)
        cts = int(m.get("createTime") or 0)
        lid = int(m.get("localId") or 0)
        return (cts, sseq, lid)

    return_messages.sort(key=sort_key, reverse=False)
    anchor_index = -1
    for i, m in enumerate(return_messages):
        if str(m.get("id") or "") == str(anchor_id):
            anchor_index = i
            break

    return {
        "status": "success",
        "account": account_dir.name,
        "username": username,
        "anchorId": anchor_id,
        "anchorIndex": anchor_index,
        "messages": return_messages,
    }
