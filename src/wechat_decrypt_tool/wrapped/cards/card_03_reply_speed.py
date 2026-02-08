from __future__ import annotations

import heapq
import math
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ...chat_helpers import (
    _build_avatar_url,
    _load_contact_rows,
    _pick_display_name,
    _should_keep_session,
)
from ...chat_search_index import (
    get_chat_search_index_db_path,
    get_chat_search_index_status,
    start_chat_search_index_build,
)
from ...logging_config import get_logger

logger = get_logger(__name__)


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


def _format_duration_zh(seconds: int | None) -> str:
    if seconds is None:
        return ""
    try:
        s = int(seconds)
    except Exception:
        s = 0
    if s < 0:
        s = 0

    if s < 60:
        return f"{s}秒"
    m, sec = divmod(s, 60)
    if m < 60:
        return f"{m}分{sec}秒" if sec else f"{m}分钟"
    h, mm = divmod(m, 60)
    if h < 24:
        return f"{h}小时{mm}分钟" if mm else f"{h}小时"
    d, hh = divmod(h, 24)
    return f"{d}天{hh}小时" if hh else f"{d}天"


@dataclass
class _ConvAgg:
    username: str
    incoming: int
    outgoing: int
    replies: int
    sum_gap: int
    sum_gap_capped: int
    min_gap: int
    max_gap: int

    @property
    def total(self) -> int:
        return int(self.incoming) + int(self.outgoing)

    def avg_gap(self) -> float:
        return float(self.sum_gap) / float(self.replies) if self.replies > 0 else 0.0

    def avg_gap_capped(self) -> float:
        return float(self.sum_gap_capped) / float(self.replies) if self.replies > 0 else 0.0


def _score_conv(*, agg: _ConvAgg, tau_seconds: float) -> float:
    # "聊天频率"：更偏向双向互动（取 min(in, out)）。
    interaction = float(min(int(agg.incoming), int(agg.outgoing)))
    if interaction <= 0.0 or agg.replies <= 0:
        return 0.0

    # "回复频率/速度"：用 capped 平均耗时做一个饱和衰减，避免极端长等待把分数打穿。
    avg_s = float(agg.avg_gap_capped())
    speed_score = 1.0 / (1.0 + (avg_s / float(max(1.0, tau_seconds))))

    volume_score = math.log1p(interaction)
    return float(speed_score * volume_score)


