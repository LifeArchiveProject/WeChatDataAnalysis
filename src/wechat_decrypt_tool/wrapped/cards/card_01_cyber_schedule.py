from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ...chat_helpers import _iter_message_db_paths, _quote_ident
from ...logging_config import get_logger

logger = get_logger(__name__)


_WEEKDAY_LABELS_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
_HOUR_LABELS = [f"{h:02d}" for h in range(24)]


@dataclass(frozen=True)
class WeekdayHourHeatmap:
    weekday_labels: list[str]
    hour_labels: list[str]
    matrix: list[list[int]]  # 7 x 24, weekday major (Mon..Sun) then hour
    total_messages: int


def _year_range_epoch_seconds(year: int) -> tuple[int, int]:
    # Use local time boundaries (same semantics as sqlite "localtime").
    start = int(datetime(year, 1, 1).timestamp())
    end = int(datetime(year + 1, 1, 1).timestamp())
    return start, end


def _list_message_tables(conn: sqlite3.Connection) -> list[str]:
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    except Exception:
        return []
    names: list[str] = []
    for r in rows:
        if not r or not r[0]:
            continue
        name = str(r[0])
        ln = name.lower()
        if ln.startswith(("msg_", "chat_")):
            names.append(name)
    return names


def _accumulate_db(
    *,
    db_path: Path,
    start_ts: int,
    end_ts: int,
    matrix: list[list[int]],
) -> int:
    """Accumulate message counts from one message shard DB into matrix.

    Returns the number of messages counted.
    """

    if not db_path.exists():
        return 0

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(db_path))

        tables = _list_message_tables(conn)
        if not tables:
            return 0

        # Convert millisecond timestamps defensively (some datasets store ms).
        # The expression yields epoch seconds as INTEGER.
        ts_expr = (
            "CASE WHEN create_time > 1000000000000 THEN CAST(create_time/1000 AS INTEGER) ELSE create_time END"
        )

        counted = 0
        for table_name in tables:
            qt = _quote_ident(table_name)
            sql = (
                "SELECT "
                # %w: 0..6 with Sunday=0, so shift to Monday=0..Sunday=6
                "((CAST(strftime('%w', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) + 6) % 7) AS weekday, "
                "CAST(strftime('%H', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) AS hour, "
                "COUNT(1) AS cnt "
                "FROM ("
                f"  SELECT {ts_expr} AS ts"
                f"  FROM {qt}"
                f"  WHERE {ts_expr} >= ? AND {ts_expr} < ?"
                ") sub "
                "GROUP BY weekday, hour"
            )
            try:
                rows = conn.execute(sql, (start_ts, end_ts)).fetchall()
            except Exception:
                continue

            for weekday, hour, cnt in rows:
                try:
                    w = int(weekday)
                    h = int(hour)
                    c = int(cnt)
                except Exception:
                    continue
                if not (0 <= w < 7 and 0 <= h < 24 and c > 0):
                    continue
                matrix[w][h] += c
                counted += c

        return counted
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def compute_weekday_hour_heatmap(*, account_dir: Path, year: int) -> WeekdayHourHeatmap:
    start_ts, end_ts = _year_range_epoch_seconds(year)

    matrix: list[list[int]] = [[0 for _ in range(24)] for _ in range(7)]
    total = 0

    db_paths = _iter_message_db_paths(account_dir)
    # Default: exclude official/biz shards (biz_message*.db) to reduce noise.
    db_paths = [p for p in db_paths if not p.name.lower().startswith("biz_message")]
    my_wxid = str(account_dir.name or "").strip()
    t0 = time.time()
    for db_path in db_paths:
        total += _accumulate_db(db_path=db_path, start_ts=start_ts, end_ts=end_ts, matrix=matrix)

    logger.info(
        "Wrapped card#1 heatmap computed: account=%s year=%s total=%s dbs=%s elapsed=%.2fs",
        my_wxid,
        year,
        total,
        len(db_paths),
        time.time() - t0,
    )

    return WeekdayHourHeatmap(
        weekday_labels=list(_WEEKDAY_LABELS_ZH),
        hour_labels=list(_HOUR_LABELS),
        matrix=matrix,
        total_messages=total,
    )


def build_card_01_cyber_schedule(*, account_dir: Path, year: int) -> dict[str, Any]:
    """Card #1: 年度赛博作息表 (24x7 heatmap)."""

    heatmap = compute_weekday_hour_heatmap(account_dir=account_dir, year=year)

    narrative = "今年你没有聊天消息"
    if heatmap.total_messages > 0:
        hour_totals = [sum(heatmap.matrix[w][h] for w in range(7)) for h in range(24)]
        # Deterministic: pick earliest hour on ties.
        most_active_hour = max(range(24), key=lambda h: (hour_totals[h], -h))
        narrative = f"你在 {most_active_hour:02d}:00 最活跃"

    return {
        "id": 1,
        "title": "年度赛博作息表",
        "scope": "global",
        "category": "A",
        "status": "ok",
        "kind": "time/weekday_hour_heatmap",
        "narrative": narrative,
        "data": {
            "weekdayLabels": heatmap.weekday_labels,
            "hourLabels": heatmap.hour_labels,
            "matrix": heatmap.matrix,
            "totalMessages": heatmap.total_messages,
        },
    }
