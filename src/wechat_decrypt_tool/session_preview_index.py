from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from .chat_helpers import (
    _build_latest_message_preview,
    _decode_message_content,
    _decode_sqlite_text,
    _infer_last_message_brief,
    _is_mostly_printable_text,
    _iter_message_db_paths,
    _quote_ident,
    _should_keep_session,
)
from .logging_config import get_logger

logger = get_logger(__name__)

_SCHEMA_VERSION = 1
_INDEX_DB_NAME = "session_preview.db"
_INDEX_DB_TMP_NAME = "session_preview.tmp.db"

_TABLE_NAME_RE = re.compile(r"^(msg_|chat_)([0-9a-f]{32})", re.IGNORECASE)


def get_session_preview_index_db_path(account_dir: Path) -> Path:
    return account_dir / _INDEX_DB_NAME


def _index_db_tmp_path(account_dir: Path) -> Path:
    return account_dir / _INDEX_DB_TMP_NAME


def _file_sig(path: Path) -> tuple[str, int, int]:
    st = path.stat()
    mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))
    return (path.name, int(st.st_size), int(mtime_ns))


def _compute_source_fingerprint(account_dir: Path) -> dict[str, Any]:
    """Compute a stable fingerprint for the current decrypted data set."""
    session_db_path = account_dir / "session.db"
    msg_paths = _iter_message_db_paths(account_dir)

    items: list[tuple[str, int, int]] = []
    try:
        if session_db_path.exists():
            items.append(_file_sig(session_db_path))
    except Exception:
        pass

    for p in msg_paths:
        try:
            if p.exists():
                items.append(_file_sig(p))
        except Exception:
            continue

    items.sort()
    payload = json.dumps(items, ensure_ascii=False, separators=(",", ":")).encode("utf-8", errors="ignore")
    return {
        "fingerprint": hashlib.sha256(payload).hexdigest(),
        "files": items,
        "dbCount": len(msg_paths),
    }


def _inspect_index(index_path: Path) -> dict[str, Any]:
    if not index_path.exists():
        return {
            "exists": False,
            "ready": False,
            "schemaVersion": None,
            "hasMetaTable": False,
            "hasPreviewTable": False,
        }

    conn = sqlite3.connect(str(index_path))
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = {str(r[0]).lower() for r in rows if r and r[0]}
        has_meta = "meta" in names
        has_preview = "session_preview" in names

        schema_version: Optional[int] = None
        if has_meta:
            try:
                r = conn.execute("SELECT value FROM meta WHERE key='schema_version' LIMIT 1").fetchone()
                if r and r[0] is not None:
                    schema_version = int(str(r[0]).strip() or "0")
            except Exception:
                schema_version = None

        ready = bool(has_preview and (schema_version is None or schema_version >= _SCHEMA_VERSION))

        return {
            "exists": True,
            "ready": ready,
            "schemaVersion": schema_version,
            "hasMetaTable": bool(has_meta),
            "hasPreviewTable": bool(has_preview),
        }
    except Exception:
        return {
            "exists": True,
            "ready": False,
            "schemaVersion": None,
            "hasMetaTable": False,
            "hasPreviewTable": False,
        }
    finally:
        conn.close()


def get_session_preview_index_status(account_dir: Path) -> dict[str, Any]:
    index_path = get_session_preview_index_db_path(account_dir)
    inspect = _inspect_index(index_path)
    meta: dict[str, str] = {}
    current: dict[str, Any] = {}
    stale = False

    if bool(inspect.get("ready")):
        conn = sqlite3.connect(str(index_path))
        try:
            rows = conn.execute("SELECT key, value FROM meta").fetchall()
            for k, v in rows:
                if k is None:
                    continue
                meta[str(k)] = "" if v is None else str(v)
        except Exception:
            meta = {}
        finally:
            conn.close()

        current = _compute_source_fingerprint(account_dir)
        expected = str(meta.get("source_fingerprint") or "").strip()
        actual = str(current.get("fingerprint") or "").strip()
        if expected and actual and expected != actual:
            stale = True

    return {
        "status": "success",
        "account": account_dir.name,
        "index": {
            "path": str(index_path),
            "exists": bool(inspect.get("exists")),
            "ready": bool(inspect.get("ready")),
            "stale": bool(stale),
            "needsRebuild": (not bool(inspect.get("ready"))) or bool(stale),
            "schemaVersion": inspect.get("schemaVersion"),
            "meta": meta,
            "current": current,
        },
    }