def compute_reply_speed_stats(*, account_dir: Path, year: int) -> dict[str, Any]:
    """
    统计“回复速度”相关指标（全局 + 每个好友），用于 Wrapped 年度总结卡片。

    Notes / 口径说明：
    - 仅统计 1v1（非群聊）会话：username 不以 "@chatroom" 结尾。
    - “一次回复”定义：对方发出消息后，你发送的第一条消息（同一段连续你发的消息只计 1 次）。
    - 默认过滤系统消息（local_type=10000），并排除 biz_message*.db。
    - 优先使用 chat_search_index.db（全量合并所有 shard），没有索引时做 best-effort 降级。
    """

    start_ts, end_ts = _year_range_epoch_seconds(int(year))
    my_username = str(account_dir.name or "").strip()

    # Scoring hyper-params (tuned for "更偏向聊天频率高的" 的直觉)。
    gap_cap_seconds = 6 * 60 * 60  # 6h: scoring 上限（超过当作一样慢）
    tau_seconds = 30 * 60  # 30min: 速度衰减的尺度

    total_replies = 0
    global_fastest: int | None = None
    global_fastest_u: str | None = None
    global_slowest: int | None = None
    global_slowest_u: str | None = None

    best_score = -1.0
    best_agg: _ConvAgg | None = None

    # NOTE: Use (score, username, agg) so the heap is always comparable even when scores tie.
    top_heap: list[tuple[float, str, _ConvAgg]] = []
    top_n = 8

    # For "今年你总共给 xxx 人发送过消息" & top-total bar-race.
    sent_to_contacts: set[str] = set()
    # Collect totals for *all* 1v1 sessions so the frontend ranking can naturally grow over time.
    all_totals: dict[str, int] = {}
    # NOTE: Use (total, username, agg) so the heap is always comparable even when totals tie.
    top_total_heap: list[tuple[int, str, _ConvAgg]] = []
    # Keep more than 10 so the bar-race "TOP10" can actually evolve (members can enter/leave over time).
    top_total_n = 100

    def consider_conv(agg: _ConvAgg) -> None:
        nonlocal best_score, best_agg
        if not agg.username:
            return
        if agg.replies <= 0:
            return
        if min(agg.incoming, agg.outgoing) <= 0:
            return

        score = _score_conv(agg=agg, tau_seconds=tau_seconds)
        if score > best_score:
            best_score = float(score)
            best_agg = agg

        if score <= 0:
            return
        key = (float(score), str(agg.username), agg)
        if len(top_heap) < top_n:
            heapq.heappush(top_heap, key)
        else:
            heapq.heappushpop(top_heap, key)

    def consider_total(agg: _ConvAgg) -> None:
        if not agg.username:
            return
        if agg.total <= 0:
            return
        # Keep the same filtering behavior as other wrapped cards.
        if not _should_keep_session(agg.username, include_official=False):
            return

        if agg.outgoing > 0:
            sent_to_contacts.add(agg.username)

        total = int(agg.total)
        all_totals[agg.username] = int(total)
        key = (total, str(agg.username), agg)
        if len(top_total_heap) < top_total_n:
            heapq.heappush(top_total_heap, key)
        else:
            heapq.heappushpop(top_total_heap, key)

    used_index = False

    # -------- Preferred path: unified search index --------
    index_path = get_chat_search_index_db_path(account_dir)
    if index_path.exists():
        conn = sqlite3.connect(str(index_path))
        try:
            has_fts = (
                conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='message_fts' LIMIT 1").fetchone()
                is not None
            )
            if has_fts and my_username:
                used_index = True
                t0 = time.time()

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
                    "AND CAST(local_type AS INTEGER) != 10000 "
                    "AND username NOT LIKE '%@chatroom'"
                )

                # Order by username, then time (ties broken by sort_seq/local_id if possible).
                sql = (
                    "SELECT "
                    "username, sender_username, "
                    f"{ts_expr} AS ts, "
                    "CAST(sort_seq AS INTEGER) AS sort_seq_i, "
                    "CAST(local_id AS INTEGER) AS local_id_i "
                    "FROM message_fts "
                    f"WHERE {where} "
                    "ORDER BY username ASC, ts ASC, sort_seq_i ASC, local_id_i ASC"
                )

                cur = conn.execute(sql, (start_ts, end_ts))

                cur_username: str = ""
                incoming = 0
                outgoing = 0
                replies = 0
                sum_gap = 0
                sum_gap_capped = 0
                min_gap = 0
                max_gap = 0
                prev_other_ts: int | None = None

                def flush() -> None:
                    nonlocal cur_username, incoming, outgoing, replies, sum_gap, sum_gap_capped, min_gap, max_gap
                    if not cur_username:
                        return
                    agg = _ConvAgg(
                        username=cur_username,
                        incoming=int(incoming),
                        outgoing=int(outgoing),
                        replies=int(replies),
                        sum_gap=int(sum_gap),
                        sum_gap_capped=int(sum_gap_capped),
                        min_gap=int(min_gap),
                        max_gap=int(max_gap),
                    )
                    consider_total(agg)
                    consider_conv(agg)

                for row in cur:
                    try:
                        username = str(row[0] or "").strip()
                        sender = str(row[1] or "").strip()
                        ts = int(row[2] or 0)
                    except Exception:
                        continue

                    if ts <= 0 or not username:
                        continue
                    if username != cur_username:
                        # flush old
                        flush()
                        # reset for new conversation
                        cur_username = username
                        incoming = outgoing = replies = 0
                        sum_gap = sum_gap_capped = 0
                        min_gap = max_gap = 0
                        prev_other_ts = None

                    # Drop system/official-ish sessions (best-effort).
                    if not _should_keep_session(username, include_official=False):
                        continue

                    is_me = sender == my_username
                    if is_me:
                        outgoing += 1
                        if prev_other_ts is not None and ts >= prev_other_ts:
                            gap = int(ts - prev_other_ts)
                            replies += 1
                            total_replies += 1
                            sum_gap += gap
                            sum_gap_capped += min(gap, gap_cap_seconds)

                            if replies == 1 or gap < min_gap:
                                min_gap = gap
                            if replies == 1 or gap > max_gap:
                                max_gap = gap

                            if global_fastest is None or gap < global_fastest:
                                global_fastest = gap
                                global_fastest_u = username
                            if global_slowest is None or gap > global_slowest:
                                global_slowest = gap
                                global_slowest_u = username

                            # Only count the first outgoing message as the "reply" to this prompt.
                            prev_other_ts = None
                    else:
                        incoming += 1
                        prev_other_ts = ts

                flush()

                logger.info(
                    "Wrapped card#3 reply_speed computed (search index): account=%s year=%s conversations_top=%s replies=%s db=%s elapsed=%.2fs",
                    str(account_dir.name or "").strip(),
                    int(year),
                    len(top_heap),
                    int(total_replies),
                    str(index_path.name),
                    time.time() - t0,
                )
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # -------- Fallback path: no index --------
    # Best-effort: if the index doesn't exist / isn't ready, auto-start building it (async) so user can
    # retry this page later. We intentionally do NOT block here.
    index_status: dict[str, Any] | None = None
    if not used_index:
        try:
            index_status = get_chat_search_index_status(account_dir)
            index = dict(index_status.get("index") or {})
            build = dict(index.get("build") or {})
            index_ready = bool(index.get("ready"))
            build_status = str(build.get("status") or "")
            index_exists = bool(index.get("exists"))

            if (not index_ready) and build_status not in {"building", "error"}:
                start_chat_search_index_build(account_dir, rebuild=bool(index_exists))
                index_status = get_chat_search_index_status(account_dir)
        except Exception:
            index_status = None

        logger.warning(
            "Wrapped card#3 reply_speed: search index missing/not ready; returning empty stats. account=%s year=%s index=%s",
            str(account_dir.name or "").strip(),
            int(year),
            str(index_path),
        )

    # Sort top buddies by score desc.
    top_buddies: list[tuple[float, _ConvAgg]] = sorted(
        [(score, agg) for score, _, agg in top_heap],
        key=lambda x: (-x[0], x[1].username),
    )
    top_totals: list[tuple[int, _ConvAgg]] = sorted(
        [(total, agg) for total, _, agg in top_total_heap],
        key=lambda x: (-x[0], x[1].username),
    )

    # Resolve contact display names/avatars for a small set (bestBuddy + extremes + top list).
    need_usernames: list[str] = []
    if best_agg is not None:
        need_usernames.append(best_agg.username)
    if global_fastest_u:
        need_usernames.append(global_fastest_u)
    if global_slowest_u:
        need_usernames.append(global_slowest_u)
    for _, agg in top_buddies:
        need_usernames.append(agg.username)
    for _, agg in top_totals:
        need_usernames.append(agg.username)

    uniq_usernames = []
    seen = set()
    for u in need_usernames:
        if u and u not in seen:
            seen.add(u)
            uniq_usernames.append(u)

    contact_rows = _load_contact_rows(account_dir / "contact.db", uniq_usernames) if uniq_usernames else {}

    def conv_to_obj(score: float | None, agg: _ConvAgg) -> dict[str, Any]:
        row = contact_rows.get(agg.username)
        display = _pick_display_name(row, agg.username)
        avatar = _build_avatar_url(str(account_dir.name or ""), agg.username) if agg.username else ""
        avg_s = agg.avg_gap()
        out: dict[str, Any] = {
            "username": agg.username,
            "displayName": display,
            "maskedName": _mask_name(display),
            "avatarUrl": avatar,
            "incomingMessages": int(agg.incoming),
            "outgoingMessages": int(agg.outgoing),
            "totalMessages": int(agg.total),
            "replyCount": int(agg.replies),
            "avgReplySeconds": float(avg_s),
            "fastestReplySeconds": int(agg.min_gap) if agg.replies > 0 else None,
            "slowestReplySeconds": int(agg.max_gap) if agg.replies > 0 else None,
        }
        if score is not None:
            out["score"] = float(score)
        return out

    best_buddy_obj = None
    if best_agg is not None:
        best_buddy_obj = conv_to_obj(best_score, best_agg)

    fastest_obj = None
    if global_fastest is not None and global_fastest_u:
        # Use the best agg if it matches; otherwise create a minimal object.
        agg = next((a for _, a in top_buddies if a.username == global_fastest_u), None)
        if agg is None and best_agg is not None and best_agg.username == global_fastest_u:
            agg = best_agg
        if agg is not None:
            fastest_obj = conv_to_obj(None, agg)
            fastest_obj["seconds"] = int(global_fastest)
        else:
            row = contact_rows.get(global_fastest_u)
            display = _pick_display_name(row, global_fastest_u)
            avatar = _build_avatar_url(str(account_dir.name or ""), global_fastest_u) if global_fastest_u else ""
            fastest_obj = {
                "username": global_fastest_u,
                "displayName": display,
                "maskedName": _mask_name(display),
                "avatarUrl": avatar,
                "seconds": int(global_fastest),
            }

    slowest_obj = None
    if global_slowest is not None and global_slowest_u:
        agg = next((a for _, a in top_buddies if a.username == global_slowest_u), None)
        if agg is None and best_agg is not None and best_agg.username == global_slowest_u:
            agg = best_agg
        if agg is not None:
            slowest_obj = conv_to_obj(None, agg)
            slowest_obj["seconds"] = int(global_slowest)
        else:
            row = contact_rows.get(global_slowest_u)
            display = _pick_display_name(row, global_slowest_u)
            avatar = _build_avatar_url(str(account_dir.name or ""), global_slowest_u) if global_slowest_u else ""
            slowest_obj = {
                "username": global_slowest_u,
                "displayName": display,
                "maskedName": _mask_name(display),
                "avatarUrl": avatar,
                "seconds": int(global_slowest),
            }

    top_list = [conv_to_obj(score, agg) for score, agg in top_buddies]

    top_totals_list = [
        {
            **conv_to_obj(None, agg),
            "totalMessages": int(total),
        }
        for total, agg in top_totals
    ]

    # Prepare "bar race" data: all 1v1 sessions (exclude official/system), cumulative per day.
    race = None
    if used_index and all_totals:
        days_in_year = int((datetime(int(year) + 1, 1, 1) - datetime(int(year), 1, 1)).days)
        u_list = [u for u, _ in sorted(all_totals.items(), key=lambda kv: (-int(kv[1] or 0), str(kv[0] or ""))) if u]
        if days_in_year > 0 and u_list:
            # Convert millisecond timestamps defensively.
            ts_expr = (
                "CASE "
                "WHEN CAST(create_time AS INTEGER) > 1000000000000 "
                "THEN CAST(CAST(create_time AS INTEGER)/1000 AS INTEGER) "
                "ELSE CAST(create_time AS INTEGER) "
                "END"
            )

            base_where = (
                f"{ts_expr} >= ? AND {ts_expr} < ? "
                "AND db_stem NOT LIKE 'biz_message%' "
                "AND CAST(local_type AS INTEGER) != 10000 "
                "AND username NOT LIKE '%@chatroom'"
            )

            sql_daily = (
                "SELECT username, "
                "CAST(strftime('%j', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) - 1 AS doy, "
                "COUNT(1) AS cnt "
                "FROM ("
                f"  SELECT username, {ts_expr} AS ts "
                "  FROM message_fts "
                f"  WHERE {base_where}"
                ") sub "
                "GROUP BY username, doy"
            )

            u_set = set(u_list)
            per_user_daily: dict[str, list[int]] = {}
            try:
                conn2 = sqlite3.connect(str(index_path))
                try:
                    rows = conn2.execute(sql_daily, (start_ts, end_ts)).fetchall()
                finally:
                    conn2.close()
            except Exception:
                rows = []

            for r in rows:
                if not r:
                    continue
                u = str(r[0] or "").strip()
                if not u or u not in u_set:
                    continue
                try:
                    doy = int(r[1] if r[1] is not None else -1)
                    cnt = int(r[2] or 0)
                except Exception:
                    continue
                if cnt <= 0 or doy < 0 or doy >= days_in_year:
                    continue
                daily = per_user_daily.get(u)
                if daily is None:
                    daily = [0] * days_in_year
                    per_user_daily[u] = daily
                daily[doy] += cnt

            # Ensure we can render display names/avatars for the whole race list.
            extra_usernames = [u for u in u_list if u and u not in contact_rows]
            if extra_usernames:
                try:
                    # sqlite has a default var limit; query in chunks.
                    CHUNK = 900
                    for i in range(0, len(extra_usernames), CHUNK):
                        contact_rows.update(_load_contact_rows(account_dir / "contact.db", extra_usernames[i : i + CHUNK]))
                except Exception:
                    pass

            series: list[dict[str, Any]] = []
            for u in u_list:
                daily = per_user_daily.get(u)
                if not daily:
                    continue
                cum: list[int] = []
                running = 0
                for x in daily:
                    running += int(x or 0)
                    cum.append(int(running))

                row = contact_rows.get(u)
                display = _pick_display_name(row, u)
                avatar = _build_avatar_url(str(account_dir.name or ""), u) if u else ""
                series.append(
                    {
                        "username": u,
                        "displayName": display,
                        "maskedName": _mask_name(display),
                        "avatarUrl": avatar,
                        "totalMessages": int(all_totals.get(u) or 0),
                        "cumulativeCounts": cum,
                    }
                )

            race = {
                "year": int(year),
                "startDate": f"{int(year)}-01-01",
                "endDate": f"{int(year)}-12-31",
                "days": int(days_in_year),
                "series": series,
            }

    # Load all contacts for lottery animation (up to 50 random contacts)
    all_contacts_list: list[dict[str, Any]] = []
    try:
        contact_db_path = account_dir / "contact.db"
        if contact_db_path.exists():
            conn = sqlite3.connect(str(contact_db_path))
            conn.row_factory = sqlite3.Row
            try:
                # Get contacts that are real users (not chatrooms, not official accounts)
                sql = """
                    SELECT username, remark, nick_name, alias, big_head_url, small_head_url
                    FROM contact
                    WHERE username NOT LIKE '%@chatroom'
                      AND username NOT LIKE 'gh_%'
                      AND username NOT LIKE 'weixin'
                      AND username NOT LIKE 'filehelper'
                      AND username NOT LIKE 'fmessage'
                      AND username NOT IN ('medianote', 'floatbottle', 'shakeapp', 'lbsapp', 'newsapp')
                      AND (nick_name IS NOT NULL AND nick_name != '')
                    ORDER BY RANDOM()
                    LIMIT 50
                """
                rows = conn.execute(sql).fetchall()
                for r in rows:
                    u = str(r["username"] or "").strip()
                    if not u:
                        continue
                    display = _pick_display_name(r, u)
                    avatar = _build_avatar_url(str(account_dir.name or ""), u) if u else ""
                    all_contacts_list.append({
                        "username": u,
                        "displayName": display,
                        "maskedName": _mask_name(display),
                        "avatarUrl": avatar,
                    })
            finally:
                conn.close()
    except Exception:
        pass

    return {
        "year": int(year),
        "sentToContacts": int(len(sent_to_contacts)),
        "replyEvents": int(total_replies),
        "fastestReplySeconds": int(global_fastest) if global_fastest is not None else None,
        "longestReplySeconds": int(global_slowest) if global_slowest is not None else None,
        "bestBuddy": best_buddy_obj,
        "fastest": fastest_obj,
        "slowest": slowest_obj,
        "topBuddies": top_list,
        "topTotals": top_totals_list,
        "allContacts": all_contacts_list,
        "race": race,
        "settings": {
            "gapCapSeconds": int(gap_cap_seconds),
            "tauSeconds": int(tau_seconds),
            "usedIndex": bool(used_index),
            "indexStatus": index_status,
        },
    }


