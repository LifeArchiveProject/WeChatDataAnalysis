from __future__ import annotations

import hashlib
import re
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from .card_01_cyber_schedule import WeekdayHourHeatmap, compute_weekday_hour_heatmap
from ...chat_search_index import get_chat_search_index_db_path
from ...chat_helpers import (
    _build_avatar_url,
    _decode_sqlite_text,
    _iter_message_db_paths,
    _load_contact_rows,
    _pick_display_name,
    _quote_ident,
    _should_keep_session,
    _to_char_token_text,
)
from ...logging_config import get_logger

logger = get_logger(__name__)


_MD5_HEX_RE = re.compile(r"(?i)[0-9a-f]{32}")
_EMOJI_CHAR_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")
# Best-effort heuristics for "new friends added" detection: WeChat system messages vary by version.
_ADDED_FRIEND_PATTERNS: tuple[str, ...] = (
    "你已添加了",
    "你添加了",
    "现在可以开始聊天了",
    "以上是打招呼的消息",
    "通过了你的朋友验证",
    "通过你的朋友验证",
)


@dataclass(frozen=True)
class GlobalOverviewStats:
    year: int
    active_days: int
    added_friends: int
    local_type_counts: dict[int, int]
    kind_counts: dict[str, int]
    latest_ts: int
    top_phrase: Optional[tuple[str, int]]
    top_emoji: Optional[tuple[str, int]]
    top_contact: Optional[tuple[str, int]]
    top_group: Optional[tuple[str, int]]


def _year_range_epoch_seconds(year: int) -> tuple[int, int]:
    # Keep the same semantics as other parts of the project: local time boundaries.
    start = int(datetime(year, 1, 1).timestamp())
    end = int(datetime(year + 1, 1, 1).timestamp())
    return start, end


def _days_in_year(year: int) -> int:
    try:
        return int((datetime(int(year) + 1, 1, 1) - datetime(int(year), 1, 1)).days)
    except Exception:
        return 365


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


