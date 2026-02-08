from __future__ import annotations

import hashlib
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ...chat_search_index import get_chat_search_index_db_path
from ...chat_helpers import (
    _build_avatar_url,
    _iter_message_db_paths,
    _load_contact_rows,
    _pick_display_name,
    _quote_ident,
    _row_to_search_hit,
)
from ...logging_config import get_logger

logger = get_logger(__name__)


_WEEKDAY_LABELS_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
_HOUR_LABELS = [f"{h:02d}" for h in range(24)]

_MD5_HEX_RE = re.compile(r"(?i)[0-9a-f]{32}")


@dataclass(frozen=True)
class WeekdayHourHeatmap:
    weekday_labels: list[str]
    hour_labels: list[str]
    matrix: list[list[int]]  # 7 x 24, weekday major (Mon..Sun) then hour
    total_messages: int


@dataclass(frozen=True)
class _SentMomentRef:
    """Lightweight reference to a sent message (for earliest/latest moment extraction)."""

    ts: int
    score: int
    username: str
    db_stem: str
    table_name: str
    local_id: int


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


def _mask_name(name: str) -> str:
    s = str(name or "").strip()
    if not s:
        return ""
    if len(s) == 1:
        return "*"
    if len(s) == 2:
        return s[0] + "*"
    return s[0] + ("*" * (len(s) - 2)) + s[-1]


def _list_session_usernames(session_db_path: Path) -> list[str]:
    if not session_db_path.exists():
        return []

    conn = sqlite3.connect(str(session_db_path))
    try:
        try:
            rows = conn.execute("SELECT username FROM SessionTable").fetchall()
        except sqlite3.OperationalError:
            rows = conn.execute("SELECT username FROM Session").fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()

    out: list[str] = []
    for r in rows:
        if not r or not r[0]:
            continue
        u = str(r[0]).strip()
        if u:
            out.append(u)
    return out