def load_session_previews(account_dir: Path, usernames: list[str]) -> dict[str, str]:
    status = get_session_preview_index_status(account_dir)
    index = dict(status.get("index") or {})
    if not bool(index.get("ready")):
        return {}
    if bool(index.get("stale")):
        return {}

    index_path = get_session_preview_index_db_path(account_dir)

    uniq = list(dict.fromkeys([str(u or "").strip() for u in usernames if str(u or "").strip()]))
    if not uniq:
        return {}

    out: dict[str, str] = {}
    conn = sqlite3.connect(str(index_path))
    conn.row_factory = sqlite3.Row
    try:
        chunk_size = 900  # sqlite 默认变量上限常见为 999
        for i in range(0, len(uniq), chunk_size):
            chunk = uniq[i : i + chunk_size]
            placeholders = ",".join(["?"] * len(chunk))
            rows = conn.execute(
                f"SELECT username, preview FROM session_preview WHERE username IN ({placeholders})",
                chunk,
            ).fetchall()
            for r in rows:
                u = str(r["username"] or "").strip()
                if not u:
                    continue
                out[u] = str(r["preview"] or "")
        return out
    finally:
        conn.close()


def _init_index_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")

    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session_preview (
            username TEXT PRIMARY KEY,
            sort_seq INTEGER NOT NULL DEFAULT 0,
            local_id INTEGER NOT NULL DEFAULT 0,
            create_time INTEGER NOT NULL DEFAULT 0,
            local_type INTEGER NOT NULL DEFAULT 0,
            sender_username TEXT NOT NULL DEFAULT '',
            preview TEXT NOT NULL DEFAULT '',
            db_stem TEXT NOT NULL DEFAULT '',
            table_name TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        ("schema_version", str(_SCHEMA_VERSION)),
    )


