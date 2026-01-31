from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ...chat_search_index import get_chat_search_index_db_path
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


def _get_time_personality(hour: int) -> str:
    if 5 <= hour <= 8:
        return "early_bird"
    if 9 <= hour <= 12:
        return "office_worker"
    if 13 <= hour <= 17:
        return "afternoon"
    if 18 <= hour <= 23:
        return "night_owl"
    if 0 <= hour <= 4:
        return "late_night"
    return "unknown"


def _get_weekday_name(weekday_index: int) -> str:
    if 0 <= weekday_index < len(_WEEKDAY_LABELS_ZH):
        return _WEEKDAY_LABELS_ZH[weekday_index]
    return ""


def _build_narrative(*, hour: int, weekday: str, total: int) -> str:
    personality = _get_time_personality(hour)

    templates: dict[str, str] = {
        "early_bird": (
            f"清晨 {hour:02d}:00，当城市还在沉睡，你已经开始了新一天的问候。"
            f"{weekday}是你最健谈的一天，这一年你用 {total:,} 条消息记录了这些早起时光。"
        ),
        "office_worker": (
            f"忙碌的上午 {hour:02d}:00，是你最常敲击键盘的时刻。"
            f"{weekday}最活跃，这一年你用 {total:,} 条消息把工作与生活都留在了对话里。"
        ),
        "afternoon": (
            f"午后的阳光里，{hour:02d}:00 是你最爱分享的时刻。"
            f"{weekday}的聊天最热闹，这一年共 {total:,} 条消息串起了你的午后时光。"
        ),
        "night_owl": (
            f"夜幕降临，{hour:02d}:00 是你最常出没的时刻。"
            f"{weekday}最活跃，这一年 {total:,} 条消息陪你把每个夜晚都聊得更亮。"
        ),
        "late_night": (
            f"当世界沉睡，凌晨 {hour:02d}:00 的你依然在线。"
            f"{weekday}最活跃，这一年 {total:,} 条深夜消息，是你与这个世界的悄悄话。"
        ),
    }
    return templates.get(personality, f"你在 {hour:02d}:00 最活跃")


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
    sender_username: str | None = None,
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

        # Optional sender filter (best-effort). When provided, we only count
        # messages whose `real_sender_id` maps to `sender_username`.
        sender_rowid: int | None = None
        if sender_username and str(sender_username).strip():
            try:
                r = conn.execute(
                    "SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1",
                    (str(sender_username).strip(),),
                ).fetchone()
                if r is not None and r[0] is not None:
                    sender_rowid = int(r[0])
            except Exception:
                sender_rowid = None

        counted = 0
        for table_name in tables:
            qt = _quote_ident(table_name)
            sender_where = ""
            params: tuple[Any, ...]
            if sender_rowid is not None:
                sender_where = " AND real_sender_id = ?"
                params = (start_ts, end_ts, sender_rowid)
            else:
                params = (start_ts, end_ts)
            sql = (
                "SELECT "
                # %w: 0..6 with Sunday=0, so shift to Monday=0..Sunday=6
                "((CAST(strftime('%w', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) + 6) % 7) AS weekday, "
                "CAST(strftime('%H', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) AS hour, "
                "COUNT(1) AS cnt "
                "FROM ("
                f"  SELECT {ts_expr} AS ts"
                f"  FROM {qt}"
                f"  WHERE {ts_expr} >= ? AND {ts_expr} < ?{sender_where}"
                ") sub "
                "GROUP BY weekday, hour"
            )
            try:
                rows = conn.execute(sql, params).fetchall()
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


