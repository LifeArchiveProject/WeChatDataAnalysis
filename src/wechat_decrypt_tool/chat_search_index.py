import os
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

from .chat_helpers import (
    _decode_sqlite_text,
    _quote_ident,
    _resolve_msg_table_name_by_map,
    _row_to_search_hit,
    _should_keep_session,
    _to_char_token_text,
    _iter_message_db_paths,
)
from .logging_config import get_logger

logger = get_logger(__name__)

_SCHEMA_VERSION = 4
_INDEX_DB_NAME = "chat_search_index.db"
_INDEX_DB_TMP_NAME = "chat_search_index.tmp.db"
_LEGACY_INDEX_DB_NAME = "message_fts.db"

_BUILD_LOCK = threading.Lock()
_BUILD_STATE: dict[str, dict[str, Any]] = {}

_DEFAULT_INSERT_BATCH_SIZE = 5000
_COMMIT_EVERY_MESSAGES = 100000


def _env_int(name: str, default: int, *, min_value: int, max_value: int) -> int:
    raw = os.environ.get(name)
    try:
        value = int(str(raw or "").strip() or default)
    except Exception:
        value = int(default)
    return max(int(min_value), min(int(max_value), int(value)))


def _insert_batch_size() -> int:
    return _env_int(
        "WECHAT_CHAT_SEARCH_INDEX_INSERT_BATCH",
        _DEFAULT_INSERT_BATCH_SIZE,
        min_value=500,
        max_value=50000,
    )


def _normalize_index_source(value: Optional[str], *, default: str = "decrypted") -> str:
    v = str(value or "").strip().lower()
    if not v:
        v = str(default or "decrypted").strip().lower()
    # 搜索索引恢复为旧模式：先由解密/同步流程落地 output/databases/{account}
    # 下的 SQLite，再从 session.db/contact.db/message_*.db 构建 FTS。
    # 因此 auto/realtime 对“索引构建”都解析为 decrypted，避免构建线程直接
    # 全量拉实时接口导致超时。
    if v in {"auto", "default", "wechat", "realtime", "real-time", "wcdb"}:
        return "decrypted"
    if v in {"decrypted", "local", "sqlite", "legacy"}:
        return "decrypted"
    return "decrypted"


def _account_key(account_dir: Path) -> str:
    return str(account_dir.name)


def _index_db_path(account_dir: Path) -> Path:
    return account_dir / _INDEX_DB_NAME


def _index_db_tmp_path(account_dir: Path) -> Path:
    return account_dir / _INDEX_DB_TMP_NAME


def get_chat_search_index_db_path(account_dir: Path) -> Path:
    """
    Preferred index file: {account}/chat_search_index.db
    Legacy (older builds): {account}/message_fts.db (only if it looks like our index schema).
    """

    preferred = account_dir / _INDEX_DB_NAME
    if preferred.exists():
        return preferred

    legacy = account_dir / _LEGACY_INDEX_DB_NAME
    if legacy.exists():
        insp = _inspect_index(legacy)
        if bool(insp.get("hasFtsTable")) and bool(insp.get("hasMetaTable")):
            return legacy

    return preferred


def _read_meta(index_path: Path) -> dict[str, str]:
    if not index_path.exists():
        return {}
    conn = sqlite3.connect(str(index_path))
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meta'").fetchall()
        if not rows:
            return {}
        out: dict[str, str] = {}
        for k, v in conn.execute("SELECT key, value FROM meta").fetchall():
            if k is None:
                continue
            out[str(k)] = "" if v is None else str(v)
        return out
    except Exception:
        return {}
    finally:
        conn.close()