def _compute_year_first_last_from_index(
    *,
    account_dir: Path,
    year: int,
    sender_username: str,
) -> tuple[Optional[_SentMomentRef], Optional[_SentMomentRef]]:
    """Find the chronologically first and last sent messages of the year (by timestamp)."""
    start_ts, end_ts = _year_range_epoch_seconds(year)
    sender = str(sender_username or "").strip()
    if not sender:
        return None, None

    index_path = get_chat_search_index_db_path(account_dir)
    if not index_path.exists():
        return None, None

    conn = sqlite3.connect(str(index_path))
    try:
        has_fts = (
            conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='message_fts' LIMIT 1").fetchone()
            is not None
        )
        if not has_fts:
            return None, None

        ts_expr = (
            "CASE "
            "WHEN CAST(create_time AS INTEGER) > 1000000000000 "
            "THEN CAST(CAST(create_time AS INTEGER)/1000 AS INTEGER) "
            "ELSE CAST(create_time AS INTEGER) "
            "END"
        )

        where = (
            f"{ts_expr} >= ? AND {ts_expr} < ? "
            "AND db_stem NOT LIKE 'biz_message%' "
            "AND sender_username = ? "
            "AND CAST(local_type AS INTEGER) != 10000"
        )

        base_sql = (
            f"SELECT {ts_expr} AS ts, username, db_stem, table_name, CAST(local_id AS INTEGER) AS local_id "
            "FROM message_fts "
            f"WHERE {where} "
        )

        def row_to_ref(r: Any) -> Optional[_SentMomentRef]:
            if not r:
                return None
            try:
                ts = int(r[0] or 0)
            except Exception:
                ts = 0
            username = str(r[1] or "").strip()
            db_stem = str(r[2] or "").strip()
            table_name = str(r[3] or "").strip()
            try:
                local_id = int(r[4] or 0)
            except Exception:
                local_id = 0

            if ts <= 0 or not username or not db_stem or not table_name or local_id <= 0:
                return None

            return _SentMomentRef(
                ts=int(ts),
                score=0,  # Not used for chronological ordering
                username=username,
                db_stem=db_stem,
                table_name=table_name,
                local_id=int(local_id),
            )

        params = (start_ts, end_ts, sender)
        sql_first = base_sql + "ORDER BY ts ASC LIMIT 1"
        sql_last = base_sql + "ORDER BY ts DESC LIMIT 1"

        first_ref = row_to_ref(conn.execute(sql_first, params).fetchone())
        last_ref = row_to_ref(conn.execute(sql_last, params).fetchone())
        return first_ref, last_ref
    except Exception:
        return None, None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _compute_year_first_last_fallback(
    *,
    account_dir: Path,
    year: int,
    sender_username: str,
) -> tuple[Optional[_SentMomentRef], Optional[_SentMomentRef]]:
    """Fallback: find chronologically first/last sent messages when no search index."""
    start_ts, end_ts = _year_range_epoch_seconds(year)
    sender = str(sender_username or "").strip()
    if not sender:
        return None, None

    session_usernames = _list_session_usernames(account_dir / "session.db")
    md5_to_username: dict[str, str] = {}
    table_to_username: dict[str, str] = {}
    for u in session_usernames:
        md5_hex = hashlib.md5(u.encode("utf-8")).hexdigest().lower()
        md5_to_username[md5_hex] = u
        table_to_username[f"msg_{md5_hex}"] = u
        table_to_username[f"chat_{md5_hex}"] = u

    def resolve_username_from_table(table_name: str) -> Optional[str]:
        ln = str(table_name or "").lower()
        u = table_to_username.get(ln)
        if u:
            return u
        m = _MD5_HEX_RE.search(ln)
        if m:
            return md5_to_username.get(m.group(0).lower())
        return None

    db_paths = _iter_message_db_paths(account_dir)
    db_paths = [p for p in db_paths if not p.name.lower().startswith("biz_message")]

    ts_expr = (
        "CASE WHEN create_time > 1000000000000 THEN CAST(create_time/1000 AS INTEGER) ELSE create_time END"
    )

    best_first: Optional[_SentMomentRef] = None
    best_last: Optional[_SentMomentRef] = None

    for db_path in db_paths:
        if not db_path.exists():
            continue

        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            conn.text_factory = bytes

            try:
                r2 = conn.execute("SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1", (sender,)).fetchone()
                sender_rowid = int(r2[0]) if r2 and r2[0] is not None else None
            except Exception:
                sender_rowid = None
            if sender_rowid is None:
                continue

            tables = _list_message_tables(conn)
            if not tables:
                continue

            for table_name in tables:
                username = resolve_username_from_table(table_name)
                if not username:
                    continue

                qt = _quote_ident(table_name)
                params = (start_ts, end_ts, int(sender_rowid))

                sql_base = (
                    f"SELECT local_id, {ts_expr} AS ts "
                    f"FROM {qt} "
                    f"WHERE {ts_expr} >= ? AND {ts_expr} < ? "
                    "AND real_sender_id = ? "
                    "AND local_type != 10000 "
                )
                sql_first = sql_base + "ORDER BY ts ASC LIMIT 1"
                sql_last = sql_base + "ORDER BY ts DESC LIMIT 1"

                try:
                    r_first = conn.execute(sql_first, params).fetchone()
                except Exception:
                    r_first = None
                if r_first:
                    try:
                        local_id = int(r_first["local_id"] or 0)
                        ts = int(r_first["ts"] or 0)
                    except Exception:
                        local_id, ts = 0, 0
                    if local_id > 0 and ts > 0:
                        ref = _SentMomentRef(
                            ts=int(ts),
                            score=0,
                            username=str(username),
                            db_stem=str(db_path.stem),
                            table_name=str(table_name),
                            local_id=int(local_id),
                        )
                        if best_first is None or ref.ts < best_first.ts:
                            best_first = ref

                try:
                    r_last = conn.execute(sql_last, params).fetchone()
                except Exception:
                    r_last = None
                if r_last:
                    try:
                        local_id = int(r_last["local_id"] or 0)
                        ts = int(r_last["ts"] or 0)
                    except Exception:
                        local_id, ts = 0, 0
                    if local_id > 0 and ts > 0:
                        ref = _SentMomentRef(
                            ts=int(ts),
                            score=0,
                            username=str(username),
                            db_stem=str(db_path.stem),
                            table_name=str(table_name),
                            local_id=int(local_id),
                        )
                        if best_last is None or ref.ts > best_last.ts:
                            best_last = ref
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass

    return best_first, best_last


