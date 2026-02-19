from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..chat_helpers import _iter_message_db_paths, _quote_ident, _resolve_account_dir
from ..chat_search_index import get_chat_search_index_db_path
from ..logging_config import get_logger
from .storage import wrapped_cache_dir, wrapped_cache_path
from .cards.card_00_global_overview import build_card_00_global_overview
from .cards.card_01_cyber_schedule import WeekdayHourHeatmap, build_card_01_cyber_schedule, compute_weekday_hour_heatmap
from .cards.card_02_message_chars import build_card_02_message_chars
from .cards.card_03_reply_speed import build_card_03_reply_speed
from .cards.card_04_monthly_best_friends_wall import build_card_04_monthly_best_friends_wall
from .cards.card_04_emoji_universe import build_card_04_emoji_universe

logger = get_logger(__name__)


# We use this number to version the cache filename so adding more cards won't accidentally serve
# an older partial cache.
_IMPLEMENTED_UPTO_ID = 5
# Bump this when we change card payloads/ordering while keeping the same implemented_upto.
_CACHE_VERSION = 18


# "Manifest" is used by the frontend to render the deck quickly, then lazily fetch each card.
# Keep this list in display order (same as the old monolithic `/api/wrapped/annual` response).
_WRAPPED_CARD_MANIFEST: tuple[dict[str, Any], ...] = (
    {
        "id": 0,
        "title": "这一年，你的微信都经历了什么？",
        "scope": "global",
        "category": "A",
        "kind": "global/overview",
    },
    {
        "id": 1,
        "title": "你是「早八人」还是「夜猫子」？",
        "scope": "global",
        "category": "A",
        "kind": "time/weekday_hour_heatmap",
    },
    {
        "id": 2,
        "title": "你今年打了多少字？够写一本书吗？",
        "scope": "global",
        "category": "C",
        "kind": "text/message_chars",
    },
    {
        "id": 3,
        "title": "谁是你「秒回」的置顶关心？",
        "scope": "global",
        "category": "B",
        "kind": "chat/reply_speed",
    },
    {
        "id": 4,
        "title": "这一年，每个月谁最懂你？",
        "scope": "global",
        "category": "B",
        "kind": "chat/monthly_best_friends_wall",
    },
    {
        "id": 5,
        "title": "这一年，你的表情包里藏了多少心情？",
        "scope": "global",
        "category": "B",
        "kind": "emoji/annual_universe",
    },
)
_WRAPPED_CARD_ID_SET = {int(c["id"]) for c in _WRAPPED_CARD_MANIFEST}


# Prevent duplicated heavy computations when multiple card endpoints are hit concurrently.
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _get_lock(key: str) -> threading.Lock:
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[key] = lock
        return lock


def _default_year() -> int:
    return datetime.now().year


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