def build_session_preview_index(
    account_dir: Path,
    *,
    rebuild: bool = False,
    include_hidden: bool = True,
    include_official: bool = True,
) -> dict[str, Any]:
    """
    Build a per-account session preview index as `{account}/session_preview.db`.

    Why: `message_*.db` tables do NOT index `create_time`, so `ORDER BY create_time DESC LIMIT 1`
    is extremely slow when done per-session at runtime. This index shifts that work to a one-time build.
    """

    account_dir = Path(account_dir)
    session_db_path = account_dir / "session.db"
    if not session_db_path.exists():
        return {
            "status": "error",
            "account": account_dir.name,
            "message": "session.db not found.",
        }

    db_paths = _iter_message_db_paths(account_dir)
    if not db_paths:
        return {
            "status": "error",
            "account": account_dir.name,
            "message": "No message databases found.",
        }

    started = time.time()
    logger.info(f"[session_preview] build start account={account_dir.name} dbs={len(db_paths)}")

    sconn = sqlite3.connect(str(session_db_path))
    sconn.row_factory = sqlite3.Row
    try:
        srows = sconn.execute(
            """
            SELECT username, is_hidden, summary, draft, last_msg_type, last_msg_sub_type, sort_timestamp, last_timestamp
            FROM SessionTable
            ORDER BY sort_timestamp DESC
            """
        ).fetchall()
    finally:
        sconn.close()

    sessions: list[sqlite3.Row] = []
    usernames: list[str] = []
    for r in srows:
        u = str(r["username"] or "").strip()
        if not u:
            continue
        if not include_hidden and int(r["is_hidden"] or 0) == 1:
            continue
        if not _should_keep_session(u, include_official=bool(include_official)):
            continue
        sessions.append(r)
        usernames.append(u)

    if not usernames:
        return {
            "status": "success",
            "account": account_dir.name,
            "message": "No sessions to index.",
            "indexed": 0,
            "path": str(get_session_preview_index_db_path(account_dir)),
        }

    md5_to_users: dict[str, list[str]] = {}
    for u in usernames:
        h = hashlib.md5(u.encode("utf-8")).hexdigest()
        md5_to_users.setdefault(h, []).append(u)

    best: dict[str, tuple[tuple[int, int, int], dict[str, Any]]] = {}

    for db_path in db_paths:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.text_factory = bytes
        try:
            trows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            md5_to_table: dict[str, str] = {}
            for tr in trows:
                if not tr or tr[0] is None:
                    continue
                name = _decode_sqlite_text(tr[0]).strip()
                if not name:
                    continue
                m = _TABLE_NAME_RE.match(name.lower())
                if not m:
                    continue
                md5_hex = str(m.group(2) or "").lower()
                if md5_hex not in md5_to_users:
                    continue
                prefix = str(m.group(1) or "").lower()
                if md5_hex not in md5_to_table or prefix == "msg_":
                    md5_to_table[md5_hex] = name

            if not md5_to_table:
                continue

            for md5_hex, table_name in md5_to_table.items():
                users = md5_to_users.get(md5_hex) or []
                if not users:
                    continue

                quoted = _quote_ident(table_name)

                row = None
                try:
                    row = conn.execute(
                        "SELECT "
                        "m.local_id, m.local_type, m.sort_seq, m.create_time, "
                        "m.message_content, m.compress_content, n.user_name AS sender_username "
                        f"FROM {quoted} m "
                        "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
                        "ORDER BY m.sort_seq DESC, m.local_id DESC "
                        "LIMIT 1"
                    ).fetchone()
                except Exception:
                    try:
                        row = conn.execute(
                            "SELECT "
                            "local_id, local_type, sort_seq, create_time, "
                            "message_content, compress_content, '' AS sender_username "
                            f"FROM {quoted} "
                            "ORDER BY sort_seq DESC, local_id DESC "
                            "LIMIT 1"
                        ).fetchone()
                    except Exception:
                        row = None

                if row is None:
                    continue

                try:
                    sort_seq = int(row["sort_seq"] or 0) if row["sort_seq"] is not None else 0
                except Exception:
                    sort_seq = 0
                try:
                    local_id = int(row["local_id"] or 0)
                except Exception:
                    local_id = 0
                try:
                    create_time = int(row["create_time"] or 0)
                except Exception:
                    create_time = 0
                sort_key = (int(sort_seq), int(local_id), int(create_time))

                raw_text = _decode_message_content(row["compress_content"], row["message_content"]).strip()
                if raw_text and (not raw_text.lstrip().startswith("<")) and (not raw_text.lstrip().startswith('"<')):
                    # Avoid leaking unreadable compressed/binary payloads into UI.
                    if not _is_mostly_printable_text(raw_text):
                        raw_text = ""
                sender_username = _decode_sqlite_text(row["sender_username"]).strip()

                for username in users:
                    prev = best.get(username)
                    if prev is not None and sort_key <= prev[0]:
                        continue

                    is_group = bool(username.endswith("@chatroom"))
                    try:
                        preview = _build_latest_message_preview(
                            username=username,
                            local_type=int(row["local_type"] or 0),
                            raw_text=raw_text,
                            is_group=is_group,
                            sender_username=sender_username,
                        )
                    except Exception:
                        preview = ""
                    if preview and (not _is_mostly_printable_text(preview)):
                        try:
                            preview = _build_latest_message_preview(
                                username=username,
                                local_type=int(row["local_type"] or 0),
                                raw_text="",
                                is_group=is_group,
                                sender_username=sender_username,
                            )
                        except Exception:
                            preview = ""
                    if not preview:
                        continue

                    best[username] = (
                        sort_key,
                        {
                            "username": username,
                            "sort_seq": int(sort_seq),
                            "local_id": int(local_id),
                            "create_time": int(create_time),
                            "local_type": int(row["local_type"] or 0),
                            "sender_username": sender_username,
                            "preview": preview,
                            "db_stem": str(db_path.stem),
                            "table_name": str(table_name),
                        },
                    )
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # Fallback: ensure we always have a non-empty lastMessage for UI (even if message tables missing).
    for r in sessions:
        u = str(r["username"] or "").strip()
        if not u:
            continue
        if u in best:
            continue
        draft_text = _decode_sqlite_text(r["draft"]).strip()
        if draft_text:
            draft_text = re.sub(r"\s+", " ", draft_text).strip()
            preview = f"[草稿] {draft_text}" if draft_text else "[草稿]"
        else:
            summary_text = _decode_sqlite_text(r["summary"]).strip()
            summary_text = re.sub(r"\s+", " ", summary_text).strip()
            if summary_text:
                preview = summary_text
            else:
                preview = _infer_last_message_brief(r["last_msg_type"], r["last_msg_sub_type"])
        best[u] = (
            (0, 0, 0),
            {
                "username": u,
                "sort_seq": 0,
                "local_id": 0,
                "create_time": 0,
                "local_type": 0,
                "sender_username": "",
                "preview": str(preview or ""),
                "db_stem": "",
                "table_name": "",
            },
        )

    final_path = get_session_preview_index_db_path(account_dir)
    tmp_path = _index_db_tmp_path(account_dir)
    try:
        if tmp_path.exists():
            tmp_path.unlink()
    except Exception:
        pass

    try:
        conn_out = sqlite3.connect(str(tmp_path))
        try:
            _init_index_db(conn_out)
            try:
                conn_out.commit()
            except Exception:
                pass
            conn_out.execute("BEGIN")
            rows_to_insert: list[tuple[Any, ...]] = []
            for _, rec in best.values():
                rows_to_insert.append(
                    (
                        rec["username"],
                        int(rec["sort_seq"] or 0),
                        int(rec["local_id"] or 0),
                        int(rec["create_time"] or 0),
                        int(rec["local_type"] or 0),
                        str(rec["sender_username"] or ""),
                        str(rec["preview"] or ""),
                        str(rec["db_stem"] or ""),
                        str(rec["table_name"] or ""),
                    )
                )
            conn_out.executemany(
                "INSERT OR REPLACE INTO session_preview("
                "username, sort_seq, local_id, create_time, local_type, sender_username, preview, db_stem, table_name"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows_to_insert,
            )
            conn_out.commit()

            built_at = int(time.time())
            conn_out.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("built_at", str(built_at)),
            )
            conn_out.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("session_count", str(len(best))),
            )
            conn_out.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("db_count", str(len(db_paths))),
            )
            src = _compute_source_fingerprint(account_dir)
            conn_out.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("source_fingerprint", str(src.get("fingerprint") or "")),
            )
            conn_out.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("source_files", json.dumps(src.get("files") or [], ensure_ascii=False)),
            )
            conn_out.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("built_include_hidden", "1" if include_hidden else "0"),
            )
            conn_out.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("built_include_official", "1" if include_official else "0"),
            )
            conn_out.commit()
        finally:
            conn_out.close()

        os.replace(str(tmp_path), str(final_path))
    except Exception as e:
        logger.exception(f"[session_preview] build failed: {e}")
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        return {
            "status": "error",
            "account": account_dir.name,
            "message": str(e),
        }

    duration = max(0.0, time.time() - started)
    logger.info(
        f"[session_preview] build done account={account_dir.name} indexed={len(best)} "
        f"durationSec={round(duration, 3)} path={final_path}"
    )
    return {
        "status": "success",
        "account": account_dir.name,
        "indexed": len(best),
        "path": str(final_path),
        "durationSec": round(duration, 3),
    }