def _inspect_index(index_path: Path) -> dict[str, Any]:
    if not index_path.exists():
        return {
            "exists": False,
            "ready": False,
            "hasFtsTable": False,
            "hasMetaTable": False,
            "hasMessageMetaTable": False,
            "hasTokenStatsTable": False,
            "schemaVersion": None,
        }

    conn = sqlite3.connect(str(index_path))
    try:
        try:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        except Exception:
            rows = []
        names = {str(r[0]).lower() for r in rows if r and r[0]}

        has_meta = "meta" in names
        has_fts = "message_fts" in names
        has_message_meta = "message_meta" in names
        has_token_stats = "message_token_stats" in names

        schema_version: Optional[int] = None
        if has_meta:
            try:
                r = conn.execute("SELECT value FROM meta WHERE key='schema_version' LIMIT 1").fetchone()
                if r and r[0] is not None:
                    schema_version = int(str(r[0]).strip() or "0")
            except Exception:
                schema_version = None

        # Indexes that predate explicit schema metadata are kept readable for
        # compatibility with tests/hand-built analysis fixtures. Once a
        # schema_version is present, require the current schema so upgraded
        # installs rebuild and get the payload_json + single-char fast path.
        ready = bool(has_fts and (schema_version is None or schema_version >= _SCHEMA_VERSION))

        return {
            "exists": True,
            "ready": ready,
            "hasFtsTable": bool(has_fts),
            "hasMetaTable": bool(has_meta),
            "hasMessageMetaTable": bool(has_message_meta),
            "hasTokenStatsTable": bool(has_token_stats),
            "schemaVersion": schema_version,
        }
    except Exception:
        return {
            "exists": True,
            "ready": False,
            "hasFtsTable": False,
            "hasMetaTable": False,
            "hasMessageMetaTable": False,
            "hasTokenStatsTable": False,
            "schemaVersion": None,
        }
    finally:
        conn.close()


def _index_meta_source(meta: dict[str, str]) -> str:
    raw = str((meta or {}).get("source") or "").strip().lower()
    if raw in {"realtime", "decrypted"}:
        return raw
    # Pre-migration indexes did not record a source and were built from local decrypted DBs.
    return "decrypted"


def get_chat_search_index_status(account_dir: Path, *, source: Optional[str] = None) -> dict[str, Any]:
    desired_source = _normalize_index_source(source, default="decrypted")
    key = _account_key(account_dir)
    index_path = get_chat_search_index_db_path(account_dir)
    inspect = _inspect_index(index_path)
    meta = _read_meta(index_path)
    actual_source = _index_meta_source(meta)
    ready = bool(inspect.get("ready")) and actual_source == desired_source
    with _BUILD_LOCK:
        state = dict(_BUILD_STATE.get(key) or {})
    return {
        "status": "success",
        "account": account_dir.name,
        "index": {
            "path": str(index_path),
            "exists": bool(inspect.get("exists")),
            "ready": bool(ready),
            "source": actual_source,
            "desiredSource": desired_source,
            "staleForSource": bool(inspect.get("ready")) and actual_source != desired_source,
            "hasFtsTable": bool(inspect.get("hasFtsTable")),
            "hasMetaTable": bool(inspect.get("hasMetaTable")),
            "schemaVersion": inspect.get("schemaVersion"),
            "meta": meta,
            "build": state,
        },
    }


def start_chat_search_index_build(account_dir: Path, *, rebuild: bool = False, source: Optional[str] = None) -> dict[str, Any]:
    source_norm = _normalize_index_source(source, default="decrypted")
    key = _account_key(account_dir)
    now = int(time.time())
    with _BUILD_LOCK:
        st = _BUILD_STATE.get(key)
        if st and st.get("status") == "building":
            return get_chat_search_index_status(account_dir, source=source_norm)
        _BUILD_STATE[key] = {
            "status": "building",
            "rebuild": bool(rebuild),
            "source": source_norm,
            "startedAt": now,
            "finishedAt": None,
            "indexedMessages": 0,
            "fetchedMessages": 0,
            "fetchCalls": 0,
            "totalConversations": 0,
            "completedConversations": 0,
            "messagesPerSec": 0,
            "currentDb": "",
            "currentConversation": "",
            "error": "",
        }

    t = threading.Thread(
        target=_build_worker,
        args=(account_dir, bool(rebuild), source_norm),
        daemon=True,
        name=f"chat-search-index:{key}",
    )
    t.start()
    return get_chat_search_index_status(account_dir, source=source_norm)


def _update_build_state(account_key: str, **kwargs: Any) -> None:
    with _BUILD_LOCK:
        st = _BUILD_STATE.get(account_key)
        if not st:
            return
        st.update(kwargs)