def list_wrapped_available_years(*, account_dir: Path) -> list[int]:
    """List years that have *any* chat messages for the account (best-effort).

    Prefer using `chat_search_index.db` (fast). If not available, fall back to scanning message
    shard databases (slower, but works without the index).
    """

    # Try a tiny cache first (years don't change often, but scanning can be expensive).
    cache_path = wrapped_cache_dir(account_dir) / "available_years.json"
    max_mtime = 0
    try:
        index_path = get_chat_search_index_db_path(account_dir)
        if index_path.exists():
            max_mtime = max(max_mtime, int(index_path.stat().st_mtime))
    except Exception:
        pass
    try:
        for p in _iter_message_db_paths(account_dir):
            try:
                if p.name.lower().startswith("biz_message"):
                    continue
                if p.exists():
                    max_mtime = max(max_mtime, int(p.stat().st_mtime))
            except Exception:
                continue
    except Exception:
        pass

    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(cached, dict):
                sig = int(cached.get("max_mtime") or 0)
                years = cached.get("years")
                if sig == max_mtime and isinstance(years, list):
                    out: list[int] = []
                    for x in years:
                        try:
                            y = int(x)
                        except Exception:
                            continue
                        if y > 0:
                            out.append(y)
                    out.sort(reverse=True)
                    return out
        except Exception:
            pass

    # Convert millisecond timestamps defensively (some datasets store ms).
    # The expression yields epoch seconds as INTEGER.
    ts_expr = (
        "CASE "
        "WHEN CAST(create_time AS INTEGER) > 1000000000000 "
        "THEN CAST(CAST(create_time AS INTEGER)/1000 AS INTEGER) "
        "ELSE CAST(create_time AS INTEGER) "
        "END"
    )

    # Fast path: use our unified search index when available.
    index_path = get_chat_search_index_db_path(account_dir)
    if index_path.exists():
        conn = sqlite3.connect(str(index_path))
        try:
            has_fts = (
                conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='message_fts' LIMIT 1").fetchone()
                is not None
            )
            if has_fts:
                sql = (
                    "SELECT "
                    "CAST(strftime('%Y', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) AS y, "
                    "COUNT(1) AS cnt "
                    "FROM ("
                    f"  SELECT {ts_expr} AS ts"
                    "  FROM message_fts"
                    f"  WHERE {ts_expr} > 0"
                    "    AND db_stem NOT LIKE 'biz_message%'"
                    ") sub "
                    "GROUP BY y "
                    "HAVING cnt > 0 "
                    "ORDER BY y DESC"
                )
                try:
                    rows = conn.execute(sql).fetchall()
                except Exception:
                    rows = []
                years: list[int] = []
                for r in rows:
                    if not r:
                        continue
                    try:
                        y = int(r[0])
                        cnt = int(r[1] or 0)
                    except Exception:
                        continue
                    if y > 0 and cnt > 0:
                        years.append(y)
                years.sort(reverse=True)
                try:
                    cache_path.write_text(
                        json.dumps({"max_mtime": max_mtime, "years": years}, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except Exception:
                    pass
                return years
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # Fallback: scan message shard DBs (may be slow on very large datasets, but only runs
    # when the index does not exist).
    year_counts: dict[int, int] = {}
    db_paths = _iter_message_db_paths(account_dir)
    db_paths = [p for p in db_paths if not p.name.lower().startswith("biz_message")]
    for db_path in db_paths:
        if not db_path.exists():
            continue
        conn = sqlite3.connect(str(db_path))
        try:
            tables = _list_message_tables(conn)
            if not tables:
                continue
            for table_name in tables:
                qt = _quote_ident(table_name)
                sql = (
                    "SELECT "
                    "CAST(strftime('%Y', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) AS y, "
                    "COUNT(1) AS cnt "
                    "FROM ("
                    f"  SELECT {ts_expr} AS ts"
                    f"  FROM {qt}"
                    f"  WHERE {ts_expr} > 0"
                    ") sub "
                    "GROUP BY y"
                )
                try:
                    rows = conn.execute(sql).fetchall()
                except Exception:
                    continue
                for r in rows:
                    if not r:
                        continue
                    try:
                        y = int(r[0])
                        cnt = int(r[1] or 0)
                    except Exception:
                        continue
                    if y > 0 and cnt > 0:
                        year_counts[y] = int(year_counts.get(y, 0)) + cnt
        finally:
            try:
                conn.close()
            except Exception:
                pass

    years = [y for y, cnt in year_counts.items() if int(cnt) > 0]
    years.sort(reverse=True)
    try:
        cache_path.write_text(
            json.dumps({"max_mtime": max_mtime, "years": years}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass
    return years


def build_wrapped_annual_response(
    *,
    account: Optional[str],
    year: Optional[int],
    refresh: bool = False,
) -> dict[str, Any]:
    """Build annual wrapped response for the given account/year.

    For now we implement cards up to id=5 (plus a meta overview card id=0).
    """

    account_dir = _resolve_account_dir(account)

    available_years = list_wrapped_available_years(account_dir=account_dir)

    # If the requested year has no messages, snap to the latest available year so the selector only
    # shows years with data.
    y = int(year or _default_year())
    if available_years and y not in available_years:
        y = int(available_years[0])
    scope = "global"

    cache_path = wrapped_cache_path(
        account_dir=account_dir,
        scope=scope,
        year=y,
        implemented_upto=_IMPLEMENTED_UPTO_ID,
        options_tag=f"v{_CACHE_VERSION}",
    )
    if (not refresh) and cache_path.exists():
        try:
            cached_obj = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(cached_obj, dict) and isinstance(cached_obj.get("cards"), list):
                cached_obj["cached"] = True
                cached_obj["availableYears"] = available_years
                return cached_obj
        except Exception:
            pass

    cards: list[dict[str, Any]] = []
    # Wrapped cards default to "messages sent by me" (outgoing), to avoid mixing directions
    # in first-person narratives like "你最常...".
    heatmap_sent = _get_or_compute_heatmap_sent(account_dir=account_dir, scope=scope, year=y, refresh=refresh)
    # Page 2: global overview (page 1 is the frontend cover slide).
    cards.append(build_card_00_global_overview(account_dir=account_dir, year=y, heatmap=heatmap_sent))
    # Page 3: cyber schedule heatmap.
    cards.append(build_card_01_cyber_schedule(account_dir=account_dir, year=y, heatmap=heatmap_sent))
    # Page 4: message char counts (sent vs received).
    cards.append(build_card_02_message_chars(account_dir=account_dir, year=y))
    # Page 5: reply speed / best chat buddy.
    cards.append(build_card_03_reply_speed(account_dir=account_dir, year=y))
    # Page 6: monthly best friends wall (photo wall).
    cards.append(build_card_04_monthly_best_friends_wall(account_dir=account_dir, year=y))
    # Page 7: annual emoji universe / meme almanac.
    cards.append(build_card_04_emoji_universe(account_dir=account_dir, year=y))

    obj: dict[str, Any] = {
        "account": account_dir.name,
        "year": y,
        "scope": scope,
        "username": None,
        "generated_at": int(time.time()),
        "cached": False,
        "availableYears": available_years,
        "cards": cards,
    }

    try:
        cache_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logger.exception("Failed to write wrapped cache: %s", cache_path)

    return obj


def build_wrapped_annual_meta(
    *,
    account: Optional[str],
    year: Optional[int],
    refresh: bool = False,
) -> dict[str, Any]:
    """Return a light-weight manifest for the Wrapped annual deck.

    This is meant to be fast so the frontend can render the deck first, then
    request each page (card) lazily to avoid freezing on initial load.
    """

    account_dir = _resolve_account_dir(account)

    available_years = list_wrapped_available_years(account_dir=account_dir)

    # Keep the same year snapping semantics as `build_wrapped_annual_response`.
    y = int(year or _default_year())
    if available_years and y not in available_years:
        y = int(available_years[0])

    if refresh:
        # The manifest itself is static today, but we keep the flag for API symmetry.
        pass

    return {
        "account": account_dir.name,
        "year": y,
        "scope": "global",
        "availableYears": available_years,
        # Shallow copy so callers can't mutate our module-level tuple.
        "cards": [dict(c) for c in _WRAPPED_CARD_MANIFEST],
    }


def _wrapped_cache_suffix() -> str:
    return f"_v{_CACHE_VERSION}"


def _wrapped_card_cache_path(*, account_dir: Path, scope: str, year: int, card_id: int) -> Path:
    # Keep stable names; per-account directory already namespaces the files.
    return wrapped_cache_dir(account_dir) / f"{scope}_{year}_card_{card_id}{_wrapped_cache_suffix()}.json"


def _wrapped_heatmap_sent_cache_path(*, account_dir: Path, scope: str, year: int) -> Path:
    return wrapped_cache_dir(account_dir) / f"{scope}_{year}_heatmap_sent{_wrapped_cache_suffix()}.json"


def _load_cached_heatmap_sent(path: Path) -> WeekdayHourHeatmap | None:
    if not path.exists():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(obj, dict):
        return None

    weekday_labels = obj.get("weekdayLabels")
    hour_labels = obj.get("hourLabels")
    matrix = obj.get("matrix")
    total = obj.get("totalMessages")

    if not isinstance(weekday_labels, list) or not isinstance(hour_labels, list) or not isinstance(matrix, list):
        return None

    try:
        total_i = int(total or 0)
    except Exception:
        total_i = 0

    # Best-effort sanitize matrix to ints; keep shape if possible.
    out_matrix: list[list[int]] = []
    for row in matrix:
        if not isinstance(row, list):
            return None
        out_row: list[int] = []
        for v in row:
            try:
                out_row.append(int(v or 0))
            except Exception:
                out_row.append(0)
        out_matrix.append(out_row)

    return WeekdayHourHeatmap(
        weekday_labels=[str(x) for x in weekday_labels],
        hour_labels=[str(x) for x in hour_labels],
        matrix=out_matrix,
        total_messages=total_i,
    )


def _get_or_compute_heatmap_sent(*, account_dir: Path, scope: str, year: int, refresh: bool) -> WeekdayHourHeatmap:
    path = _wrapped_heatmap_sent_cache_path(account_dir=account_dir, scope=scope, year=year)
    lock = _get_lock(str(path))
    with lock:
        if not refresh:
            cached = _load_cached_heatmap_sent(path)
            if cached is not None:
                return cached

        heatmap = compute_weekday_hour_heatmap(account_dir=account_dir, year=year, sender_username=account_dir.name)
        try:
            path.write_text(
                json.dumps(
                    {
                        "weekdayLabels": heatmap.weekday_labels,
                        "hourLabels": heatmap.hour_labels,
                        "matrix": heatmap.matrix,
                        "totalMessages": heatmap.total_messages,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("Failed to write wrapped heatmap cache: %s", path)
        return heatmap


def build_wrapped_annual_card(
    *,
    account: Optional[str],
    year: Optional[int],
    card_id: int,
    refresh: bool = False,
) -> dict[str, Any]:
    """Build one Wrapped card (page) on-demand.

    The result is cached per account/year/card_id to avoid recomputing when users
    flip back and forth between pages.
    """

    cid = int(card_id)
    if cid not in _WRAPPED_CARD_ID_SET:
        raise ValueError(f"Unknown Wrapped card id: {cid}")

    account_dir = _resolve_account_dir(account)

    available_years = list_wrapped_available_years(account_dir=account_dir)
    y = int(year or _default_year())
    if available_years and y not in available_years:
        y = int(available_years[0])

    scope = "global"
    cache_path = _wrapped_card_cache_path(account_dir=account_dir, scope=scope, year=y, card_id=cid)

    lock = _get_lock(str(cache_path))
    with lock:
        if (not refresh) and cache_path.exists():
            try:
                cached_obj = json.loads(cache_path.read_text(encoding="utf-8"))
                if isinstance(cached_obj, dict) and int(cached_obj.get("id") or -1) == cid:
                    return cached_obj
            except Exception:
                pass

        heatmap_sent: WeekdayHourHeatmap | None = None
        if cid in (0, 1):
            heatmap_sent = _get_or_compute_heatmap_sent(account_dir=account_dir, scope=scope, year=y, refresh=refresh)

        if cid == 0:
            card = build_card_00_global_overview(account_dir=account_dir, year=y, heatmap=heatmap_sent)
        elif cid == 1:
            card = build_card_01_cyber_schedule(account_dir=account_dir, year=y, heatmap=heatmap_sent)
        elif cid == 2:
            card = build_card_02_message_chars(account_dir=account_dir, year=y)
        elif cid == 3:
            card = build_card_03_reply_speed(account_dir=account_dir, year=y)
        elif cid == 4:
            card = build_card_04_monthly_best_friends_wall(account_dir=account_dir, year=y)
        elif cid == 5:
            card = build_card_04_emoji_universe(account_dir=account_dir, year=y)
        else:
            # Should be unreachable due to _WRAPPED_CARD_ID_SET check.
            raise ValueError(f"Unknown Wrapped card id: {cid}")

        try:
            cache_path.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("Failed to write wrapped card cache: %s", cache_path)

        return card
