from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping, Optional

SQLITE_HEADER = b"SQLite format 3\x00"


def _clean_text(value: Any, *, limit: int = 240) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _clean_error(exc: BaseException, *, limit: int = 240) -> str:
    text = _clean_text(exc, limit=limit)
    if text:
        return f"{type(exc).__name__}: {text}"
    return type(exc).__name__


def _quote_ident(name: str) -> str:
    return '"' + str(name or "").replace('"', '""') + '"'


def collect_sqlite_diagnostics(
    path: str | Path,
    *,
    quick_check: bool = True,
    table_name: Optional[str] = None,
    table_sample_limit: int = 5,
) -> dict[str, Any]:
    db_path = Path(path)
    diagnostics: dict[str, Any] = {
        "path": str(db_path),
        "exists": bool(db_path.exists()),
    }

    if not diagnostics["exists"]:
        return diagnostics

    try:
        diagnostics["size"] = int(db_path.stat().st_size)
    except Exception as exc:
        diagnostics["size_error"] = _clean_error(exc)

    try:
        with db_path.open("rb") as f:
            header = f.read(len(SQLITE_HEADER))
        diagnostics["header_ok"] = header == SQLITE_HEADER
        diagnostics["header_hex"] = header.hex()
    except Exception as exc:
        diagnostics["header_error"] = _clean_error(exc)

    if not quick_check:
        return diagnostics

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(db_path))

        try:
            row = conn.execute("PRAGMA page_size").fetchone()
            diagnostics["page_size"] = int((row[0] if row is not None else 0) or 0)
        except Exception as exc:
            diagnostics["page_size_error"] = _clean_error(exc)

        try:
            row = conn.execute("PRAGMA page_count").fetchone()
            diagnostics["page_count"] = int((row[0] if row is not None else 0) or 0)
        except Exception as exc:
            diagnostics["page_count_error"] = _clean_error(exc)

        try:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
            table_names = [str(row[0]) for row in rows if row and row[0]]
            diagnostics["table_count"] = len(table_names)
            if table_names:
                diagnostics["tables_sample"] = table_names[: max(int(table_sample_limit or 0), 1)]
        except Exception as exc:
            diagnostics["table_list_error"] = _clean_error(exc)

        if table_name:
            diagnostics["target_table"] = str(table_name)
            try:
                cols = conn.execute(f"PRAGMA table_info({_quote_ident(table_name)})").fetchall()
                diagnostics["target_table_exists"] = bool(cols)
                if cols:
                    diagnostics["target_table_columns"] = [
                        str(col[1])
                        for col in cols[:8]
                        if len(col) > 1 and str(col[1] or "").strip()
                    ]
            except Exception as exc:
                diagnostics["target_table_error"] = _clean_error(exc)

        try:
            rows = conn.execute("PRAGMA quick_check").fetchall()
            values = [_clean_text(row[0]) for row in rows if row and row[0] is not None]
            if values:
                diagnostics["quick_check"] = values[0] if len(values) == 1 else values[:5]
                diagnostics["quick_check_ok"] = len(values) == 1 and values[0].lower() == "ok"
                if len(values) > 5:
                    diagnostics["quick_check_truncated"] = len(values) - 5
            else:
                diagnostics["quick_check"] = ""
                diagnostics["quick_check_ok"] = None
        except Exception as exc:
            diagnostics["quick_check_error"] = _clean_error(exc)
            diagnostics["quick_check_ok"] = False
    except Exception as exc:
        diagnostics["connect_error"] = _clean_error(exc)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    return diagnostics


def is_usable_sqlite_db(path: str | Path) -> bool:
    db_path = Path(path)
    if not db_path.exists() or (not db_path.is_file()):
        return False

    try:
        if int(db_path.stat().st_size) <= len(SQLITE_HEADER):
            return False
    except Exception:
        return False

    try:
        with db_path.open("rb") as f:
            if f.read(len(SQLITE_HEADER)) != SQLITE_HEADER:
                return False
    except Exception:
        return False

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA schema_version").fetchone()
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1").fetchone()
        return row is not None
    except Exception:
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def sqlite_diagnostics_status(diagnostics: Mapping[str, Any]) -> str:
    if not diagnostics:
        return "not_run"
    if not diagnostics.get("exists", False):
        return "missing"
    if diagnostics.get("header_ok") is False:
        return "bad_header"
    if diagnostics.get("connect_error"):
        return "connect_error"
    if diagnostics.get("quick_check_error"):
        return "quick_check_error"
    if diagnostics.get("quick_check_ok") is False:
        return "quick_check_failed"
    if diagnostics.get("quick_check_ok") is True:
        return "ok"
    return "header_only"


def format_sqlite_diagnostics(diagnostics: Mapping[str, Any]) -> str:
    compact: dict[str, Any] = {}
    for key, value in diagnostics.items():
        if value in (None, "", [], {}):
            continue
        compact[str(key)] = value
    return json.dumps(compact, ensure_ascii=False, sort_keys=True)