def _compute_sent_moment_refs_from_index(
    *,
    account_dir: Path,
    year: int,
    sender_username: str,
) -> tuple[Optional[_SentMomentRef], Optional[_SentMomentRef]]:
    start_ts, end_ts = _year_range_epoch_seconds(year)
    sender = str(sender_username or "").strip()
    if not sender:
        return None, None

    index_path = get_chat_search_index_db_path(account_dir)
    if not index_path.exists():
        return None, None

    conn = sqlite3.connect(str(index_path))
    try:
        has_fts = (
            conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='message_fts' LIMIT 1").fetchone()
            is not None
        )
        if not has_fts:
            return None, None

        # Convert millisecond timestamps defensively (some datasets store ms).
        ts_expr = (
            "CASE "
            "WHEN CAST(create_time AS INTEGER) > 1000000000000 "
            "THEN CAST(CAST(create_time AS INTEGER)/1000 AS INTEGER) "
            "ELSE CAST(create_time AS INTEGER) "
            "END"
        )

        # NOTE: local_type=10000 are mostly system messages; exclude to make the moment nicer.
        where = (
            f"{ts_expr} >= ? AND {ts_expr} < ? "
            "AND db_stem NOT LIKE 'biz_message%' "
            "AND sender_username = ? "
            "AND CAST(local_type AS INTEGER) != 10000"
        )

        base_sql = (
            "SELECT ts, username, db_stem, table_name, CAST(local_id AS INTEGER) AS local_id, "
            "CAST(strftime('%H', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) AS h, "
            "CAST(strftime('%M', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) AS m, "
            "CAST(strftime('%S', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) AS s "
            "FROM ("
            f"  SELECT {ts_expr} AS ts, username, db_stem, table_name, local_id "
            "  FROM message_fts "
            f"  WHERE {where}"
            ") sub "
        )

        def row_to_ref(r: Any) -> Optional[_SentMomentRef]:
            if not r:
                return None
            try:
                ts = int(r[0] or 0)
            except Exception:
                ts = 0
            username = str(r[1] or "").strip()
            db_stem = str(r[2] or "").strip()
            table_name = str(r[3] or "").strip()
            try:
                local_id = int(r[4] or 0)
            except Exception:
                local_id = 0
            try:
                h = int(r[5] or 0)
                m = int(r[6] or 0)
                s = int(r[7] or 0)
            except Exception:
                h, m, s = 0, 0, 0

            if ts <= 0 or not username or not db_stem or not table_name or local_id <= 0:
                return None

            # Treat 00:00-04:59 as "late night": shift them +24h so they rank after 23:xx.
            score = (h * 3600 + m * 60 + s) + (86400 if h < 5 else 0)

            return _SentMomentRef(
                ts=int(ts),
                score=int(score),
                username=username,
                db_stem=db_stem,
                table_name=table_name,
                local_id=int(local_id),
            )

        params = (start_ts, end_ts, sender)
        sql_earliest = (
            base_sql
            + "ORDER BY (h*3600 + m*60 + s + CASE WHEN h < 5 THEN 86400 ELSE 0 END) ASC, ts ASC LIMIT 1"
        )
        sql_latest = (
            base_sql
            + "ORDER BY (h*3600 + m*60 + s + CASE WHEN h < 5 THEN 86400 ELSE 0 END) DESC, ts DESC LIMIT 1"
        )

        earliest_ref = row_to_ref(conn.execute(sql_earliest, params).fetchone())
        latest_ref = row_to_ref(conn.execute(sql_latest, params).fetchone())
        return earliest_ref, latest_ref
    except Exception:
        return None, None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _compute_sent_moment_refs_fallback(
    *,
    account_dir: Path,
    year: int,
    sender_username: str,
) -> tuple[Optional[_SentMomentRef], Optional[_SentMomentRef]]:
    """Fallback implementation when no search index is present."""

    start_ts, end_ts = _year_range_epoch_seconds(year)
    sender = str(sender_username or "").strip()
    if not sender:
        return None, None

    # Resolve all sessions (usernames) so we can map msg_xxx/chat_xxx tables back to usernames.
    session_usernames = _list_session_usernames(account_dir / "session.db")
    md5_to_username: dict[str, str] = {}
    table_to_username: dict[str, str] = {}
    for u in session_usernames:
        md5_hex = hashlib.md5(u.encode("utf-8")).hexdigest().lower()
        md5_to_username[md5_hex] = u
        table_to_username[f"msg_{md5_hex}"] = u
        table_to_username[f"chat_{md5_hex}"] = u

    def resolve_username_from_table(table_name: str) -> Optional[str]:
        ln = str(table_name or "").lower()
        u = table_to_username.get(ln)
        if u:
            return u
        m = _MD5_HEX_RE.search(ln)
        if m:
            return md5_to_username.get(m.group(0).lower())
        return None

    db_paths = _iter_message_db_paths(account_dir)
    db_paths = [p for p in db_paths if not p.name.lower().startswith("biz_message")]

    ts_expr = (
        "CASE WHEN create_time > 1000000000000 THEN CAST(create_time/1000 AS INTEGER) ELSE create_time END"
    )

    best_earliest: Optional[_SentMomentRef] = None
    best_latest: Optional[_SentMomentRef] = None

    for db_path in db_paths:
        if not db_path.exists():
            continue

        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            conn.text_factory = bytes

            # Resolve sender rowid for this shard so we can filter sent messages.
            try:
                r2 = conn.execute("SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1", (sender,)).fetchone()
                sender_rowid = int(r2[0]) if r2 and r2[0] is not None else None
            except Exception:
                sender_rowid = None
            if sender_rowid is None:
                continue

            tables = _list_message_tables(conn)
            if not tables:
                continue

            for table_name in tables:
                username = resolve_username_from_table(table_name)
                if not username:
                    continue

                qt = _quote_ident(table_name)
                params = (start_ts, end_ts, int(sender_rowid))

                sql_base = (
                    "SELECT local_id, ts, "
                    "CAST(strftime('%H', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) AS h, "
                    "CAST(strftime('%M', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) AS m, "
                    "CAST(strftime('%S', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) AS s "
                    "FROM ("
                    f"  SELECT local_id, {ts_expr} AS ts "
                    f"  FROM {qt} "
                    f"  WHERE {ts_expr} >= ? AND {ts_expr} < ? "
                    "    AND real_sender_id = ? "
                    "    AND local_type != 10000"
                    ") sub "
                )
                sql_earliest = (
                    sql_base
                    + "ORDER BY (h*3600 + m*60 + s + CASE WHEN h < 5 THEN 86400 ELSE 0 END) ASC, ts ASC LIMIT 1"
                )
                sql_latest = (
                    sql_base
                    + "ORDER BY (h*3600 + m*60 + s + CASE WHEN h < 5 THEN 86400 ELSE 0 END) DESC, ts DESC LIMIT 1"
                )

                try:
                    r_earliest = conn.execute(sql_earliest, params).fetchone()
                except Exception:
                    r_earliest = None
                if r_earliest:
                    try:
                        local_id = int(r_earliest["local_id"] or 0)
                        ts = int(r_earliest["ts"] or 0)
                        h = int(r_earliest["h"] or 0)
                        m = int(r_earliest["m"] or 0)
                        s = int(r_earliest["s"] or 0)
                    except Exception:
                        local_id, ts, h, m, s = 0, 0, 0, 0, 0
                    if local_id > 0 and ts > 0:
                        score = (h * 3600 + m * 60 + s) + (86400 if h < 5 else 0)
                        ref = _SentMomentRef(
                            ts=int(ts),
                            score=int(score),
                            username=str(username),
                            db_stem=str(db_path.stem),
                            table_name=str(table_name),
                            local_id=int(local_id),
                        )
                        if best_earliest is None or ref.score < best_earliest.score or (
                            ref.score == best_earliest.score and ref.ts < best_earliest.ts
                        ):
                            best_earliest = ref

                try:
                    r_latest = conn.execute(sql_latest, params).fetchone()
                except Exception:
                    r_latest = None
                if r_latest:
                    try:
                        local_id = int(r_latest["local_id"] or 0)
                        ts = int(r_latest["ts"] or 0)
                        h = int(r_latest["h"] or 0)
                        m = int(r_latest["m"] or 0)
                        s = int(r_latest["s"] or 0)
                    except Exception:
                        local_id, ts, h, m, s = 0, 0, 0, 0, 0
                    if local_id > 0 and ts > 0:
                        score = (h * 3600 + m * 60 + s) + (86400 if h < 5 else 0)
                        ref = _SentMomentRef(
                            ts=int(ts),
                            score=int(score),
                            username=str(username),
                            db_stem=str(db_path.stem),
                            table_name=str(table_name),
                            local_id=int(local_id),
                        )
                        if best_latest is None or ref.score > best_latest.score or (
                            ref.score == best_latest.score and ref.ts > best_latest.ts
                        ):
                            best_latest = ref
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass

    return best_earliest, best_latest


