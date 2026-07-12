from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Optional


ExecQuery = Callable[..., list[dict[str, Any]]]
NormalizeItem = Callable[[dict[str, Any]], dict[str, Any]]
OpenCursor = Callable[..., int]
FetchCursorBatch = Callable[[int, int], tuple[list[dict[str, Any]], bool]]
CloseCursor = Callable[[int, int], None]
GetMessages = Callable[..., list[dict[str, Any]]]


class RealtimeMessageReadError(RuntimeError):
    pass


@dataclass(frozen=True)
class RealtimeMessageBatch:
    rows: list[dict[str, Any]]
    has_more: bool
    strategy: str
    authoritative: bool
    db_path: Optional[Path] = None
    table_name: str = ""
    my_rowid: Optional[int] = None
    tables_found: int = 0
    databases_probed: int = 0
    diagnostics: tuple[str, ...] = ()


def _pick(item: Any, *keys: str) -> Any:
    if not isinstance(item, dict):
        return None
    lowered = {str(k or "").strip().lower(): v for k, v in item.items() if v is not None}
    for key in keys:
        if key in item and item[key] is not None:
            return item[key]
        value = lowered.get(str(key or "").strip().lower())
        if value is not None:
            return value
    return None


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _quote_ident(name: str) -> str:
    return '"' + str(name or "").replace('"', '""') + '"'


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(int(value))
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, (bytes, bytearray)):
        return "X'" + bytes(value).hex() + "'"
    return "'" + str(value).replace("'", "''") + "'"