def _sqlite_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({_quote_ident(table_name)})").fetchall()
    except Exception:
        return set()

    columns: set[str] = set()
    for row in rows:
        try:
            name = str(row["name"] if isinstance(row, sqlite3.Row) else row[1] or "").strip().lower()
        except Exception:
            name = ""
        if name:
            columns.add(name)
    return columns


def _load_session_table_targets(account_dir: Path) -> dict[str, dict[str, Any]]:
    session_db_path = account_dir / "session.db"
    if not session_db_path.exists():
        return {}

    conn = sqlite3.connect(str(session_db_path))
    conn.row_factory = sqlite3.Row
    try:
        columns = _sqlite_table_columns(conn, "SessionTable")
        if "username" not in columns:
            return {}
        hidden_expr = "is_hidden" if "is_hidden" in columns else "0"
        rows = conn.execute(f"SELECT username, {hidden_expr} AS is_hidden FROM SessionTable").fetchall()
    finally:
        conn.close()

    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        u = str(r["username"] or "").strip()
        if not u:
            continue
        if not _should_keep_session(u, include_official=True):
            continue
        out[u] = {
            "is_hidden": 1 if int(r["is_hidden"] or 0) == 1 else 0,
            "is_official": 1 if u.startswith("gh_") else 0,
        }
    return out


def _load_contact_usernames_for_index(account_dir: Path) -> set[str]:
    contact_db_path = account_dir / "contact.db"
    if not contact_db_path.exists():
        return set()

    out: set[str] = set()
    conn = sqlite3.connect(str(contact_db_path))
    conn.row_factory = sqlite3.Row
    try:
        for table in ("contact", "stranger"):
            columns = _sqlite_table_columns(conn, table)
            if "username" not in columns:
                continue
            try:
                rows = conn.execute(f"SELECT username FROM {_quote_ident(table)}").fetchall()
            except Exception:
                continue
            for row in rows:
                username = _decode_sqlite_text(row["username"]).strip()
                if username:
                    out.add(username)
    finally:
        conn.close()
    return out


def _load_name2id_usernames_for_index(conn: sqlite3.Connection) -> set[str]:
    columns = _sqlite_table_columns(conn, "Name2Id")
    username_col = "user_name" if "user_name" in columns else ("username" if "username" in columns else "")
    if not username_col:
        return set()

    out: set[str] = set()
    try:
        rows = conn.execute(f"SELECT {_quote_ident(username_col)} AS username FROM Name2Id").fetchall()
    except Exception:
        return out

    for row in rows:
        try:
            raw = row["username"] if isinstance(row, sqlite3.Row) else row[0]
        except Exception:
            raw = ""
        username = _decode_sqlite_text(raw).strip()
        if username:
            out.add(username)
    return out


def _load_message_backed_index_targets(*, account_dir: Path, seed_usernames: set[str]) -> set[str]:
    out: set[str] = set()
    for db_path in _iter_message_db_paths(account_dir):
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            table_names = [_decode_sqlite_text(r["name"] if isinstance(r, sqlite3.Row) else r[0]).strip() for r in rows]
            lower_to_actual = {name.lower(): name for name in table_names if name}
            if not lower_to_actual:
                continue

            candidates = set(seed_usernames)
            candidates.update(_load_name2id_usernames_for_index(conn))
            for username in candidates:
                u = str(username or "").strip()
                if not u or u == account_dir.name:
                    continue
                if not _should_keep_session(u, include_official=True):
                    continue
                if _resolve_msg_table_name_by_map(lower_to_actual, u):
                    out.add(u)
        except Exception:
            continue
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
    return out


def _load_sessions_for_index(account_dir: Path) -> dict[str, dict[str, Any]]:
    sessions = _load_session_table_targets(account_dir)
    contact_usernames = _load_contact_usernames_for_index(account_dir)
    message_backed_usernames = _load_message_backed_index_targets(
        account_dir=account_dir,
        seed_usernames=contact_usernames,
    )

    for u in sorted(message_backed_usernames):
        if u in sessions:
            continue
        sessions[u] = {
            "is_hidden": 0,
            "is_official": 1 if u.startswith("gh_") else 0,
        }

    return sessions


