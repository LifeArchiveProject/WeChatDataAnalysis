from __future__ import annotations

import hashlib
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

_TABLE_NAME = "session_last_message"
_TABLE_NAME_RE = re.compile(r"^(msg_|chat_)([0-9a-f]{32})", re.IGNORECASE)
_PREVIEW_MAX_LEN = 400


def _session_db_path(account_dir: Path) -> Path:
    return Path(account_dir) / "session.db"


def _row_get(row: sqlite3.Row, key: str) -> Any:
    try:
        return row[key]
    except Exception:
        return None


def _normalize_preview(text: str) -> str:
    s = str(text or "").strip()
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > _PREVIEW_MAX_LEN:
        return s[:_PREVIEW_MAX_LEN]
    return s


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_TABLE_NAME} (
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


def get_session_last_message_status(account_dir: Path) -> dict[str, Any]:
    account_dir = Path(account_dir)
    session_db_path = _session_db_path(account_dir)
    if not session_db_path.exists():
        return {
            "status": "error",
            "account": account_dir.name,
            "message": "session.db not found.",
        }

    conn = sqlite3.connect(str(session_db_path))
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND lower(name)=lower(?) LIMIT 1",
            (_TABLE_NAME,),
        ).fetchone()
        exists = bool(row and row[0])
        if not exists:
            return {
                "status": "success",
                "account": account_dir.name,
                "table": {
                    "name": _TABLE_NAME,
                    "exists": False,
                    "rowCount": 0,
                    "builtAt": None,
                },
            }
        count = int(conn.execute(f"SELECT COUNT(1) FROM {_TABLE_NAME}").fetchone()[0] or 0)
        built_at = conn.execute(f"SELECT MAX(built_at) FROM {_TABLE_NAME}").fetchone()[0]
        try:
            built_at_int: Optional[int] = int(built_at) if built_at is not None else None
        except Exception:
            built_at_int = None
        return {
            "status": "success",
            "account": account_dir.name,
            "table": {
                "name": _TABLE_NAME,
                "exists": True,
                "rowCount": count,
                "builtAt": built_at_int,
            },
        }
    finally:
        conn.close()


def load_session_last_messages(account_dir: Path, usernames: list[str]) -> dict[str, str]:
    if not usernames:
        return {}

    account_dir = Path(account_dir)
    session_db_path = _session_db_path(account_dir)
    if not session_db_path.exists():
        return {}

    uniq = list(dict.fromkeys([str(u or "").strip() for u in usernames if str(u or "").strip()]))
    if not uniq:
        return {}

    out: dict[str, str] = {}
    conn = sqlite3.connect(str(session_db_path))
    conn.row_factory = sqlite3.Row
    try:
        chunk_size = 900
        for i in range(0, len(uniq), chunk_size):
            chunk = uniq[i : i + chunk_size]
            placeholders = ",".join(["?"] * len(chunk))
            rows = conn.execute(
                f"SELECT username, preview FROM {_TABLE_NAME} WHERE username IN ({placeholders})",
                chunk,
            ).fetchall()
            for r in rows:
                u = str(r["username"] or "").strip()
                if not u:
                    continue
                out[u] = str(r["preview"] or "")
        return out
    except Exception:
        return {}
    finally:
        conn.close()