def build_card_03_reply_speed(*, account_dir: Path, year: int) -> dict[str, Any]:
    stats = compute_reply_speed_stats(account_dir=account_dir, year=year)

    fastest = stats.get("fastestReplySeconds")
    longest = stats.get("longestReplySeconds")
    best = stats.get("bestBuddy") or None
    replies = int(stats.get("replyEvents") or 0)

    if replies <= 0:
        narrative = "今年你还没有可统计的“回复”记录（或尚未构建搜索索引）。"
    else:
        parts: list[str] = []
        if fastest is not None:
            parts.append(f"最快一次，你只用了 {_format_duration_zh(int(fastest))} 就回了消息。")
        if longest is not None:
            parts.append(f"最长一次，你让对方等了 {_format_duration_zh(int(longest))}。")
        if best and isinstance(best, dict) and best.get("displayName"):
            avg_s = best.get("avgReplySeconds")
            try:
                avg_i = int(round(float(avg_s or 0.0)))
            except Exception:
                avg_i = 0
            parts.append(
                f"最像你的聊天搭子是「{_mask_name(str(best.get('displayName') or ''))}」，平均每条回复用时 {_format_duration_zh(avg_i)}。"
            )
        narrative = "".join(parts) if parts else "你的回复速度，藏着你最在意的人。"

    return {
        "id": 3,
        "title": "谁是你「秒回」的置顶关心？",
        "scope": "global",
        "category": "B",
        "status": "ok",
        "kind": "chat/reply_speed",
        "narrative": narrative,
        "data": stats,
    }
