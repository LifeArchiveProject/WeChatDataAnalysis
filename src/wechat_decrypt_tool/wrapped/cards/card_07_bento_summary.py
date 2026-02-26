from __future__ import annotations

from typing import Any


def _as_data(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        return {}
    data = obj.get("data")
    if isinstance(data, dict):
        return data
    return obj


def _pick_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return int(default)


def _pick_float(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        return v if v == v else float(default)  # NaN guard
    except Exception:
        return float(default)


def _pick_str(x: Any, default: str = "") -> str:
    s = str(x or "").strip()
    return s if s else str(default)


def _pick_obj(d: Any, keys: tuple[str, ...]) -> dict[str, Any] | None:
    if not isinstance(d, dict):
        return None
    out: dict[str, Any] = {}
    for k in keys:
        if k in d:
            out[k] = d.get(k)
    return out if out else None


def build_card_07_bento_summary_from_sources(
    *,
    year: int,
    overview: dict[str, Any],
    heatmap: dict[str, Any],
    message_chars: dict[str, Any],
    reply_speed: dict[str, Any],
    monthly: dict[str, Any],
    emoji: dict[str, Any],
) -> dict[str, Any]:
    """Card #7: Bento Summary (prototype style merged into Wrapped deck).

    The frontend expects a stable `data.snapshot` object to render without running extra JS.
    """

    overview_d = _as_data(overview)
    heatmap_d = _as_data(heatmap)
    message_chars_d = _as_data(message_chars)
    reply_speed_d = _as_data(reply_speed)
    monthly_d = _as_data(monthly)
    emoji_d = _as_data(emoji)

    top_group_raw = overview_d.get("topGroup")
    top_group = None
    if isinstance(top_group_raw, dict):
        display = _pick_str(top_group_raw.get("displayName"), "--")
        top_group = {
            "displayName": display,
            "maskedName": display,
            "avatarUrl": _pick_str(top_group_raw.get("avatarUrl"), ""),
            "messages": _pick_int(top_group_raw.get("messages"), 0),
        }

    best_buddy_raw = reply_speed_d.get("bestBuddy")
    best_buddy = None
    if isinstance(best_buddy_raw, dict):
        display = _pick_str(best_buddy_raw.get("displayName"), "--")
        best_buddy = {
            "displayName": display,
            "maskedName": display,
            "avatarUrl": _pick_str(best_buddy_raw.get("avatarUrl"), ""),
            "totalMessages": _pick_int(best_buddy_raw.get("totalMessages"), 0),
            "longestStreakDays": _pick_int(best_buddy_raw.get("longestStreakDays"), 0),
            "peakHour": best_buddy_raw.get("peakHour"),
            "peakHourLabel": _pick_str(best_buddy_raw.get("peakHourLabel"), ""),
        }

    fastest_raw = reply_speed_d.get("fastest")
    fastest = None
    if isinstance(fastest_raw, dict):
        display = _pick_str(fastest_raw.get("displayName"), "--")
        fastest = {
            "displayName": display,
            "maskedName": display,
            "avatarUrl": _pick_str(fastest_raw.get("avatarUrl"), ""),
            "seconds": _pick_int(fastest_raw.get("seconds"), 0),
        }

    slowest_raw = reply_speed_d.get("slowest")
    slowest = None
    if isinstance(slowest_raw, dict):
        display = _pick_str(slowest_raw.get("displayName"), "--")
        slowest = {
            "displayName": display,
            "maskedName": display,
            "avatarUrl": _pick_str(slowest_raw.get("avatarUrl"), ""),
            "seconds": _pick_int(slowest_raw.get("seconds"), 0),
        }

    reply_stats_raw = reply_speed_d.get("replyStats")
    reply_stats = None
    if isinstance(reply_stats_raw, dict):
        reply_stats = {
            "p50Seconds": reply_stats_raw.get("p50Seconds"),
            "p90Seconds": reply_stats_raw.get("p90Seconds"),
        }

    top_phrase_raw = overview_d.get("topPhrase")
    top_phrase = None
    if isinstance(top_phrase_raw, dict):
        phrase = _pick_str(top_phrase_raw.get("phrase"), "")
        count = _pick_int(top_phrase_raw.get("count"), 0)
        if phrase and count > 0:
            top_phrase = {"phrase": phrase, "count": count}

    sent_sticker_count = _pick_int(emoji_d.get("sentStickerCount"), _pick_int(overview_d.get("sentStickerCount"), 0))
    top_sticker = None
    top_stickers = emoji_d.get("topStickers")
    if isinstance(top_stickers, list) and top_stickers:
        x0 = top_stickers[0] if isinstance(top_stickers[0], dict) else None
        if x0:
            url = _pick_str(x0.get("emojiUrl") or x0.get("imageUrl") or x0.get("url"), "")
            cnt = _pick_int(x0.get("count"), 0)
            if url:
                top_sticker = {"imageUrl": url, "count": cnt}

    top_unicode_emoji = ""
    top_unicode_emoji_count = 0
    top_unicode_emojis = emoji_d.get("topUnicodeEmojis")
    if isinstance(top_unicode_emojis, list) and top_unicode_emojis:
        x0 = top_unicode_emojis[0] if isinstance(top_unicode_emojis[0], dict) else None
        if x0:
            top_unicode_emoji = _pick_str(x0.get("emoji"), "")
            top_unicode_emoji_count = _pick_int(x0.get("count"), 0)

    # "Top emoji" should be picked across both unicode emoji and WeChat built-in emoji.
    # The deck has a separate "sticker" card; here we focus on emoji-like items.
    top_emoji: dict[str, Any] | None = None
    emoji_candidates: list[dict[str, Any]] = []

    top_wechat_emojis = emoji_d.get("topWechatEmojis")
    if isinstance(top_wechat_emojis, list) and top_wechat_emojis:
        for item in top_wechat_emojis:
            if not isinstance(item, dict):
                continue
            key = _pick_str(item.get("key"), "")
            cnt = _pick_int(item.get("count"), 0)
            if key and cnt > 0:
                emoji_candidates.append(
                    {
                        "kind": "wechat",
                        "key": key,
                        "count": cnt,
                        "assetPath": _pick_str(item.get("assetPath"), ""),
                    }
                )

    top_text_emojis = emoji_d.get("topTextEmojis")
    if isinstance(top_text_emojis, list) and top_text_emojis:
        for item in top_text_emojis:
            if not isinstance(item, dict):
                continue
            key = _pick_str(item.get("key"), "")
            cnt = _pick_int(item.get("count"), 0)
            if key and cnt > 0:
                emoji_candidates.append(
                    {
                        "kind": "wechat",
                        "key": key,
                        "count": cnt,
                        "assetPath": _pick_str(item.get("assetPath"), ""),
                    }
                )

    if isinstance(top_unicode_emojis, list) and top_unicode_emojis:
        for item in top_unicode_emojis:
            if not isinstance(item, dict):
                continue
            emo = _pick_str(item.get("emoji"), "")
            cnt = _pick_int(item.get("count"), 0)
            if emo and cnt > 0:
                emoji_candidates.append({"kind": "unicode", "emoji": emo, "count": cnt})

    if emoji_candidates:
        best = max(
            emoji_candidates,
            key=lambda x: (
                _pick_int(x.get("count"), 0),
                1 if str(x.get("kind")) == "wechat" else 0,
                _pick_str(x.get("key") or x.get("emoji"), ""),
            ),
        )
        if str(best.get("kind")) == "wechat":
            top_emoji = {
                "kind": "wechat",
                "key": _pick_str(best.get("key"), ""),
                "count": _pick_int(best.get("count"), 0),
                "assetPath": _pick_str(best.get("assetPath"), ""),
            }
        else:
            top_emoji = {
                "kind": "unicode",
                "emoji": _pick_str(best.get("emoji"), ""),
                "count": _pick_int(best.get("count"), 0),
            }

    monthly_best_buddies: list[dict[str, Any]] = []
    months = monthly_d.get("months")
    if isinstance(months, list) and months:
        for item in months:
            if not isinstance(item, dict):
                continue
            m = _pick_int(item.get("month"), 0)
            winner = item.get("winner") if isinstance(item.get("winner"), dict) else None
            metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else None
            raw = item.get("raw") if isinstance(item.get("raw"), dict) else None
            monthly_best_buddies.append(
                {
                    "month": m,
                    "displayName": _pick_str((winner or {}).get("displayName"), "--"),
                    "maskedName": _pick_str((winner or {}).get("displayName"), "--"),
                    "avatarUrl": _pick_str((winner or {}).get("avatarUrl"), ""),
                    "messages": _pick_int((raw or {}).get("totalMessages"), 0),
                    "metrics": metrics if metrics else None,
                }
            )

    # Ensure we always return 12 items for the grid.
    if len(monthly_best_buddies) != 12:
        fixed = {int(x.get("month") or 0): x for x in monthly_best_buddies if isinstance(x, dict)}
        monthly_best_buddies = []
        for m in range(1, 13):
            monthly_best_buddies.append(
                fixed.get(m)
                or {
                    "month": m,
                    "displayName": "--",
                    "maskedName": "--",
                    "avatarUrl": "",
                    "messages": 0,
                    "metrics": None,
                }
            )

    snapshot: dict[str, Any] = {
        "year": _pick_int(year),
        "totalMessages": _pick_int(overview_d.get("totalMessages"), _pick_int(heatmap_d.get("totalMessages"), 0)),
        "messagesPerDay": _pick_float(overview_d.get("messagesPerDay"), 0.0),
        "sentChars": _pick_int(message_chars_d.get("sentChars"), 0),
        "addedFriends": _pick_int(overview_d.get("addedFriends"), 0),
        "mostActiveHour": overview_d.get("mostActiveHour"),
        "topGroup": top_group,
        "bestBuddy": best_buddy,
        "fastest": fastest,
        "slowest": slowest,
        "replyStats": reply_stats,
        "topPhrase": top_phrase,
        "sentStickerCount": int(sent_sticker_count),
        "topSticker": top_sticker,
        "topEmoji": top_emoji,
        "topUnicodeEmoji": top_unicode_emoji,
        "topUnicodeEmojiCount": int(top_unicode_emoji_count),
        "monthlyBestBuddies": monthly_best_buddies,
        "weekdayLabels": heatmap_d.get("weekdayLabels") or [],
        "hourLabels": heatmap_d.get("hourLabels") or [],
        "weekdayHourMatrix": heatmap_d.get("matrix") or [],
    }

    return {
        "id": 7,
        "title": "便当总览：一屏看完这一年",
        "scope": "global",
        "category": "A",
        "status": "ok",
        "kind": "global/bento_summary",
        "narrative": "把这一年的关键信息装进一份便当。",
        "data": {"snapshot": snapshot},
    }