def build_session_last_message_table(
    account_dir: Path,
    *,
    rebuild: bool = False,
    include_hidden: bool = True,
    include_official: bool = True,
) -> dict[str, Any]:
    """
    Build a per-account cache table `{account}/session.db::{session_last_message}`.

    The UI session list needs "last message preview" per conversation; querying message_*.db on every refresh is slow.
    This shifts that work to decrypt-time (or one-time manual rebuild).
    """

    account_dir = Path(account_dir)
    session_db_path = _session_db_path(account_dir)
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
    logger.info(f"[session_last_message] build start account={account_dir.name} dbs={len(db_paths)}")

    sconn = sqlite3.connect(str(session_db_path))
    sconn.row_factory = sqlite3.Row
    try:
        try:
            srows = sconn.execute(
                """
                SELECT username, is_hidden, summary, draft, last_msg_type, last_msg_sub_type, sort_timestamp, last_timestamp
                FROM SessionTable
                ORDER BY sort_timestamp DESC
                """
            ).fetchall()
        except sqlite3.OperationalError:
            srows = sconn.execute(
                """
                SELECT username, is_hidden, summary, draft, sort_timestamp, last_timestamp
                FROM SessionTable
                ORDER BY sort_timestamp DESC
                """
            ).fetchall()
    finally:
        sconn.close()

    sessions: list[sqlite3.Row] = []
    usernames: list[str] = []
    expected_ts_by_user: dict[str, int] = {}
    for r in srows:
        u = str(_row_get(r, "username") or "").strip()
        if not u:
            continue
        if not include_hidden and int(_row_get(r, "is_hidden") or 0) == 1:
            continue
        if not _should_keep_session(u, include_official=bool(include_official)):
            continue
        sessions.append(r)
        usernames.append(u)
        ts = int(_row_get(r, "sort_timestamp") or 0)
        if ts <= 0:
            ts = int(_row_get(r, "last_timestamp") or 0)
        expected_ts_by_user[u] = int(ts or 0)

    if not usernames:
        return {
            "status": "success",
            "account": account_dir.name,
            "message": "No sessions to build.",
            "built": 0,
            "durationSec": 0.0,
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

                # If session.db indicates a newer timestamp, fall back to slower but correct ordering.
                need_slow = False
                for username in users:
                    expected_ts = int(expected_ts_by_user.get(username) or 0)
                    if expected_ts > 0 and int(create_time or 0) > 0 and int(create_time or 0) < expected_ts:
                        need_slow = True
                        break

                if need_slow:
                    try:
                        row2 = conn.execute(
                            "SELECT "
                            "m.local_id, m.local_type, m.sort_seq, m.create_time, "
                            "m.message_content, m.compress_content, n.user_name AS sender_username "
                            f"FROM {quoted} m "
                            "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
                            "ORDER BY COALESCE(m.create_time, 0) DESC, COALESCE(m.sort_seq, 0) DESC, m.local_id DESC "
                            "LIMIT 1"
                        ).fetchone()
                    except Exception:
                        try:
                            row2 = conn.execute(
                                "SELECT "
                                "local_id, local_type, sort_seq, create_time, "
                                "message_content, compress_content, '' AS sender_username "
                                f"FROM {quoted} "
                                "ORDER BY COALESCE(create_time, 0) DESC, COALESCE(sort_seq, 0) DESC, local_id DESC "
                                "LIMIT 1"
                            ).fetchone()
                        except Exception:
                            row2 = None
                    if row2 is not None:
                        row = row2
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

                sort_key = (int(create_time), int(sort_seq), int(local_id))

                raw_text = _decode_message_content(row["compress_content"], row["message_content"]).strip()
                if raw_text and (not raw_text.lstrip().startswith("<")) and (not raw_text.lstrip().startswith('"<')):
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

                    preview = _normalize_preview(preview)
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

    # Fallback: always have a non-empty preview for UI.
    for r in sessions:
        u = str(_row_get(r, "username") or "").strip()
        if not u:
            continue
        if u in best:
            continue

        draft_text = _normalize_preview(_decode_sqlite_text(_row_get(r, "draft")).strip())
        if draft_text:
            preview = f"[草稿] {draft_text}" if draft_text else "[草稿]"
        else:
            summary_text = _normalize_preview(_decode_sqlite_text(_row_get(r, "summary")).strip())
            if summary_text:
                preview = summary_text
            else:
                preview = _infer_last_message_brief(_row_get(r, "last_msg_type"), _row_get(r, "last_msg_sub_type"))
        preview = _normalize_preview(preview)
        best[u] = (
            (0, 0, 0),
            {
                "username": u,
                "sort_seq": 0,
                "local_id": 0,
                "create_time": 0,
                "local_type": 0,
                "sender_username": "",
                "preview": preview,
                "db_stem": "",
                "table_name": "",
            },
        )

    built_at = int(time.time())
    conn_out = sqlite3.connect(str(session_db_path))
    try:
        _ensure_table(conn_out)
        if rebuild:
            try:
                conn_out.execute(f"DELETE FROM {_TABLE_NAME}")
            except Exception:
                pass

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
                    int(built_at),
                )
            )

        conn_out.executemany(
            f"INSERT OR REPLACE INTO {_TABLE_NAME}("
            "username, sort_seq, local_id, create_time, local_type, sender_username, preview, db_stem, table_name, built_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows_to_insert,
        )
        conn_out.commit()
    finally:
        conn_out.close()

    duration = max(0.0, time.time() - started)
    logger.info(
        f"[session_last_message] build done account={account_dir.name} sessions={len(best)} "
        f"durationSec={round(duration, 3)} table={_TABLE_NAME}"
    )
    return {
        "status": "success",
        "account": account_dir.name,
        "built": len(best),
        "table": _TABLE_NAME,
        "durationSec": round(duration, 3),
    }
