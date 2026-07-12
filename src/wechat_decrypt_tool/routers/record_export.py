from __future__ import annotations

import copy
import html
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..chat_export_service import export_prepared_chat_archive
from ..export_integrity import (
    export_css,
    load_wce_integrity_native,
    write_file_integrity_sidecars,
    write_protected_html_file,
)
from ..xlsx_export import build_xlsx_workbook
from .biz import get_biz_messages, get_wechat_pay_records
from .favorites import list_favorites
from .general import (
    list_finder_records,
    list_friend_verifications,
    list_mini_programs,
    list_payment_records,
)


router = APIRouter()

DatasetName = Literal[
    "favorites",
    "friend-verifications",
    "mini-programs",
    "finder",
    "payments",
    "biz",
]
ExportFormat = Literal["html", "json", "txt", "excel"]

_DATASET_LABELS = {
    "favorites": "收藏",
    "friend-verifications": "好友验证",
    "mini-programs": "小程序",
    "finder": "视频号直播",
    "payments": "转账与红包",
    "biz": "服务号记录",
}
_INVALID_FILE_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class RecordExportRequest(BaseModel):
    account: Optional[str] = Field(None, description="账号目录名")
    dataset: DatasetName
    username: str = ""
    subject_name: str = ""
    format: ExportFormat = "html"
    types: list[str] = Field(default_factory=list)
    query: str = ""
    output_dir: str
    file_name: str = ""


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\x00", "").strip()


def _safe_file_stem(value: Any, fallback: str) -> str:
    text = _INVALID_FILE_CHARS_RE.sub("_", _clean_text(value))
    text = re.sub(r"\s+", " ", text).strip(" .")
    for suffix in (".html", ".json", ".txt", ".xlsx", ".excel", ".zip"):
        if text.lower().endswith(suffix):
            text = text[: -len(suffix)].rstrip(" .")
            break
    return (text[:120].rstrip(" .") or fallback)[:120]


def _normalized_types(values: list[str]) -> set[str]:
    result = {_clean_text(value).lower() for value in values if _clean_text(value)}
    result.discard("all")
    return result


def _record_types(dataset: str, item: dict[str, Any]) -> set[str]:
    if dataset == "favorites":
        result: set[str] = set()
        if item.get("textBlocks"):
            result.add("text")
        for part in item.get("attachments") or []:
            render_type = _clean_text(part.get("renderType")).lower()
            result.add(render_type or "other")
        if not result:
            result.add("other")
        return result
    if dataset == "friend-verifications":
        return {"outgoing" if bool(item.get("isSender")) else "incoming"}
    if dataset == "mini-programs":
        return {"mini_program"}
    if dataset == "finder":
        return {_clean_text(item.get("kind")).lower() or "live"}
    if dataset == "payments":
        if _clean_text(item.get("kind")).lower() == "redpacket":
            return {"redpacket"}
        return {_clean_text(item.get("transferState")).lower() or "unknown"}
    if dataset == "biz":
        return {"payment" if item.get("merchant_name") else "article"}
    return {"other"}


def _filter_records(dataset: str, items: list[dict[str, Any]], selected_types: set[str]) -> list[dict[str, Any]]:
    if not selected_types:
        return items
    return [item for item in items if _record_types(dataset, item) & selected_types]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value) if value not in (None, "") else default
    except Exception:
        return default