def compute_weekday_hour_heatmap(*, account_dir: Path, year: int, sender_username: str | None = None) -> WeekdayHourHeatmap:
    start_ts, end_ts = _year_range_epoch_seconds(year)

    matrix: list[list[int]] = [[0 for _ in range(24)] for _ in range(7)]
    total = 0

    # Prefer using our unified search index if available; it's much faster than scanning all msg tables.
    index_path = get_chat_search_index_db_path(account_dir)
    if index_path.exists():
        conn = sqlite3.connect(str(index_path))
        try:
            has_fts = (
                conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='message_fts' LIMIT 1"
                ).fetchone()
                is not None
            )
            if has_fts:
                # Convert millisecond timestamps defensively (some datasets store ms).
                ts_expr = (
                    "CASE "
                    "WHEN CAST(create_time AS INTEGER) > 1000000000000 "
                    "THEN CAST(CAST(create_time AS INTEGER)/1000 AS INTEGER) "
                    "ELSE CAST(create_time AS INTEGER) "
                    "END"
                )
                sender_clause = ""
                if sender_username and str(sender_username).strip():
                    sender_clause = "    AND sender_username = ?"
                sql = (
                    "SELECT "
                    "((CAST(strftime('%w', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) + 6) % 7) AS weekday, "
                    "CAST(strftime('%H', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) AS hour, "
                    "COUNT(1) AS cnt "
                    "FROM ("
                    f"  SELECT {ts_expr} AS ts"
                    "  FROM message_fts"
                    f"  WHERE {ts_expr} >= ? AND {ts_expr} < ?"
                    "    AND db_stem NOT LIKE 'biz_message%'"
                    f"{sender_clause}"
                    ") sub "
                    "GROUP BY weekday, hour"
                )

                t0 = time.time()
                try:
                    params: tuple[Any, ...] = (start_ts, end_ts)
                    if sender_username and str(sender_username).strip():
                        params = (start_ts, end_ts, str(sender_username).strip())
                    rows = conn.execute(sql, params).fetchall()
                except Exception:
                    rows = []

                for r in rows:
                    if not r:
                        continue
                    try:
                        w = int(r[0] or 0)
                        h = int(r[1] or 0)
                        cnt = int(r[2] or 0)
                    except Exception:
                        continue
                    if 0 <= w < 7 and 0 <= h < 24 and cnt > 0:
                        matrix[w][h] += cnt
                        total += cnt

                logger.info(
                    "Wrapped heatmap computed (search index): account=%s year=%s total=%s sender=%s db=%s elapsed=%.2fs",
                    str(account_dir.name or "").strip(),
                    year,
                    total,
                    str(sender_username).strip() if sender_username else "*",
                    str(index_path.name),
                    time.time() - t0,
                )

                return WeekdayHourHeatmap(
                    weekday_labels=list(_WEEKDAY_LABELS_ZH),
                    hour_labels=list(_HOUR_LABELS),
                    matrix=matrix,
                    total_messages=total,
                )
        finally:
            try:
                conn.close()
            except Exception:
                pass

    db_paths = _iter_message_db_paths(account_dir)
    # Default: exclude official/biz shards (biz_message*.db) to reduce noise.
    db_paths = [p for p in db_paths if not p.name.lower().startswith("biz_message")]
    my_wxid = str(account_dir.name or "").strip()
    t0 = time.time()
    for db_path in db_paths:
        total += _accumulate_db(
            db_path=db_path,
            start_ts=start_ts,
            end_ts=end_ts,
            matrix=matrix,
            sender_username=str(sender_username).strip() if sender_username else None,
        )

    logger.info(
        "Wrapped heatmap computed: account=%s year=%s total=%s sender=%s dbs=%s elapsed=%.2fs",
        my_wxid,
        year,
        total,
        str(sender_username).strip() if sender_username else "*",
        len(db_paths),
        time.time() - t0,
    )

    return WeekdayHourHeatmap(
        weekday_labels=list(_WEEKDAY_LABELS_ZH),
        hour_labels=list(_HOUR_LABELS),
        matrix=matrix,
        total_messages=total,
    )


def build_card_01_cyber_schedule(
    *,
    account_dir: Path,
    year: int,
    heatmap: WeekdayHourHeatmap | None = None,
) -> dict[str, Any]:
    """Card #1: 年度赛博作息表 (24x7 heatmap).

    `heatmap` can be provided by the caller to reuse computation across cards.
    """

    sender = str(account_dir.name or "").strip()
    heatmap = heatmap or compute_weekday_hour_heatmap(account_dir=account_dir, year=year, sender_username=sender)

    narrative = "今年你没有发出聊天消息"
    if heatmap.total_messages > 0:
        hour_totals = [sum(heatmap.matrix[w][h] for w in range(7)) for h in range(24)]
        # Deterministic: pick earliest hour on ties.
        most_active_hour = max(range(24), key=lambda h: (hour_totals[h], -h))

        weekday_totals = [sum(heatmap.matrix[w][h] for h in range(24)) for w in range(7)]
        # Deterministic: pick earliest weekday on ties.
        most_active_weekday = max(range(7), key=lambda w: (weekday_totals[w], -w))
        weekday_name = _get_weekday_name(most_active_weekday)

        narrative = _build_narrative(
            hour=most_active_hour,
            weekday=weekday_name,
            total=heatmap.total_messages,
        )

    return {
        "id": 1,
        "title": "你是「早八人」还是「夜猫子」？",
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