def _accumulate_db_daily_counts(
    *,
    db_path: Path,
    start_ts: int,
    end_ts: int,
    counts: list[int],
    sender_username: str | None = None,
) -> int:
    """Accumulate per-day message counts from one message shard DB into counts list.

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

        # Convert millisecond timestamps defensively.
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
                "SELECT CAST(strftime('%j', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) - 1 AS doy, "
                "COUNT(1) AS cnt "
                "FROM ("
                f"  SELECT {ts_expr} AS ts"
                f"  FROM {qt}"
                f"  WHERE {ts_expr} >= ? AND {ts_expr} < ?{sender_where}"
                ") sub "
                "GROUP BY doy"
            )

            try:
                rows = conn.execute(sql, params).fetchall()
            except Exception:
                continue

            for doy, cnt in rows:
                try:
                    d = int(doy if doy is not None else -1)
                    c = int(cnt or 0)
                except Exception:
                    continue
                if c <= 0 or d < 0 or d >= len(counts):
                    continue
                counts[d] += c
                counted += c

        return counted
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def compute_annual_daily_counts(*, account_dir: Path, year: int, sender_username: str | None = None) -> list[int]:
    """Compute per-day message counts for the given year.

    The output is a 0-indexed day-of-year list (length 365/366). Counts default to
    "messages sent by me" when sender_username is provided.
    """

    start_ts, end_ts = _year_range_epoch_seconds(year)
    days = _days_in_year(year)
    counts: list[int] = [0 for _ in range(days)]

    sender = str(sender_username or "").strip()

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
                if sender:
                    sender_clause = "    AND sender_username = ?"

                sql = (
                    "SELECT "
                    "CAST(strftime('%j', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) - 1 AS doy, "
                    "COUNT(1) AS cnt "
                    "FROM ("
                    f"  SELECT {ts_expr} AS ts"
                    "  FROM message_fts"
                    f"  WHERE {ts_expr} >= ? AND {ts_expr} < ?"
                    "    AND db_stem NOT LIKE 'biz_message%'"
                    f"{sender_clause}"
                    ") sub "
                    "GROUP BY doy"
                )

                t0 = time.time()
                try:
                    params: tuple[Any, ...] = (start_ts, end_ts)
                    if sender:
                        params = (start_ts, end_ts, sender)
                    rows = conn.execute(sql, params).fetchall()
                except Exception:
                    rows = []

                total = 0
                for r in rows:
                    if not r:
                        continue
                    try:
                        doy = int(r[0] if r[0] is not None else -1)
                        cnt = int(r[1] or 0)
                    except Exception:
                        continue
                    if cnt <= 0 or doy < 0 or doy >= days:
                        continue
                    counts[doy] += cnt
                    total += cnt

                logger.info(
                    "Wrapped annual heatmap computed (search index): account=%s year=%s total=%s sender=%s db=%s elapsed=%.2fs",
                    str(account_dir.name or "").strip(),
                    year,
                    total,
                    sender or "*",
                    str(index_path.name),
                    time.time() - t0,
                )

                return counts
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
    total = 0
    for db_path in db_paths:
        total += _accumulate_db_daily_counts(
            db_path=db_path,
            start_ts=start_ts,
            end_ts=end_ts,
            counts=counts,
            sender_username=sender or None,
        )

    logger.info(
        "Wrapped annual heatmap computed: account=%s year=%s total=%s sender=%s dbs=%s elapsed=%.2fs",
        my_wxid,
        year,
        total,
        sender or "*",
        len(db_paths),
        time.time() - t0,
    )

    return counts


def _ymd_from_doy(*, year: int, doy: int) -> str:
    try:
        dt = datetime(int(year), 1, 1) + timedelta(days=int(doy))
    except Exception:
        return ""
    return dt.strftime("%Y-%m-%d")


def _best_doy_by_max(values: list[int]) -> tuple[int, int] | tuple[None, int]:
    best_doy: int | None = None
    best = 0
    for i, v in enumerate(values):
        try:
            n = int(v or 0)
        except Exception:
            n = 0
        if n > best or (n == best and best_doy is not None and i < best_doy):
            best = n
            best_doy = i
    return best_doy, best


def compute_annual_heatmap_highlights(
    *,
    account_dir: Path,
    year: int,
    sender_username: str,
    sent_daily_counts: list[int],
) -> list[dict[str, Any]]:
    """Compute special day highlights for the annual calendar heatmap (best-effort).

    We prefer the unified search index when available; fallback mode returns the subset
    that can be derived from `sent_daily_counts` without scanning all message content.
    """

    days = int(len(sent_daily_counts) or _days_in_year(year))
    out: list[dict[str, Any]] = []

    def add_highlight(
        *,
        key: str,
        label: str,
        doy: int,
        value: int | None = None,
        value_label: str = "",
        date: str = "",
    ) -> None:
        try:
            d = int(doy)
        except Exception:
            return
        if d < 0 or d >= days:
            return
        ymd = str(date or "") or _ymd_from_doy(year=int(year), doy=d)
        if not ymd:
            return
        obj: dict[str, Any] = {
            "key": str(key),
            "label": str(label),
            "doy": int(d),
            "date": ymd,
        }
        if value is not None:
            try:
                obj["value"] = int(value)
            except Exception:
                pass
        if value_label:
            obj["valueLabel"] = str(value_label)
        out.append(obj)

    # 3. Sent messages max day (always available from sent daily counts)
    best_doy, best_val = _best_doy_by_max(sent_daily_counts or [])
    if best_doy is not None and best_val > 0:
        add_highlight(key="sent_messages_max", label="发送消息条数最多的一天", doy=int(best_doy), value=int(best_val), value_label=f"{int(best_val)} 条")

    sender = str(sender_username or "").strip()
    if not sender:
        return out

    index_path = get_chat_search_index_db_path(account_dir)
    if not index_path.exists():
        return out

    start_ts, end_ts = _year_range_epoch_seconds(year)

    conn = sqlite3.connect(str(index_path))
    try:
        has_fts = (
            conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='message_fts' LIMIT 1").fetchone()
            is not None
        )
        if not has_fts:
            return out

        # Convert millisecond timestamps defensively (some datasets store ms).
        ts_expr = (
            "CASE "
            "WHEN CAST(create_time AS INTEGER) > 1000000000000 "
            "THEN CAST(CAST(create_time AS INTEGER)/1000 AS INTEGER) "
            "ELSE CAST(create_time AS INTEGER) "
            "END"
        )

        base_where = f"{ts_expr} >= ? AND {ts_expr} < ? AND db_stem NOT LIKE 'biz_message%'"
        base_params: tuple[Any, ...] = (start_ts, end_ts)

        def fetch_best_doy_value(sql: str, params: tuple[Any, ...]) -> tuple[int, int] | None:
            try:
                r = conn.execute(sql, params).fetchone()
            except Exception:
                r = None
            if not r:
                return None
            try:
                doy = int(r[0] if r[0] is not None else -1)
                val = int(r[1] or 0)
            except Exception:
                return None
            if val <= 0 or doy < 0 or doy >= days:
                return None
            return doy, val

        # 1. Sent chars max day (text messages only, non-whitespace approximation)
        char_expr = (
            "length(replace(replace(replace(replace(coalesce(text,''),' ',''), char(10), ''), char(13), ''), char(9), ''))"
        )
        sql_sent_chars = (
            "SELECT doy, chars FROM ("
            "  SELECT CAST(strftime('%j', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) - 1 AS doy, "
            f"         SUM({char_expr}) AS chars "
            "  FROM ("
            f"    SELECT {ts_expr} AS ts, text "
            "    FROM message_fts "
            f"    WHERE {base_where} AND sender_username = ? AND CAST(local_type AS INTEGER) = 1"
            "  ) sub "
            "  GROUP BY doy"
            ") t ORDER BY chars DESC, doy ASC LIMIT 1"
        )
        r_sent_chars = fetch_best_doy_value(sql_sent_chars, base_params + (sender,))
        if r_sent_chars is not None:
            doy, v = r_sent_chars
            add_highlight(key="sent_chars_max", label="发送字最多的一天", doy=doy, value=v, value_label=f"{v} 字")

        # 2. Received chars max day (text messages only)
        sql_recv_chars = (
            "SELECT doy, chars FROM ("
            "  SELECT CAST(strftime('%j', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) - 1 AS doy, "
            f"         SUM({char_expr}) AS chars "
            "  FROM ("
            f"    SELECT {ts_expr} AS ts, text "
            "    FROM message_fts "
            f"    WHERE {base_where} AND COALESCE(sender_username,'') != ? AND CAST(local_type AS INTEGER) = 1"
            "  ) sub "
            "  GROUP BY doy"
            ") t ORDER BY chars DESC, doy ASC LIMIT 1"
        )
        r_recv_chars = fetch_best_doy_value(sql_recv_chars, base_params + (sender,))
        if r_recv_chars is not None:
            doy, v = r_recv_chars
            add_highlight(key="received_chars_max", label="接收字最多的一天", doy=doy, value=v, value_label=f"{v} 字")

        # 4. Received message count max day (exclude system messages)
        sql_recv_msgs = (
            "SELECT doy, cnt FROM ("
            "  SELECT CAST(strftime('%j', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) - 1 AS doy, "
            "         COUNT(1) AS cnt "
            "  FROM ("
            f"    SELECT {ts_expr} AS ts "
            "    FROM message_fts "
            f"    WHERE {base_where} AND COALESCE(sender_username,'') != ? AND CAST(local_type AS INTEGER) != 10000"
            "  ) sub "
            "  GROUP BY doy"
            ") t ORDER BY cnt DESC, doy ASC LIMIT 1"
        )
        r_recv_msgs = fetch_best_doy_value(sql_recv_msgs, base_params + (sender,))
        if r_recv_msgs is not None:
            doy, v = r_recv_msgs
            add_highlight(key="received_messages_max", label="接收消息条数最多的一天", doy=doy, value=v, value_label=f"{v} 条")

        # 5. Added friends max day (best-effort via system message patterns, exclude official/chatrooms)
        added_like_patterns = [f"%{p}%" for p in _ADDED_FRIEND_PATTERNS if str(p or "").strip()]
        if added_like_patterns:
            cond_added = " OR ".join(["text LIKE ?"] * len(added_like_patterns))
            sql_added = (
                "SELECT doy, cnt FROM ("
                "  SELECT CAST(strftime('%j', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) - 1 AS doy, "
                "         COUNT(DISTINCT username) AS cnt "
                "  FROM ("
                f"    SELECT {ts_expr} AS ts, username, text "
                "    FROM message_fts "
                f"    WHERE {base_where} "
                "      AND CAST(local_type AS INTEGER) = 10000 "
                "      AND COALESCE(is_official, 0) = 0 "
                "      AND username NOT LIKE '%@chatroom' "
                f"      AND ({cond_added})"
                "  ) sub "
                "  GROUP BY doy"
                ") t ORDER BY cnt DESC, doy ASC LIMIT 1"
            )
            params_added: tuple[Any, ...] = base_params + tuple(added_like_patterns)
            r_added = fetch_best_doy_value(sql_added, params_added)
            if r_added is not None:
                doy, v = r_added
                add_highlight(key="added_friends_max", label="加好友最多的一天", doy=doy, value=v, value_label=f"{v} 位")

        # 6. Sticker/emoji messages max day (WeChat local_type=47)
        sql_emoji_msgs = (
            "SELECT doy, cnt FROM ("
            "  SELECT CAST(strftime('%j', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) - 1 AS doy, "
            "         COUNT(1) AS cnt "
            "  FROM ("
            f"    SELECT {ts_expr} AS ts "
            "    FROM message_fts "
            f"    WHERE {base_where} AND sender_username = ? AND CAST(local_type AS INTEGER) = 47"
            "  ) sub "
            "  GROUP BY doy"
            ") t ORDER BY cnt DESC, doy ASC LIMIT 1"
        )
        r_emoji_msgs = fetch_best_doy_value(sql_emoji_msgs, base_params + (sender,))
        if r_emoji_msgs is not None:
            doy, v = r_emoji_msgs
            add_highlight(key="sticker_messages_max", label="发表情包最多的一天", doy=doy, value=v, value_label=f"{v} 条")

        # 7. Unicode emoji chars max day (best-effort; count emoji codepoints in sent text)
        emoji_counts: list[int] = [0 for _ in range(days)]
        sql_emoji_text = (
            "SELECT doy, text FROM ("
            "  SELECT "
            "    CAST(strftime('%j', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) - 1 AS doy, "
            "    text "
            "  FROM ("
            f"    SELECT {ts_expr} AS ts, text "
            "    FROM message_fts "
            f"    WHERE {base_where} AND sender_username = ? AND CAST(local_type AS INTEGER) = 1"
            "  ) sub2"
            ") sub "
            "WHERE text IS NOT NULL AND text != ''"
        )
        try:
            cur = conn.execute(sql_emoji_text, base_params + (sender,))
        except Exception:
            cur = None
        if cur is not None:
            for r in cur:
                try:
                    doy = int(r[0] if r and r[0] is not None else -1)
                except Exception:
                    continue
                if doy < 0 or doy >= days:
                    continue
                try:
                    txt = str(r[1] or "")
                except Exception:
                    txt = ""
                if not txt:
                    continue
                emoji_counts[doy] += len(_EMOJI_CHAR_RE.findall(txt))

        best_emoji_doy, best_emoji = _best_doy_by_max(emoji_counts)
        if best_emoji_doy is not None and best_emoji > 0:
            add_highlight(
                key="emoji_chars_max",
                label="发emoji最多的一天",
                doy=int(best_emoji_doy),
                value=int(best_emoji),
                value_label=f"{int(best_emoji)} 个",
            )

    finally:
        try:
            conn.close()
        except Exception:
            pass

    return out


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


def _mask_name(name: str) -> str:
    s = str(name or "").strip()
    if not s:
        return ""
    if len(s) == 1:
        return "*"
    if len(s) == 2:
        return s[0] + "*"
    return s[0] + ("*" * (len(s) - 2)) + s[-1]


def _normalize_phrase(v: Any) -> str:
    s = _decode_sqlite_text(v).strip()
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return ""
    if len(s) > 12:
        return ""
    lower = s.lower()
    if "http://" in lower or "https://" in lower:
        return ""
    if s.startswith("<"):
        return ""
    # Avoid pure punctuation / numbers.
    if not re.search(r"[\u4e00-\u9fffA-Za-z]", s):
        return ""
    return s


def _normalize_emoji(v: Any) -> str:
    s = _decode_sqlite_text(v).strip()
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    if not s or len(s) > 48:
        return ""
    if s.startswith("<"):
        return ""
    # If it is an md5 or some opaque token, don't show it.
    if re.fullmatch(r"(?i)[0-9a-f]{32}", s):
        return ""
    return s


def _kind_from_local_type(t: int) -> str:
    # See `_infer_local_type` in chat_helpers for known values.
    if t == 1:
        return "text"
    if t == 3:
        return "image"
    if t == 34:
        return "voice"
    if t == 43:
        return "video"
    if t == 47:
        return "emoji"
    if t in (49, 17179869233, 21474836529, 154618822705, 12884901937, 270582939697):
        return "link"
    if t == 25769803825:
        return "file"
    if t == 10000:
        return "system"
    if t == 50:
        return "voip"
    if t == 244813135921:
        return "quote"
    if t == 8594229559345:
        return "red_packet"
    if t == 8589934592049:
        return "transfer"
    if t == 266287972401:
        return "pat"
    return "other"


def _weekday_name_zh(weekday_index: int) -> str:
    labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    if 0 <= weekday_index < len(labels):
        return labels[weekday_index]
    return ""


def _kind_label_zh(kind: str) -> str:
    return {
        "text": "文字",
        "emoji": "表情包",
        "voice": "语音",
        "image": "图片",
        "video": "视频",
        "link": "链接/小程序",
        "file": "文件",
        "system": "系统消息",
        "other": "其他",
    }.get(kind, kind)


def compute_global_overview_stats(
    *,
    account_dir: Path,
    year: int,
    sender_username: str | None = None,
) -> GlobalOverviewStats:
    """Compute global overview stats for wrapped.

    Notes:
    - Best-effort only. Different WeChat versions may store different message types/values.
    - We default to excluding `biz_message*.db` to reduce noise.
    - If `sender_username` is provided, only messages sent by that sender are counted
      (best-effort).
    """

    start_ts, end_ts = _year_range_epoch_seconds(year)
    sender = str(sender_username).strip() if sender_username and str(sender_username).strip() else None

    # Prefer using the unified search index if available; it already merges all shards/tables.
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
                t0 = time.time()

                ts_expr = (
                    "CASE "
                    "WHEN CAST(create_time AS INTEGER) > 1000000000000 "
                    "THEN CAST(CAST(create_time AS INTEGER)/1000 AS INTEGER) "
                    "ELSE CAST(create_time AS INTEGER) "
                    "END"
                )
                where = f"{ts_expr} >= ? AND {ts_expr} < ? AND db_stem NOT LIKE 'biz_message%'"
                params: tuple[Any, ...] = (start_ts, end_ts)
                if sender:
                    where += " AND sender_username = ?"
                    params = (start_ts, end_ts, sender)

                # activeDays + latest_ts in one pass.
                sql_meta = (
                    "SELECT "
                    "COUNT(DISTINCT date(datetime(ts, 'unixepoch', 'localtime'))) AS active_days, "
                    "MAX(ts) AS latest_ts "
                    "FROM ("
                    f"  SELECT {ts_expr} AS ts"
                    "  FROM message_fts"
                    f"  WHERE {where}"
                    ") sub"
                )
                r = conn.execute(sql_meta, params).fetchone()
                active_days_i = int((r[0] if r else 0) or 0)
                latest_ts_i = int((r[1] if r else 0) or 0)

                # local_type distribution (for message kind).
                local_type_counts_i: Counter[int] = Counter()
                kind_counts_i: Counter[str] = Counter()
                try:
                    rows = conn.execute(
                        f"SELECT CAST(local_type AS INTEGER) AS lt, COUNT(1) AS cnt "
                        f"FROM message_fts WHERE {where} GROUP BY lt",
                        params,
                    ).fetchall()
                except Exception:
                    rows = []
                for rr in rows:
                    if not rr:
                        continue
                    try:
                        lt = int(rr[0] or 0)
                        cnt = int(rr[1] or 0)
                    except Exception:
                        continue
                    if cnt <= 0:
                        continue
                    local_type_counts_i[lt] += cnt
                    kind_counts_i[_kind_from_local_type(lt)] += cnt

                # Top conversations (best-effort: only needs a small LIMIT).
                per_username_counts_i: Counter[str] = Counter()
                try:
                    rows_u = conn.execute(
                        f"SELECT username, COUNT(1) AS cnt "
                        f"FROM message_fts WHERE {where} "
                        "GROUP BY username ORDER BY cnt DESC LIMIT 400",
                        params,
                    ).fetchall()
                except Exception:
                    rows_u = []
                for rr in rows_u:
                    if not rr:
                        continue
                    u = str(rr[0] or "").strip()
                    if not u:
                        continue
                    try:
                        cnt = int(rr[1] or 0)
                    except Exception:
                        cnt = 0
                    if cnt > 0:
                        per_username_counts_i[u] = cnt

                # Top phrases (short text only).
                phrase_counts_i: Counter[str] = Counter()
                try:
                    rows_p = conn.execute(
                        f"SELECT \"text\" AS txt, COUNT(1) AS cnt "
                        f"FROM message_fts WHERE {where} AND render_type = 'text' "
                        "  AND \"text\" IS NOT NULL "
                        "  AND TRIM(\"text\") != '' "
                        "  AND LENGTH(TRIM(\"text\")) <= 12 "
                        "GROUP BY txt ORDER BY cnt DESC LIMIT 400",
                        params,
                    ).fetchall()
                except Exception:
                    rows_p = []
                for rr in rows_p:
                    if not rr:
                        continue
                    phrase = _normalize_phrase(rr[0])
                    if not phrase:
                        continue
                    try:
                        cnt = int(rr[1] or 0)
                    except Exception:
                        cnt = 0
                    if cnt > 0:
                        phrase_counts_i[phrase] += cnt

                def pick_top(counter: Counter[Any]) -> Optional[tuple[Any, int]]:
                    if not counter:
                        return None
                    best_item = max(counter.items(), key=lambda kv: (kv[1], str(kv[0])))
                    if best_item[1] <= 0:
                        return None
                    return best_item[0], int(best_item[1])

                def is_keep_username(u: str) -> bool:
                    return _should_keep_session(u, include_official=False)

                contact_counts_i = Counter(
                    {
                        u: c
                        for u, c in per_username_counts_i.items()
                        if (not u.endswith("@chatroom")) and is_keep_username(u)
                    }
                )
                group_counts_i = Counter(
                    {u: c for u, c in per_username_counts_i.items() if u.endswith("@chatroom") and is_keep_username(u)}
                )
                top_contact = pick_top(contact_counts_i)
                top_group = pick_top(group_counts_i)
                top_phrase = pick_top(phrase_counts_i)

                # New friends added in this year (best-effort via WeChat system messages).
                added_friend_usernames: set[str] = set()
                try:
                    like_patterns: list[str] = []
                    for pat in _ADDED_FRIEND_PATTERNS:
                        tok = _to_char_token_text(pat)
                        if tok:
                            like_patterns.append(f"%{tok}%")

                    if like_patterns:
                        where_added = f"{ts_expr} >= ? AND {ts_expr} < ? AND db_stem NOT LIKE 'biz_message%'"
                        cond_added = " OR ".join(['\"text\" LIKE ?'] * len(like_patterns))
                        rows_added = conn.execute(
                            f"SELECT DISTINCT username FROM message_fts "
                            f"WHERE {where_added} "
                            "AND CAST(local_type AS INTEGER) = 10000 "
                            f"AND ({cond_added})",
                            (start_ts, end_ts, *like_patterns),
                        ).fetchall()
                        for rr in rows_added:
                            if not rr or not rr[0]:
                                continue
                            u = str(rr[0] or "").strip()
                            if not u or u.endswith("@chatroom") or (not is_keep_username(u)):
                                continue
                            added_friend_usernames.add(u)
                except Exception:
                    added_friend_usernames = set()

                added_friends_i = len(added_friend_usernames)

                total_messages = int(sum(local_type_counts_i.values()))
                logger.info(
                    "Wrapped card#0 overview computed (search index): account=%s year=%s total=%s active_days=%s sender=%s db=%s elapsed=%.2fs",
                    str(account_dir.name or "").strip(),
                    year,
                    total_messages,
                    active_days_i,
                    sender or "*",
                    str(index_path.name),
                    time.time() - t0,
                )

                return GlobalOverviewStats(
                    year=year,
                    active_days=active_days_i,
                    added_friends=added_friends_i,
                    local_type_counts={int(k): int(v) for k, v in local_type_counts_i.items()},
                    kind_counts={str(k): int(v) for k, v in kind_counts_i.items()},
                    latest_ts=latest_ts_i,
                    top_phrase=(str(top_phrase[0]), int(top_phrase[1])) if top_phrase else None,
                    top_emoji=None,
                    top_contact=(str(top_contact[0]), int(top_contact[1])) if top_contact else None,
                    top_group=(str(top_group[0]), int(top_group[1])) if top_group else None,
                )
        finally:
            try:
                conn.close()
            except Exception:
                pass

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

    # Convert millisecond timestamps defensively.
    ts_expr = (
        "CASE WHEN create_time > 1000000000000 THEN CAST(create_time/1000 AS INTEGER) ELSE create_time END"
    )

    local_type_counts: Counter[int] = Counter()
    kind_counts: Counter[str] = Counter()
    active_days: set[str] = set()
    per_username_counts: Counter[str] = Counter()
    phrase_counts: Counter[str] = Counter()
    added_friend_usernames: set[str] = set()
    added_like_patterns = [f"%{p}%" for p in _ADDED_FRIEND_PATTERNS if str(p or "").strip()]

    latest_ts = 0

    t0 = time.time()
    for db_path in db_paths:
        if not db_path.exists():
            continue
        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(str(db_path))
            tables = _list_message_tables(conn)
            if not tables:
                continue

            skip_sender_stats = False
            sender_rowid: int | None = None
            if sender:
                try:
                    r2 = conn.execute(
                        "SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1",
                        (sender,),
                    ).fetchone()
                    if r2 is not None and r2[0] is not None:
                        sender_rowid = int(r2[0])
                except Exception:
                    sender_rowid = None
                # Can't reliably filter by sender for this shard; skip sender-only stats to avoid mixing directions.
                if sender_rowid is None:
                    skip_sender_stats = True

            for table_name in tables:
                qt = _quote_ident(table_name)
                username = resolve_username_from_table(table_name)

                # New friends added: detect common WeChat system messages within this year.
                if (
                    added_like_patterns
                    and username
                    and (not username.endswith("@chatroom"))
                    and _should_keep_session(username, include_official=False)
                ):
                    cond_added = " OR ".join(["CAST(message_content AS TEXT) LIKE ?"] * len(added_like_patterns))
                    sql_added = (
                        f"SELECT 1 FROM {qt} "
                        f"WHERE local_type = 10000 "
                        f"  AND {ts_expr} >= ? AND {ts_expr} < ? "
                        f"  AND ({cond_added}) "
                        "LIMIT 1"
                    )
                    try:
                        r_added = conn.execute(sql_added, (start_ts, end_ts, *added_like_patterns)).fetchone()
                    except Exception:
                        r_added = None
                    if r_added is not None:
                        added_friend_usernames.add(username)

                if skip_sender_stats:
                    continue
                sender_where = " AND real_sender_id = ?" if sender_rowid is not None else ""
                params = (start_ts, end_ts, sender_rowid) if sender_rowid is not None else (start_ts, end_ts)

                # 1) local_type distribution + table total
                sql_types = (
                    "SELECT local_type, COUNT(1) AS cnt "
                    "FROM ("
                    f"  SELECT local_type, {ts_expr} AS ts "
                    f"  FROM {qt} "
                    f"  WHERE {ts_expr} >= ? AND {ts_expr} < ?{sender_where}"
                    ") sub "
                    "GROUP BY local_type"
                )
                try:
                    rows = conn.execute(sql_types, params).fetchall()
                except Exception:
                    continue
                if not rows:
                    continue

                table_total = 0
                table_text_cnt = 0
                for r in rows:
                    if not r:
                        continue
                    try:
                        lt = int(r[0] or 0)
                    except Exception:
                        lt = 0
                    try:
                        cnt = int(r[1] or 0)
                    except Exception:
                        cnt = 0
                    if cnt <= 0:
                        continue
                    table_total += cnt
                    local_type_counts[lt] += cnt
                    kind_counts[_kind_from_local_type(lt)] += cnt
                    if lt == 1:
                        table_text_cnt = cnt

                if table_total <= 0:
                    continue
                if username:
                    per_username_counts[username] += table_total

                # 3) active days (distinct dates)
                sql_days = (
                    "SELECT DISTINCT date(datetime(ts, 'unixepoch', 'localtime')) AS d "
                    "FROM ("
                    f"  SELECT {ts_expr} AS ts"
                    f"  FROM {qt}"
                    f"  WHERE {ts_expr} >= ? AND {ts_expr} < ?{sender_where}"
                    ") sub"
                )
                try:
                    rows_d = conn.execute(sql_days, params).fetchall()
                except Exception:
                    rows_d = []
                for rd in rows_d:
                    if not rd or not rd[0]:
                        continue
                    active_days.add(str(rd[0]))

                # 4) latest timestamp within this year
                sql_max_ts = f"SELECT MAX({ts_expr}) AS mx FROM {qt} WHERE {ts_expr} >= ? AND {ts_expr} < ?{sender_where}"
                try:
                    rmax = conn.execute(sql_max_ts, params).fetchone()
                except Exception:
                    rmax = None
                try:
                    mx = int((rmax[0] if rmax else 0) or 0)
                except Exception:
                    mx = 0
                if mx > latest_ts:
                    latest_ts = mx

                # 5) top phrases (best-effort via short, repeated text messages)
                if table_text_cnt > 0:
                    sql_phrase = (
                        "SELECT message_content AS txt, COUNT(1) AS cnt "
                        f"FROM {qt} "
                        f"WHERE local_type = 1 "
                        f"  AND {ts_expr} >= ? AND {ts_expr} < ?{sender_where} "
                        "  AND message_content IS NOT NULL "
                        "  AND TRIM(CAST(message_content AS TEXT)) != '' "
                        "  AND LENGTH(TRIM(CAST(message_content AS TEXT))) <= 12 "
                        "GROUP BY txt "
                        "ORDER BY cnt DESC "
                        "LIMIT 60"
                    )
                    try:
                        rows_p = conn.execute(sql_phrase, params).fetchall()
                    except Exception:
                        rows_p = []
                    for rp in rows_p:
                        if not rp:
                            continue
                        phrase = _normalize_phrase(rp[0])
                        if not phrase:
                            continue
                        try:
                            cnt = int(rp[1] or 0)
                        except Exception:
                            cnt = 0
                        if cnt > 0:
                            phrase_counts[phrase] += cnt
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def pick_top(counter: Counter[Any]) -> Optional[tuple[Any, int]]:
        if not counter:
            return None
        # Deterministic tie-breaker: key string ascending.
        best_item = max(counter.items(), key=lambda kv: (kv[1], str(kv[0])))
        if best_item[1] <= 0:
            return None
        return best_item[0], int(best_item[1])

    # Pick top contact & group (exclude official/service accounts by default).
    def is_keep_username(u: str) -> bool:
        return _should_keep_session(u, include_official=False)

    contact_counts = Counter({u: c for u, c in per_username_counts.items() if (not u.endswith("@chatroom")) and is_keep_username(u)})
    group_counts = Counter({u: c for u, c in per_username_counts.items() if u.endswith("@chatroom") and is_keep_username(u)})
    top_contact = pick_top(contact_counts)
    top_group = pick_top(group_counts)

    top_phrase = pick_top(phrase_counts)

    total_messages = int(sum(local_type_counts.values()))

    logger.info(
        "Wrapped card#0 overview computed: account=%s year=%s total=%s active_days=%s sender=%s dbs=%s elapsed=%.2fs",
        str(account_dir.name or "").strip(),
        year,
        total_messages,
        len(active_days),
        sender or "*",
        len(db_paths),
        time.time() - t0,
    )

    return GlobalOverviewStats(
        year=year,
        active_days=len(active_days),
        added_friends=len(added_friend_usernames),
        local_type_counts={int(k): int(v) for k, v in local_type_counts.items()},
        kind_counts={str(k): int(v) for k, v in kind_counts.items()},
        latest_ts=int(latest_ts),
        top_phrase=(str(top_phrase[0]), int(top_phrase[1])) if top_phrase else None,
        top_emoji=None,
        top_contact=(str(top_contact[0]), int(top_contact[1])) if top_contact else None,
        top_group=(str(top_group[0]), int(top_group[1])) if top_group else None,
    )


def build_card_00_global_overview(
    *,
    account_dir: Path,
    year: int,
    heatmap: WeekdayHourHeatmap | None = None,
) -> dict[str, Any]:
    """Card #0: 年度全局概览（开场综合页，建议作为第2页）。"""

    sender = str(account_dir.name or "").strip()
    heatmap = heatmap or compute_weekday_hour_heatmap(account_dir=account_dir, year=year, sender_username=sender)
    stats = compute_global_overview_stats(account_dir=account_dir, year=year, sender_username=sender)

    # Resolve display names for top sessions (best-effort).
    contact_db_path = account_dir / "contact.db"
    top_usernames: list[str] = []
    if stats.top_contact:
        top_usernames.append(stats.top_contact[0])
    if stats.top_group:
        top_usernames.append(stats.top_group[0])
    contact_rows = _load_contact_rows(contact_db_path, top_usernames) if top_usernames else {}

    top_contact_obj = None
    if stats.top_contact:
        u, cnt = stats.top_contact
        row = contact_rows.get(u)
        display = _pick_display_name(row, u)
        avatar = _build_avatar_url(str(account_dir.name or ""), u) if u else ""
        top_contact_obj = {
            "username": u,
            "displayName": display,
            "maskedName": _mask_name(display),
            "avatarUrl": avatar,
            "messages": int(cnt),
            "isGroup": False,
        }

    top_group_obj = None
    if stats.top_group:
        u, cnt = stats.top_group
        row = contact_rows.get(u)
        display = _pick_display_name(row, u)
        avatar = _build_avatar_url(str(account_dir.name or ""), u) if u else ""
        top_group_obj = {
            "username": u,
            "displayName": display,
            "maskedName": _mask_name(display),
            "avatarUrl": avatar,
            "messages": int(cnt),
            "isGroup": True,
        }

    # Derive the top "message kind".
    top_kind = None
    if stats.kind_counts:
        kc = Counter(stats.kind_counts)
        # Exclude mostly-unhelpful kinds from the "top" pick.
        for drop in ("system", "other"):
            if drop in kc:
                del kc[drop]
        if kc:
            kind, count = max(kc.items(), key=lambda kv: (kv[1], str(kv[0])))
            ratio = (float(count) / float(heatmap.total_messages)) if heatmap.total_messages > 0 else 0.0
            top_kind = {
                "kind": str(kind),
                "label": _kind_label_zh(str(kind)),
                "count": int(count),
                "ratio": ratio,
            }

    messages_per_day = 0.0
    if stats.active_days > 0:
        messages_per_day = heatmap.total_messages / float(stats.active_days)

    most_active_hour: Optional[int] = None
    most_active_weekday: Optional[int] = None
    if heatmap.total_messages > 0:
        hour_totals = [sum(heatmap.matrix[w][h] for w in range(7)) for h in range(24)]
        most_active_hour = max(range(24), key=lambda h: (hour_totals[h], -h))

        weekday_totals = [sum(heatmap.matrix[w][h] for h in range(24)) for w in range(7)]
        most_active_weekday = max(range(7), key=lambda w: (weekday_totals[w], -w))

    most_active_weekday_name = _weekday_name_zh(most_active_weekday or -1) if most_active_weekday is not None else ""

    highlight = None
    if stats.latest_ts > 0:
        dt = datetime.fromtimestamp(int(stats.latest_ts))
        highlight = {
            "timestamp": int(stats.latest_ts),
            "date": dt.strftime("%Y-%m-%d"),
            "time": dt.strftime("%H:%M"),
            # Keep it privacy-safe by default: no content/object here.
            "action": "你还在微信里发送消息",
        }

    daily_counts = compute_annual_daily_counts(account_dir=account_dir, year=year, sender_username=sender)
    annual_highlights = compute_annual_heatmap_highlights(
        account_dir=account_dir,
        year=year,
        sender_username=sender,
        sent_daily_counts=daily_counts,
    )
    annual_heatmap = {
        "year": int(year),
        "startDate": f"{int(year)}-01-01",
        "endDate": f"{int(year)}-12-31",
        "days": int(len(daily_counts)),
        "dailyCounts": daily_counts,
        "highlights": annual_highlights,
    }

    lines: list[str] = []
    if heatmap.total_messages > 0:
        lines.append(f"今年以来，你在微信里发送了 {heatmap.total_messages:,} 条消息，平均每天 {messages_per_day:.1f} 条。")
    else:
        lines.append("今年以来，你在微信里还没有发出聊天消息。")

    if stats.active_days > 0:
        if most_active_hour is not None and most_active_weekday_name:
            lines.append(f"和微信共度的 {stats.active_days} 天里，你最常在 {most_active_hour} 点出没；{most_active_weekday_name}是你最爱聊天的日子。")
        else:
            lines.append(f"和微信共度的 {stats.active_days} 天里，你留下了很多对话的痕迹。")

    if top_contact_obj or top_group_obj:
        parts: list[str] = []
        if top_contact_obj:
            parts.append(f"你发消息最多的人是「{top_contact_obj['maskedName']}」（{int(top_contact_obj['messages']):,} 条）")
        if top_group_obj:
            parts.append(f"你最常发言的群是「{top_group_obj['maskedName']}」（{int(top_group_obj['messages']):,} 条）")
        if parts:
            lines.append("，".join(parts) + "。")

    if top_kind and top_kind.get("count", 0) > 0:
        pct = float(top_kind.get("ratio") or 0.0) * 100.0
        lines.append(f"你最常用的表达方式是{top_kind['label']}（占 {pct:.0f}%）。")

    if stats.top_phrase and stats.top_phrase[0] and stats.top_phrase[1] > 0:
        phrase, cnt = stats.top_phrase
        lines.append(f"你今年说得最多的一句话是「{phrase}」（共 {cnt:,} 次）。")

    # NOTE: We keep the `highlight` field in `data` for future use, but do not
    # surface it in the page narrative for now (per product requirement).

    narrative = "一屏读懂你的年度微信聊天画像"

    return {
        "id": 0,
        "title": "这一年，你的微信都经历了什么？",
        "scope": "global",
        "category": "A",
        "status": "ok",
        "kind": "global/overview",
        "narrative": narrative,
        "data": {
            "year": int(year),
            "totalMessages": int(heatmap.total_messages),
            "activeDays": int(stats.active_days),
            "addedFriends": int(stats.added_friends),
            "sentMediaCount": int(stats.kind_counts.get("image", 0) + stats.kind_counts.get("video", 0)),
            "sentStickerCount": int(stats.kind_counts.get("emoji", 0)),
            "messagesPerDay": messages_per_day,
            "mostActiveHour": most_active_hour,
            "mostActiveWeekday": most_active_weekday,
            "mostActiveWeekdayName": most_active_weekday_name,
            "topContact": top_contact_obj,
            "topGroup": top_group_obj,
            "topKind": top_kind,
            "annualHeatmap": annual_heatmap,
            "topPhrase": {"phrase": stats.top_phrase[0], "count": int(stats.top_phrase[1])} if stats.top_phrase else None,
            "topEmoji": {"emoji": stats.top_emoji[0], "count": int(stats.top_emoji[1])} if stats.top_emoji else None,
            "highlight": highlight,
            "lines": lines,
        },
    }