def _favorite_contact(item: dict[str, Any]) -> dict[str, Any]:
    for key in ("senderContact", "sourceChatContact", "sourceContact"):
        value = item.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _favorite_chat_messages(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    ordered_items = sorted(
        (item for item in items if isinstance(item, dict)),
        key=lambda item: (
            _safe_int(item.get("updateTime"), 0),
            _safe_int(item.get("localId"), 0),
        ),
    )

    for item in ordered_items:
        prepared_count = len(prepared)
        original = item.get("originalMessage") if isinstance(item.get("originalMessage"), dict) else {}
        contact = _favorite_contact(item)
        local_id = _safe_int(item.get("localId"), 0)
        favorite_server_id = _safe_int(item.get("serverId"), 0)
        source_server_id = _safe_int(item.get("sourceId"), 0)
        create_time = _safe_int(item.get("updateTime"), 0) or _safe_int(original.get("createTime"), 0)
        create_time_text = _clean_text(item.get("updateTimeText") or original.get("createTimeText"))
        is_sent = bool(original.get("isSent"))
        media_username = _clean_text(
            item.get("conversationUsername")
            or item.get("sourceChatUsername")
            or item.get("sourceUsername")
        )
        sender_username = _clean_text(
            original.get("senderUsername")
            or item.get("senderUsername")
            or contact.get("username")
            or item.get("sourceUsername")
        )
        sender_display_name = _clean_text(
            original.get("senderDisplayName")
            or contact.get("displayName")
            or contact.get("name")
            or contact.get("nickname")
            or contact.get("remark")
            or item.get("sourceName")
        ) or "未知来源"
        if not sender_username:
            sender_username = f"favorite_source_{local_id or favorite_server_id or len(prepared) + 1}"

        def base_message(suffix: str) -> dict[str, Any]:
            return {
                "id": f"favorite_{local_id}_{favorite_server_id}_{suffix}",
                "localId": local_id,
                "serverId": source_server_id or favorite_server_id,
                "createTime": create_time,
                "createTimeText": create_time_text,
                "isSent": is_sent,
                "senderUsername": sender_username,
                "senderDisplayName": sender_display_name,
                "_mediaUsername": media_username,
            }

        if _safe_int(item.get("type"), 0) == 14:
            message = copy.deepcopy(original)
            message.update(base_message("chat_history"))
            message["type"] = 49
            message["renderType"] = "chatHistory"
            message["title"] = _clean_text(original.get("title") or item.get("title")) or "聊天记录"
            message["content"] = _clean_text(original.get("content") or item.get("summary")) or "聊天记录"
            prepared.append(message)
            # A type-14 favorite already carries its complete recordItem. Expanding its
            # text blocks and attachments here duplicates every entry outside the archive.
            continue

        for index, text in enumerate(item.get("textBlocks") or []):
            content = _clean_text(text)
            if not content:
                continue
            message = base_message(f"text_{index}")
            message.update({"type": 1, "renderType": "text", "content": content})
            prepared.append(message)

        for index, attachment in enumerate(item.get("attachments") or []):
            if not isinstance(attachment, dict):
                continue
            render_type_raw = _clean_text(attachment.get("renderType") or "text")
            render_key = render_type_raw.lower()
            if render_key == "contact":
                render_type = "text"
            elif render_key == "chathistory":
                render_type = "chatHistory"
            else:
                render_type = render_type_raw or "text"

            title = _clean_text(attachment.get("title") or attachment.get("typeLabel")) or "收藏内容"
            content = _clean_text(
                attachment.get("description")
                or attachment.get("title")
                or f"[{_clean_text(attachment.get('typeLabel')) or '收藏内容'}]"
            )
            full_md5 = _clean_text(attachment.get("fullMd5")).lower()
            thumb_md5 = _clean_text(attachment.get("thumbMd5")).lower()
            data_id = _clean_text(attachment.get("dataId"))
            location = attachment.get("location") if isinstance(attachment.get("location"), dict) else {}
            voice_server_id = source_server_id or _safe_int(data_id, 0) or favorite_server_id

            message = base_message(f"attachment_{data_id or index}")
            message.update(
                {
                    "serverId": voice_server_id if render_type == "voice" else (source_server_id or favorite_server_id),
                    "type": _safe_int(attachment.get("dataType"), _safe_int(item.get("type"), 0)),
                    "renderType": render_type,
                    "content": content,
                    "title": title,
                    "url": _clean_text(attachment.get("url") or attachment.get("mediaUrl")),
                    "thumbUrl": _clean_text(attachment.get("preview")),
                    "from": _clean_text(attachment.get("sourceName")),
                    "fromAvatar": _clean_text(attachment.get("sourceAvatar")),
                    "linkType": _clean_text(attachment.get("linkType")),
                    "imageMd5": full_md5 or thumb_md5,
                    "imageMd5Candidates": [value for value in (full_md5, thumb_md5) if value],
                    "imageFileId": data_id if render_type == "image" else "",
                    "imageFileIdCandidates": [data_id] if render_type == "image" and data_id else [],
                    "imageUrl": _clean_text(original.get("imageUrl") if render_type == "image" else ""),
                    "emojiMd5": full_md5 or thumb_md5,
                    "emojiFileId": data_id if render_type == "emoji" else "",
                    "emojiUrl": _clean_text(original.get("emojiUrl") if render_type == "emoji" else ""),
                    "videoMd5": full_md5,
                    "videoThumbMd5": thumb_md5,
                    "videoFileId": data_id if render_type == "video" else "",
                    "videoThumbFileId": data_id if render_type == "video" else "",
                    "videoUrl": _clean_text(original.get("videoUrl") if render_type == "video" else ""),
                    "videoThumbUrl": _clean_text(original.get("videoThumbUrl") if render_type == "video" else ""),
                    "voiceLength": _safe_int(attachment.get("duration"), 0),
                    "fileSize": _safe_int(attachment.get("fullSize"), 0),
                    "fileMd5": full_md5,
                    "fileFileId": data_id if render_type == "file" else "",
                    "locationLat": _clean_text(location.get("latitude")),
                    "locationLng": _clean_text(location.get("longitude")),
                    "locationPoiname": _clean_text(location.get("poiname") or attachment.get("title")),
                    "locationLabel": _clean_text(
                        location.get("label") or location.get("address") or attachment.get("description")
                    ),
                }
            )
            prepared.append(message)

        if len(prepared) == prepared_count:
            fallback = base_message("fallback")
            fallback.update(
                {
                    "type": _safe_int(item.get("type"), 0),
                    "renderType": "text",
                    "content": _clean_text(item.get("summary") or item.get("title") or item.get("typeLabel")) or "收藏内容",
                }
            )
            prepared.append(fallback)

    return prepared


def _collect_pages(loader, *, page_size: int = 500) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    items: list[dict[str, Any]] = []
    offset = 0
    first_response: dict[str, Any] = {}
    while True:
        response = loader(offset, page_size)
        if not first_response:
            first_response = response
        page = response.get("items") if isinstance(response, dict) else []
        page = page if isinstance(page, list) else []
        items.extend(row for row in page if isinstance(row, dict))
        scanned = 0
        try:
            scanned = int(response.get("scanned") if isinstance(response, dict) else 0)
        except Exception:
            scanned = 0
        step = scanned if scanned > 0 else len(page)
        if not response.get("hasMore") or step <= 0:
            break
        offset += step
    return items, first_response


def _load_records(request: Request, req: RecordExportRequest) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    common = {
        "account": req.account,
        "q": _clean_text(req.query),
        "source": "realtime",
    }
    if req.dataset == "favorites":
        return _collect_pages(
            lambda offset, _limit: list_favorites(
                request=request,
                kind="all",
                tag_id=0,
                limit=200,
                offset=offset,
                **common,
            ),
            page_size=200,
        )
    if req.dataset == "friend-verifications":
        return _collect_pages(
            lambda offset, limit: list_friend_verifications(
                request=request,
                limit=limit,
                offset=offset,
                **common,
            )
        )
    if req.dataset == "mini-programs":
        return _collect_pages(
            lambda offset, limit: list_mini_programs(
                limit=limit,
                offset=offset,
                **common,
            )
        )
    if req.dataset == "finder":
        return _collect_pages(
            lambda offset, limit: list_finder_records(
                request=request,
                limit=limit,
                offset=offset,
                **common,
            )
        )
    if req.dataset == "payments":
        return _collect_pages(
            lambda offset, limit: list_payment_records(
                request=request,
                kind="all",
                status="all",
                limit=limit,
                offset=offset,
                **common,
            )
        )
    if req.dataset == "biz":
        username = _clean_text(req.username)
        if not username:
            raise HTTPException(status_code=400, detail="username is required for biz export.")

        def load_biz_page(offset: int, limit: int) -> dict[str, Any]:
            if username == "gh_3dfda90e39d6":
                response = get_wechat_pay_records(
                    account=req.account,
                    limit=limit,
                    offset=offset,
                    source="auto",
                )
            else:
                response = get_biz_messages(
                    username=username,
                    account=req.account,
                    limit=limit,
                    offset=offset,
                    source="auto",
                )
            normalized = dict(response or {})
            normalized["items"] = normalized.get("data") if isinstance(normalized.get("data"), list) else []
            normalized["dataSource"] = _clean_text(normalized.get("source")) or "realtime"
            return normalized

        return _collect_pages(load_biz_page)
    raise HTTPException(status_code=400, detail="Unsupported dataset.")


def _contact_value(item: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = item.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _record_identity(dataset: str, item: dict[str, Any]) -> tuple[str, str, str]:
    contact: dict[str, Any] = {}
    if dataset == "friend-verifications":
        contact = _contact_value(item, "contact")
        fallback = item.get("remark") or item.get("userName")
        time_text = item.get("timeText")
    elif dataset == "finder":
        contact = _contact_value(item, "contact")
        fallback = item.get("finderUsername") or "视频号"
        time_text = ""
    elif dataset == "payments":
        contact = _contact_value(item, "senderContact", "payerContact", "sessionContact")
        fallback = item.get("senderUserName") or item.get("payPayer") or item.get("sessionName")
        detail = item.get("message") if isinstance(item.get("message"), dict) else {}
        time_text = (
            item.get("beginTransferTimeText")
            or item.get("lastUpdateTimeText")
            or item.get("messageCreateTimeText")
            or detail.get("createTimeText")
        )
    else:
        fallback = (item.get("titles") or [""])[0] if isinstance(item.get("titles"), list) else ""
        fallback = fallback or item.get("userName") or "小程序"
        time_text = item.get("lastUpdateText")
    name = _clean_text(contact.get("displayName") or contact.get("name") or fallback) or "未知来源"
    avatar = _clean_text(contact.get("avatar") or contact.get("avatarUrl"))
    if dataset == "mini-programs":
        avatar = _clean_text(item.get("brandIconUrl"))
    return name, avatar, _clean_text(time_text)


def _safe_web_url(value: Any) -> str:
    url = _clean_text(value)
    return url if url.lower().startswith(("http://", "https://")) else ""


def _generic_record_html(dataset: str, item: dict[str, Any]) -> str:
    if dataset == "friend-verifications":
        direction = "我发起" if item.get("isSender") else "对方发起"
        return f'<div class="bubble"><b>{direction}</b><br>{html.escape(_clean_text(item.get("content") or item.get("remark") or "无验证内容"))}</div>'
    if dataset == "mini-programs":
        titles = " · ".join(_clean_text(value) for value in item.get("titles") or [] if _clean_text(value))
        body = _clean_text(item.get("summary", {}).get("registerBody") if isinstance(item.get("summary"), dict) else "")
        return f'<div class="bubble"><b>{html.escape(titles or _clean_text(item.get("userName")))}</b><br>{html.escape(body)}</div>'
    if dataset == "finder":
        preview = _safe_web_url(item.get("coverUrl") or (item.get("liveInfo") or {}).get("coverUrl"))
        href = _safe_web_url(item.get("jumpUrl") or item.get("liveUrl") or item.get("profileUrl"))
        image = f'<img src="{html.escape(preview, quote=True)}" alt="">' if preview else ""
        attrs = f' href="{html.escape(href, quote=True)}" target="_blank"' if href else ""
        return f'<a class="link finder"{attrs}>{image}<div><b>{html.escape(_clean_text(item.get("description") or "视频号直播"))}</b><p>{html.escape(_clean_text(item.get("finderUsername")))}</p></div></a>'
    if dataset == "payments":
        label = "转账" if item.get("kind") == "transfer" else "红包"
        detail = item.get("message") if isinstance(item.get("message"), dict) else {}
        summary = _clean_text(item.get("messageSummary") or detail.get("content") or item.get("transferId") or item.get("sendId"))
        status = _clean_text(item.get("transferStatus")) if item.get("kind") == "transfer" else ""
        status_html = f'<small>{html.escape(status)}</small>' if status else ""
        return f'<div class="payment"><span>¥</span><div><b>{label}</b><p>{html.escape(summary)}</p>{status_html}</div></div>'
    return f'<pre>{html.escape(json.dumps(item, ensure_ascii=False, indent=2, default=str))}</pre>'


def _image_or_fallback(url: Any, fallback: str, *, class_name: str) -> str:
    safe_url = _safe_web_url(url)
    if safe_url:
        return (
            f'<img class="{class_name}" src="{html.escape(safe_url, quote=True)}" '
            f'alt="" loading="lazy" referrerpolicy="no-referrer">'
        )
    return f'<span class="{class_name} fallback">{html.escape((fallback[:1] or "?").upper())}</span>'


def _mini_program_export_html(item: dict[str, Any]) -> str:
    summary = item.get("summary") if isinstance(item.get("summary"), dict) else {}
    titles = [_clean_text(value) for value in item.get("titles") or [] if _clean_text(value)]
    for key in ("bindEntries", "wxaEntries"):
        for entry in summary.get(key) or []:
            if isinstance(entry, dict) and _clean_text(entry.get("title")):
                titles.append(_clean_text(entry.get("title")))
    titles = list(dict.fromkeys(titles))
    register_body = _clean_text(summary.get("registerBody"))
    primary = (titles[0] if titles else register_body) or "未命名小程序"
    secondary = [value for value in titles if value != primary]
    categories: list[str] = []
    for row in summary.get("categories") or []:
        if isinstance(row, dict):
            value = " / ".join(filter(None, (_clean_text(row.get("first")), _clean_text(row.get("second")))))
        else:
            value = _clean_text(row)
        if value:
            categories.append(value)
    meta_parts = []
    if categories:
        meta_parts.append(f'<div class="entry-meta accent"># {html.escape(" · ".join(categories))}</div>')
    if secondary:
        meta_parts.append(f'<div class="entry-meta">{html.escape(" · ".join(secondary))}</div>')
    summary_html = ""
    if register_body and register_body != primary:
        summary_html = f'<p>{html.escape(register_body)}</p>'
    icon = _image_or_fallback(item.get("brandIconUrl"), primary, class_name="entry-image")
    return (
        '<article class="mini-entry">'
        f'<div class="entry-visual">{icon}</div>'
        '<div class="entry-content">'
        f'<div class="entry-head"><strong>{html.escape(primary)}</strong>'
        f'<time>{html.escape(_clean_text(item.get("lastUpdateText")) or "时间未记录")}</time></div>'
        f'{summary_html}{"".join(meta_parts)}'
        '</div></article>'
    )


def _finder_export_html(item: dict[str, Any]) -> str:
    name, avatar, _time_text_value = _record_identity("finder", item)
    live_info = item.get("liveInfo") if isinstance(item.get("liveInfo"), dict) else {}
    visual_url = avatar or item.get("coverUrl") or live_info.get("coverUrl")
    description = _clean_text(item.get("description") or live_info.get("desc")) or "直播简介未记录"
    identifier = _clean_text(item.get("finderLiveId") or live_info.get("objectId"))
    live_status = int(item.get("liveStatus") or 0)
    replay_status = int(item.get("replayStatus") or 0)
    if live_status == 1:
        status, tone = "直播中", "live"
    elif live_status == 2 and replay_status == 1:
        status, tone = "回放", "replay"
    elif live_status == 2:
        status, tone = "已结束", "ended"
    else:
        status, tone = "状态未记录", "ended"
    paid = '<span class="tag paid">付费</span>' if int(item.get("chargeFlag") or 0) > 0 else ""
    href = _safe_web_url(item.get("liveUrl") or item.get("jumpUrl") or item.get("profileUrl"))
    tag = "a" if href else "article"
    attrs = f' href="{html.escape(href, quote=True)}" target="_blank" rel="noreferrer"' if href else ""
    visual = _image_or_fallback(visual_url, name, class_name="entry-image")
    action = '<span class="open-action">↗</span>' if href else '<span class="open-action muted">×</span>'
    return (
        f'<{tag} class="finder-entry"{attrs}>'
        f'<div class="finder-visual">{visual}</div>'
        '<div class="entry-content">'
        f'<div class="entry-title-row"><strong>{html.escape(name)}</strong>{paid}</div>'
        f'<p>{html.escape(description)}</p>'
        f'<div class="entry-meta accent"># {html.escape("直播编号 " + identifier if identifier else "直播编号未记录")}</div>'
        '</div>'
        f'<span class="tag {tone}">{status}</span>{action}</{tag}>'
    )


def _contact_name(item: dict[str, Any], contact_key: str, raw_key: str, fallback: str) -> str:
    contact = item.get(contact_key) if isinstance(item.get(contact_key), dict) else {}
    return _clean_text(contact.get("displayName") or contact.get("name") or item.get(raw_key)) or fallback


def _payment_export_html(item: dict[str, Any]) -> str:
    name, avatar, time_text = _record_identity("payments", item)
    kind = _clean_text(item.get("kind")).lower()
    detail = item.get("message") if isinstance(item.get("message"), dict) else {}
    amount = _clean_text(item.get("amountText") or item.get("amount") or detail.get("amountText") or detail.get("amount"))
    if amount and not amount.startswith(("¥", "￥")):
        amount = "¥" + amount
    if not amount:
        amount = "金额未保存" if kind == "redpacket" else "金额未解析"
    status = _clean_text(item.get("transferStatus")) if kind == "transfer" else "红包"
    state = _clean_text(item.get("transferState")) or "unknown"
    if kind == "transfer":
        payer = _contact_name(item, "payerContact", "payPayer", "未知付款方")
        receiver = _contact_name(item, "receiverContact", "payReceiver", "未知收款方")
        route = (
            f'<span><i>付款人</i>{html.escape(payer)}</span>'
            f'<b>→</b><span><i>收款人</i>{html.escape(receiver)}</span>'
        )
    else:
        sender = _contact_name(item, "senderContact", "senderUserName", "未知发送人")
        route = f'<span><i>发送</i>{html.escape(sender)}</span>'
    memo = _clean_text(item.get("transferMemo") or detail.get("transferMemo"))
    memo_html = f'<span>备注 {html.escape(memo)}</span>' if memo and memo not in {"微信转账", amount} else ""
    avatar_html = _image_or_fallback(avatar, name, class_name="entry-image")
    amount_class = " muted" if not _clean_text(item.get("amountText") or item.get("amount")) else (" red" if kind == "redpacket" else "")
    return (
        '<article class="ledger-row">'
        f'<div class="ledger-avatar">{avatar_html}</div>'
        '<div class="entry-content">'
        f'<div class="entry-title-row"><strong>{html.escape(name)}</strong><span class="tag {html.escape(state)}">{html.escape(status or "状态未记录")}</span></div>'
        f'<div class="ledger-route">{route}</div>'
        f'<div class="ledger-meta"><time>{html.escape(time_text or "时间未记录")}</time>{memo_html}</div>'
        '</div>'
        f'<div class="ledger-amount{amount_class}">{html.escape(amount.replace("￥", "¥"))}</div>'
        '</article>'
    )


def _biz_export_html(item: dict[str, Any]) -> str:
    is_payment = bool(_clean_text(item.get("merchant_name")))
    title = _clean_text(item.get("title")) or ("微信支付" if is_payment else "未命名文章")
    description = _clean_text(item.get("description") or item.get("des"))
    timestamp = int(item.get("timestamp") or item.get("create_time") or 0)
    time_text = _clean_text(item.get("formatted_time"))
    if not time_text and timestamp > 0:
        try:
            time_text = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            time_text = ""
    if is_payment:
        merchant = _clean_text(item.get("merchant_name")) or "微信支付"
        avatar = _image_or_fallback(item.get("merchant_icon"), merchant, class_name="entry-image")
        return (
            '<article class="biz-entry payment-entry">'
            f'<div class="biz-source"><div class="biz-avatar">{avatar}</div><strong>{html.escape(merchant)}</strong></div>'
            f'<h2>{html.escape(title)}</h2><p>{html.escape(description)}</p><time>{html.escape(time_text)}</time>'
            '</article>'
        )

    href = _safe_web_url(item.get("url"))
    cover = _safe_web_url(item.get("cover"))
    main_tag = "a" if href else "div"
    attrs = f' href="{html.escape(href, quote=True)}" target="_blank" rel="noreferrer"' if href else ""
    cover_html = f'<img src="{html.escape(cover, quote=True)}" alt="" loading="lazy" referrerpolicy="no-referrer">' if cover else '<div class="biz-cover-fallback">文章</div>'
    sub_rows = []
    for child in (item.get("content_list") or [])[1:]:
        if not isinstance(child, dict):
            continue
        child_title = _clean_text(child.get("title"))
        if not child_title:
            continue
        child_href = _safe_web_url(child.get("url"))
        child_tag = "a" if child_href else "div"
        child_attrs = f' href="{html.escape(child_href, quote=True)}" target="_blank" rel="noreferrer"' if child_href else ""
        sub_rows.append(f'<{child_tag} class="biz-sub-row"{child_attrs}>{html.escape(child_title)}<span>↗</span></{child_tag}>')
    return (
        '<article class="biz-entry">'
        f'<{main_tag} class="biz-main"{attrs}>{cover_html}<div class="biz-cover-shade"></div><h2>{html.escape(title)}</h2></{main_tag}>'
        f'<p>{html.escape(description)}</p><time>{html.escape(time_text)}</time>{"".join(sub_rows)}'
        '</article>'
    )


def _render_project_records_html(payload: dict[str, Any]) -> str:
    dataset = _clean_text(payload.get("dataset"))
    renderers = {
        "mini-programs": _mini_program_export_html,
        "finder": _finder_export_html,
        "payments": _payment_export_html,
        "biz": _biz_export_html,
    }
    renderer = renderers[dataset]
    rows = "".join(renderer(item) for item in payload.get("items") or [] if isinstance(item, dict))
    label = _DATASET_LABELS.get(dataset, dataset)
    subject_name = _clean_text(payload.get("subjectName"))
    heading = subject_name if dataset == "biz" and subject_name else label
    count = len(payload.get("items") or [])
    account = _clean_text(payload.get("account"))
    source = "实时库" if _clean_text(payload.get("dataSource")) == "realtime" else "已解密数据"
    grid_class = {
        "mini-programs": "mini",
        "finder": "finder",
        "payments": "payments",
        "biz": "biz",
    }[dataset]
    section_label = {
        "mini-programs": "全部小程序",
        "finder": "全部直播",
        "payments": "全部记录",
        "biz": "全部记录",
    }[dataset]
    empty = '<div class="empty">没有可导出的记录</div>' if not rows else ""
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(heading)}导出</title><style>{export_css("records-project")}</style></head>
<body><div class="records-page"><main class="records-frame">
<header class="masthead"><div><h1>{html.escape(heading)}</h1><span class="count">共<strong>{count}</strong>条记录</span></div>
<div class="export-meta">账号 {html.escape(account)} · {source} · 导出于 {html.escape(_clean_text(payload.get("generatedAt")))}</div></header>
<div class="section-bar"><strong>{section_label}</strong><span>已显示 {count} 条</span></div>
{empty}<section class="records-grid {grid_class}">{rows}</section>
</main></div></body></html>'''


def _render_html(payload: dict[str, Any]) -> str:
    dataset = _clean_text(payload.get("dataset"))
    if dataset in {"mini-programs", "finder", "payments", "biz"}:
        return _render_project_records_html(payload)
    cards: list[str] = []
    for item in payload.get("items") or []:
        name, avatar, time_text = _record_identity(dataset, item)
        fallback = html.escape((name[:1] or "?").upper())
        avatar_html = f'<img src="{html.escape(avatar, quote=True)}" alt="">' if _safe_web_url(avatar) else fallback
        content = _generic_record_html(dataset, item)
        cards.append(
            '<article class="message">'
            f'<div class="avatar">{avatar_html}</div>'
            '<div class="message-body">'
            f'<header><strong>{html.escape(name)}</strong><time>{html.escape(time_text)}</time></header>'
            f'<div class="content">{content}</div>'
            '</div></article>'
        )
    label = _DATASET_LABELS.get(dataset, dataset)
    selected = "、".join(payload.get("types") or []) or "全部"
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(label)}导出</title><style>{export_css("records-generic")}</style></head><body><div class="page"><div class="mast"><h1>{html.escape(label)}</h1><div class="meta">账号 {html.escape(_clean_text(payload.get("account")))} · 实时库 · 共 {len(payload.get("items") or [])} 条 · 类型 {html.escape(selected)}</div></div><main>{''.join(cards)}</main></div></body></html>'''


def _render_txt(payload: dict[str, Any]) -> str:
    lines = [
        f"{_DATASET_LABELS.get(payload['dataset'], payload['dataset'])}导出",
        f"账号: {payload.get('account', '')}",
        f"数据源: {payload.get('dataSource', 'realtime')}",
        f"数量: {len(payload.get('items') or [])}",
        "",
    ]
    dataset = payload["dataset"]
    for index, item in enumerate(payload.get("items") or [], 1):
        name, _avatar, time_text = _record_identity(dataset, item)
        lines.append(f"[{index}] {name}{('  ' + time_text) if time_text else ''}")
        if dataset == "friend-verifications":
            lines.append("方向: " + ("我发起" if item.get("isSender") else "对方发起"))
            lines.append(_clean_text(item.get("content") or item.get("remark") or "无验证内容"))
        else:
            lines.append(json.dumps(item, ensure_ascii=False, default=str, sort_keys=True))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _write_atomic(path: Path, content: str) -> None:
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(content, encoding="utf-8", newline="\n")
    temp_path.replace(path)


def _write_atomic_bytes(path: Path, content: bytes) -> None:
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_bytes(content)
    temp_path.replace(path)


def _render_excel(payload: dict[str, Any]) -> bytes:
    dataset = _clean_text(payload.get("dataset"))
    rows: list[list[str]] = []
    for index, item in enumerate(payload.get("items") or [], start=1):
        record = item if isinstance(item, dict) else {"value": item}
        name, _avatar, time_text = _record_identity(dataset, record)
        rows.append(
            [
                str(index),
                name,
                time_text,
                ", ".join(sorted(_record_types(dataset, record))),
                json.dumps(record, ensure_ascii=False, default=str, sort_keys=True),
            ]
        )
    return build_xlsx_workbook(
        [
            (
                _DATASET_LABELS.get(dataset, dataset) or "记录",
                ["序号", "名称", "时间", "类型", "完整数据"],
                rows,
            )
        ]
    )


@router.post("/api/records/export", summary="导出收藏和通用记录")
def export_records(request: Request, req: RecordExportRequest):
    load_wce_integrity_native()
    output_raw = _clean_text(req.output_dir)
    if not output_raw:
        raise HTTPException(status_code=400, detail="output_dir is required.")
    output_dir = Path(output_raw).expanduser()
    if not output_dir.is_absolute():
        raise HTTPException(status_code=400, detail="output_dir must be an absolute path.")
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to prepare output_dir: {exc}") from exc

    items, source_response = _load_records(request, req)
    selected_types = _normalized_types(req.types)
    items = _filter_records(req.dataset, items, selected_types)
    account = _clean_text(source_response.get("account") or req.account)

    if req.dataset == "favorites":
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_stem = f"favorites_{_safe_file_stem(account, 'account')}_{timestamp}"
        stem = _safe_file_stem(req.file_name, default_stem)
        prepared_messages = _favorite_chat_messages(items)
        last_timestamp = max((_safe_int(message.get("createTime"), 0) for message in prepared_messages), default=0)
        conversations = [
            {
                "username": "__favorites__",
                "displayName": "收藏",
                "isGroup": False,
                "previewText": f"{len(items)} 条收藏",
                "lastTimestamp": last_timestamp,
                "messages": prepared_messages,
            }
        ]
        try:
            job = export_prepared_chat_archive(
                account=account or req.account,
                output_dir=output_dir,
                file_name=f"{stem}.zip",
                title="收藏",
                export_format=req.format,
                conversations=conversations,
                include_media=True,
                media_kinds=["image", "emoji", "video", "video_thumb", "voice", "file"],
                message_types=sorted(selected_types),
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to export favorites: {exc}") from exc
        if job.status != "done" or not job.zip_path:
            raise HTTPException(status_code=500, detail=job.error or "Failed to export favorites archive.")
        return {
            "status": "success",
            "account": account,
            "dataset": req.dataset,
            "format": req.format,
            "dataSource": _clean_text(source_response.get("dataSource")) or "realtime",
            "outputPath": str(job.zip_path),
            "count": len(items),
            "messagesExported": int(job.progress.messages_exported or 0),
            "mediaCopied": int(job.progress.media_copied or 0),
            "mediaMissing": int(job.progress.media_missing or 0),
            "types": sorted(selected_types),
        }

    payload = {
        "dataset": req.dataset,
        "datasetLabel": _DATASET_LABELS[req.dataset],
        "account": account,
        "username": _clean_text(req.username),
        "subjectName": _clean_text(req.subject_name),
        "dataSource": _clean_text(source_response.get("dataSource")) or "realtime",
        "database": _clean_text(source_response.get("database")),
        "query": _clean_text(req.query),
        "types": sorted(selected_types),
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "count": len(items),
        "items": items,
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    scope_stem = _safe_file_stem(req.subject_name, _safe_file_stem(account, "account"))
    default_stem = f"{req.dataset}_{scope_stem}_{timestamp}"
    stem = _safe_file_stem(req.file_name, default_stem)
    extension = "xlsx" if req.format == "excel" else req.format
    output_path = output_dir / f"{stem}.{extension}"
    export_id = uuid.uuid4().hex
    try:
        if req.format == "json":
            content = json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n"
            _write_atomic(output_path, content)
        elif req.format == "txt":
            content = _render_txt(payload)
            _write_atomic(output_path, content)
        elif req.format == "excel":
            _write_atomic_bytes(output_path, _render_excel(payload))
        else:
            content = _render_html(payload)
            integrity_manifest_path, integrity_signature_path = write_protected_html_file(output_path, content, export_id)
        if req.format != "html":
            integrity_manifest_path, integrity_signature_path = write_file_integrity_sidecars(output_path, export_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to export records: {exc}") from exc

    return {
        "status": "success",
        "account": account,
        "dataset": req.dataset,
        "username": _clean_text(req.username),
        "format": req.format,
        "dataSource": payload["dataSource"],
        "outputPath": str(output_path),
        "integrityManifestPath": str(integrity_manifest_path),
        "integritySignaturePath": str(integrity_signature_path),
        "count": len(items),
        "types": sorted(selected_types),
    }