def _clean_account_name(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.lower().startswith("wxid_"):
        match = re.match(r"^(wxid_[^_]+)", text, flags=re.IGNORECASE)
        return match.group(1) if match else text
    match = re.match(r"^(.+)_([a-zA-Z0-9]{4})$", text)
    return match.group(1) if match else text


def _locked_call(rt_conn: Any, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    lock = getattr(rt_conn, "lock", None)
    if lock is None:
        return func(*args, **kwargs)
    with lock:
        return func(*args, **kwargs)


def _message_db_paths(db_storage_dir: Optional[Path], username: str) -> list[Path]:
    if db_storage_dir is None:
        return []
    message_dir = Path(db_storage_dir) / "message"
    try:
        if not message_dir.is_dir():
            return []
    except Exception:
        return []

    normal: list[Path] = []
    biz: list[Path] = []
    other: list[Path] = []
    try:
        for path in message_dir.iterdir():
            try:
                if not path.is_file():
                    continue
            except Exception:
                continue
            name = path.name.lower()
            if re.match(r"^message(_\d+)?\.db$", name):
                normal.append(path)
            elif re.match(r"^biz_message(_\d+)?\.db$", name):
                biz.append(path)
            elif name.endswith(".db") and "message" in name:
                other.append(path)
    except Exception:
        return []

    for paths in (normal, biz, other):
        paths.sort(key=lambda item: item.name.lower())
    if str(username or "").strip().startswith("gh_"):
        return biz + normal + other
    return normal + biz + other


def _resolve_tables(
    *,
    rt_conn: Any,
    db_storage_dir: Optional[Path],
    username: str,
    exec_query: ExecQuery,
) -> tuple[list[tuple[Path, str]], int, int, list[str]]:
    expected = f"Msg_{hashlib.md5(str(username or '').strip().encode('utf-8')).hexdigest()}"
    sql = (
        "SELECT name FROM sqlite_master WHERE type='table' AND lower(name)=lower("
        + _sql_literal(expected)
        + ") LIMIT 1"
    )
    candidates = _message_db_paths(db_storage_dir, username)
    resolved: list[tuple[Path, str]] = []
    probed = 0
    diagnostics: list[str] = []
    for db_path in candidates:
        try:
            rows = _locked_call(
                rt_conn,
                exec_query,
                rt_conn.handle,
                kind="message",
                path=str(db_path),
                sql=sql,
            )
            probed += 1
        except Exception as exc:
            diagnostics.append(f"probe {db_path.name}: {exc}")
            continue
        for row in rows or []:
            actual = str(_pick(row, "name") or "").strip()
            if actual:
                resolved.append((db_path, actual))
                break
    return resolved, len(candidates), probed, diagnostics


def _lookup_my_rowid(
    *,
    rt_conn: Any,
    account_dir: Path,
    db_path: Path,
    exec_query: ExecQuery,
) -> Optional[int]:
    candidates: list[str] = []
    for value in (
        getattr(rt_conn, "native_wxid", ""),
        account_dir.name,
        _clean_account_name(account_dir.name),
    ):
        text = str(value or "").strip()
        if text and text not in candidates:
            candidates.append(text)
    if not candidates:
        return None

    values = ", ".join(_sql_literal(value) for value in candidates)
    order = " ".join(
        f"WHEN user_name = {_sql_literal(value)} THEN {index}" for index, value in enumerate(candidates)
    )
    sql = (
        "SELECT rowid AS rowid FROM Name2Id "
        f"WHERE user_name IN ({values}) "
        f"ORDER BY CASE {order} ELSE {len(candidates)} END LIMIT 1"
    )
    try:
        rows = _locked_call(
            rt_conn,
            exec_query,
            rt_conn.handle,
            kind="message",
            path=str(db_path),
            sql=sql,
        )
    except Exception:
        return None
    rowid = _to_int(_pick(rows[0], "rowid")) if rows else 0
    return rowid if rowid > 0 else None


def _select_candidates(table_name: str, limit: int) -> tuple[str, ...]:
    table = _quote_ident(table_name)
    base = (
        "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, "
        "m.create_time, m.message_content, m.compress_content, "
    )
    tail = (
        f"FROM {table} m LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
        "ORDER BY m.create_time DESC, m.sort_seq DESC, m.local_id DESC "
        f"LIMIT {int(limit)}"
    )
    return (
        "SELECT " + base + "m.packed_info_data AS packed_info_data, m.source AS msg_source, "
        "n.user_name AS sender_username " + tail,
        "SELECT " + base + "m.packed_info_data AS packed_info_data, NULL AS msg_source, "
        "n.user_name AS sender_username " + tail,
        "SELECT " + base + "NULL AS packed_info_data, m.source AS msg_source, "
        "n.user_name AS sender_username " + tail,
        "SELECT " + base + "NULL AS packed_info_data, NULL AS msg_source, "
        "n.user_name AS sender_username " + tail,
    )


def _select_window_candidates(
    table_name: str,
    *,
    where_sql: str,
    order_sql: str,
    limit: int,
) -> tuple[str, ...]:
    table = _quote_ident(table_name)
    base = (
        "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, "
        "m.create_time, m.message_content, m.compress_content, "
    )
    tail = (
        f"FROM {table} m LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
        f"WHERE {where_sql} ORDER BY {order_sql} LIMIT {int(limit)}"
    )
    return (
        "SELECT " + base + "m.packed_info_data AS packed_info_data, m.source AS msg_source, "
        "n.user_name AS sender_username " + tail,
        "SELECT " + base + "m.packed_info_data AS packed_info_data, NULL AS msg_source, "
        "n.user_name AS sender_username " + tail,
        "SELECT " + base + "NULL AS packed_info_data, m.source AS msg_source, "
        "n.user_name AS sender_username " + tail,
        "SELECT " + base + "NULL AS packed_info_data, NULL AS msg_source, "
        "n.user_name AS sender_username " + tail,
    )


def _query_first_supported(
    *,
    rt_conn: Any,
    db_path: Path,
    statements: tuple[str, ...],
    exec_query: ExecQuery,
) -> list[dict[str, Any]]:
    last_error: Optional[Exception] = None
    for sql in statements:
        try:
            return list(
                _locked_call(
                    rt_conn,
                    exec_query,
                    rt_conn.handle,
                    kind="message",
                    path=str(db_path),
                    sql=sql,
                )
                or []
            )
        except Exception as exc:
            last_error = exc
    raise RealtimeMessageReadError(f"Cannot query realtime table {db_path.name}: {last_error or 'unknown error'}")


def count_realtime_message_rows_via_exec(
    *,
    rt_conn: Any,
    account_dir: Path,
    username: str,
    db_storage_dir: Optional[Path],
    exec_query: ExecQuery,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    local_types: Optional[set[int]] = None,
) -> Optional[int]:
    resolved, candidate_count, probed, _diagnostics = _resolve_tables(
        rt_conn=rt_conn,
        db_storage_dir=db_storage_dir,
        username=username,
        exec_query=exec_query,
    )
    if candidate_count <= 0 or probed != candidate_count:
        return None
    if not resolved:
        return 0

    where: list[str] = []
    if start_time is not None:
        where.append(f"create_time >= {int(start_time)}")
    if end_time is not None:
        where.append(f"create_time <= {int(end_time)}")
    wanted_types = sorted({int(value) for value in (local_types or set()) if int(value) != 0})
    if wanted_types:
        where.append("local_type IN (" + ", ".join(str(value) for value in wanted_types) + ")")
    suffix = " WHERE " + " AND ".join(where) if where else ""

    total = 0
    for db_path, table_name in resolved:
        sql = f"SELECT COUNT(*) AS count FROM {_quote_ident(table_name)}{suffix}"
        try:
            rows = _locked_call(
                rt_conn,
                exec_query,
                rt_conn.handle,
                kind="message",
                path=str(db_path),
                sql=sql,
            )
        except Exception:
            return None
        total += _to_int(_pick(rows[0], "count")) if rows else 0
    return total


def fetch_anchor_via_exec(
    *,
    rt_conn: Any,
    username: str,
    db_storage_dir: Optional[Path],
    exec_query: ExecQuery,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
) -> RealtimeMessageBatch:
    """Fetch the earliest realtime row without walking the conversation."""

    resolved, candidate_count, probed, diagnostics = _resolve_tables(
        rt_conn=rt_conn,
        db_storage_dir=db_storage_dir,
        username=username,
        exec_query=exec_query,
    )
    authoritative = bool(candidate_count > 0 and probed == candidate_count)
    if not resolved:
        return RealtimeMessageBatch(
            [],
            False,
            "exec_anchor",
            authoritative,
            tables_found=0,
            databases_probed=probed,
            diagnostics=tuple(diagnostics),
        )

    where: list[str] = []
    if start_time is not None:
        where.append(f"create_time >= {int(start_time)}")
    if end_time is not None:
        where.append(f"create_time < {int(end_time)}")
    suffix = " WHERE " + " AND ".join(where) if where else ""

    candidates: list[dict[str, Any]] = []
    failed_queries = 0
    for db_path, table_name in resolved:
        sql = (
            "SELECT local_id, create_time, COALESCE(sort_seq, 0) AS sort_seq "
            f"FROM {_quote_ident(table_name)}{suffix} "
            "ORDER BY create_time ASC, COALESCE(sort_seq, 0) ASC, local_id ASC LIMIT 1"
        )
        try:
            raw_rows = _locked_call(
                rt_conn,
                exec_query,
                rt_conn.handle,
                kind="message",
                path=str(db_path),
                sql=sql,
            )
        except Exception as exc:
            failed_queries += 1
            diagnostics.append(f"anchor {db_path.name}/{table_name}: {exc}")
            continue
        for raw in raw_rows or []:
            if not isinstance(raw, dict):
                continue
            local_id = _to_int(_pick(raw, "local_id", "localId"))
            if local_id <= 0:
                continue
            candidates.append(
                {
                    "local_id": local_id,
                    "create_time": _to_int(_pick(raw, "create_time", "createTime")),
                    "sort_seq": _to_int(_pick(raw, "sort_seq", "sortSeq")),
                    "_db_path": str(db_path),
                    "db_name": db_path.name,
                    "table_name": table_name,
                }
            )
            break

    authoritative = bool(authoritative and failed_queries == 0)
    candidates.sort(
        key=lambda row: (
            _to_int(row.get("create_time")),
            _to_int(row.get("sort_seq")),
            _to_int(row.get("local_id")),
            str(row.get("_db_path") or ""),
        )
    )
    first = candidates[:1]
    first_db_path = Path(str(first[0]["_db_path"])) if first else None
    first_table_name = str(first[0].get("table_name") or "") if first else ""
    return RealtimeMessageBatch(
        first,
        False,
        "exec_anchor",
        authoritative,
        db_path=first_db_path,
        table_name=first_table_name,
        tables_found=len(resolved),
        databases_probed=probed,
        diagnostics=tuple(diagnostics),
    )


def fetch_context_via_exec(
    *,
    rt_conn: Any,
    account_dir: Path,
    username: str,
    anchor_db_stem: str,
    anchor_table_name: str,
    anchor_local_id: int,
    before: int,
    after: int,
    db_storage_dir: Optional[Path],
    exec_query: ExecQuery,
    normalize_item: NormalizeItem,
) -> RealtimeMessageBatch:
    """Read a bounded chronological window around a realtime message."""

    resolved, candidate_count, probed, diagnostics = _resolve_tables(
        rt_conn=rt_conn,
        db_storage_dir=db_storage_dir,
        username=username,
        exec_query=exec_query,
    )
    authoritative = bool(candidate_count > 0 and probed == candidate_count)
    if not resolved:
        return RealtimeMessageBatch(
            [],
            False,
            "exec_context",
            authoritative,
            tables_found=0,
            databases_probed=probed,
            diagnostics=tuple(diagnostics),
        )

    requested_stem = str(anchor_db_stem or "").strip().lower()
    requested_table = str(anchor_table_name or "").strip().lower()
    anchor_target: Optional[tuple[Path, str]] = None
    for db_path, table_name in resolved:
        if requested_stem and db_path.stem.lower() != requested_stem:
            continue
        if requested_table and table_name.lower() != requested_table:
            continue
        anchor_target = (db_path, table_name)
        break
    if anchor_target is None and len(resolved) == 1:
        anchor_target = resolved[0]
    if anchor_target is None:
        return RealtimeMessageBatch(
            [],
            False,
            "exec_context",
            False,
            tables_found=len(resolved),
            databases_probed=probed,
            diagnostics=tuple(diagnostics + ["anchor database/table could not be resolved"]),
        )

    anchor_db_path, anchor_table = anchor_target
    anchor_statements = _select_window_candidates(
        anchor_table,
        where_sql=f"m.local_id = {int(anchor_local_id)}",
        order_sql="m.local_id ASC",
        limit=1,
    )
    try:
        anchor_raw = _query_first_supported(
            rt_conn=rt_conn,
            db_path=anchor_db_path,
            statements=anchor_statements,
            exec_query=exec_query,
        )
    except Exception as exc:
        diagnostics.append(f"context anchor {anchor_db_path.name}/{anchor_table}: {exc}")
        return RealtimeMessageBatch(
            [],
            False,
            "exec_context",
            False,
            tables_found=len(resolved),
            databases_probed=probed,
            diagnostics=tuple(diagnostics),
        )
    if not anchor_raw:
        return RealtimeMessageBatch(
            [],
            False,
            "exec_context",
            authoritative,
            tables_found=len(resolved),
            databases_probed=probed,
            diagnostics=tuple(diagnostics),
        )

    anchor_create_time = _to_int(_pick(anchor_raw[0], "create_time", "createTime"))
    anchor_sort_seq = _to_int(_pick(anchor_raw[0], "sort_seq", "sortSeq"))
    before_where = (
        f"m.create_time < {anchor_create_time} OR "
        f"(m.create_time = {anchor_create_time} AND COALESCE(m.sort_seq, 0) < {anchor_sort_seq}) OR "
        f"(m.create_time = {anchor_create_time} AND COALESCE(m.sort_seq, 0) = {anchor_sort_seq} "
        f"AND m.local_id < {int(anchor_local_id)})"
    )
    after_where = (
        f"m.create_time > {anchor_create_time} OR "
        f"(m.create_time = {anchor_create_time} AND COALESCE(m.sort_seq, 0) > {anchor_sort_seq}) OR "
        f"(m.create_time = {anchor_create_time} AND COALESCE(m.sort_seq, 0) = {anchor_sort_seq} "
        f"AND m.local_id > {int(anchor_local_id)})"
    )

    raw_candidates: list[tuple[dict[str, Any], Path, str, Optional[int]]] = []
    anchor_my_rowid = _lookup_my_rowid(
        rt_conn=rt_conn,
        account_dir=account_dir,
        db_path=anchor_db_path,
        exec_query=exec_query,
    )
    raw_candidates.append((anchor_raw[0], anchor_db_path, anchor_table, anchor_my_rowid))

    query_failed = False
    for db_path, table_name in resolved:
        my_rowid = _lookup_my_rowid(
            rt_conn=rt_conn,
            account_dir=account_dir,
            db_path=db_path,
            exec_query=exec_query,
        )
        for side, take, where_sql, order_sql in (
            (
                "before",
                max(0, int(before)),
                before_where,
                "m.create_time DESC, COALESCE(m.sort_seq, 0) DESC, m.local_id DESC",
            ),
            (
                "after",
                max(0, int(after)),
                after_where,
                "m.create_time ASC, COALESCE(m.sort_seq, 0) ASC, m.local_id ASC",
            ),
        ):
            if take <= 0:
                continue
            try:
                selected = _query_first_supported(
                    rt_conn=rt_conn,
                    db_path=db_path,
                    statements=_select_window_candidates(
                        table_name,
                        where_sql=where_sql,
                        order_sql=order_sql,
                        limit=take,
                    ),
                    exec_query=exec_query,
                )
            except Exception as exc:
                query_failed = True
                diagnostics.append(f"context {side} {db_path.name}/{table_name}: {exc}")
                continue
            for raw in selected:
                if isinstance(raw, dict):
                    raw_candidates.append((raw, db_path, table_name, my_rowid))

    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()
    for raw, db_path, table_name, my_rowid in raw_candidates:
        item = normalize_item(raw)
        if not isinstance(item, dict):
            continue
        local_id = _to_int(_pick(item, "local_id", "localId"))
        if local_id <= 0:
            continue
        key = (str(db_path).lower(), table_name.lower(), local_id)
        if key in seen:
            continue
        seen.add(key)
        item["_db_path"] = str(db_path)
        item["db_name"] = db_path.name
        item["table_name"] = table_name
        if my_rowid is not None:
            item["__my_rowid"] = int(my_rowid)
            real_sender_id = _to_int(_pick(item, "real_sender_id", "realSenderId"))
            if real_sender_id > 0:
                item.setdefault("computed_is_send", int(real_sender_id == int(my_rowid)))
        normalized.append(item)

    normalized.sort(
        key=lambda row: (
            _to_int(_pick(row, "create_time", "createTime")),
            _to_int(_pick(row, "sort_seq", "sortSeq")),
            _to_int(_pick(row, "local_id", "localId")),
            str(_pick(row, "_db_path") or ""),
        )
    )
    anchor_index = next(
        (
            index
            for index, row in enumerate(normalized)
            if str(_pick(row, "_db_path") or "").lower() == str(anchor_db_path).lower()
            and str(_pick(row, "table_name") or "").lower() == anchor_table.lower()
            and _to_int(_pick(row, "local_id", "localId")) == int(anchor_local_id)
        ),
        -1,
    )
    if anchor_index < 0:
        return RealtimeMessageBatch(
            [],
            False,
            "exec_context",
            False,
            tables_found=len(resolved),
            databases_probed=probed,
            diagnostics=tuple(diagnostics + ["anchor row disappeared from normalized context"]),
        )
    start = max(0, anchor_index - max(0, int(before)))
    end = min(len(normalized), anchor_index + max(0, int(after)) + 1)
    window = normalized[start:end]
    return RealtimeMessageBatch(
        window,
        False,
        "exec_context",
        bool(authoritative and not query_failed),
        db_path=anchor_db_path,
        table_name=anchor_table,
        my_rowid=anchor_my_rowid,
        tables_found=len(resolved),
        databases_probed=probed,
        diagnostics=tuple(diagnostics),
    )


def fetch_rows_via_exec(
    *,
    rt_conn: Any,
    account_dir: Path,
    username: str,
    take: int,
    db_storage_dir: Optional[Path],
    exec_query: ExecQuery,
    normalize_item: NormalizeItem,
) -> RealtimeMessageBatch:
    take = int(take)
    if take <= 0:
        return RealtimeMessageBatch([], False, "exec", True)

    resolved, candidate_count, probed, diagnostics = _resolve_tables(
        rt_conn=rt_conn,
        db_storage_dir=db_storage_dir,
        username=username,
        exec_query=exec_query,
    )
    authoritative = bool(candidate_count > 0 and probed == candidate_count)
    if not resolved:
        return RealtimeMessageBatch(
            [],
            False,
            "exec",
            authoritative,
            tables_found=0,
            databases_probed=probed,
            diagnostics=tuple(diagnostics),
        )

    all_rows: list[dict[str, Any]] = []
    any_over_probe = False
    first_db_path: Optional[Path] = None
    first_table_name = ""
    first_my_rowid: Optional[int] = None
    probe_limit = take + 1

    for db_path, table_name in resolved:
        my_rowid = _lookup_my_rowid(
            rt_conn=rt_conn,
            account_dir=account_dir,
            db_path=db_path,
            exec_query=exec_query,
        )
        raw_rows: Optional[list[dict[str, Any]]] = None
        last_error: Optional[Exception] = None
        for sql in _select_candidates(table_name, probe_limit):
            try:
                raw_rows = _locked_call(
                    rt_conn,
                    exec_query,
                    rt_conn.handle,
                    kind="message",
                    path=str(db_path),
                    sql=sql,
                )
                break
            except Exception as exc:
                last_error = exc
        if raw_rows is None:
            raise RealtimeMessageReadError(
                f"Cannot query realtime table {db_path.name}/{table_name}: {last_error or 'unknown error'}"
            )

        if first_db_path is None:
            first_db_path = db_path
            first_table_name = table_name
            first_my_rowid = my_rowid
        raw_list = list(raw_rows or [])
        if len(raw_list) > take:
            any_over_probe = True
        for raw in raw_list[:take]:
            if not isinstance(raw, dict):
                continue
            item = normalize_item(raw)
            if not isinstance(item, dict):
                continue
            item["_db_path"] = str(db_path)
            item["db_name"] = db_path.name
            item["table_name"] = table_name
            if my_rowid is not None:
                item["__my_rowid"] = int(my_rowid)
                item.setdefault("debug_my_rowid", int(my_rowid))
                real_sender_id = _to_int(_pick(item, "real_sender_id", "realSenderId"))
                if real_sender_id > 0:
                    item.setdefault("computed_is_send", int(real_sender_id == int(my_rowid)))
            all_rows.append(item)

    all_rows.sort(
        key=lambda row: (
            _to_int(_pick(row, "create_time", "createTime")),
            _to_int(_pick(row, "sort_seq", "sortSeq")),
            _to_int(_pick(row, "local_id", "localId")),
            str(_pick(row, "_db_path") or ""),
        ),
        reverse=True,
    )
    has_more = bool(any_over_probe or len(all_rows) > take)
    rows = all_rows[:take]
    if rows:
        path_text = str(_pick(rows[0], "_db_path") or "").strip()
        if path_text:
            first_db_path = Path(path_text)
        first_table_name = str(_pick(rows[0], "table_name") or first_table_name).strip()
        rowid = _to_int(_pick(rows[0], "__my_rowid", "debug_my_rowid"))
        if rowid > 0:
            first_my_rowid = rowid
    return RealtimeMessageBatch(
        rows,
        has_more,
        "exec",
        authoritative,
        db_path=first_db_path,
        table_name=first_table_name,
        my_rowid=first_my_rowid,
        tables_found=len(resolved),
        databases_probed=probed,
        diagnostics=tuple(diagnostics),
    )


def fetch_all_rows_via_exec_paged(
    *,
    rt_conn: Any,
    account_dir: Path,
    username: str,
    db_storage_dir: Optional[Path],
    exec_query: ExecQuery,
    normalize_item: NormalizeItem,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    local_types: Optional[set[int]] = None,
    page_size: int = 1000,
) -> RealtimeMessageBatch:
    """Read a full conversation without creating an unbounded sidecar response."""

    size = max(1, min(int(page_size or 1000), 1000))
    resolved, candidate_count, probed, diagnostics = _resolve_tables(
        rt_conn=rt_conn,
        db_storage_dir=db_storage_dir,
        username=username,
        exec_query=exec_query,
    )
    authoritative = bool(candidate_count > 0 and probed == candidate_count)
    if not resolved:
        return RealtimeMessageBatch(
            [],
            False,
            "exec_paged",
            authoritative,
            tables_found=0,
            databases_probed=probed,
            diagnostics=tuple(diagnostics),
        )

    all_rows: list[dict[str, Any]] = []
    first_db_path: Optional[Path] = None
    first_table_name = ""
    first_my_rowid: Optional[int] = None
    wanted_types = sorted({int(value) for value in (local_types or set()) if int(value) != 0})

    def row_key(row: dict[str, Any]) -> tuple[int, int, int]:
        return (
            _to_int(_pick(row, "create_time", "createTime")),
            _to_int(_pick(row, "sort_seq", "sortSeq")),
            _to_int(_pick(row, "local_id", "localId")),
        )

    for db_path, table_name in resolved:
        my_rowid = _lookup_my_rowid(
            rt_conn=rt_conn,
            account_dir=account_dir,
            db_path=db_path,
            exec_query=exec_query,
        )
        boundary: Optional[tuple[int, int, int]] = None
        selected_statement: Optional[int] = None

        while True:
            where_parts: list[str] = []
            if wanted_types:
                where_parts.append("m.local_type IN (" + ", ".join(str(value) for value in wanted_types) + ")")
            if start_time is not None:
                where_parts.append(f"m.create_time >= {int(start_time)}")
            if end_time is not None:
                where_parts.append(f"m.create_time <= {int(end_time)}")
            if boundary is not None:
                create_time, sort_seq, local_id = boundary
                where_parts.append(
                    "(m.create_time > {0} OR "
                    "(m.create_time = {0} AND m.sort_seq > {1}) OR "
                    "(m.create_time = {0} AND m.sort_seq = {1} AND m.local_id > {2}))".format(
                        create_time,
                        sort_seq,
                        local_id,
                    )
                )

            statements = _select_window_candidates(
                table_name,
                where_sql=" AND ".join(where_parts) if where_parts else "1=1",
                order_sql="m.create_time ASC, m.sort_seq ASC, m.local_id ASC",
                limit=size,
            )
            indexes = list(range(len(statements)))
            if selected_statement is not None:
                indexes.remove(selected_statement)
                indexes.insert(0, selected_statement)

            raw_rows: Optional[list[dict[str, Any]]] = None
            last_error: Optional[Exception] = None
            for statement_index in indexes:
                try:
                    raw_rows = list(
                        _locked_call(
                            rt_conn,
                            exec_query,
                            rt_conn.handle,
                            kind="message",
                            path=str(db_path),
                            sql=statements[statement_index],
                        )
                        or []
                    )
                    selected_statement = statement_index
                    break
                except Exception as exc:
                    last_error = exc

            if raw_rows is None:
                raise RealtimeMessageReadError(
                    f"Cannot query realtime table {db_path.name}/{table_name}: {last_error or 'unknown error'}"
                )
            if not raw_rows:
                break
            if len(raw_rows) > size:
                raise RealtimeMessageReadError(
                    f"Realtime query exceeded bounded page size for {db_path.name}/{table_name}: "
                    f"received {len(raw_rows)}, limit {size}"
                )

            page_rows = [row for row in raw_rows if isinstance(row, dict)]
            if not page_rows:
                raise RealtimeMessageReadError(
                    f"Realtime query returned malformed rows for {db_path.name}/{table_name}"
                )
            page_rows.sort(key=row_key)
            next_boundary = row_key(page_rows[-1])
            if boundary is not None and next_boundary <= boundary:
                raise RealtimeMessageReadError(
                    f"Realtime pagination did not advance for {db_path.name}/{table_name} at {boundary}"
                )

            if first_db_path is None:
                first_db_path = db_path
                first_table_name = table_name
                first_my_rowid = my_rowid

            for raw in page_rows:
                item = normalize_item(raw)
                if not isinstance(item, dict):
                    continue
                item["_db_path"] = str(db_path)
                item["db_name"] = db_path.name
                item["table_name"] = table_name
                if my_rowid is not None:
                    item["__my_rowid"] = int(my_rowid)
                    item.setdefault("debug_my_rowid", int(my_rowid))
                    real_sender_id = _to_int(_pick(item, "real_sender_id", "realSenderId"))
                    if real_sender_id > 0:
                        item.setdefault("computed_is_send", int(real_sender_id == int(my_rowid)))
                all_rows.append(item)

            boundary = next_boundary
            if len(raw_rows) < size:
                break

    all_rows.sort(
        key=lambda row: (
            _to_int(_pick(row, "create_time", "createTime")),
            _to_int(_pick(row, "sort_seq", "sortSeq")),
            _to_int(_pick(row, "local_id", "localId")),
            str(_pick(row, "_db_path") or ""),
        )
    )
    return RealtimeMessageBatch(
        all_rows,
        False,
        "exec_paged",
        authoritative,
        db_path=first_db_path,
        table_name=first_table_name,
        my_rowid=first_my_rowid,
        tables_found=len(resolved),
        databases_probed=probed,
        diagnostics=tuple(diagnostics),
    )


def fetch_rows_via_cursor(
    *,
    rt_conn: Any,
    username: str,
    take: int,
    open_cursor: OpenCursor,
    fetch_batch: FetchCursorBatch,
    close_cursor: CloseCursor,
    normalize_item: NormalizeItem,
) -> RealtimeMessageBatch:
    take = int(take)
    if take <= 0:
        return RealtimeMessageBatch([], False, "cursor", True)
    cursor = _locked_call(
        rt_conn,
        open_cursor,
        rt_conn.handle,
        username,
        batch_size=max(1, min(take + 1, 500)),
        ascending=False,
        begin_timestamp=0,
        end_timestamp=0,
        lite=False,
    )
    if int(cursor or 0) <= 0:
        return RealtimeMessageBatch([], False, "cursor", False)

    rows: list[dict[str, Any]] = []
    has_more = False
    try:
        empty_with_more = 0
        while len(rows) <= take:
            batch, batch_has_more = _locked_call(rt_conn, fetch_batch, rt_conn.handle, int(cursor))
            has_more = bool(batch_has_more)
            if not batch:
                if batch_has_more and empty_with_more < 2:
                    empty_with_more += 1
                    continue
                break
            empty_with_more = 0
            for raw in batch:
                if not isinstance(raw, dict):
                    continue
                item = normalize_item(raw)
                if not isinstance(item, dict) or _to_int(_pick(item, "local_id", "localId")) <= 0:
                    continue
                rows.append(item)
                if len(rows) > take:
                    break
            if len(rows) > take or not batch_has_more:
                break
    finally:
        try:
            _locked_call(rt_conn, close_cursor, rt_conn.handle, int(cursor))
        except Exception:
            pass
    return RealtimeMessageBatch(rows[:take], bool(has_more or len(rows) > take), "cursor", True)


def read_all_realtime_message_rows(
    *,
    rt_conn: Any,
    account_dir: Path,
    username: str,
    db_storage_dir: Optional[Path],
    exec_query: ExecQuery,
    open_cursor: OpenCursor,
    fetch_batch: FetchCursorBatch,
    close_cursor: CloseCursor,
    get_messages: GetMessages,
    normalize_item: NormalizeItem,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    local_types: Optional[set[int]] = None,
    initial_take: int = 1000,
) -> RealtimeMessageBatch:
    diagnostics: list[str] = []
    exec_empty: Optional[RealtimeMessageBatch] = None
    exec_partial = False
    try:
        batch = fetch_all_rows_via_exec_paged(
            rt_conn=rt_conn,
            account_dir=account_dir,
            username=username,
            db_storage_dir=db_storage_dir,
            exec_query=exec_query,
            normalize_item=normalize_item,
            start_time=start_time,
            end_time=end_time,
            local_types=local_types,
            page_size=initial_take,
        )
        diagnostics.extend(batch.diagnostics)
        if batch.tables_found > 0:
            if batch.authoritative:
                result = batch
            else:
                exec_partial = True
                diagnostics.append("exec: one or more realtime message databases could not be probed")
                result = None
        else:
            if batch.authoritative:
                exec_empty = batch
            result = None
    except Exception as exc:
        diagnostics.append(f"exec: {exc}")
        result = None

    if result is None and exec_empty is None:
        take = max(1, int(initial_take))
        try:
            while True:
                batch = fetch_rows_via_cursor(
                    rt_conn=rt_conn,
                    username=username,
                    take=take,
                    open_cursor=open_cursor,
                    fetch_batch=fetch_batch,
                    close_cursor=close_cursor,
                    normalize_item=normalize_item,
                )
                if not batch.authoritative:
                    break
                if not batch.has_more:
                    result = batch
                    break
                if take >= 2_000_000_000:
                    raise RealtimeMessageReadError("Realtime conversation exceeds the supported message count.")
                take = min(take * 2, 2_000_000_000)
        except Exception as exc:
            diagnostics.append(f"cursor: {exc}")

    if result is None and exec_empty is None and not exec_partial:
        rows: list[dict[str, Any]] = []
        offset = 0
        batch_size = max(1, int(initial_take))
        try:
            while True:
                raw_rows = _locked_call(
                    rt_conn,
                    get_messages,
                    rt_conn.handle,
                    username,
                    limit=batch_size,
                    offset=offset,
                )
                if not raw_rows:
                    break
                for raw in raw_rows:
                    if isinstance(raw, dict):
                        item = normalize_item(raw)
                        if isinstance(item, dict):
                            rows.append(item)
                offset += len(raw_rows)
                if len(raw_rows) < batch_size:
                    break
        except Exception as exc:
            diagnostics.append(f"native: {exc}")
        if rows:
            result = RealtimeMessageBatch(rows, False, "native", True)

    if result is None:
        if exec_empty is not None:
            result = exec_empty
        else:
            detail = "; ".join(diagnostics[-5:]) or "no realtime reader returned an authoritative result"
            raise RealtimeMessageReadError(
                f"Unable to read realtime messages for {username}; refusing to export an unverified empty result: {detail}"
            )

    wanted_types = {int(value) for value in (local_types or set()) if int(value) != 0} if local_types else None
    filtered: list[dict[str, Any]] = []
    for item in result.rows:
        create_time = _to_int(_pick(item, "create_time", "createTime"))
        local_type = _to_int(_pick(item, "local_type", "localType", "type"))
        if wanted_types and local_type not in wanted_types:
            continue
        if start_time is not None and create_time < int(start_time):
            continue
        if end_time is not None and create_time > int(end_time):
            continue
        filtered.append(item)
    filtered.sort(
        key=lambda row: (
            _to_int(_pick(row, "create_time", "createTime")),
            _to_int(_pick(row, "sort_seq", "sortSeq")),
            _to_int(_pick(row, "local_id", "localId")),
            str(_pick(row, "_db_path") or ""),
        )
    )
    return replace(result, rows=filtered, has_more=False, diagnostics=tuple(dict.fromkeys(diagnostics)))
