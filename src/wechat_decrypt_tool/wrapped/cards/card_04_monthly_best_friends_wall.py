from __future__ import annotations

import math
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

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


@dataclass
class _MonthConvAgg:
    username: str
    month: int
    incoming: int = 0
    outgoing: int = 0
    replies: int = 0
    sum_gap: int = 0
    sum_gap_capped: int = 0
    active_days: set[int] = field(default_factory=set)
    time_bucket_mask: int = 0

    @property
    def total(self) -> int:
        return int(self.incoming) + int(self.outgoing)

    @property
    def interaction(self) -> int:
        return min(int(self.incoming), int(self.outgoing))

    @property
    def active_days_count(self) -> int:
        return len(self.active_days)

    @property
    def time_bucket_count(self) -> int:
        m = int(self.time_bucket_mask) & 0xF
        return (m & 1) + ((m >> 1) & 1) + ((m >> 2) & 1) + ((m >> 3) & 1)

    def avg_reply_seconds(self) -> float:
        if self.replies <= 0:
            return 0.0
        return float(self.sum_gap) / float(self.replies)

    def avg_reply_seconds_capped(self) -> float:
        if self.replies <= 0:
            return 0.0
        return float(self.sum_gap_capped) / float(self.replies)

    def observe(self, *, day: int, hour: int) -> None:
        if 1 <= day <= 31:
            self.active_days.add(int(day))
        bucket = max(0, min(3, int(hour) // 6))
        self.time_bucket_mask |= 1 << bucket


def _score_month_agg(
    *,
    agg: _MonthConvAgg,
    month_max_interaction: int,
    month_max_active_days: int,
    tau_seconds: float,
    weights: dict[str, float],
) -> dict[str, float]:
    max_interaction = max(1, int(month_max_interaction))
    max_active = max(1, int(month_max_active_days))
    interaction_score = math.log1p(float(agg.interaction)) / math.log1p(float(max_interaction))
    speed_score = 1.0 / (1.0 + (float(agg.avg_reply_seconds_capped()) / float(max(1.0, tau_seconds))))
    continuity_score = float(agg.active_days_count) / float(max_active)
    coverage_score = float(agg.time_bucket_count) / 4.0
    final_score = (
        float(weights["interaction"]) * interaction_score
        + float(weights["speed"]) * speed_score
        + float(weights["continuity"]) * continuity_score
        + float(weights["coverage"]) * coverage_score
    )
    return {
        "interaction": float(interaction_score),
        "speed": float(speed_score),
        "continuity": float(continuity_score),
        "coverage": float(coverage_score),
        "final": float(final_score),
    }


def compute_monthly_best_friends_wall_stats(*, account_dir: Path, year: int) -> dict[str, Any]:
    start_ts, end_ts = _year_range_epoch_seconds(int(year))
    my_username = str(account_dir.name or "").strip()

    gap_cap_seconds = 6 * 60 * 60
    tau_seconds = 30 * 60
    weights = {
        "interaction": 0.40,
        "speed": 0.30,
        "continuity": 0.20,
        "coverage": 0.10,
    }
    eligibility = {
        "minTotalMessages": 8,
        "minInteraction": 3,
        "minReplyCount": 1,
        "minActiveDays": 2,
    }

    per_month_aggs: dict[int, list[_MonthConvAgg]] = {m: [] for m in range(1, 13)}
    used_index = False
    index_status: dict[str, Any] | None = None

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

                cur_username = ""
                conv_month_aggs: dict[int, _MonthConvAgg] = {}
                prev_other_ts: int | None = None

                def flush_conv() -> None:
                    nonlocal cur_username, conv_month_aggs, prev_other_ts
                    if not cur_username:
                        return
                    for m, agg in conv_month_aggs.items():
                        if 1 <= int(m) <= 12 and agg.total > 0:
                            per_month_aggs[int(m)].append(agg)
                    conv_month_aggs = {}
                    prev_other_ts = None

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
                        flush_conv()
                        cur_username = username

                    if not _should_keep_session(username, include_official=False):
                        continue

                    dt = datetime.fromtimestamp(ts)
                    month = int(dt.month)
                    if month < 1 or month > 12:
                        continue
                    agg = conv_month_aggs.get(month)
                    if agg is None:
                        agg = _MonthConvAgg(username=username, month=month)
                        conv_month_aggs[month] = agg
                    agg.observe(day=int(dt.day), hour=int(dt.hour))

                    is_me = sender == my_username
                    if is_me:
                        agg.outgoing += 1
                        if prev_other_ts is not None and ts >= prev_other_ts:
                            gap = int(ts - prev_other_ts)
                            agg.replies += 1
                            agg.sum_gap += gap
                            agg.sum_gap_capped += min(gap, gap_cap_seconds)
                            prev_other_ts = None
                    else:
                        agg.incoming += 1
                        prev_other_ts = ts

                flush_conv()

                logger.info(
                    "Wrapped card#4 monthly_best_friends computed (search index): account=%s year=%s elapsed=%.2fs",
                    str(account_dir.name or "").strip(),
                    int(year),
                    time.time() - t0,
                )
        finally:
            try:
                conn.close()
            except Exception:
                pass

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

    month_winner_raw: dict[int, dict[str, Any]] = {}
    winner_usernames: list[str] = []
    for month in range(1, 13):
        aggs = list(per_month_aggs.get(month) or [])
        eligible: list[_MonthConvAgg] = []
        for agg in aggs:
            if agg.total < int(eligibility["minTotalMessages"]):
                continue
            if agg.interaction < int(eligibility["minInteraction"]):
                continue
            if agg.replies < int(eligibility["minReplyCount"]):
                continue
            if agg.active_days_count < int(eligibility["minActiveDays"]):
                continue
            eligible.append(agg)

        if not eligible:
            continue

        month_max_interaction = max(agg.interaction for agg in eligible)
        month_max_active_days = max(agg.active_days_count for agg in eligible)
        scored: list[tuple[tuple[float, float, float, float, str], _MonthConvAgg, dict[str, float]]] = []
        for agg in eligible:
            score = _score_month_agg(
                agg=agg,
                month_max_interaction=month_max_interaction,
                month_max_active_days=month_max_active_days,
                tau_seconds=float(tau_seconds),
                weights=weights,
            )
            tie_key = (
                -float(score["final"]),
                -float(agg.interaction),
                float(agg.avg_reply_seconds_capped()),
                -float(agg.active_days_count),
                str(agg.username),
            )
            scored.append((tie_key, agg, score))
        scored.sort(key=lambda x: x[0])
        _, winner_agg, winner_score = scored[0]
        month_winner_raw[month] = {
            "agg": winner_agg,
            "score": winner_score,
        }
        winner_usernames.append(winner_agg.username)

    uniq_winner_usernames: list[str] = []
    seen: set[str] = set()
    for u in winner_usernames:
        if u and u not in seen:
            seen.add(u)
            uniq_winner_usernames.append(u)

    contact_rows = _load_contact_rows(account_dir / "contact.db", uniq_winner_usernames) if uniq_winner_usernames else {}

    months: list[dict[str, Any]] = []
    for month in range(1, 13):
        winner_pack = month_winner_raw.get(month)
        if not winner_pack:
            months.append(
                {
                    "month": month,
                    "winner": None,
                    "metrics": None,
                    "raw": None,
                    "isFallback": False,
                    "reason": "insufficient_data",
                }
            )
            continue

        agg: _MonthConvAgg = winner_pack["agg"]
        score = dict(winner_pack["score"] or {})
        row = contact_rows.get(agg.username)
        display = _pick_display_name(row, agg.username)
        avatar = _build_avatar_url(str(account_dir.name or ""), agg.username) if agg.username else ""

        months.append(
            {
                "month": month,
                "winner": {
                    "username": agg.username,
                    "displayName": display,
                    "maskedName": _mask_name(display),
                    "avatarUrl": avatar,
                    "score": float(score.get("final") or 0.0),
                    "score100": round(float(score.get("final") or 0.0) * 100.0, 1),
                },
                "metrics": {
                    "interactionScore": float(score.get("interaction") or 0.0),
                    "speedScore": float(score.get("speed") or 0.0),
                    "continuityScore": float(score.get("continuity") or 0.0),
                    "coverageScore": float(score.get("coverage") or 0.0),
                },
                "raw": {
                    "incomingMessages": int(agg.incoming),
                    "outgoingMessages": int(agg.outgoing),
                    "totalMessages": int(agg.total),
                    "interaction": int(agg.interaction),
                    "replyCount": int(agg.replies),
                    "avgReplySeconds": float(agg.avg_reply_seconds()),
                    "avgReplySecondsCapped": float(agg.avg_reply_seconds_capped()),
                    "activeDays": int(agg.active_days_count),
                    "timeBucketsCount": int(agg.time_bucket_count),
                },
                "isFallback": False,
            }
        )

    winner_month_counts: dict[str, int] = {}
    for item in months:
        w = item.get("winner")
        if not isinstance(w, dict):
            continue
        u = str(w.get("username") or "").strip()
        if not u:
            continue
        winner_month_counts[u] = int(winner_month_counts.get(u, 0)) + 1

    top_champion = None
    if winner_month_counts:
        champion_username = sorted(winner_month_counts.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))[0][0]
        champion_months = int(winner_month_counts.get(champion_username) or 0)
        row = contact_rows.get(champion_username)
        display = _pick_display_name(row, champion_username)
        top_champion = {
            "username": champion_username,
            "displayName": display,
            "maskedName": _mask_name(display),
            "monthsWon": champion_months,
        }

    filled_months = [int(x.get("month") or 0) for x in months if isinstance(x.get("winner"), dict)]

    return {
        "year": int(year),
        "months": months,
        "summary": {
            "monthsWithWinner": int(len(filled_months)),
            "topChampion": top_champion,
            "filledMonths": filled_months,
        },
        "settings": {
            "weights": {
                "interaction": float(weights["interaction"]),
                "speed": float(weights["speed"]),
                "continuity": float(weights["continuity"]),
                "coverage": float(weights["coverage"]),
            },
            "tauSeconds": int(tau_seconds),
            "gapCapSeconds": int(gap_cap_seconds),
            "eligibility": {
                "minTotalMessages": int(eligibility["minTotalMessages"]),
                "minInteraction": int(eligibility["minInteraction"]),
                "minReplyCount": int(eligibility["minReplyCount"]),
                "minActiveDays": int(eligibility["minActiveDays"]),
            },
            "usedIndex": bool(used_index),
            "indexStatus": index_status,
        },
    }


def build_card_04_monthly_best_friends_wall(*, account_dir: Path, year: int) -> dict[str, Any]:
    data = compute_monthly_best_friends_wall_stats(account_dir=account_dir, year=year)
    summary = dict(data.get("summary") or {})
    top_champion = summary.get("topChampion")
    months_with_winner = int(summary.get("monthsWithWinner") or 0)

    if months_with_winner <= 0:
        narrative = "今年还没有足够的聊天互动数据来评选每月最佳好友（或搜索索引尚未就绪）。"
    elif isinstance(top_champion, dict) and top_champion.get("displayName"):
        champ_name = str(top_champion.get("displayName") or "")
        months_won = int(top_champion.get("monthsWon") or 0)
        narrative = f"{champ_name} 拿下了 {months_won} 个月的月度最佳好友；这一年你们的聊天默契很稳定。"
    else:
        narrative = f"你在 {months_with_winner} 个月里都出现了稳定的“月度最佳好友”。"

    return {
        "id": 4,
        "title": "陪你走过每个月的人",
        "scope": "global",
        "category": "B",
        "status": "ok",
        "kind": "chat/monthly_best_friends_wall",
        "narrative": narrative,
        "data": data,
    }
