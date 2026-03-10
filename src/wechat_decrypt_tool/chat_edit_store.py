from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from .app_paths import get_output_dir

_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


def _db_path() -> Path:
    return get_output_dir() / "message_edits.db"


def _connect() -> sqlite3.Connection:
    db_path = _db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=5)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def ensure_schema() -> None:
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = _connect()
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS message_edits (
            account TEXT NOT NULL,
            session_id TEXT NOT NULL,
            db TEXT NOT NULL,
            table_name TEXT NOT NULL,
            local_id INTEGER NOT NULL,
            first_edited_at INTEGER NOT NULL,
            last_edited_at INTEGER NOT NULL,
            edit_count INTEGER NOT NULL,
            original_msg_json TEXT NOT NULL,
            original_resource_json TEXT,
            edited_cols_json TEXT,
            PRIMARY KEY (account, session_id, db, table_name, local_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_message_edits_account_session ON message_edits(account, session_id)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_message_edits_account_last ON message_edits(account, last_edited_at)")

    # Backwards-compatible migrations for existing DBs.
    try:
        cols = {
            str(r[1] or "").strip().lower()
            for r in conn.execute("PRAGMA table_info(message_edits)").fetchall()
            if r and len(r) > 1 and r[1]
        }
        if "edited_cols_json" not in cols:
            conn.execute("ALTER TABLE message_edits ADD COLUMN edited_cols_json TEXT")
    except Exception:
        pass
    conn.commit()


def _now_ms() -> int:
    return int(time.time() * 1000)


def format_message_id(db: str, table_name: str, local_id: int) -> str:
    return f"{str(db or '').strip()}:{str(table_name or '').strip()}:{int(local_id or 0)}"


def parse_message_id(message_id: str) -> tuple[str, str, int]:
    parts = str(message_id or "").split(":", 2)
    if len(parts) != 3:
        raise ValueError("Invalid message_id format.")
    db = str(parts[0] or "").strip()
    table_name = str(parts[1] or "").strip()
    try:
        local_id = int(parts[2] or 0)
    except Exception:
        raise ValueError("Invalid message_id format.")
    if not db or not table_name or local_id <= 0:
        raise ValueError("Invalid message_id format.")
    return db, table_name, local_id


def _bytes_to_hex(value: bytes) -> str:
    return "0x" + value.hex()


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


def _jsonify_blobs(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (bytes, bytearray, memoryview)):
        return _bytes_to_hex(bytes(obj))
    if isinstance(obj, dict):
        return {str(k): _jsonify_blobs(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonify_blobs(v) for v in obj]
    return obj


def _dejsonify_blobs(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, str):
        b = _hex_to_bytes(obj)
        return b if b is not None else obj
    if isinstance(obj, dict):
        return {str(k): _dejsonify_blobs(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_dejsonify_blobs(v) for v in obj]
    return obj


def dumps_json_with_blobs(obj: Any) -> str:
    return json.dumps(_jsonify_blobs(obj), ensure_ascii=False, separators=(",", ":"))


def loads_json_with_blobs(payload: str) -> Any:
    return _dejsonify_blobs(json.loads(str(payload or "") or "null"))


def upsert_original_once(
    *,
    account: str,
    session_id: str,
    db: str,
    table_name: str,
    local_id: int,
    original_msg: dict[str, Any],
    original_resource: Optional[dict[str, Any]],
    now_ms: Optional[int] = None,
) -> None:
    """Insert the original snapshot for a message only once, then bump counters on subsequent edits."""
    a = str(account or "").strip()
    sid = str(session_id or "").strip()
    db_norm = str(db or "").strip()
    t = str(table_name or "").strip()
    lid = int(local_id or 0)
    if not a or not sid or not db_norm or not t or lid <= 0:
        raise ValueError("Missing required keys for message edit store.")

    ts = int(now_ms if now_ms is not None else _now_ms())
    msg_json = dumps_json_with_blobs(original_msg or {})
    res_json = dumps_json_with_blobs(original_resource) if original_resource is not None else None

    conn: Optional[sqlite3.Connection] = None
    try:
        conn = _connect()
        existing = conn.execute(
            """
            SELECT 1
            FROM message_edits
            WHERE account = ? AND session_id = ? AND db = ? AND table_name = ? AND local_id = ?
            LIMIT 1
            """,
            (a, sid, db_norm, t, lid),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO message_edits(
                    account, session_id, db, table_name, local_id,
                    first_edited_at, last_edited_at, edit_count,
                    original_msg_json, original_resource_json, edited_cols_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (a, sid, db_norm, t, lid, ts, ts, 1, msg_json, res_json, None),
            )
        else:
            conn.execute(
                """
                UPDATE message_edits
                SET last_edited_at = ?, edit_count = edit_count + 1
                WHERE account = ? AND session_id = ? AND db = ? AND table_name = ? AND local_id = ?
                """,
                (ts, a, sid, db_norm, t, lid),
            )
        conn.commit()
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def _parse_json_str_list(payload: Any) -> list[str]:
    if payload is None:
        return []
    if isinstance(payload, (list, tuple)):
        return [str(x or "").strip() for x in payload if str(x or "").strip()]
    s = str(payload or "").strip()
    if not s:
        return []
    try:
        v = json.loads(s)
    except Exception:
        return []
    if not isinstance(v, list):
        return []
    return [str(x or "").strip() for x in v if str(x or "").strip()]


def merge_edited_columns(
    *,
    account: str,
    session_id: str,
    db: str,
    table_name: str,
    local_id: int,
    columns: list[str],
) -> bool:
    """Merge edited message column names into the per-message edit record.

    This allows reset to restore only the fields actually modified by the tool.
    """
    a = str(account or "").strip()
    sid = str(session_id or "").strip()
    db_norm = str(db or "").strip()
    t = str(table_name or "").strip()
    lid = int(local_id or 0)
    if not a or not sid or not db_norm or not t or lid <= 0:
        return False

    cols_in = [str(x or "").strip() for x in (columns or []) if str(x or "").strip()]
    if not cols_in:
        return True

    conn: Optional[sqlite3.Connection] = None
    try:
        conn = _connect()
        row = conn.execute(
            """
            SELECT edited_cols_json
            FROM message_edits
            WHERE account = ? AND session_id = ? AND db = ? AND table_name = ? AND local_id = ?
            LIMIT 1
            """,
            (a, sid, db_norm, t, lid),
        ).fetchone()
        if row is None:
            return False

        existing = _parse_json_str_list(row[0] if row and len(row) else None)
        merged = {c.lower() for c in existing if c} | {c.lower() for c in cols_in if c}
        merged_list = sorted(merged)
        payload = json.dumps(merged_list, ensure_ascii=False, separators=(",", ":"))
        conn.execute(
            """
            UPDATE message_edits
            SET edited_cols_json = ?
            WHERE account = ? AND session_id = ? AND db = ? AND table_name = ? AND local_id = ?
            """,
            (payload, a, sid, db_norm, t, lid),
        )
        conn.commit()
        return True
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    out: dict[str, Any] = {}
    for k in row.keys():
        out[str(k)] = row[k]
    return out


def list_sessions(account: str) -> list[dict[str, Any]]:
    a = str(account or "").strip()
    if not a:
        return []

    conn: Optional[sqlite3.Connection] = None
    try:
        conn = _connect()
        rows = conn.execute(
            """
            SELECT session_id, COUNT(*) AS msg_count, MAX(last_edited_at) AS last_edited_at
            FROM message_edits
            WHERE account = ?
            GROUP BY session_id
            ORDER BY last_edited_at DESC
            """,
            (a,),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            try:
                sid = str(r["session_id"] or "").strip()
            except Exception:
                sid = ""
            if not sid:
                continue
            out.append(
                {
                    "session_id": sid,
                    "msg_count": int(r["msg_count"] or 0),
                    "last_edited_at": int(r["last_edited_at"] or 0),
                }
            )
        return out
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def list_messages(account: str, session_id: str) -> list[dict[str, Any]]:
    a = str(account or "").strip()
    sid = str(session_id or "").strip()
    if not a or not sid:
        return []

    conn: Optional[sqlite3.Connection] = None
    try:
        conn = _connect()
        rows = conn.execute(
            """
            SELECT *
            FROM message_edits
            WHERE account = ? AND session_id = ?
            ORDER BY last_edited_at ASC, local_id ASC
            """,
            (a, sid),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            item = _row_to_dict(r) or {}
            try:
                item["message_id"] = format_message_id(item.get("db") or "", item.get("table_name") or "", item.get("local_id") or 0)
            except Exception:
                item["message_id"] = ""
            out.append(item)
        return out
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def get_message_edit(account: str, session_id: str, message_id: str) -> Optional[dict[str, Any]]:
    a = str(account or "").strip()
    sid = str(session_id or "").strip()
    if not a or not sid or not message_id:
        return None
    try:
        db, table_name, local_id = parse_message_id(message_id)
    except Exception:
        return None

    conn: Optional[sqlite3.Connection] = None
    try:
        conn = _connect()
        row = conn.execute(
            """
            SELECT *
            FROM message_edits
            WHERE account = ? AND session_id = ? AND db = ? AND table_name = ? AND local_id = ?
            LIMIT 1
            """,
            (a, sid, db, table_name, int(local_id)),
        ).fetchone()
        item = _row_to_dict(row)
        if not item:
            return None
        item["message_id"] = format_message_id(db, table_name, local_id)
        return item
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def delete_message_edit(account: str, session_id: str, message_id: str) -> bool:
    a = str(account or "").strip()
    sid = str(session_id or "").strip()
    if not a or not sid or not message_id:
        return False
    try:
        db, table_name, local_id = parse_message_id(message_id)
    except Exception:
        return False

    conn: Optional[sqlite3.Connection] = None
    try:
        conn = _connect()
        cur = conn.execute(
            """
            DELETE FROM message_edits
            WHERE account = ? AND session_id = ? AND db = ? AND table_name = ? AND local_id = ?
            """,
            (a, sid, db, table_name, int(local_id)),
        )
        conn.commit()
        return int(getattr(cur, "rowcount", 0) or 0) > 0
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def update_message_edit_local_id(
    *,
    account: str,
    session_id: str,
    db: str,
    table_name: str,
    old_local_id: int,
    new_local_id: int,
) -> bool:
    """Update the primary key local_id for an existing edit record (unsafe operations may change Msg.local_id)."""
    a = str(account or "").strip()
    sid = str(session_id or "").strip()
    db_norm = str(db or "").strip()
    t = str(table_name or "").strip()
    old_lid = int(old_local_id or 0)
    new_lid = int(new_local_id or 0)
    if not a or not sid or not db_norm or not t or old_lid <= 0 or new_lid <= 0:
        return False
    if old_lid == new_lid:
        return True

    conn: Optional[sqlite3.Connection] = None
    try:
        conn = _connect()
        cur = conn.execute(
            """
            UPDATE message_edits
            SET local_id = ?
            WHERE account = ? AND session_id = ? AND db = ? AND table_name = ? AND local_id = ?
            """,
            (new_lid, a, sid, db_norm, t, old_lid),
        )
        conn.commit()
        return int(getattr(cur, "rowcount", 0) or 0) > 0
    except Exception:
        return False
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def delete_account_edits(account: str) -> int:
    a = str(account or "").strip()
    if not a:
        return 0

    conn: Optional[sqlite3.Connection] = None
    try:
        conn = _connect()
        cur = conn.execute(
            """
            DELETE FROM message_edits
            WHERE account = ?
            """,
            (a,),
        )
        conn.commit()
        return int(getattr(cur, "rowcount", 0) or 0)
    except Exception:
        return 0
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass
