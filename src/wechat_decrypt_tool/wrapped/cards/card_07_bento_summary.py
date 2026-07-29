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
    keywords: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Card #7: Bento Summary (prototype style merged into Wrapped deck).

    The frontend expects a stable `data.snapshot` object to render without running extra JS.

    末页要在一屏内直显前面所有卡片的内容，所以这里把各 source 已经算好的字段尽量透传过来，
    全部只做挑选 + 裁剪，不额外查库。``keywords`` 是后加的第 7 个 source，默认 None 以兼容旧调用方。
    """

    overview_d = _as_data(overview)
    heatmap_d = _as_data(heatmap)
    message_chars_d = _as_data(message_chars)
    reply_speed_d = _as_data(reply_speed)
    monthly_d = _as_data(monthly)
    emoji_d = _as_data(emoji)
    keywords_d = _as_data(keywords or {})

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

    # 末页右下角要并排显示前 5 个表情：沿用上面的候选池，按次数排序去重后取 5。
    top_emojis: list[dict[str, Any]] = []
    if emoji_candidates:
        seen: set[str] = set()
        for it in sorted(
            emoji_candidates,
            key=lambda x: (
                -_pick_int(x.get("count"), 0),
                0 if str(x.get("kind")) == "wechat" else 1,
                _pick_str(x.get("key") or x.get("emoji"), ""),
            ),
        ):
            kind = str(it.get("kind"))
            token = _pick_str(it.get("key") or it.get("emoji"), "")
            dedup = f"{kind}:{token}"
            if not token or dedup in seen:
                continue
            seen.add(dedup)
            if kind == "wechat":
                top_emojis.append(
                    {
                        "kind": "wechat",
                        "key": token,
                        "count": _pick_int(it.get("count"), 0),
                        "assetPath": _pick_str(it.get("assetPath"), ""),
                    }
                )
            else:
                top_emojis.append({"kind": "unicode", "emoji": token, "count": _pick_int(it.get("count"), 0)})
            if len(top_emojis) >= 5:
                break

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

    # Card 0 已经算好、但此前没有透传给便当页的字段。这些是「年鉴」版面里人情味最重的素材
    # （峰值日当天的首末原话、365 天逐日计数、活跃天数），全部复用 overview 的结果，不额外查库。
    top_contact_raw = overview_d.get("topContact")
    top_contact = None
    if isinstance(top_contact_raw, dict):
        display = _pick_str(top_contact_raw.get("displayName"), "--")
        top_contact = {
            "displayName": display,
            "maskedName": display,
            "avatarUrl": _pick_str(top_contact_raw.get("avatarUrl"), ""),
            "messages": _pick_int(top_contact_raw.get("messages"), 0),
        }

    peak_day_raw = overview_d.get("peakDay")
    peak_day = peak_day_raw if isinstance(peak_day_raw, dict) else None

    annual_heatmap_raw = overview_d.get("annualHeatmap")
    annual_heatmap = annual_heatmap_raw if isinstance(annual_heatmap_raw, dict) else None

    # 深夜专栏：card 1（赛博作息）已经算好了 partner + latestMoment，直接透传。
    # latestMoment.direction 区分 sent/received，前端据此决定这句话该署「你」还是对方。
    night_raw = heatmap_d.get("nightCompanion")
    night_companion = None
    if isinstance(night_raw, dict):
        partner_raw = night_raw.get("partner")
        moment_raw = night_raw.get("latestMoment")
        partner = None
        if isinstance(partner_raw, dict):
            display = _pick_str(partner_raw.get("displayName"), "--")
            partner = {
                "displayName": display,
                "maskedName": display,
                "avatarUrl": _pick_str(partner_raw.get("avatarUrl"), ""),
                "nightMessages": _pick_int(partner_raw.get("nightMessages"), 0),
                "sharePct": _pick_float(partner_raw.get("sharePct"), 0.0),
            }
        moment = moment_raw if isinstance(moment_raw, dict) and _pick_str(moment_raw.get("content")) else None
        if partner or moment:
            night_companion = {
                "nightMessagesTotal": _pick_int(night_raw.get("nightMessagesTotal"), 0),
                "myNightMessages": _pick_int(night_raw.get("myNightMessages"), 0),
                "partner": partner,
                "latestMoment": moment,
            }

    # ---- 以下全部是「前面各卡已算好、末页要直显」的透传字段 ----

    def _person(raw: Any, extra: tuple[str, ...] = ()) -> dict[str, Any] | None:
        """统一的人物摘要：只带昵称/头像 + 指定的几个计数，绝不整包透传。"""
        if not isinstance(raw, dict):
            return None
        display = _pick_str(raw.get("displayName"), "--")
        out: dict[str, Any] = {
            "displayName": display,
            "maskedName": display,
            "avatarUrl": _pick_str(raw.get("avatarUrl"), ""),
        }
        for k in extra:
            if k in raw:
                out[k] = raw.get(k)
        return out

    # card 2：字数 / 键盘 / 语音 / 通话
    sent_book = message_chars_d.get("sentBook") if isinstance(message_chars_d.get("sentBook"), dict) else None
    keyboard_raw = message_chars_d.get("keyboard")
    keyboard = None
    if isinstance(keyboard_raw, dict):
        hits = keyboard_raw.get("keyHits")
        top_keys: list[dict[str, Any]] = []
        if isinstance(hits, dict):
            # 104 键全量没用，只取前 3
            for k, v in sorted(hits.items(), key=lambda kv: -_pick_int(kv[1], 0))[:3]:
                top_keys.append({"key": _pick_str(k), "count": _pick_int(v, 0)})
        elif isinstance(hits, list):
            for it in sorted(
                [x for x in hits if isinstance(x, dict)], key=lambda x: -_pick_int(x.get("count"), 0)
            )[:3]:
                top_keys.append({"key": _pick_str(it.get("key")), "count": _pick_int(it.get("count"), 0)})
        keyboard = {"totalKeyHits": _pick_int(keyboard_raw.get("totalKeyHits"), 0), "topKeys": top_keys}

    voice_raw = message_chars_d.get("voice")
    voice = None
    if isinstance(voice_raw, dict):
        voice = {
            "sentSeconds": _pick_int(voice_raw.get("sentSeconds"), 0),
            "sentCount": _pick_int(voice_raw.get("sentCount"), 0),
            "receivedSeconds": _pick_int(voice_raw.get("receivedSeconds"), 0),
            "receivedCount": _pick_int(voice_raw.get("receivedCount"), 0),
            "topSentPartner": _person(voice_raw.get("topSentPartner"), ("count",)),
            "topReceivedPartner": _person(voice_raw.get("topReceivedPartner"), ("count",)),
            "longest": _pick_obj(voice_raw.get("longest"), ("seconds", "direction", "displayName", "date")),
        }

    calls_raw = message_chars_d.get("calls")
    calls = None
    if isinstance(calls_raw, dict):
        calls = {
            "totalSeconds": _pick_int(calls_raw.get("totalSeconds"), 0),
            "totalCount": _pick_int(calls_raw.get("totalCount"), 0),
            "connectedCount": _pick_int(calls_raw.get("connectedCount"), 0),
            "videoCount": _pick_int(calls_raw.get("videoCount"), 0),
            "voiceCount": _pick_int(calls_raw.get("voiceCount"), 0),
            "missedOrCanceledCount": _pick_int(calls_raw.get("missedOrCanceledCount"), 0),
            "topPartner": _person(calls_raw.get("topPartner"), ("count", "seconds")),
        }

    # card 1：全年第一条 / 最后一条。只取时间，不取正文——页脚不显示原话，少传即少泄露。
    def _stamp(raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        d, t = _pick_str(raw.get("date")), _pick_str(raw.get("time"))
        return {"date": d, "time": t} if (d or t) else None

    # card 3：谁先开口
    initiative_raw = reply_speed_d.get("initiative")
    initiative = None
    if isinstance(initiative_raw, dict):
        initiative = {
            "conversationCount": _pick_int(initiative_raw.get("conversationCount"), 0),
            "initiatedByMe": _pick_int(initiative_raw.get("initiatedByMe"), 0),
            "initiatedByOthers": _pick_int(initiative_raw.get("initiatedByOthers"), 0),
            "initiationRatePct": _pick_float(initiative_raw.get("initiationRatePct"), 0.0),
            "mutualFriend": _person(initiative_raw.get("mutualFriend"), ("sentCount", "receivedCount")),
            "topInitiatedByMe": [
                x for x in (_person(i, ("count",)) for i in (initiative_raw.get("topInitiatedByMe") or [])[:2]) if x
            ],
            "topInitiatedToMe": [
                x for x in (_person(i, ("count",)) for i in (initiative_raw.get("topInitiatedToMe") or [])[:2]) if x
            ],
        }

    # card 3 年度聊天排行：只取前 3，带双向条需要的 out/in
    top_totals: list[dict[str, Any]] = []
    for it in (reply_speed_d.get("topTotals") or [])[:5]:
        if not isinstance(it, dict):
            continue
        p3 = _person(it, ("outgoingMessages", "incomingMessages", "totalMessages"))
        if p3:
            top_totals.append(p3)

    # card 4 月度：桂冠得主。summary.topChampion 不带头像，按 username 从 months[].winner 回填。
    monthly_summary = None
    summary_raw = monthly_d.get("summary")
    if isinstance(summary_raw, dict):
        champ_raw = summary_raw.get("topChampion")
        champ = None
        if isinstance(champ_raw, dict):
            uname = _pick_str(champ_raw.get("username"), "")
            avatar = ""
            for item in monthly_d.get("months") or []:
                w = item.get("winner") if isinstance(item, dict) else None
                if isinstance(w, dict) and _pick_str(w.get("username")) == uname:
                    avatar = _pick_str(w.get("avatarUrl"), "")
                    break
            display = _pick_str(champ_raw.get("displayName"), "--")
            champ = {
                "displayName": display,
                "maskedName": display,
                "avatarUrl": avatar,
                "monthsWon": _pick_int(champ_raw.get("monthsWon"), 0),
            }
        monthly_summary = {
            "monthsWithWinner": _pick_int(summary_raw.get("monthsWithWinner"), 0),
            "topChampion": champ,
        }

    # card 4 表情：缩略图与斗图对手
    sticker_thumbs: list[dict[str, Any]] = []
    ts_all = emoji_d.get("topStickers")
    if isinstance(ts_all, list):
        for it in ts_all[1:6]:
            if not isinstance(it, dict):
                continue
            url = _pick_str(it.get("emojiUrl") or it.get("imageUrl") or it.get("url"), "")
            if url:
                sticker_thumbs.append({"imageUrl": url, "count": _pick_int(it.get("count"), 0)})

    # card 5 关键词。只取确定性的计数结果；examples / bubbleMessages 每次请求都会变，
    # 透传会让缓存住的 card 7 与实时重建的 card 6 对不上，必须排除。
    kw_list: list[dict[str, Any]] = []
    for it in (keywords_d.get("keywords") or [])[:8]:
        if isinstance(it, dict):
            w = _pick_str(it.get("word") or it.get("phrase"), "")
            if w:
                kw_list.append({"word": w, "count": _pick_int(it.get("count"), 0)})
    top_keyword_raw = keywords_d.get("topKeyword")
    top_keyword = None
    if isinstance(top_keyword_raw, dict):
        w = _pick_str(top_keyword_raw.get("word") or top_keyword_raw.get("phrase"), "")
        if w:
            top_keyword = {"word": w, "count": _pick_int(top_keyword_raw.get("count"), 0)}
    kw_meta_raw = keywords_d.get("meta")
    keyword_meta = None
    if isinstance(kw_meta_raw, dict):
        keyword_meta = {
            "matchedCandidates": _pick_int(kw_meta_raw.get("matchedCandidates"), 0),
            "uniquePhrases": _pick_int(kw_meta_raw.get("uniquePhrases"), 0),
        }

    # bestBuddy 补上往来与回复分布
    if best_buddy is not None and isinstance(best_buddy_raw, dict):
        for k in (
            "outgoingMessages",
            "incomingMessages",
            "replyCount",
            "avgReplySeconds",
            "fastestReplySeconds",
            "slowestReplySeconds",
        ):
            if k in best_buddy_raw:
                best_buddy[k] = best_buddy_raw.get(k)

    snapshot: dict[str, Any] = {
        "year": _pick_int(year),
        "totalMessages": _pick_int(overview_d.get("totalMessages"), _pick_int(heatmap_d.get("totalMessages"), 0)),
        "messagesPerDay": _pick_float(overview_d.get("messagesPerDay"), 0.0),
        "sentChars": _pick_int(message_chars_d.get("sentChars"), 0),
        "addedFriends": _pick_int(overview_d.get("addedFriends"), 0),
        "activeDays": _pick_int(overview_d.get("activeDays"), 0),
        "sentMediaCount": _pick_int(overview_d.get("sentMediaCount"), 0),
        "mostActiveHour": overview_d.get("mostActiveHour"),
        "mostActiveWeekdayName": _pick_str(overview_d.get("mostActiveWeekdayName"), ""),
        "topContact": top_contact,
        "peakDay": peak_day,
        "annualHeatmap": annual_heatmap,
        "nightCompanion": night_companion,
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
        # ---- 末页一屏全览新增 ----
        "sentBook": sent_book,
        "receivedChars": _pick_int(message_chars_d.get("receivedChars"), 0),
        "receivedA4": _pick_obj(message_chars_d.get("receivedA4"), ("text", "object", "a4")),
        "keyboard": keyboard,
        "voice": voice,
        "calls": calls,
        "yearFirstSent": _stamp(heatmap_d.get("yearFirstSent")),
        "yearLastSent": _stamp(heatmap_d.get("yearLastSent")),
        "sentToContacts": _pick_int(reply_speed_d.get("sentToContacts"), 0),
        "initiative": initiative,
        "monthlySummary": monthly_summary,
        "uniqueStickerTypeCount": _pick_int(emoji_d.get("uniqueStickerTypeCount"), 0),
        "stickerPerActiveDay": _pick_float(emoji_d.get("stickerPerActiveDay"), 0.0),
        "stickerShareOfSentMessages": _pick_float(emoji_d.get("stickerShareOfSentMessages"), 0.0),
        "newStickerCountThisYear": _pick_int(emoji_d.get("newStickerCountThisYear"), 0),
        "topBattlePartner": _person(emoji_d.get("topBattlePartner"), ("stickerCount",)),
        "topStickerThumbs": sticker_thumbs,
        "topTotals": top_totals,
        "stickerActiveDays": _pick_int(emoji_d.get("stickerActiveDays"), 0),
        "revivedStickerCount": _pick_int(emoji_d.get("revivedStickerCount"), 0),
        "revivedMaxGapDays": _pick_int(emoji_d.get("revivedMaxGapDays"), 0),
        "stickerPeakHour": emoji_d.get("peakHour"),
        "stickerPeakWeekdayName": _pick_str(emoji_d.get("peakWeekdayName"), ""),
        "topEmojis": top_emojis,
        "topKeyword": top_keyword,
        "keywords": kw_list,
        "keywordMeta": keyword_meta,
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
