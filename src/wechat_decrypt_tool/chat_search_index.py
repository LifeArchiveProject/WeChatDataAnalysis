import os
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

_SCHEMA_VERSION = 1
_INDEX_DB_NAME = "chat_search_index.db"
_INDEX_DB_TMP_NAME = "chat_search_index.tmp.db"
_LEGACY_INDEX_DB_NAME = "message_fts.db"

_BUILD_LOCK = threading.Lock()
_BUILD_STATE: dict[str, dict[str, Any]] = {}


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

        schema_version: Optional[int] = None
        if has_meta:
            try:
                r = conn.execute("SELECT value FROM meta WHERE key='schema_version' LIMIT 1").fetchone()
                if r and r[0] is not None:
                    schema_version = int(str(r[0]).strip() or "0")
            except Exception:
                schema_version = None

        ready = bool(has_fts and (schema_version is None or schema_version >= _SCHEMA_VERSION))

        return {
            "exists": True,
            "ready": ready,
            "hasFtsTable": bool(has_fts),
            "hasMetaTable": bool(has_meta),
            "schemaVersion": schema_version,
        }
    except Exception:
        return {
            "exists": True,
            "ready": False,
            "hasFtsTable": False,
            "hasMetaTable": False,
            "schemaVersion": None,
        }
    finally:
        conn.close()


def get_chat_search_index_status(account_dir: Path) -> dict[str, Any]:
    key = _account_key(account_dir)
    index_path = get_chat_search_index_db_path(account_dir)
    inspect = _inspect_index(index_path)
    meta = _read_meta(index_path)
    with _BUILD_LOCK:
        state = dict(_BUILD_STATE.get(key) or {})
    return {
        "status": "success",
        "account": account_dir.name,
        "index": {
            "path": str(index_path),
            "exists": bool(inspect.get("exists")),
            "ready": bool(inspect.get("ready")),
            "hasFtsTable": bool(inspect.get("hasFtsTable")),
            "hasMetaTable": bool(inspect.get("hasMetaTable")),
            "schemaVersion": inspect.get("schemaVersion"),
            "meta": meta,
            "build": state,
        },
    }


def start_chat_search_index_build(account_dir: Path, *, rebuild: bool = False) -> dict[str, Any]:
    key = _account_key(account_dir)
    now = int(time.time())
    with _BUILD_LOCK:
        st = _BUILD_STATE.get(key)
        if st and st.get("status") == "building":
            return get_chat_search_index_status(account_dir)
        _BUILD_STATE[key] = {
            "status": "building",
            "rebuild": bool(rebuild),
            "startedAt": now,
            "finishedAt": None,
            "indexedMessages": 0,
            "currentDb": "",
            "currentConversation": "",
            "error": "",
        }

    t = threading.Thread(
        target=_build_worker,
        args=(account_dir, bool(rebuild)),
        daemon=True,
        name=f"chat-search-index:{key}",
    )
    t.start()
    return get_chat_search_index_status(account_dir)


def _update_build_state(account_key: str, **kwargs: Any) -> None:
    with _BUILD_LOCK:
        st = _BUILD_STATE.get(account_key)
        if not st:
            return
        st.update(kwargs)


def _load_sessions_for_index(account_dir: Path) -> dict[str, dict[str, Any]]:
    session_db_path = account_dir / "session.db"
    if not session_db_path.exists():
        return {}

    conn = sqlite3.connect(str(session_db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT username, is_hidden FROM SessionTable").fetchall()
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


def _init_index_db(conn: sqlite3.Connection) -> None:
    # NOTE: This index DB is built as a temporary file and then atomically swapped in.
    # Using WAL here would create `-wal/-shm` side files that are *not* swapped together,
    # which can lead to a final DB missing schema/data (e.g. "no such table: message_fts").
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")

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
            tokenize='unicode61'
        )
        """
    )
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        ("schema_version", str(_SCHEMA_VERSION)),
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


def _build_worker(account_dir: Path, rebuild: bool) -> None:
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
                "text, username, render_type, create_time, sort_seq, local_id, server_id, local_type, "
                "db_stem, table_name, sender_username, is_hidden, is_official"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )

            batch: list[tuple[Any, ...]] = []
            indexed = 0

            _safe_begin(conn_fts)

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
                                )
                            )

                            if len(batch) >= 1000:
                                conn_fts.executemany(insert_sql, batch)
                                indexed += len(batch)
                                batch.clear()
                                _update_build_state(key, indexedMessages=int(indexed))

                                if indexed % 20000 == 0:
                                    conn_fts.commit()
                                    _safe_begin(conn_fts)
                finally:
                    msg_conn.close()

            if batch:
                conn_fts.executemany(insert_sql, batch)
                indexed += len(batch)
                batch.clear()
                _update_build_state(key, indexedMessages=int(indexed))

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