def _init_index_db(conn: sqlite3.Connection) -> None:
    # NOTE: This index DB is built as a temporary file and then atomically swapped in.
    # Using WAL here would create `-wal/-shm` side files that are *not* swapped together.
    # Because the file is disposable until `os.replace`, journal=OFF is acceptable and
    # avoids a large amount of write amplification during first full index builds.
    try:
        conn.execute("PRAGMA journal_mode=OFF")
    except Exception:
        conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA locking_mode=EXCLUSIVE")
    conn.execute("PRAGMA cache_size=-131072")
    try:
        conn.execute("PRAGMA mmap_size=268435456")
    except Exception:
        pass

    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(
            text,
            username UNINDEXED,
            render_type UNINDEXED,
            create_time UNINDEXED,
            sort_seq UNINDEXED,
            local_id UNINDEXED,
            server_id UNINDEXED,
            local_type UNINDEXED,
            db_stem UNINDEXED,
            table_name UNINDEXED,
            sender_username UNINDEXED,
            is_hidden UNINDEXED,
            is_official UNINDEXED,
            payload_json UNINDEXED,
            tokenize='unicode61'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS message_meta (
            rowid INTEGER PRIMARY KEY,
            text TEXT NOT NULL,
            username TEXT NOT NULL,
            render_type TEXT NOT NULL,
            create_time INTEGER NOT NULL DEFAULT 0,
            sort_seq INTEGER NOT NULL DEFAULT 0,
            local_id INTEGER NOT NULL DEFAULT 0,
            server_id INTEGER NOT NULL DEFAULT 0,
            local_type INTEGER NOT NULL DEFAULT 0,
            db_stem TEXT NOT NULL,
            table_name TEXT NOT NULL,
            sender_username TEXT NOT NULL,
            is_hidden INTEGER NOT NULL DEFAULT 0,
            is_official INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS message_token_stats (
            token TEXT PRIMARY KEY,
            doc_count INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        ("schema_version", str(_SCHEMA_VERSION)),
    )


def _create_message_meta_indexes(conn: sqlite3.Connection) -> None:
    # Create these after the bulk insert. Maintaining secondary B-tree indexes
    # during the first full SQLite scan noticeably slows index builds on large accounts.
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_message_meta_visible_time
        ON message_meta(is_hidden, is_official, create_time DESC, sort_seq DESC, local_id DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_message_meta_username_time
        ON message_meta(username, create_time DESC, sort_seq DESC, local_id DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_message_meta_sender_time
        ON message_meta(sender_username, create_time DESC, sort_seq DESC, local_id DESC)
        """
    )


def _safe_begin(conn: sqlite3.Connection) -> None:
    try:
        if not conn.in_transaction:
            conn.execute("BEGIN")
    except sqlite3.OperationalError as e:
        # Some environments may report `in_transaction` inconsistently; avoid hard failing on nested BEGIN.
        if "within a transaction" in str(e).lower():
            return
        raise


_INDEX_PAYLOAD_KEYS = (
    "id",
    "db",
    "table",
    "username",
    "localId",
    "serverId",
    "serverIdStr",
    "type",
    "renderType",
    "createTime",
    "sortSeq",
    "senderUsername",
    "senderDisplayName",
    "senderAvatar",
    "isSent",
    "content",
    "title",
    "url",
    "quoteTitle",
    "quoteContent",
    "amount",
    "locationPoiname",
    "locationLabel",
    "source",
)


def _json_dumps_compact(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return "{}"


def _update_single_char_token_stats(counter: dict[str, int], token_text: str) -> None:
    """Track per-document single-character token frequency for high-hit search planning."""

    try:
        tokens = set(str(token_text or "").split())
    except Exception:
        return
    for token in tokens:
        t = str(token or "").strip()
        if len(t) == 1:
            counter[t] = int(counter.get(t, 0)) + 1


def _flush_index_batch(
    conn: sqlite3.Connection,
    *,
    insert_fts_sql: str,
    insert_meta_sql: str,
    batch: list[tuple[Any, ...]],
    next_rowid: int,
) -> tuple[int, int]:
    if not batch:
        return 0, int(next_rowid)

    fts_rows: list[tuple[Any, ...]] = []
    meta_rows: list[tuple[Any, ...]] = []
    rowid = int(next_rowid)
    for rec in batch:
        fts_rows.append((rowid, *rec))
        meta_rows.append(
            (
                rowid,
                rec[0],   # text
                rec[1],   # username
                rec[2],   # render_type
                rec[3],   # create_time
                rec[4],   # sort_seq
                rec[5],   # local_id
                rec[6],   # server_id
                rec[7],   # local_type
                rec[8],   # db_stem
                rec[9],   # table_name
                rec[10],  # sender_username
                rec[11],  # is_hidden
                rec[12],  # is_official
            )
        )
        rowid += 1

    conn.executemany(insert_fts_sql, fts_rows)
    conn.executemany(insert_meta_sql, meta_rows)
    count = len(batch)
    batch.clear()
    return count, rowid


def _hit_to_index_payload(hit: dict[str, Any], *, source: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in _INDEX_PAYLOAD_KEYS:
        if key in hit and hit.get(key) is not None:
            payload[key] = hit.get(key)
    payload["source"] = source
    return payload


def _build_worker(account_dir: Path, rebuild: bool, source: str = "decrypted") -> None:
    key = _account_key(account_dir)
    started = time.time()
    tmp_path = _index_db_tmp_path(account_dir)
    final_path = _index_db_path(account_dir)

    try:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass

        source_norm = _normalize_index_source(source, default="decrypted")
        sessions = _load_sessions_for_index(account_dir)
        if not sessions:
            raise RuntimeError("No sessions found (session.db empty or missing).")

        db_paths = _iter_message_db_paths(account_dir)
        if not db_paths:
            raise RuntimeError("No message databases found for this account.")

        conn_fts = sqlite3.connect(str(tmp_path))
        conn_fts.isolation_level = None  # manual transaction control (prevents implicit BEGIN)
        try:
            _init_index_db(conn_fts)
            try:
                conn_fts.commit()
            except Exception:
                pass
            insert_sql = (
                "INSERT INTO message_fts("
                "rowid, text, username, render_type, create_time, sort_seq, local_id, server_id, local_type, "
                "db_stem, table_name, sender_username, is_hidden, is_official, payload_json"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
            insert_meta_sql = (
                "INSERT INTO message_meta("
                "rowid, text, username, render_type, create_time, sort_seq, local_id, server_id, local_type, "
                "db_stem, table_name, sender_username, is_hidden, is_official"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )

            batch: list[tuple[Any, ...]] = []
            token_doc_counts: dict[str, int] = {}
            indexed = 0
            fetched = 0
            fetch_calls = 0
            insert_batch_size = _insert_batch_size()
            last_commit_index = 0
            next_rowid = 1

            _safe_begin(conn_fts)
            _update_build_state(
                key,
                totalConversations=len(sessions),
                completedConversations=0,
                insertBatchSize=insert_batch_size,
                commitEveryMessages=_COMMIT_EVERY_MESSAGES,
            )

            completed_conversations: set[str] = set()
            for db_path in db_paths:
                _update_build_state(key, currentDb=str(db_path.name))
                msg_conn = sqlite3.connect(str(db_path))
                msg_conn.row_factory = sqlite3.Row
                msg_conn.text_factory = bytes
                try:
                    try:
                        trows = msg_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                        lower_to_actual: dict[str, str] = {}
                        for x in trows:
                            if not x or x[0] is None:
                                continue
                            nm = _decode_sqlite_text(x[0]).strip()
                            if not nm:
                                continue
                            lower_to_actual[nm.lower()] = nm
                    except Exception:
                        lower_to_actual = {}

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

                    for conv_username, sess_info in sessions.items():
                        _update_build_state(key, currentConversation=str(conv_username))
                        table_name = _resolve_msg_table_name_by_map(lower_to_actual, conv_username)
                        if not table_name:
                            continue

                        is_group = bool(conv_username.endswith("@chatroom"))
                        quoted_table = _quote_ident(table_name)

                        sql_with_join = (
                            "SELECT "
                            "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                            "m.message_content, m.compress_content, n.user_name AS sender_username "
                            f"FROM {quoted_table} m "
                            "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid"
                        )
                        sql_no_join = (
                            "SELECT "
                            "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                            "m.message_content, m.compress_content, '' AS sender_username "
                            f"FROM {quoted_table} m "
                        )

                        try:
                            cursor = msg_conn.execute(sql_with_join)
                        except Exception:
                            cursor = msg_conn.execute(sql_no_join)

                        for r in cursor:
                            try:
                                hit = _row_to_search_hit(
                                    r,
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
                            if not haystack.strip():
                                continue

                            token_text = _to_char_token_text(haystack)
                            if not token_text:
                                continue
                            _update_single_char_token_stats(token_doc_counts, token_text)

                            batch.append(
                                (
                                    token_text,
                                    conv_username,
                                    str(hit.get("renderType") or ""),
                                    int(hit.get("createTime") or 0),
                                    int(hit.get("sortSeq") or 0),
                                    int(hit.get("localId") or 0),
                                    int(hit.get("serverId") or 0),
                                    int(hit.get("type") or 0),
                                    str(db_path.stem),
                                    str(table_name),
                                    str(hit.get("senderUsername") or ""),
                                    int(sess_info.get("is_hidden") or 0),
                                    int(sess_info.get("is_official") or 0),
                                    _json_dumps_compact(_hit_to_index_payload(hit, source="decrypted")),
                                )
                            )

                            if len(batch) >= insert_batch_size:
                                flushed, next_rowid = _flush_index_batch(
                                    conn_fts,
                                    insert_fts_sql=insert_sql,
                                    insert_meta_sql=insert_meta_sql,
                                    batch=batch,
                                    next_rowid=next_rowid,
                                )
                                indexed += flushed
                                elapsed = max(0.001, time.time() - started)
                                _update_build_state(
                                    key,
                                    indexedMessages=int(indexed),
                                    messagesPerSec=round(indexed / elapsed, 1),
                                    uniqueSearchTokens=len(token_doc_counts),
                                )

                                if indexed - last_commit_index >= _COMMIT_EVERY_MESSAGES:
                                    conn_fts.commit()
                                    last_commit_index = indexed
                                _safe_begin(conn_fts)
                        completed_conversations.add(str(conv_username))
                        _update_build_state(key, completedConversations=len(completed_conversations))
                finally:
                    msg_conn.close()

            if batch:
                flushed, next_rowid = _flush_index_batch(
                    conn_fts,
                    insert_fts_sql=insert_sql,
                    insert_meta_sql=insert_meta_sql,
                    batch=batch,
                    next_rowid=next_rowid,
                )
                indexed += flushed
                elapsed = max(0.001, time.time() - started)
                _update_build_state(
                    key,
                    indexedMessages=int(indexed),
                    fetchedMessages=int(fetched),
                    fetchCalls=int(fetch_calls),
                    messagesPerSec=round(indexed / elapsed, 1),
                    uniqueSearchTokens=len(token_doc_counts),
                )

            if token_doc_counts:
                conn_fts.executemany(
                    "INSERT INTO message_token_stats(token, doc_count) VALUES(?, ?)",
                    sorted((str(token), int(count)) for token, count in token_doc_counts.items()),
                )

            _create_message_meta_indexes(conn_fts)

            conn_fts.commit()

            finished_at = int(time.time())
            conn_fts.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("built_at", str(finished_at)),
            )
            conn_fts.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("message_count", str(indexed)),
            )
            conn_fts.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("source", source_norm),
            )
            conn_fts.commit()
        finally:
            conn_fts.close()

        if rebuild or final_path.exists():
            try:
                os.replace(str(tmp_path), str(final_path))
            except Exception:
                if tmp_path.exists():
                    tmp_path.unlink()
                raise
        else:
            os.replace(str(tmp_path), str(final_path))

        duration = max(0.0, time.time() - started)
        _update_build_state(
            key,
            status="ready",
            finishedAt=int(time.time()),
            currentDb="",
            currentConversation="",
            error="",
            durationSec=round(duration, 3),
        )
    except Exception as e:
        logger.exception("Failed to build chat search index")
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        _update_build_state(
            key,
            status="error",
            finishedAt=int(time.time()),
            error=str(e),
        )