def _fetch_message_moment_payload(
    *,
    account_dir: Path,
    ref: _SentMomentRef,
    contact_rows: dict[str, sqlite3.Row],
) -> Optional[dict[str, Any]]:
    """Resolve ref -> a payload for the frontend card (content is blurred in UI)."""

    username = str(ref.username or "").strip()
    if not username:
        return None

    db_path = account_dir / f"{ref.db_stem}.db"
    if not db_path.exists():
        return None

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.text_factory = bytes

        my_rowid: Optional[int]
        try:
            r2 = conn.execute("SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1", (str(account_dir.name),)).fetchone()
            my_rowid = int(r2[0]) if r2 and r2[0] is not None else None
        except Exception:
            my_rowid = None

        qt = _quote_ident(ref.table_name)
        sql_with_join = (
            "SELECT "
            "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
            "m.message_content, m.compress_content, n.user_name AS sender_username "
            f"FROM {qt} m "
            "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
            "WHERE m.local_id = ? LIMIT 1"
        )
        sql_no_join = (
            "SELECT "
            "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
            "m.message_content, m.compress_content, '' AS sender_username "
            f"FROM {qt} m "
            "WHERE m.local_id = ? LIMIT 1"
        )

        try:
            row = conn.execute(sql_with_join, (int(ref.local_id),)).fetchone()
        except Exception:
            row = None
        if row is None:
            try:
                row = conn.execute(sql_no_join, (int(ref.local_id),)).fetchone()
            except Exception:
                row = None
        if row is None:
            return None

        hit = _row_to_search_hit(
            row,
            db_path=db_path,
            table_name=str(ref.table_name),
            username=username,
            account_dir=account_dir,
            is_group=bool(username.endswith("@chatroom")),
            my_rowid=my_rowid,
        )

        content = str(hit.get("content") or "").strip()
        content = re.sub(r"\s+", " ", content).strip()
        if len(content) > 120:
            content = content[:117] + "..."

        dt = datetime.fromtimestamp(int(ref.ts))

        contact_row = contact_rows.get(username)
        display = _pick_display_name(contact_row, username)
        avatar = _build_avatar_url(str(account_dir.name or ""), username) if username else ""

        return {
            "timestamp": int(ref.ts),
            "date": dt.strftime("%Y-%m-%d"),
            "time": dt.strftime("%H:%M"),
            "username": username,
            "displayName": display,
            "maskedName": _mask_name(display),
            "avatarUrl": avatar,
            "content": content,
            "renderType": str(hit.get("renderType") or ""),
            "isGroup": bool(username.endswith("@chatroom")),
        }
    except Exception:
        return None
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


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

    # Earliest/latest sent message moments (best-effort).
    earliest_sent = None
    latest_sent = None
    if heatmap.total_messages > 0:
        t0 = time.time()
        ref_earliest, ref_latest = _compute_sent_moment_refs_from_index(
            account_dir=account_dir,
            year=year,
            sender_username=sender,
        )
        if ref_earliest is None and ref_latest is None:
            ref_earliest, ref_latest = _compute_sent_moment_refs_fallback(
                account_dir=account_dir,
                year=year,
                sender_username=sender,
            )

        usernames: list[str] = []
        if ref_earliest and ref_earliest.username:
            usernames.append(ref_earliest.username)
        if ref_latest and ref_latest.username and ref_latest.username not in usernames:
            usernames.append(ref_latest.username)
        contact_rows = _load_contact_rows(account_dir / "contact.db", usernames) if usernames else {}

        if ref_earliest is not None:
            earliest_sent = _fetch_message_moment_payload(account_dir=account_dir, ref=ref_earliest, contact_rows=contact_rows)
        if ref_latest is not None:
            latest_sent = _fetch_message_moment_payload(account_dir=account_dir, ref=ref_latest, contact_rows=contact_rows)

        logger.info(
            "Wrapped card#1 moments computed: account=%s year=%s earliest=%s latest=%s elapsed=%.2fs",
            str(account_dir.name or "").strip(),
            year,
            "ok" if earliest_sent else "none",
            "ok" if latest_sent else "none",
            time.time() - t0,
        )

    # Year's chronologically first/last sent messages (by timestamp, not time-of-day).
    year_first_sent = None
    year_last_sent = None
    if heatmap.total_messages > 0:
        t0 = time.time()
        ref_first, ref_last = _compute_year_first_last_from_index(
            account_dir=account_dir,
            year=year,
            sender_username=sender,
        )
        if ref_first is None and ref_last is None:
            ref_first, ref_last = _compute_year_first_last_fallback(
                account_dir=account_dir,
                year=year,
                sender_username=sender,
            )

        # Collect usernames for contact lookup (reuse existing contact_rows if possible).
        extra_usernames: list[str] = []
        if ref_first and ref_first.username:
            extra_usernames.append(ref_first.username)
        if ref_last and ref_last.username and ref_last.username not in extra_usernames:
            extra_usernames.append(ref_last.username)
        # Load contacts for new usernames not already in contact_rows.
        new_usernames = [u for u in extra_usernames if u not in contact_rows]
        if new_usernames:
            extra_contacts = _load_contact_rows(account_dir / "contact.db", new_usernames)
            contact_rows.update(extra_contacts)

        if ref_first is not None:
            year_first_sent = _fetch_message_moment_payload(account_dir=account_dir, ref=ref_first, contact_rows=contact_rows)
        if ref_last is not None:
            year_last_sent = _fetch_message_moment_payload(account_dir=account_dir, ref=ref_last, contact_rows=contact_rows)

        logger.info(
            "Wrapped card#1 year first/last computed: account=%s year=%s first=%s last=%s elapsed=%.2fs",
            str(account_dir.name or "").strip(),
            year,
            "ok" if year_first_sent else "none",
            "ok" if year_last_sent else "none",
            time.time() - t0,
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
            "earliestSent": earliest_sent,
            "latestSent": latest_sent,
            "yearFirstSent": year_first_sent,
            "yearLastSent": year_last_sent,
        },
    }
