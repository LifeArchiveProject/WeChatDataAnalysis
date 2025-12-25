import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from ..logging_config import get_logger
from ..chat_search_index import (
    get_chat_search_index_db_path,
    get_chat_search_index_status,
    start_chat_search_index_build,
)
from ..chat_helpers import (
    _build_avatar_url,
    _build_fts_query,
    _decode_message_content,
    _decode_sqlite_text,
    _extract_sender_from_group_xml,
    _extract_xml_attr,
    _extract_xml_tag_or_attr,
    _extract_xml_tag_text,
    _format_session_time,
    _infer_last_message_brief,
    _infer_message_brief_by_local_type,
    _infer_transfer_status_text,
    _iter_message_db_paths,
    _list_decrypted_accounts,
    _make_search_tokens,
    _make_snippet,
    _match_tokens,
    _load_contact_rows,
    _load_latest_message_previews,
    _lookup_resource_md5,
    _parse_app_message,
    _parse_pat_message,
    _pick_avatar_url,
    _pick_display_name,
    _query_head_image_usernames,
    _quote_ident,
    _resolve_account_dir,
    _resolve_msg_table_name,
    _row_to_search_hit,
    _resource_lookup_chat_id,
    _should_keep_session,
    _split_group_sender_prefix,
    _to_char_token_text,
)
from ..media_helpers import _try_find_decrypted_resource
from ..path_fix import PathFixRoute
from ..session_preview_index import (
    build_session_preview_index,
    get_session_preview_index_status,
    load_session_previews,
)

logger = get_logger(__name__)

_DEBUG_SESSIONS = os.environ.get("WECHAT_TOOL_DEBUG_SESSIONS", "0") == "1"

router = APIRouter(route_class=PathFixRoute)

def _normalize_session_type(value: Optional[str]) -> Optional[str]:
    v = str(value or "").strip().lower()
    if not v or v in {"all", "any", "none", "null", "0"}:
        return None
    if v in {"group", "groups", "chatroom", "chatrooms"}:
        return "group"
    if v in {"single", "singles", "person", "people", "user", "users", "contact", "contacts"}:
        return "single"
    raise HTTPException(status_code=400, detail="Invalid session_type, use 'group' or 'single'.")


@router.get("/api/chat/search-index/status", summary="消息搜索索引状态")
async def chat_search_index_status(account: Optional[str] = None):
    account_dir = _resolve_account_dir(account)
    return get_chat_search_index_status(account_dir)


@router.post("/api/chat/search-index/build", summary="构建/重建消息搜索索引")
async def chat_search_index_build(account: Optional[str] = None, rebuild: bool = False):
    account_dir = _resolve_account_dir(account)
    return start_chat_search_index_build(account_dir, rebuild=bool(rebuild))


@router.get("/api/chat/session-preview/status", summary="会话最新消息预览索引状态")
async def session_preview_status(account: Optional[str] = None):
    account_dir = _resolve_account_dir(account)
    return get_session_preview_index_status(account_dir)


@router.post("/api/chat/session-preview/build", summary="构建/重建会话最新消息预览索引")
async def session_preview_build(
    account: Optional[str] = None,
    rebuild: bool = False,
    include_hidden: bool = True,
    include_official: bool = True,
):
    account_dir = _resolve_account_dir(account)
    return build_session_preview_index(
        account_dir,
        rebuild=bool(rebuild),
        include_hidden=bool(include_hidden),
        include_official=bool(include_official),
    )


@router.get("/api/chat/search-index/senders", summary="消息搜索索引发送者列表")
async def chat_search_index_senders(
    account: Optional[str] = None,
    username: Optional[str] = None,
    session_type: Optional[str] = None,
    message_q: Optional[str] = None,
    limit: int = 200,
    q: Optional[str] = None,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    render_types: Optional[str] = None,
    include_hidden: bool = False,
    include_official: bool = False,
):
    if limit <= 0:
        limit = 200
    if limit > 2000:
        limit = 2000

    username = str(username or "").strip()
    if not username:
        username = None

    session_type_norm = _normalize_session_type(session_type)

    message_q = str(message_q or "").strip()
    if not message_q:
        message_q = None

    q = str(q or "").strip()
    if not q:
        q = None

    account_dir = _resolve_account_dir(account)
    contact_db_path = account_dir / "contact.db"

    index_status = get_chat_search_index_status(account_dir)
    index = dict(index_status.get("index") or {})
    build = dict(index.get("build") or {})

    index_exists = bool(index.get("exists"))
    index_ready = bool(index.get("ready"))
    build_status = str(build.get("status") or "").strip()

    if (not index_ready) and build_status not in {"building", "error"}:
        start_chat_search_index_build(account_dir, rebuild=bool(index_exists))
        index_status = get_chat_search_index_status(account_dir)
        index = dict(index_status.get("index") or {})
        build = dict(index.get("build") or {})
        build_status = str(build.get("status") or "").strip()
        index_exists = bool(index.get("exists"))
        index_ready = bool(index.get("ready"))

    if build_status == "error":
        return {
            "status": "index_error",
            "account": account_dir.name,
            "username": username,
            "scope": "conversation" if username else "global",
            "senders": [],
            "index": index,
            "message": str(build.get("error") or "Search index build failed."),
        }

    if not index_ready:
        return {
            "status": "index_building",
            "account": account_dir.name,
            "username": username,
            "scope": "conversation" if username else "global",
            "senders": [],
            "index": index,
            "message": "Search index is building. Please retry in a moment.",
        }

    if username is None and message_q is None:
        return {
            "status": "success",
            "account": account_dir.name,
            "username": None,
            "scope": "global",
            "senders": [],
            "index": index,
            "message": "Provide message_q to list global senders.",
        }

    index_db_path = get_chat_search_index_db_path(account_dir)
    conn = sqlite3.connect(str(index_db_path))
    conn.row_factory = sqlite3.Row
    try:
        where_parts: list[str] = ["sender_username <> ''"]
        params: list[Any] = []

        if message_q is not None:
            fts_query = _build_fts_query(message_q)
            if fts_query:
                where_parts.insert(0, "message_fts MATCH ?")
                params.append(fts_query)

        if username is not None:
            where_parts.append("username = ?")
            params.append(username)
        elif session_type_norm == "group":
            where_parts.append("username LIKE ?")
            params.append("%@chatroom")
        elif session_type_norm == "single":
            where_parts.append("username NOT LIKE ?")
            params.append("%@chatroom")

        if q is not None:
            where_parts.append("sender_username LIKE ?")
            params.append(f"%{q}%")

        want_types: Optional[set[str]] = None
        if render_types is not None:
            parts = [p.strip() for p in str(render_types or "").split(",") if p.strip()]
            want_types = {p for p in parts if p}
            if not want_types:
                want_types = None

        if want_types is not None:
            types_sorted = sorted(want_types)
            placeholders = ",".join(["?"] * len(types_sorted))
            where_parts.append(f"render_type IN ({placeholders})")
            params.extend(types_sorted)

        start_ts = int(start_time) if start_time is not None else None
        end_ts = int(end_time) if end_time is not None else None
        if start_ts is not None and start_ts < 0:
            start_ts = 0
        if end_ts is not None and end_ts < 0:
            end_ts = 0

        if start_ts is not None:
            where_parts.append("CAST(create_time AS INTEGER) >= ?")
            params.append(int(start_ts))
        if end_ts is not None:
            where_parts.append("CAST(create_time AS INTEGER) <= ?")
            params.append(int(end_ts))

        if not include_hidden:
            where_parts.append("CAST(is_hidden AS INTEGER) = 0")
        if not include_official:
            where_parts.append("CAST(is_official AS INTEGER) = 0")

        where_sql = " AND ".join(where_parts)
        rows = conn.execute(
            f"""
            SELECT
                sender_username AS sender_username,
                COUNT(*) AS c
            FROM message_fts
            WHERE {where_sql}
            GROUP BY sender_username
            ORDER BY c DESC, sender_username ASC
            LIMIT ?
            """,
            params + [int(limit)],
        ).fetchall()
    finally:
        conn.close()

    sender_usernames = [str(r["sender_username"] or "").strip() for r in rows if r and r["sender_username"]]
    sender_usernames = [u for u in sender_usernames if u]
    contact_rows = _load_contact_rows(contact_db_path, sender_usernames)
    head_image_db_path = account_dir / "head_image.db"
    local_sender_avatars = _query_head_image_usernames(head_image_db_path, sender_usernames)

    senders: list[dict[str, Any]] = []
    for r in rows:
        su = str(r["sender_username"] or "").strip()
        if not su:
            continue
        cnt = int(r["c"] or 0)
        row = contact_rows.get(su)
        avatar_url = _pick_avatar_url(row)
        if (not avatar_url) and (su in local_sender_avatars):
            avatar_url = _build_avatar_url(account_dir.name, su)
        senders.append(
            {
                "username": su,
                "displayName": _pick_display_name(row, su) if row is not None else su,
                "avatar": avatar_url,
                "count": cnt,
            }
        )

    return {
        "status": "success",
        "account": account_dir.name,
        "username": username,
        "scope": "conversation" if username else "global",
        "senders": senders,
        "index": index,
    }


def _append_full_messages_from_rows(
    *,
    merged: list[dict[str, Any]],
    sender_usernames: list[str],
    quote_usernames: list[str],
    pat_usernames: set[str],
    rows: list[sqlite3.Row],
    db_path: Path,
    table_name: str,
    username: str,
    account_dir: Path,
    is_group: bool,
    my_rowid: Optional[int],
    resource_conn: Optional[sqlite3.Connection],
    resource_chat_id: Optional[int],
) -> None:
    for r in rows:
        local_id = int(r["local_id"] or 0)
        create_time = int(r["create_time"] or 0)
        sort_seq = int(r["sort_seq"] or 0) if r["sort_seq"] is not None else 0
        local_type = int(r["local_type"] or 0)
        sender_username = _decode_sqlite_text(r["sender_username"]).strip()

        is_sent = False
        if my_rowid is not None:
            try:
                is_sent = int(r["real_sender_id"] or 0) == int(my_rowid)
            except Exception:
                is_sent = False

        raw_text = _decode_message_content(r["compress_content"], r["message_content"])
        raw_text = raw_text.strip()

        sender_prefix = ""
        if is_group and not raw_text.startswith("<") and not raw_text.startswith('"<'):
            sender_prefix, raw_text = _split_group_sender_prefix(raw_text)

        if is_group and sender_prefix:
            sender_username = sender_prefix

        if is_group and (raw_text.startswith("<") or raw_text.startswith('"<')):
            xml_sender = _extract_sender_from_group_xml(raw_text)
            if xml_sender:
                sender_username = xml_sender

        if is_sent:
            sender_username = account_dir.name
        elif (not is_group) and (not sender_username):
            sender_username = username

        if sender_username:
            sender_usernames.append(sender_username)

        render_type = "text"
        content_text = raw_text
        title = ""
        url = ""
        image_md5 = ""
        emoji_md5 = ""
        emoji_url = ""
        thumb_url = ""
        image_url = ""
        image_file_id = ""
        video_md5 = ""
        video_thumb_md5 = ""
        video_file_id = ""
        video_thumb_file_id = ""
        video_url = ""
        video_thumb_url = ""
        voice_length = ""
        quote_username = ""
        quote_title = ""
        quote_content = ""
        quote_server_id = ""
        quote_type = ""
        quote_voice_length = ""
        amount = ""
        cover_url = ""
        file_size = ""
        pay_sub_type = ""
        transfer_status = ""
        file_md5 = ""
        transfer_id = ""
        voip_type = ""

        if local_type == 10000:
            render_type = "system"
            if "revokemsg" in raw_text:
                content_text = "撤回了一条消息"
            else:
                content_text = re.sub(r"</?[_a-zA-Z0-9]+[^>]*>", "", raw_text)
                content_text = re.sub(r"\s+", " ", content_text).strip() or "[系统消息]"
        elif local_type == 49:
            parsed = _parse_app_message(raw_text)
            render_type = str(parsed.get("renderType") or "text")
            content_text = str(parsed.get("content") or "")
            title = str(parsed.get("title") or "")
            url = str(parsed.get("url") or "")
            quote_title = str(parsed.get("quoteTitle") or "")
            quote_content = str(parsed.get("quoteContent") or "")
            quote_username = str(parsed.get("quoteUsername") or "")
            quote_server_id = str(parsed.get("quoteServerId") or "")
            quote_type = str(parsed.get("quoteType") or "")
            quote_voice_length = str(parsed.get("quoteVoiceLength") or "")
            amount = str(parsed.get("amount") or "")
            cover_url = str(parsed.get("coverUrl") or "")
            thumb_url = str(parsed.get("thumbUrl") or "")
            file_size = str(parsed.get("size") or "")
            pay_sub_type = str(parsed.get("paySubType") or "")
            file_md5 = str(parsed.get("fileMd5") or "")
            transfer_id = str(parsed.get("transferId") or "")

            if render_type == "transfer":
                # 直接从原始 XML 提取 transferid（可能在 wcpayinfo 内）
                if not transfer_id:
                    transfer_id = _extract_xml_tag_or_attr(raw_text, "transferid") or ""
                transfer_status = _infer_transfer_status_text(
                    is_sent=is_sent,
                    paysubtype=pay_sub_type,
                    receivestatus=str(parsed.get("receiveStatus") or ""),
                    sendertitle=str(parsed.get("senderTitle") or ""),
                    receivertitle=str(parsed.get("receiverTitle") or ""),
                    senderdes=str(parsed.get("senderDes") or ""),
                    receiverdes=str(parsed.get("receiverDes") or ""),
                )
                if not content_text:
                    content_text = transfer_status or "转账"
        elif local_type == 266287972401:
            render_type = "system"
            template = _extract_xml_tag_text(raw_text, "template")
            if template:
                pat_usernames.update(
                    {m.group(1) for m in re.finditer(r"\$\{([^}]+)\}", template) if m.group(1)}
                )
                content_text = "[拍一拍]"
            else:
                content_text = "[拍一拍]"
        elif local_type == 244813135921:
            render_type = "quote"
            parsed = _parse_app_message(raw_text)
            content_text = str(parsed.get("content") or "[引用消息]")
            quote_title = str(parsed.get("quoteTitle") or "")
            quote_content = str(parsed.get("quoteContent") or "")
            quote_username = str(parsed.get("quoteUsername") or "")
            quote_server_id = str(parsed.get("quoteServerId") or "")
            quote_type = str(parsed.get("quoteType") or "")
            quote_voice_length = str(parsed.get("quoteVoiceLength") or "")
        elif local_type == 3:
            render_type = "image"
            # 先尝试从 XML 中提取 md5（不同版本字段可能不同）
            image_md5 = _extract_xml_attr(raw_text, "md5") or _extract_xml_tag_text(raw_text, "md5")
            if not image_md5:
                for k in [
                    "cdnthumbmd5",
                    "cdnthumd5",
                    "cdnmidimgmd5",
                    "cdnbigimgmd5",
                    "hdmd5",
                    "hevc_mid_md5",
                    "hevc_md5",
                    "imgmd5",
                    "filemd5",
                ]:
                    image_md5 = _extract_xml_attr(raw_text, k) or _extract_xml_tag_text(raw_text, k)
                    if image_md5:
                        break

            # Extract CDN URL (some versions store a non-HTTP "file id" string here)
            _cdn_url_or_id = (
                _extract_xml_attr(raw_text, "cdnthumburl")
                or _extract_xml_attr(raw_text, "cdnthumurl")
                or _extract_xml_attr(raw_text, "cdnmidimgurl")
                or _extract_xml_attr(raw_text, "cdnbigimgurl")
                or _extract_xml_tag_text(raw_text, "cdnthumburl")
                or _extract_xml_tag_text(raw_text, "cdnthumurl")
                or _extract_xml_tag_text(raw_text, "cdnmidimgurl")
                or _extract_xml_tag_text(raw_text, "cdnbigimgurl")
            )
            _cdn_url_or_id = str(_cdn_url_or_id or "").strip()
            image_url = _cdn_url_or_id if _cdn_url_or_id.startswith(("http://", "https://")) else ""
            if (not image_url) and _cdn_url_or_id:
                image_file_id = _cdn_url_or_id

            if (not image_md5) and resource_conn is not None:
                image_md5 = _lookup_resource_md5(
                    resource_conn,
                    resource_chat_id,
                    message_local_type=local_type,
                    server_id=int(r["server_id"] or 0),
                    local_id=local_id,
                    create_time=create_time,
                )
            content_text = "[图片]"
        elif local_type == 34:
            render_type = "voice"
            duration = _extract_xml_attr(raw_text, "voicelength")
            voice_length = duration
            content_text = f"[语音 {duration}秒]" if duration else "[语音]"
        elif local_type == 43 or local_type == 62:
            render_type = "video"
            video_md5 = _extract_xml_attr(raw_text, "md5")
            video_thumb_md5 = _extract_xml_attr(raw_text, "cdnthumbmd5")
            video_thumb_url_or_id = _extract_xml_attr(raw_text, "cdnthumburl") or _extract_xml_tag_text(
                raw_text, "cdnthumburl"
            )
            video_url_or_id = _extract_xml_attr(raw_text, "cdnvideourl") or _extract_xml_tag_text(
                raw_text, "cdnvideourl"
            )

            video_thumb_url = (
                video_thumb_url_or_id
                if str(video_thumb_url_or_id or "").strip().lower().startswith(("http://", "https://"))
                else ""
            )
            video_url = (
                video_url_or_id
                if str(video_url_or_id or "").strip().lower().startswith(("http://", "https://"))
                else ""
            )
            video_thumb_file_id = "" if video_thumb_url else (str(video_thumb_url_or_id or "").strip() or "")
            video_file_id = "" if video_url else (str(video_url_or_id or "").strip() or "")
            if (not video_thumb_md5) and resource_conn is not None:
                video_thumb_md5 = _lookup_resource_md5(
                    resource_conn,
                    resource_chat_id,
                    message_local_type=local_type,
                    server_id=int(r["server_id"] or 0),
                    local_id=local_id,
                    create_time=create_time,
                )
            content_text = "[视频]"
        elif local_type == 47:
            render_type = "emoji"
            emoji_md5 = _extract_xml_attr(raw_text, "md5")
            if not emoji_md5:
                emoji_md5 = _extract_xml_tag_text(raw_text, "md5")
            emoji_url = _extract_xml_attr(raw_text, "cdnurl")
            if not emoji_url:
                emoji_url = _extract_xml_tag_text(raw_text, "cdn_url")
            if (not emoji_md5) and resource_conn is not None:
                emoji_md5 = _lookup_resource_md5(
                    resource_conn,
                    resource_chat_id,
                    message_local_type=local_type,
                    server_id=int(r["server_id"] or 0),
                    local_id=local_id,
                    create_time=create_time,
                )
            content_text = "[表情]"
        elif local_type == 50:
            render_type = "voip"
            try:
                block = raw_text
                m_voip = re.search(
                    r"(<VoIPBubbleMsg[^>]*>.*?</VoIPBubbleMsg>)",
                    raw_text,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                if m_voip:
                    block = m_voip.group(1) or raw_text
                room_type = str(_extract_xml_tag_text(block, "room_type") or "").strip()
                if room_type == "0":
                    voip_type = "video"
                elif room_type == "1":
                    voip_type = "audio"

                voip_msg = str(_extract_xml_tag_text(block, "msg") or "").strip()
                content_text = voip_msg or "通话"
            except Exception:
                content_text = "通话"
        elif local_type != 1:
            if not content_text:
                content_text = _infer_message_brief_by_local_type(local_type)
            else:
                if content_text.startswith("<") or content_text.startswith('"<'):
                    if "<appmsg" in content_text.lower():
                        parsed = _parse_app_message(content_text)
                        rt = str(parsed.get("renderType") or "")
                        if rt and rt != "text":
                            render_type = rt
                            content_text = str(parsed.get("content") or content_text)
                            title = str(parsed.get("title") or title)
                            url = str(parsed.get("url") or url)
                            quote_title = str(parsed.get("quoteTitle") or quote_title)
                            quote_content = str(parsed.get("quoteContent") or quote_content)
                            amount = str(parsed.get("amount") or amount)
                            cover_url = str(parsed.get("coverUrl") or cover_url)
                            thumb_url = str(parsed.get("thumbUrl") or thumb_url)
                            file_size = str(parsed.get("size") or file_size)
                            pay_sub_type = str(parsed.get("paySubType") or pay_sub_type)
                            file_md5 = str(parsed.get("fileMd5") or file_md5)
                            transfer_id = str(parsed.get("transferId") or transfer_id)

                            if render_type == "transfer":
                                # 如果 transferId 仍为空，尝试从原始 XML 提取
                                if not transfer_id:
                                    transfer_id = _extract_xml_tag_or_attr(content_text, "transferid") or ""
                                transfer_status = _infer_transfer_status_text(
                                    is_sent=is_sent,
                                    paysubtype=pay_sub_type,
                                    receivestatus=str(parsed.get("receiveStatus") or ""),
                                    sendertitle=str(parsed.get("senderTitle") or ""),
                                    receivertitle=str(parsed.get("receiverTitle") or ""),
                                    senderdes=str(parsed.get("senderDes") or ""),
                                    receiverdes=str(parsed.get("receiverDes") or ""),
                                )
                                if not content_text:
                                    content_text = transfer_status or "转账"
                    t = _extract_xml_tag_text(content_text, "title")
                    d = _extract_xml_tag_text(content_text, "des")
                    content_text = t or d or _infer_message_brief_by_local_type(local_type)

        if not content_text:
            content_text = _infer_message_brief_by_local_type(local_type)

        if quote_username:
            quote_usernames.append(str(quote_username).strip())

        merged.append(
            {
                "id": f"{db_path.stem}:{table_name}:{local_id}",
                "localId": local_id,
                "serverId": int(r["server_id"] or 0),
                "serverIdStr": str(int(r["server_id"] or 0)) if int(r["server_id"] or 0) else "",
                "type": local_type,
                "createTime": create_time,
                "sortSeq": sort_seq,
                "senderUsername": sender_username,
                "isSent": bool(is_sent),
                "renderType": render_type,
                "content": content_text,
                "title": title,
                "url": url,
                "imageMd5": image_md5,
                "imageFileId": image_file_id,
                "emojiMd5": emoji_md5,
                "emojiUrl": emoji_url,
                "thumbUrl": thumb_url,
                "imageUrl": image_url,
                "videoMd5": video_md5,
                "videoThumbMd5": video_thumb_md5,
                "videoFileId": video_file_id,
                "videoThumbFileId": video_thumb_file_id,
                "videoUrl": video_url,
                "videoThumbUrl": video_thumb_url,
                "voiceLength": voice_length,
                "voipType": voip_type,
                "quoteUsername": str(quote_username).strip(),
                "quoteServerId": str(quote_server_id).strip(),
                "quoteType": str(quote_type).strip(),
                "quoteVoiceLength": str(quote_voice_length).strip(),
                "quoteTitle": quote_title,
                "quoteContent": quote_content,
                "amount": amount,
                "coverUrl": cover_url,
                "fileSize": file_size,
                "fileMd5": file_md5,
                "paySubType": pay_sub_type,
                "transferStatus": transfer_status,
                "transferId": transfer_id,
                "_rawText": raw_text if local_type == 266287972401 else "",
            }
        )


def _postprocess_full_messages(
    *,
    merged: list[dict[str, Any]],
    sender_usernames: list[str],
    quote_usernames: list[str],
    pat_usernames: set[str],
    account_dir: Path,
    username: str,
    base_url: str,
    contact_db_path: Path,
    head_image_db_path: Path,
) -> None:
    # 后处理：关联转账消息的最终状态
    # 策略：优先使用 transferId 精确匹配，回退到金额+时间窗口匹配
    # paysubtype 含义：1=不明确 3=已收款 4=对方退回给你 8=发起转账 9=被对方退回 10=已过期

    # 收集已退还和已收款的转账ID和金额
    returned_transfer_ids: set[str] = set()  # 退还状态的 transferId
    received_transfer_ids: set[str] = set()  # 已收款状态的 transferId
    returned_amounts_with_time: list[tuple[str, int]] = []  # (金额, 时间戳) 用于退还回退匹配
    received_amounts_with_time: list[tuple[str, int]] = []  # (金额, 时间戳) 用于收款回退匹配

    for m in merged:
        if m.get("renderType") == "transfer":
            pst = str(m.get("paySubType") or "")
            tid = str(m.get("transferId") or "").strip()
            amt = str(m.get("amount") or "")
            ts = int(m.get("createTime") or 0)

            if pst in ("4", "9"):  # 退还状态
                if tid:
                    returned_transfer_ids.add(tid)
                if amt:
                    returned_amounts_with_time.append((amt, ts))
            elif pst == "3":  # 已收款状态
                if tid:
                    received_transfer_ids.add(tid)
                if amt:
                    received_amounts_with_time.append((amt, ts))

    # 更新原始转账消息的状态
    for m in merged:
        if m.get("renderType") == "transfer":
            pst = str(m.get("paySubType") or "")
            # 只更新未确定状态的原始转账消息（paysubtype=1 或 8）
            if pst in ("1", "8"):
                tid = str(m.get("transferId") or "").strip()
                amt = str(m.get("amount") or "")
                ts = int(m.get("createTime") or 0)

                # 优先检查退还状态（退还优先于收款）
                should_mark_returned = False
                should_mark_received = False

                # 策略1：精确 transferId 匹配
                if tid:
                    if tid in returned_transfer_ids:
                        should_mark_returned = True
                    elif tid in received_transfer_ids:
                        should_mark_received = True

                # 策略2：回退到金额+时间窗口匹配（24小时内同金额）
                if not should_mark_returned and not should_mark_received and amt:
                    for ret_amt, ret_ts in returned_amounts_with_time:
                        if ret_amt == amt and abs(ret_ts - ts) <= 86400:
                            should_mark_returned = True
                            break
                    if not should_mark_returned:
                        for rec_amt, rec_ts in received_amounts_with_time:
                            if rec_amt == amt and abs(rec_ts - ts) <= 86400:
                                should_mark_received = True
                                break

                if should_mark_returned:
                    m["paySubType"] = "9"
                    m["transferStatus"] = "已被退还"
                elif should_mark_received:
                    m["paySubType"] = "3"
                    # 根据 isSent 判断：发起方显示"已收款"，收款方显示"已被接收"
                    is_sent = m.get("isSent", False)
                    m["transferStatus"] = "已收款" if is_sent else "已被接收"

    uniq_senders = list(
        dict.fromkeys([u for u in (sender_usernames + list(pat_usernames) + quote_usernames) if u])
    )
    sender_contact_rows = _load_contact_rows(contact_db_path, uniq_senders)
    local_sender_avatars = _query_head_image_usernames(head_image_db_path, uniq_senders)

    for m in merged:
        su = str(m.get("senderUsername") or "")
        if not su:
            continue
        row = sender_contact_rows.get(su)
        m["senderDisplayName"] = _pick_display_name(row, su)
        avatar_url = _pick_avatar_url(row)
        if not avatar_url and su in local_sender_avatars:
            avatar_url = base_url + _build_avatar_url(account_dir.name, su)
        m["senderAvatar"] = avatar_url

        qu = str(m.get("quoteUsername") or "").strip()
        if qu:
            qrow = sender_contact_rows.get(qu)
            qt = str(m.get("quoteTitle") or "").strip()
            if qrow is not None:
                remark = ""
                try:
                    remark = str(qrow["remark"] or "").strip()
                except Exception:
                    remark = ""
                if remark:
                    m["quoteTitle"] = remark
                elif not qt:
                    m["quoteTitle"] = _pick_display_name(qrow, qu)
            elif not qt:
                m["quoteTitle"] = qu

        # Media URL fallback: if CDN URLs missing, use local media endpoints.
        try:
            rt = str(m.get("renderType") or "")
            if rt == "image":
                if not str(m.get("imageUrl") or ""):
                    md5 = str(m.get("imageMd5") or "").strip()
                    file_id = str(m.get("imageFileId") or "").strip()
                    if md5:
                        m["imageUrl"] = (
                            base_url
                            + f"/api/chat/media/image?account={quote(account_dir.name)}&md5={quote(md5)}&username={quote(username)}"
                        )
                    elif file_id:
                        m["imageUrl"] = (
                            base_url
                            + f"/api/chat/media/image?account={quote(account_dir.name)}&file_id={quote(file_id)}&username={quote(username)}"
                        )
            elif rt == "emoji":
                md5 = str(m.get("emojiMd5") or "")
                if md5:
                    existing_local: Optional[Path] = None
                    try:
                        existing_local = _try_find_decrypted_resource(account_dir, str(md5).lower())
                    except Exception:
                        existing_local = None

                    if existing_local:
                        try:
                            cur = str(m.get("emojiUrl") or "")
                            if cur and re.match(r"^https?://", cur, flags=re.I) and (
                                "/api/chat/media/emoji" not in cur
                            ):
                                m["emojiRemoteUrl"] = cur
                        except Exception:
                            pass

                        m["emojiUrl"] = (
                            base_url
                            + f"/api/chat/media/emoji?account={quote(account_dir.name)}&md5={quote(md5)}&username={quote(username)}"
                        )
                    elif (not str(m.get("emojiUrl") or "")):
                        m["emojiUrl"] = (
                            base_url
                            + f"/api/chat/media/emoji?account={quote(account_dir.name)}&md5={quote(md5)}&username={quote(username)}"
                        )
            elif rt == "video":
                video_thumb_url = str(m.get("videoThumbUrl") or "").strip()
                video_thumb_md5 = str(m.get("videoThumbMd5") or "").strip()
                video_thumb_file_id = str(m.get("videoThumbFileId") or "").strip()
                if (not video_thumb_url) or (
                    not video_thumb_url.lower().startswith(("http://", "https://"))
                ):
                    if video_thumb_md5:
                        m["videoThumbUrl"] = (
                            base_url
                            + f"/api/chat/media/video_thumb?account={quote(account_dir.name)}&md5={quote(video_thumb_md5)}&username={quote(username)}"
                        )
                    elif video_thumb_file_id:
                        m["videoThumbUrl"] = (
                            base_url
                            + f"/api/chat/media/video_thumb?account={quote(account_dir.name)}&file_id={quote(video_thumb_file_id)}&username={quote(username)}"
                        )

                video_url = str(m.get("videoUrl") or "").strip()
                video_md5 = str(m.get("videoMd5") or "").strip()
                video_file_id = str(m.get("videoFileId") or "").strip()
                if (not video_url) or (not video_url.lower().startswith(("http://", "https://"))):
                    if video_md5:
                        m["videoUrl"] = (
                            base_url
                            + f"/api/chat/media/video?account={quote(account_dir.name)}&md5={quote(video_md5)}&username={quote(username)}"
                        )
                    elif video_file_id:
                        m["videoUrl"] = (
                            base_url
                            + f"/api/chat/media/video?account={quote(account_dir.name)}&file_id={quote(video_file_id)}&username={quote(username)}"
                        )
            elif rt == "voice":
                if str(m.get("serverId") or ""):
                    sid = int(m.get("serverId") or 0)
                    if sid:
                        m["voiceUrl"] = base_url + f"/api/chat/media/voice?account={quote(account_dir.name)}&server_id={sid}"
        except Exception:
            pass

        if int(m.get("type") or 0) == 266287972401:
            raw = str(m.get("_rawText") or "")
            if raw:
                m["content"] = _parse_pat_message(raw, sender_contact_rows)

        if "_rawText" in m:
            m.pop("_rawText", None)


@router.get("/api/chat/accounts", summary="列出已解密账号")
async def list_chat_accounts():
    """列出 output/databases 下可用于聊天预览的账号目录"""
    accounts = _list_decrypted_accounts()
    if not accounts:
        return {
            "status": "error",
            "accounts": [],
            "default_account": None,
            "message": "No decrypted databases found. Please decrypt first.",
        }

    return {
        "status": "success",
        "accounts": accounts,
        "default_account": accounts[0],
    }


@router.get("/api/chat/sessions", summary="获取会话列表（聊天左侧列表）")
async def list_chat_sessions(
    request: Request,
    account: Optional[str] = None,
    limit: int = 400,
    include_hidden: bool = False,
    include_official: bool = False,
    preview: str = "latest",
):
    """从 session.db + contact.db 读取会话列表，用于前端聊天界面动态渲染联系人"""
    if limit <= 0:
        raise HTTPException(status_code=400, detail="Invalid limit.")
    if limit > 2000:
        limit = 2000

    account_dir = _resolve_account_dir(account)
    session_db_path = account_dir / "session.db"
    contact_db_path = account_dir / "contact.db"
    head_image_db_path = account_dir / "head_image.db"
    base_url = str(request.base_url).rstrip("/")

    sconn = sqlite3.connect(str(session_db_path))
    sconn.row_factory = sqlite3.Row
    try:
        try:
            rows = sconn.execute(
                """
                SELECT
                    username,
                    unread_count,
                    is_hidden,
                    summary,
                    draft,
                    last_timestamp,
                    sort_timestamp,
                    last_msg_locald_id,
                    last_msg_type,
                    last_msg_sub_type,
                    last_msg_sender,
                    last_sender_display_name
                FROM SessionTable
                ORDER BY sort_timestamp DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = sconn.execute(
                """
                SELECT
                    username,
                    unread_count,
                    is_hidden,
                    summary,
                    draft,
                    last_timestamp,
                    sort_timestamp,
                    last_msg_type,
                    last_msg_sub_type
                FROM SessionTable
                ORDER BY sort_timestamp DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
    finally:
        sconn.close()

    filtered: list[sqlite3.Row] = []
    usernames: list[str] = []
    for r in rows:
        username = r["username"] or ""
        if not username:
            continue
        if not include_hidden and int(r["is_hidden"] or 0) == 1:
            continue
        if not _should_keep_session(username, include_official=include_official):
            continue
        filtered.append(r)
        usernames.append(username)

    contact_rows = _load_contact_rows(contact_db_path, usernames)
    local_avatar_usernames = _query_head_image_usernames(head_image_db_path, usernames)

    preview_mode = str(preview or "").strip().lower()
    if preview_mode not in {"latest", "index", "session", "db", "none"}:
        preview_mode = "latest"

    latest_previews: dict[str, str] = {}
    index_status: Optional[dict[str, Any]] = None
    if preview_mode in {"latest", "index", "db"}:
        try:
            index_status = get_session_preview_index_status(account_dir)
            latest_previews = load_session_previews(account_dir, usernames)
        except Exception:
            index_status = None
            latest_previews = {}

    if preview_mode in {"latest", "db"}:
        missing = [u for u in usernames if u and (u not in latest_previews)]
        if missing:
            legacy = _load_latest_message_previews(account_dir, missing)
            for u, v in legacy.items():
                if v:
                    latest_previews[u] = v

    sessions: list[dict[str, Any]] = []
    for r in filtered:
        username = r["username"]
        c_row = contact_rows.get(username)

        display_name = _pick_display_name(c_row, username)
        avatar_url = _pick_avatar_url(c_row)
        if not avatar_url and username in local_avatar_usernames:
            avatar_url = base_url + _build_avatar_url(account_dir.name, username)

        last_message = ""
        draft_text = _decode_sqlite_text(r["draft"]).strip()
        if draft_text:
            draft_text = re.sub(r"\s+", " ", draft_text).strip()
            last_message = f"[草稿] {draft_text}" if draft_text else "[草稿]"
        elif preview_mode in {"latest", "db", "index"} and str(latest_previews.get(username) or "").strip():
            last_message = str(latest_previews.get(username) or "").strip()
        elif preview_mode != "none":
            summary_text = _decode_sqlite_text(r["summary"]).strip()
            summary_text = re.sub(r"\s+", " ", summary_text).strip()
            if summary_text:
                last_message = summary_text
            else:
                last_message = _infer_last_message_brief(r["last_msg_type"], r["last_msg_sub_type"])

        last_time = _format_session_time(r["sort_timestamp"] or r["last_timestamp"])

        sessions.append(
            {
                "id": username,
                "username": username,
                "name": display_name,
                "avatar": avatar_url,
                "lastMessage": last_message,
                "lastMessageTime": last_time,
                "unreadCount": int(r["unread_count"] or 0),
                "isGroup": bool(username.endswith("@chatroom")),
            }
        )

    return {
        "status": "success",
        "account": account_dir.name,
        "total": len(sessions),
        "sessions": sessions,
        "previewIndex": index_status.get("index") if isinstance(index_status, dict) else None,
    }


@router.get("/api/chat/messages", summary="获取会话消息列表")
async def list_chat_messages(
    request: Request,
    username: str,
    account: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    order: str = "asc",
):
    if not username:
        raise HTTPException(status_code=400, detail="Missing username.")
    if limit <= 0:
        raise HTTPException(status_code=400, detail="Invalid limit.")
    if limit > 500:
        limit = 500
    if offset < 0:
        offset = 0

    account_dir = _resolve_account_dir(account)
    db_paths = _iter_message_db_paths(account_dir)
    contact_db_path = account_dir / "contact.db"
    head_image_db_path = account_dir / "head_image.db"
    message_resource_db_path = account_dir / "message_resource.db"
    base_url = str(request.base_url).rstrip("/")
    if not db_paths:
        return {
            "status": "error",
            "account": account_dir.name,
            "username": username,
            "total": 0,
            "messages": [],
            "message": "No message databases found for this account.",
        }

    resource_conn: Optional[sqlite3.Connection] = None
    resource_chat_id: Optional[int] = None
    try:
        if message_resource_db_path.exists():
            resource_conn = sqlite3.connect(str(message_resource_db_path))
            resource_conn.row_factory = sqlite3.Row
            resource_chat_id = _resource_lookup_chat_id(resource_conn, username)
    except Exception:
        if resource_conn is not None:
            try:
                resource_conn.close()
            except Exception:
                pass
        resource_conn = None
        resource_chat_id = None

    want_asc = str(order or "").lower() != "desc"
    take = int(limit) + int(offset)
    take_probe = take + 1
    merged: list[dict[str, Any]] = []
    sender_usernames: list[str] = []
    quote_usernames: list[str] = []
    pat_usernames: set[str] = set()
    is_group = bool(username.endswith("@chatroom"))
    has_more_any = False

    for db_path in db_paths:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            table_name = _resolve_msg_table_name(conn, username)
            if not table_name:
                continue

            my_wxid = account_dir.name
            my_rowid = None
            try:
                r = conn.execute(
                    "SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1",
                    (my_wxid,),
                ).fetchone()
                if r is not None:
                    my_rowid = int(r[0])
            except Exception:
                my_rowid = None

            quoted_table = _quote_ident(table_name)
            sql_with_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, n.user_name AS sender_username "
                f"FROM {quoted_table} m "
                "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
                "ORDER BY m.create_time DESC, m.sort_seq DESC, m.local_id DESC "
                "LIMIT ?"
            )
            sql_no_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, '' AS sender_username "
                f"FROM {quoted_table} m "
                "ORDER BY m.create_time DESC, m.sort_seq DESC, m.local_id DESC "
                "LIMIT ?"
            )

            # Force sqlite3 to return TEXT as raw bytes for this query, so we can zstd-decompress
            # compress_content reliably.
            conn.text_factory = bytes

            try:
                rows = conn.execute(sql_with_join, (take_probe,)).fetchall()
            except Exception:
                rows = conn.execute(sql_no_join, (take_probe,)).fetchall()
            if len(rows) > take:
                has_more_any = True
                rows = rows[:take]

            for r in rows:
                local_id = int(r["local_id"] or 0)
                create_time = int(r["create_time"] or 0)
                sort_seq = int(r["sort_seq"] or 0) if r["sort_seq"] is not None else 0
                local_type = int(r["local_type"] or 0)
                sender_username = _decode_sqlite_text(r["sender_username"]).strip()

                is_sent = False
                if my_rowid is not None:
                    try:
                        is_sent = int(r["real_sender_id"] or 0) == int(my_rowid)
                    except Exception:
                        is_sent = False

                raw_text = _decode_message_content(r["compress_content"], r["message_content"])
                raw_text = raw_text.strip()

                sender_prefix = ""
                if is_group and not raw_text.startswith("<") and not raw_text.startswith('"<'):
                    sender_prefix, raw_text = _split_group_sender_prefix(raw_text)

                if is_group and sender_prefix:
                    sender_username = sender_prefix

                if is_group and (raw_text.startswith("<") or raw_text.startswith('"<')):
                    xml_sender = _extract_sender_from_group_xml(raw_text)
                    if xml_sender:
                        sender_username = xml_sender

                if is_sent:
                    sender_username = account_dir.name
                elif (not is_group) and (not sender_username):
                    sender_username = username

                if sender_username:
                    sender_usernames.append(sender_username)

                render_type = "text"
                content_text = raw_text
                title = ""
                url = ""
                image_md5 = ""
                emoji_md5 = ""
                emoji_url = ""
                thumb_url = ""
                image_url = ""
                image_file_id = ""
                video_md5 = ""
                video_thumb_md5 = ""
                video_file_id = ""
                video_thumb_file_id = ""
                video_url = ""
                video_thumb_url = ""
                voice_length = ""
                quote_username = ""
                quote_title = ""
                quote_content = ""
                quote_server_id = ""
                quote_type = ""
                quote_voice_length = ""
                amount = ""
                cover_url = ""
                file_size = ""
                pay_sub_type = ""
                transfer_status = ""
                file_md5 = ""
                transfer_id = ""
                voip_type = ""

                if local_type == 10000:
                    render_type = "system"
                    if "revokemsg" in raw_text:
                        content_text = "撤回了一条消息"
                    else:
                        import re

                        content_text = re.sub(r"</?[_a-zA-Z0-9]+[^>]*>", "", raw_text)
                        content_text = re.sub(r"\s+", " ", content_text).strip() or "[系统消息]"
                elif local_type == 49:
                    parsed = _parse_app_message(raw_text)
                    render_type = str(parsed.get("renderType") or "text")
                    content_text = str(parsed.get("content") or "")
                    title = str(parsed.get("title") or "")
                    url = str(parsed.get("url") or "")
                    quote_title = str(parsed.get("quoteTitle") or "")
                    quote_content = str(parsed.get("quoteContent") or "")
                    quote_username = str(parsed.get("quoteUsername") or "")
                    quote_server_id = str(parsed.get("quoteServerId") or "")
                    quote_type = str(parsed.get("quoteType") or "")
                    quote_voice_length = str(parsed.get("quoteVoiceLength") or "")
                    amount = str(parsed.get("amount") or "")
                    cover_url = str(parsed.get("coverUrl") or "")
                    thumb_url = str(parsed.get("thumbUrl") or "")
                    file_size = str(parsed.get("size") or "")
                    pay_sub_type = str(parsed.get("paySubType") or "")
                    file_md5 = str(parsed.get("fileMd5") or "")
                    transfer_id = str(parsed.get("transferId") or "")

                    if render_type == "transfer":
                        # 直接从原始 XML 提取 transferid（可能在 wcpayinfo 内）
                        if not transfer_id:
                            transfer_id = _extract_xml_tag_or_attr(raw_text, "transferid") or ""
                        transfer_status = _infer_transfer_status_text(
                            is_sent=is_sent,
                            paysubtype=pay_sub_type,
                            receivestatus=str(parsed.get("receiveStatus") or ""),
                            sendertitle=str(parsed.get("senderTitle") or ""),
                            receivertitle=str(parsed.get("receiverTitle") or ""),
                            senderdes=str(parsed.get("senderDes") or ""),
                            receiverdes=str(parsed.get("receiverDes") or ""),
                        )
                        if not content_text:
                            content_text = transfer_status or "转账"
                elif local_type == 266287972401:
                    render_type = "system"
                    template = _extract_xml_tag_text(raw_text, "template")
                    if template:
                        import re

                        pat_usernames.update({m.group(1) for m in re.finditer(r"\$\{([^}]+)\}", template) if m.group(1)})
                        content_text = "[拍一拍]"
                    else:
                        content_text = "[拍一拍]"
                elif local_type == 244813135921:
                    render_type = "quote"
                    parsed = _parse_app_message(raw_text)
                    content_text = str(parsed.get("content") or "[引用消息]")
                    quote_title = str(parsed.get("quoteTitle") or "")
                    quote_content = str(parsed.get("quoteContent") or "")
                    quote_username = str(parsed.get("quoteUsername") or "")
                    quote_server_id = str(parsed.get("quoteServerId") or "")
                    quote_type = str(parsed.get("quoteType") or "")
                    quote_voice_length = str(parsed.get("quoteVoiceLength") or "")
                elif local_type == 3:
                    render_type = "image"
                    # 先尝试从 XML 中提取 md5（不同版本字段可能不同）
                    image_md5 = _extract_xml_attr(raw_text, "md5") or _extract_xml_tag_text(raw_text, "md5")
                    if not image_md5:
                        for k in [
                            "cdnthumbmd5",
                            "cdnthumd5",
                            "cdnmidimgmd5",
                            "cdnbigimgmd5",
                            "hdmd5",
                            "hevc_mid_md5",
                            "hevc_md5",
                            "imgmd5",
                            "filemd5",
                        ]:
                            image_md5 = _extract_xml_attr(raw_text, k) or _extract_xml_tag_text(raw_text, k)
                            if image_md5:
                                break

                    # Extract CDN URL (some versions store a non-HTTP "file id" string here)
                    _cdn_url_or_id = (
                        _extract_xml_attr(raw_text, "cdnthumburl")
                        or _extract_xml_attr(raw_text, "cdnthumurl")
                        or _extract_xml_attr(raw_text, "cdnmidimgurl")
                        or _extract_xml_attr(raw_text, "cdnbigimgurl")
                        or _extract_xml_tag_text(raw_text, "cdnthumburl")
                        or _extract_xml_tag_text(raw_text, "cdnthumurl")
                        or _extract_xml_tag_text(raw_text, "cdnmidimgurl")
                        or _extract_xml_tag_text(raw_text, "cdnbigimgurl")
                    )
                    _cdn_url_or_id = str(_cdn_url_or_id or "").strip()
                    image_url = _cdn_url_or_id if _cdn_url_or_id.startswith(("http://", "https://")) else ""
                    if (not image_url) and _cdn_url_or_id:
                        image_file_id = _cdn_url_or_id

                    if (not image_md5) and resource_conn is not None:
                        image_md5 = _lookup_resource_md5(
                            resource_conn,
                            resource_chat_id,
                            message_local_type=local_type,
                            server_id=int(r["server_id"] or 0),
                            local_id=local_id,
                            create_time=create_time,
                        )
                    content_text = "[图片]"
                elif local_type == 34:
                    render_type = "voice"
                    duration = _extract_xml_attr(raw_text, "voicelength")
                    voice_length = duration
                    content_text = f"[语音 {duration}秒]" if duration else "[语音]"
                elif local_type == 43 or local_type == 62:
                    render_type = "video"
                    video_md5 = _extract_xml_attr(raw_text, "md5")
                    video_thumb_md5 = _extract_xml_attr(raw_text, "cdnthumbmd5")
                    video_thumb_url_or_id = _extract_xml_attr(raw_text, "cdnthumburl") or _extract_xml_tag_text(
                        raw_text, "cdnthumburl"
                    )
                    video_url_or_id = _extract_xml_attr(raw_text, "cdnvideourl") or _extract_xml_tag_text(
                        raw_text, "cdnvideourl"
                    )

                    video_thumb_url = (
                        video_thumb_url_or_id
                        if str(video_thumb_url_or_id or "").strip().lower().startswith(("http://", "https://"))
                        else ""
                    )
                    video_url = (
                        video_url_or_id
                        if str(video_url_or_id or "").strip().lower().startswith(("http://", "https://"))
                        else ""
                    )
                    video_thumb_file_id = "" if video_thumb_url else (str(video_thumb_url_or_id or "").strip() or "")
                    video_file_id = "" if video_url else (str(video_url_or_id or "").strip() or "")
                    if (not video_thumb_md5) and resource_conn is not None:
                        video_thumb_md5 = _lookup_resource_md5(
                            resource_conn,
                            resource_chat_id,
                            message_local_type=local_type,
                            server_id=int(r["server_id"] or 0),
                            local_id=local_id,
                            create_time=create_time,
                        )
                    content_text = "[视频]"
                elif local_type == 47:
                    render_type = "emoji"
                    emoji_md5 = _extract_xml_attr(raw_text, "md5")
                    if not emoji_md5:
                        emoji_md5 = _extract_xml_tag_text(raw_text, "md5")
                    emoji_url = _extract_xml_attr(raw_text, "cdnurl")
                    if not emoji_url:
                        emoji_url = _extract_xml_tag_text(raw_text, "cdn_url")
                    if (not emoji_md5) and resource_conn is not None:
                        emoji_md5 = _lookup_resource_md5(
                            resource_conn,
                            resource_chat_id,
                            message_local_type=local_type,
                            server_id=int(r["server_id"] or 0),
                            local_id=local_id,
                            create_time=create_time,
                        )
                    content_text = "[表情]"
                elif local_type == 50:
                    render_type = "voip"
                    try:
                        import re

                        block = raw_text
                        m_voip = re.search(
                            r"(<VoIPBubbleMsg[^>]*>.*?</VoIPBubbleMsg>)",
                            raw_text,
                            flags=re.IGNORECASE | re.DOTALL,
                        )
                        if m_voip:
                            block = m_voip.group(1) or raw_text
                        room_type = str(_extract_xml_tag_text(block, "room_type") or "").strip()
                        if room_type == "0":
                            voip_type = "video"
                        elif room_type == "1":
                            voip_type = "audio"

                        voip_msg = str(_extract_xml_tag_text(block, "msg") or "").strip()
                        content_text = voip_msg or "通话"
                    except Exception:
                        content_text = "通话"
                elif local_type != 1:
                    if not content_text:
                        content_text = _infer_message_brief_by_local_type(local_type)
                    else:
                        if content_text.startswith("<") or content_text.startswith('"<'):
                            if "<appmsg" in content_text.lower():
                                parsed = _parse_app_message(content_text)
                                rt = str(parsed.get("renderType") or "")
                                if rt and rt != "text":
                                    render_type = rt
                                    content_text = str(parsed.get("content") or content_text)
                                    title = str(parsed.get("title") or title)
                                    url = str(parsed.get("url") or url)
                                    quote_title = str(parsed.get("quoteTitle") or quote_title)
                                    quote_content = str(parsed.get("quoteContent") or quote_content)
                                    amount = str(parsed.get("amount") or amount)
                                    cover_url = str(parsed.get("coverUrl") or cover_url)
                                    thumb_url = str(parsed.get("thumbUrl") or thumb_url)
                                    file_size = str(parsed.get("size") or file_size)
                                    pay_sub_type = str(parsed.get("paySubType") or pay_sub_type)
                                    file_md5 = str(parsed.get("fileMd5") or file_md5)
                                    transfer_id = str(parsed.get("transferId") or transfer_id)

                                    if render_type == "transfer":
                                        # 如果 transferId 仍为空，尝试从原始 XML 提取
                                        if not transfer_id:
                                            transfer_id = _extract_xml_tag_or_attr(content_text, "transferid") or ""
                                        transfer_status = _infer_transfer_status_text(
                                            is_sent=is_sent,
                                            paysubtype=pay_sub_type,
                                            receivestatus=str(parsed.get("receiveStatus") or ""),
                                            sendertitle=str(parsed.get("senderTitle") or ""),
                                            receivertitle=str(parsed.get("receiverTitle") or ""),
                                            senderdes=str(parsed.get("senderDes") or ""),
                                            receiverdes=str(parsed.get("receiverDes") or ""),
                                        )
                                        if not content_text:
                                            content_text = transfer_status or "转账"
                            t = _extract_xml_tag_text(content_text, "title")
                            d = _extract_xml_tag_text(content_text, "des")
                            content_text = t or d or _infer_message_brief_by_local_type(local_type)

                if not content_text:
                    content_text = _infer_message_brief_by_local_type(local_type)

                if quote_username:
                    quote_usernames.append(str(quote_username).strip())

                merged.append(
                    {
                        "id": f"{db_path.stem}:{table_name}:{local_id}",
                        "localId": local_id,
                        "serverId": int(r["server_id"] or 0),
                        "serverIdStr": str(int(r["server_id"] or 0)) if int(r["server_id"] or 0) else "",
                        "type": local_type,
                        "createTime": create_time,
                        "sortSeq": sort_seq,
                        "senderUsername": sender_username,
                        "isSent": bool(is_sent),
                        "renderType": render_type,
                        "content": content_text,
                        "title": title,
                        "url": url,
                        "imageMd5": image_md5,
                        "imageFileId": image_file_id,
                        "emojiMd5": emoji_md5,
                        "emojiUrl": emoji_url,
                        "thumbUrl": thumb_url,
                        "imageUrl": image_url,
                        "videoMd5": video_md5,
                        "videoThumbMd5": video_thumb_md5,
                        "videoFileId": video_file_id,
                        "videoThumbFileId": video_thumb_file_id,
                        "videoUrl": video_url,
                        "videoThumbUrl": video_thumb_url,
                        "voiceLength": voice_length,
                        "voipType": voip_type,
                        "quoteUsername": str(quote_username).strip(),
                        "quoteServerId": str(quote_server_id).strip(),
                        "quoteType": str(quote_type).strip(),
                        "quoteVoiceLength": str(quote_voice_length).strip(),
                        "quoteTitle": quote_title,
                        "quoteContent": quote_content,
                        "amount": amount,
                        "coverUrl": cover_url,
                        "fileSize": file_size,
                        "fileMd5": file_md5,
                        "paySubType": pay_sub_type,
                        "transferStatus": transfer_status,
                        "transferId": transfer_id,
                        "_rawText": raw_text if local_type == 266287972401 else "",
                    }
                )
        finally:
            conn.close()

    if resource_conn is not None:
        try:
            resource_conn.close()
        except Exception:
            pass

    # 后处理：关联转账消息的最终状态
    # 策略：优先使用 transferId 精确匹配，回退到金额+时间窗口匹配
    # paysubtype 含义：1=不明确 3=已收款 4=对方退回给你 8=发起转账 9=被对方退回 10=已过期

    # 收集已退还和已收款的转账ID和金额
    returned_transfer_ids: set[str] = set()  # 退还状态的 transferId
    received_transfer_ids: set[str] = set()  # 已收款状态的 transferId
    returned_amounts_with_time: list[tuple[str, int]] = []  # (金额, 时间戳) 用于退还回退匹配
    received_amounts_with_time: list[tuple[str, int]] = []  # (金额, 时间戳) 用于收款回退匹配

    for m in merged:
        if m.get("renderType") == "transfer":
            pst = str(m.get("paySubType") or "")
            tid = str(m.get("transferId") or "").strip()
            amt = str(m.get("amount") or "")
            ts = int(m.get("createTime") or 0)

            if pst in ("4", "9"):  # 退还状态
                if tid:
                    returned_transfer_ids.add(tid)
                if amt:
                    returned_amounts_with_time.append((amt, ts))
            elif pst == "3":  # 已收款状态
                if tid:
                    received_transfer_ids.add(tid)
                if amt:
                    received_amounts_with_time.append((amt, ts))

    # 更新原始转账消息的状态
    for m in merged:
        if m.get("renderType") == "transfer":
            pst = str(m.get("paySubType") or "")
            # 只更新未确定状态的原始转账消息（paysubtype=1 或 8）
            if pst in ("1", "8"):
                tid = str(m.get("transferId") or "").strip()
                amt = str(m.get("amount") or "")
                ts = int(m.get("createTime") or 0)

                # 优先检查退还状态（退还优先于收款）
                should_mark_returned = False
                should_mark_received = False

                # 策略1：精确 transferId 匹配
                if tid:
                    if tid in returned_transfer_ids:
                        should_mark_returned = True
                    elif tid in received_transfer_ids:
                        should_mark_received = True

                # 策略2：回退到金额+时间窗口匹配（24小时内同金额）
                if not should_mark_returned and not should_mark_received and amt:
                    for ret_amt, ret_ts in returned_amounts_with_time:
                        if ret_amt == amt and abs(ret_ts - ts) <= 86400:
                            should_mark_returned = True
                            break
                    if not should_mark_returned:
                        for rec_amt, rec_ts in received_amounts_with_time:
                            if rec_amt == amt and abs(rec_ts - ts) <= 86400:
                                should_mark_received = True
                                break

                if should_mark_returned:
                    m["paySubType"] = "9"
                    m["transferStatus"] = "已被退还"
                elif should_mark_received:
                    m["paySubType"] = "3"
                    # 根据 isSent 判断：发起方显示"已收款"，收款方显示"已被接收"
                    is_sent = m.get("isSent", False)
                    m["transferStatus"] = "已收款" if is_sent else "已被接收"

    uniq_senders = list(
        dict.fromkeys(
            [u for u in (sender_usernames + list(pat_usernames) + quote_usernames) if u]
        )
    )
    sender_contact_rows = _load_contact_rows(contact_db_path, uniq_senders)
    local_sender_avatars = _query_head_image_usernames(head_image_db_path, uniq_senders)

    for m in merged:
        su = str(m.get("senderUsername") or "")
        if not su:
            continue
        row = sender_contact_rows.get(su)
        m["senderDisplayName"] = _pick_display_name(row, su)
        avatar_url = _pick_avatar_url(row)
        if not avatar_url and su in local_sender_avatars:
            avatar_url = base_url + _build_avatar_url(account_dir.name, su)
        m["senderAvatar"] = avatar_url

        qu = str(m.get("quoteUsername") or "").strip()
        if qu:
            qrow = sender_contact_rows.get(qu)
            qt = str(m.get("quoteTitle") or "").strip()
            if qrow is not None:
                remark = ""
                try:
                    remark = str(qrow["remark"] or "").strip()
                except Exception:
                    remark = ""
                if remark:
                    m["quoteTitle"] = remark
                elif not qt:
                    m["quoteTitle"] = _pick_display_name(qrow, qu)
            elif not qt:
                m["quoteTitle"] = qu

        # Media URL fallback: if CDN URLs missing, use local media endpoints.
        try:
            rt = str(m.get("renderType") or "")
            if rt == "image":
                if not str(m.get("imageUrl") or ""):
                    md5 = str(m.get("imageMd5") or "").strip()
                    file_id = str(m.get("imageFileId") or "").strip()
                    if md5:
                        m["imageUrl"] = (
                            base_url
                            + f"/api/chat/media/image?account={quote(account_dir.name)}&md5={quote(md5)}&username={quote(username)}"
                        )
                    elif file_id:
                        m["imageUrl"] = (
                            base_url
                            + f"/api/chat/media/image?account={quote(account_dir.name)}&file_id={quote(file_id)}&username={quote(username)}"
                        )
            elif rt == "emoji":
                md5 = str(m.get("emojiMd5") or "")
                if md5:
                    existing_local: Optional[Path] = None
                    try:
                        existing_local = _try_find_decrypted_resource(account_dir, str(md5).lower())
                    except Exception:
                        existing_local = None

                    if existing_local:
                        try:
                            import re

                            cur = str(m.get("emojiUrl") or "")
                            if cur and re.match(r"^https?://", cur, flags=re.I) and ("/api/chat/media/emoji" not in cur):
                                m["emojiRemoteUrl"] = cur
                        except Exception:
                            pass

                        m["emojiUrl"] = (
                            base_url
                            + f"/api/chat/media/emoji?account={quote(account_dir.name)}&md5={quote(md5)}&username={quote(username)}"
                        )
                    elif (not str(m.get("emojiUrl") or "")):
                        m["emojiUrl"] = (
                            base_url
                            + f"/api/chat/media/emoji?account={quote(account_dir.name)}&md5={quote(md5)}&username={quote(username)}"
                        )
            elif rt == "video":
                video_thumb_url = str(m.get("videoThumbUrl") or "").strip()
                video_thumb_md5 = str(m.get("videoThumbMd5") or "").strip()
                video_thumb_file_id = str(m.get("videoThumbFileId") or "").strip()
                if (not video_thumb_url) or (
                    not video_thumb_url.lower().startswith(("http://", "https://"))
                ):
                    if video_thumb_md5:
                        m["videoThumbUrl"] = (
                            base_url
                            + f"/api/chat/media/video_thumb?account={quote(account_dir.name)}&md5={quote(video_thumb_md5)}&username={quote(username)}"
                        )
                    elif video_thumb_file_id:
                        m["videoThumbUrl"] = (
                            base_url
                            + f"/api/chat/media/video_thumb?account={quote(account_dir.name)}&file_id={quote(video_thumb_file_id)}&username={quote(username)}"
                        )

                video_url = str(m.get("videoUrl") or "").strip()
                video_md5 = str(m.get("videoMd5") or "").strip()
                video_file_id = str(m.get("videoFileId") or "").strip()
                if (not video_url) or (not video_url.lower().startswith(("http://", "https://"))):
                    if video_md5:
                        m["videoUrl"] = (
                            base_url
                            + f"/api/chat/media/video?account={quote(account_dir.name)}&md5={quote(video_md5)}&username={quote(username)}"
                        )
                    elif video_file_id:
                        m["videoUrl"] = (
                            base_url
                            + f"/api/chat/media/video?account={quote(account_dir.name)}&file_id={quote(video_file_id)}&username={quote(username)}"
                        )
            elif rt == "voice":
                if str(m.get("serverId") or ""):
                    sid = int(m.get("serverId") or 0)
                    if sid:
                        m["voiceUrl"] = base_url + f"/api/chat/media/voice?account={quote(account_dir.name)}&server_id={sid}"
        except Exception:
            pass

        if int(m.get("type") or 0) == 266287972401:
            raw = str(m.get("_rawText") or "")
            if raw:
                m["content"] = _parse_pat_message(raw, sender_contact_rows)

        if "_rawText" in m:
            m.pop("_rawText", None)

    def sort_key(m: dict[str, Any]) -> tuple[int, int, int]:
        sseq = int(m.get("sortSeq") or 0)
        cts = int(m.get("createTime") or 0)
        lid = int(m.get("localId") or 0)
        return (cts, sseq, lid)

    merged.sort(key=sort_key, reverse=True)
    has_more_global = bool(has_more_any or (len(merged) > (int(offset) + int(limit))))
    page = merged[int(offset) : int(offset) + int(limit)]
    if want_asc:
        page = list(reversed(page))

    return {
        "status": "success",
        "account": account_dir.name,
        "username": username,
        "total": int(offset) + len(page) + (1 if has_more_global else 0),
        "hasMore": bool(has_more_global),
        "messages": page,
    }


async def _search_chat_messages_via_fts(
    request: Request,
    *,
    q: str,
    account: Optional[str],
    username: Optional[str],
    sender: Optional[str],
    session_type: Optional[str],
    limit: int,
    offset: int,
    start_time: Optional[int],
    end_time: Optional[int],
    render_types: Optional[str],
    include_hidden: bool,
    include_official: bool,
) -> dict[str, Any]:
    tokens = _make_search_tokens(q)
    if not tokens:
        raise HTTPException(status_code=400, detail="Missing q.")

    if limit <= 0:
        raise HTTPException(status_code=400, detail="Invalid limit.")
    if limit > 200:
        limit = 200
    if offset < 0:
        offset = 0

    start_ts = int(start_time) if start_time is not None else None
    end_ts = int(end_time) if end_time is not None else None
    if start_ts is not None and start_ts < 0:
        start_ts = 0
    if end_ts is not None and end_ts < 0:
        end_ts = 0

    want_types: Optional[set[str]] = None
    if render_types is not None:
        parts = [p.strip() for p in str(render_types or "").split(",") if p.strip()]
        want_types = {p for p in parts if p}
        if not want_types:
            want_types = None

    username = str(username).strip() if username else None
    if not username:
        username = None

    sender = str(sender).strip() if sender else None
    if not sender:
        sender = None

    session_type_norm = _normalize_session_type(session_type)

    account_dir = _resolve_account_dir(account)
    contact_db_path = account_dir / "contact.db"
    head_image_db_path = account_dir / "head_image.db"
    base_url = str(request.base_url).rstrip("/")

    index_status = get_chat_search_index_status(account_dir)
    index = dict(index_status.get("index") or {})
    build = dict(index.get("build") or {})

    index_exists = bool(index.get("exists"))
    index_ready = bool(index.get("ready"))
    build_status = str(build.get("status") or "").strip()

    if (not index_ready) and build_status not in {"building", "error"}:
        start_chat_search_index_build(account_dir, rebuild=bool(index_exists))
        index_status = get_chat_search_index_status(account_dir)
        index = dict(index_status.get("index") or {})
        build = dict(index.get("build") or {})
        build_status = str(build.get("status") or "").strip()
        index_exists = bool(index.get("exists"))
        index_ready = bool(index.get("ready"))

    if build_status == "error":
        return {
            "status": "index_error",
            "account": account_dir.name,
            "q": q,
            "tokens": tokens,
            "scope": "conversation" if username else "global",
            "username": username,
            "offset": int(offset),
            "limit": int(limit),
            "baseUrl": base_url,
            "total": 0,
            "hasMore": False,
            "hits": [],
            "index": index,
            "message": str(build.get("error") or "Search index build failed."),
        }

    if not index_ready:
        return {
            "status": "index_building",
            "account": account_dir.name,
            "q": q,
            "tokens": tokens,
            "scope": "conversation" if username else "global",
            "username": username,
            "offset": int(offset),
            "limit": int(limit),
            "baseUrl": base_url,
            "total": 0,
            "hasMore": False,
            "hits": [],
            "index": index,
            "message": "Search index is building. Please retry in a moment.",
        }

    fts_query = _build_fts_query(q)
    if not fts_query:
        raise HTTPException(status_code=400, detail="Missing q.")

    index_db_path = get_chat_search_index_db_path(account_dir)
    conn = sqlite3.connect(str(index_db_path))
    conn.row_factory = sqlite3.Row
    try:
        try:
            where_parts: list[str] = ["message_fts MATCH ?"]
            params: list[Any] = [fts_query]

            if username:
                where_parts.append("username = ?")
                params.append(str(username))
            elif session_type_norm == "group":
                where_parts.append("username LIKE ?")
                params.append("%@chatroom")
            elif session_type_norm == "single":
                where_parts.append("username NOT LIKE ?")
                params.append("%@chatroom")

            if sender:
                where_parts.append("sender_username = ?")
                params.append(str(sender))

            if want_types is not None:
                types_sorted = sorted(want_types)
                placeholders = ",".join(["?"] * len(types_sorted))
                where_parts.append(f"render_type IN ({placeholders})")
                params.extend(types_sorted)

            if start_ts is not None:
                where_parts.append("CAST(create_time AS INTEGER) >= ?")
                params.append(int(start_ts))
            if end_ts is not None:
                where_parts.append("CAST(create_time AS INTEGER) <= ?")
                params.append(int(end_ts))

            if not include_hidden:
                where_parts.append("CAST(is_hidden AS INTEGER) = 0")
            if not include_official:
                where_parts.append("CAST(is_official AS INTEGER) = 0")

            where_sql = " AND ".join(where_parts)
            total_row = conn.execute(f"SELECT COUNT(*) AS c FROM message_fts WHERE {where_sql}", params).fetchone()
            total = int(total_row[0] or 0) if total_row is not None else 0

            rows = conn.execute(
                f"""
                SELECT
                    username,
                    db_stem,
                    table_name,
                    local_id
                FROM message_fts
                WHERE {where_sql}
                ORDER BY
                    CAST(create_time AS INTEGER) DESC,
                    CAST(sort_seq AS INTEGER) DESC,
                    CAST(local_id AS INTEGER) DESC
                LIMIT ? OFFSET ?
                """,
                params + [int(limit), int(offset)],
            ).fetchall()
        except Exception as e:
            logger.exception("Chat search index query failed")
            return {
                "status": "index_error",
                "account": account_dir.name,
                "q": q,
                "tokens": tokens,
                "scope": "conversation" if username else "global",
                "username": username,
                "offset": int(offset),
                "limit": int(limit),
                "baseUrl": base_url,
                "total": 0,
                "hasMore": False,
                "hits": [],
                "index": index,
                "message": str(e),
            }
    finally:
        conn.close()

    db_paths = _iter_message_db_paths(account_dir)
    stem_to_path = {p.stem: p for p in db_paths}

    groups: dict[tuple[Path, str, str], list[int]] = {}
    ordered_keys: list[tuple[Path, str, str, int]] = []
    for r in rows:
        conv_username = str(r["username"] or "").strip()
        db_stem = str(r["db_stem"] or "").strip()
        table_name = str(r["table_name"] or "").strip()
        local_id = int(r["local_id"] or 0)
        if not conv_username or not db_stem or not table_name or local_id <= 0:
            continue
        db_path = stem_to_path.get(db_stem)
        if db_path is None:
            continue
        groups.setdefault((db_path, table_name, conv_username), []).append(local_id)
        ordered_keys.append((db_path, table_name, conv_username, local_id))

    hit_by_key: dict[tuple[Path, str, str, int], dict[str, Any]] = {}

    for (db_path, table_name, conv_username), local_ids in groups.items():
        uniq_local_ids = list(dict.fromkeys([int(x) for x in local_ids if int(x) > 0]))
        if not uniq_local_ids:
            continue

        msg_conn = sqlite3.connect(str(db_path))
        msg_conn.row_factory = sqlite3.Row
        msg_conn.text_factory = bytes
        try:
            my_rowid = None
            try:
                r2 = msg_conn.execute(
                    "SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1",
                    (account_dir.name,),
                ).fetchone()
                if r2 is not None and r2[0] is not None:
                    my_rowid = int(r2[0])
            except Exception:
                my_rowid = None

            placeholders = ",".join(["?"] * len(uniq_local_ids))
            quoted_table = _quote_ident(table_name)

            sql_with_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, n.user_name AS sender_username "
                f"FROM {quoted_table} m "
                "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
                f"WHERE m.local_id IN ({placeholders})"
            )
            sql_no_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, '' AS sender_username "
                f"FROM {quoted_table} m "
                f"WHERE m.local_id IN ({placeholders})"
            )

            try:
                try:
                    msg_rows = msg_conn.execute(sql_with_join, uniq_local_ids).fetchall()
                except Exception:
                    msg_rows = msg_conn.execute(sql_no_join, uniq_local_ids).fetchall()
            except Exception:
                continue

            is_group = bool(conv_username.endswith("@chatroom"))
            for rr in msg_rows:
                local_id = int(rr["local_id"] or 0)
                if local_id <= 0:
                    continue
                try:
                    hit = _row_to_search_hit(
                        rr,
                        db_path=db_path,
                        table_name=table_name,
                        username=conv_username,
                        account_dir=account_dir,
                        is_group=is_group,
                        my_rowid=my_rowid,
                    )
                except Exception:
                    continue

                hay_items = [
                    str(hit.get("content") or ""),
                    str(hit.get("title") or ""),
                    str(hit.get("url") or ""),
                    str(hit.get("quoteTitle") or ""),
                    str(hit.get("quoteContent") or ""),
                    str(hit.get("amount") or ""),
                ]
                haystack = "\n".join([x for x in hay_items if x.strip()])
                snippet_src = (
                    str(hit.get("content") or "").strip()
                    or str(hit.get("title") or "").strip()
                    or haystack
                )
                hit["snippet"] = _make_snippet(snippet_src, tokens)
                hit_by_key[(db_path, table_name, conv_username, local_id)] = hit
        finally:
            msg_conn.close()

    hits: list[dict[str, Any]] = []
    for k in ordered_keys:
        h = hit_by_key.get(k)
        if h is not None:
            hits.append(h)

    scope = "conversation" if username else "global"

    if username:
        uniq_usernames = list(dict.fromkeys([username] + [str(x.get("senderUsername") or "") for x in hits]))
        contact_rows = _load_contact_rows(contact_db_path, uniq_usernames)
        local_avatar_usernames = _query_head_image_usernames(head_image_db_path, uniq_usernames)
        conv_row = contact_rows.get(username)
        conv_name = _pick_display_name(conv_row, username)
        conv_avatar = _pick_avatar_url(conv_row)
        if (not conv_avatar) and (username in local_avatar_usernames):
            conv_avatar = base_url + _build_avatar_url(account_dir.name, username)

        for h in hits:
            su = str(h.get("senderUsername") or "").strip()
            h["conversationName"] = conv_name
            h["conversationAvatar"] = conv_avatar
            if su:
                row = contact_rows.get(su)
                h["senderDisplayName"] = (
                    _pick_display_name(row, su)
                    if row is not None
                    else (conv_name if su == username else su)
                )
                avatar_url = _pick_avatar_url(row)
                if (not avatar_url) and (su in local_avatar_usernames):
                    avatar_url = base_url + _build_avatar_url(account_dir.name, su)
                h["senderAvatar"] = avatar_url
    else:
        uniq_contacts = list(
            dict.fromkeys(
                [str(x.get("username") or "") for x in hits] + [str(x.get("senderUsername") or "") for x in hits]
            )
        )
        contact_rows = _load_contact_rows(contact_db_path, uniq_contacts)
        local_avatar_usernames = _query_head_image_usernames(head_image_db_path, uniq_contacts)

        for h in hits:
            cu = str(h.get("username") or "").strip()
            su = str(h.get("senderUsername") or "").strip()
            crow = contact_rows.get(cu)
            conv_name = _pick_display_name(crow, cu) if cu else ""
            h["conversationName"] = conv_name or cu
            conv_avatar = _pick_avatar_url(crow)
            if (not conv_avatar) and cu and (cu in local_avatar_usernames):
                conv_avatar = base_url + _build_avatar_url(account_dir.name, cu)
            h["conversationAvatar"] = conv_avatar
            if su:
                row = contact_rows.get(su)
                h["senderDisplayName"] = (
                    _pick_display_name(row, su) if row is not None else (conv_name if su == cu else su)
                )
                avatar_url = _pick_avatar_url(row)
                if (not avatar_url) and (su in local_avatar_usernames):
                    avatar_url = base_url + _build_avatar_url(account_dir.name, su)
                h["senderAvatar"] = avatar_url

    return {
        "status": "success",
        "account": account_dir.name,
        "scope": scope,
        "username": username,
        "q": q,
        "tokens": tokens,
        "offset": int(offset),
        "limit": int(limit),
        "baseUrl": base_url,
        "total": int(total),
        "hasMore": bool(int(offset) + int(limit) < int(total)),
        "index": index,
        "hits": hits,
    }


@router.get("/api/chat/search", summary="搜索聊天记录（消息）")
async def search_chat_messages(
    request: Request,
    q: str,
    account: Optional[str] = None,
    username: Optional[str] = None,
    sender: Optional[str] = None,
    session_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    render_types: Optional[str] = None,
    include_hidden: bool = False,
    include_official: bool = False,
    session_limit: int = 200,
    per_chat_scan: int = 200,
    scan_limit: int = 20000,
):
    return await _search_chat_messages_via_fts(
        request,
        q=q,
        account=account,
        username=username,
        sender=sender,
        session_type=session_type,
        limit=limit,
        offset=offset,
        start_time=start_time,
        end_time=end_time,
        render_types=render_types,
        include_hidden=include_hidden,
        include_official=include_official,
    )

    tokens = _make_search_tokens(q)
    if not tokens:
        raise HTTPException(status_code=400, detail="Missing q.")

    if limit <= 0:
        raise HTTPException(status_code=400, detail="Invalid limit.")
    if limit > 200:
        limit = 200
    if offset < 0:
        offset = 0

    if session_limit <= 0:
        session_limit = 200
    if session_limit > 2000:
        session_limit = 2000

    if per_chat_scan <= 0:
        per_chat_scan = 200
    if per_chat_scan > 5000:
        per_chat_scan = 5000

    if scan_limit <= 0:
        scan_limit = 20000
    if scan_limit > 200000:
        scan_limit = 200000

    start_ts = int(start_time) if start_time is not None else None
    end_ts = int(end_time) if end_time is not None else None
    if start_ts is not None and start_ts < 0:
        start_ts = 0
    if end_ts is not None and end_ts < 0:
        end_ts = 0

    want_types: Optional[set[str]] = None
    if render_types is not None:
        parts = [p.strip() for p in str(render_types or "").split(",") if p.strip()]
        want_types = {p for p in parts if p}
        if not want_types:
            want_types = None

    account_dir = _resolve_account_dir(account)
    db_paths = _iter_message_db_paths(account_dir)
    contact_db_path = account_dir / "contact.db"
    session_db_path = account_dir / "session.db"

    if not db_paths:
        return {
            "status": "error",
            "account": account_dir.name,
            "q": q,
            "hits": [],
            "hasMore": False,
            "scanLimited": False,
            "scannedMessages": 0,
            "message": "No message databases found for this account.",
        }

    def build_haystack(hit: dict[str, Any]) -> str:
        items = [
            str(hit.get("content") or ""),
            str(hit.get("title") or ""),
            str(hit.get("url") or ""),
            str(hit.get("quoteTitle") or ""),
            str(hit.get("quoteContent") or ""),
            str(hit.get("amount") or ""),
        ]
        return "\n".join([x for x in items if x.strip()])

    def scan_conversation(conv_username: str, *, per_db_limit: int, max_hits: Optional[int] = None) -> tuple[list[dict[str, Any]], int, bool]:
        is_group = bool(conv_username.endswith("@chatroom"))
        scanned = 0
        truncated = False
        hits: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for db_path in db_paths:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            try:
                table_name = _resolve_msg_table_name(conn, conv_username)
                if not table_name:
                    continue

                my_wxid = account_dir.name
                my_rowid = None
                try:
                    r2 = conn.execute(
                        "SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1",
                        (my_wxid,),
                    ).fetchone()
                    if r2 is not None:
                        my_rowid = int(r2[0])
                except Exception:
                    my_rowid = None

                where_parts: list[str] = []
                params: list[Any] = []
                if start_ts is not None:
                    where_parts.append("m.create_time >= ?")
                    params.append(int(start_ts))
                if end_ts is not None:
                    where_parts.append("m.create_time <= ?")
                    params.append(int(end_ts))

                where_sql = ""
                if where_parts:
                    where_sql = "WHERE " + " AND ".join(where_parts)

                quoted_table = _quote_ident(table_name)
                sql_with_join = (
                    "SELECT "
                    "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                    "m.message_content, m.compress_content, n.user_name AS sender_username "
                    f"FROM {quoted_table} m "
                    "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
                    f"{where_sql} "
                    "ORDER BY m.create_time DESC, m.sort_seq DESC, m.local_id DESC "
                    "LIMIT ?"
                )
                sql_no_join = (
                    "SELECT "
                    "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                    "m.message_content, m.compress_content, '' AS sender_username "
                    f"FROM {quoted_table} m "
                    f"{where_sql} "
                    "ORDER BY m.create_time DESC, m.sort_seq DESC, m.local_id DESC "
                    "LIMIT ?"
                )

                conn.text_factory = bytes

                per_db_probe = int(per_db_limit) + 1
                params_probe = list(params) + [per_db_probe]
                try:
                    rows = conn.execute(sql_with_join, params_probe).fetchall()
                except Exception:
                    rows = conn.execute(sql_no_join, params_probe).fetchall()

                if len(rows) > per_db_limit:
                    truncated = True
                    rows = rows[:per_db_limit]

                scanned += len(rows)

                for rr in rows:
                    hit = _row_to_search_hit(
                        rr,
                        db_path=db_path,
                        table_name=table_name,
                        username=conv_username,
                        account_dir=account_dir,
                        is_group=is_group,
                        my_rowid=my_rowid,
                    )
                    if want_types is not None and str(hit.get("renderType") or "") not in want_types:
                        continue

                    haystack = build_haystack(hit)
                    if not _match_tokens(haystack, tokens):
                        continue

                    mid = str(hit.get("id") or "")
                    if not mid or mid in seen_ids:
                        continue
                    seen_ids.add(mid)

                    snippet_src = str(hit.get("content") or "").strip() or str(hit.get("title") or "").strip() or haystack
                    hit["snippet"] = _make_snippet(snippet_src, tokens)
                    hits.append(hit)

                    if max_hits is not None and len(hits) >= int(max_hits):
                        return hits, scanned, True
            finally:
                conn.close()

        return hits, scanned, truncated

    base_url = str(request.base_url).rstrip("/")

    hits: list[dict[str, Any]] = []
    scanned_messages = 0
    scan_limited = False

    if username:
        conv_hits, scanned, truncated = scan_conversation(username, per_db_limit=scan_limit)
        scanned_messages = scanned
        scan_limited = bool(truncated)

        conv_hits.sort(
            key=lambda h: (
                int(h.get("createTime") or 0),
                int(h.get("sortSeq") or 0),
                int(h.get("localId") or 0),
            ),
            reverse=True,
        )
        total_in_scan = len(conv_hits)
        page = conv_hits[int(offset) : int(offset) + int(limit)]

        uniq_usernames = list(dict.fromkeys([username] + [str(x.get("senderUsername") or "") for x in page]))
        contact_rows = _load_contact_rows(contact_db_path, uniq_usernames)
        conv_row = contact_rows.get(username)
        conv_name = _pick_display_name(conv_row, username)

        for h in page:
            su = str(h.get("senderUsername") or "").strip()
            h["conversationName"] = conv_name
            if su:
                row = contact_rows.get(su)
                h["senderDisplayName"] = _pick_display_name(row, su) if row is not None else (conv_name if su == username else su)

        return {
            "status": "success",
            "account": account_dir.name,
            "scope": "conversation",
            "username": username,
            "q": q,
            "tokens": tokens,
            "offset": int(offset),
            "limit": int(limit),
            "totalInScan": total_in_scan,
            "hasMore": bool((int(offset) + int(limit) < total_in_scan) or scan_limited),
            "scanLimited": bool(scan_limited),
            "scannedMessages": int(scanned_messages),
            "hits": page,
        }

    # Global: scan recent conversations (session.db), then keep only top K newest hits within the scanned window.
    if not session_db_path.exists():
        raise HTTPException(status_code=404, detail="session.db not found for this account.")

    sconn = sqlite3.connect(str(session_db_path))
    sconn.row_factory = sqlite3.Row
    try:
        rows = sconn.execute(
            """
            SELECT
                username,
                is_hidden,
                sort_timestamp,
                last_timestamp
            FROM SessionTable
            ORDER BY sort_timestamp DESC
            LIMIT ?
            """,
            (int(session_limit),),
        ).fetchall()
    finally:
        sconn.close()

    conv_usernames: list[str] = []
    for r in rows:
        u = str(r["username"] or "").strip()
        if not u:
            continue
        if not include_hidden and int(r["is_hidden"] or 0) == 1:
            continue
        if not _should_keep_session(u, include_official=include_official):
            continue
        conv_usernames.append(u)

    top_k = min(5000, int(offset) + int(limit) + 2000)
    heap: list[tuple[tuple[int, int, int], dict[str, Any]]] = []

    for conv in conv_usernames:
        conv_hits, scanned, truncated = scan_conversation(conv, per_db_limit=per_chat_scan, max_hits=50)
        scanned_messages += int(scanned)
        if truncated:
            scan_limited = True
        for h in conv_hits:
            k = (
                int(h.get("createTime") or 0),
                int(h.get("sortSeq") or 0),
                int(h.get("localId") or 0),
            )
            heapq.heappush(heap, (k, h))
            if len(heap) > top_k:
                heapq.heappop(heap)

    heap.sort(key=lambda x: x[0], reverse=True)
    hits_all = [x[1] for x in heap]
    total_in_scan = len(hits_all)
    page = hits_all[int(offset) : int(offset) + int(limit)]

    uniq_contacts = list(
        dict.fromkeys(
            [str(x.get("username") or "") for x in page] + [str(x.get("senderUsername") or "") for x in page]
        )
    )
    contact_rows = _load_contact_rows(contact_db_path, uniq_contacts)

    for h in page:
        cu = str(h.get("username") or "").strip()
        su = str(h.get("senderUsername") or "").strip()
        crow = contact_rows.get(cu)
        conv_name = _pick_display_name(crow, cu) if cu else ""
        h["conversationName"] = conv_name or cu
        if su:
            row = contact_rows.get(su)
            h["senderDisplayName"] = _pick_display_name(row, su) if row is not None else (conv_name if su == cu else su)

    return {
        "status": "success",
        "account": account_dir.name,
        "scope": "global",
        "q": q,
        "tokens": tokens,
        "offset": int(offset),
        "limit": int(limit),
        "baseUrl": base_url,
        "totalInScan": total_in_scan,
        "hasMore": bool((int(offset) + int(limit) < total_in_scan) or scan_limited or (total_in_scan >= top_k)),
        "scanLimited": bool(scan_limited),
        "scannedMessages": int(scanned_messages),
        "conversationsScanned": len(conv_usernames),
        "hits": page,
    }


@router.get("/api/chat/messages/around", summary="定位到某条消息并返回上下文")
async def get_chat_messages_around(
    request: Request,
    username: str,
    anchor_id: str,
    account: Optional[str] = None,
    before: int = 20,
    after: int = 20,
):
    if not username:
        raise HTTPException(status_code=400, detail="Missing username.")
    if not anchor_id:
        raise HTTPException(status_code=400, detail="Missing anchor_id.")
    if before < 0:
        before = 0
    if after < 0:
        after = 0
    if before > 200:
        before = 200
    if after > 200:
        after = 200

    parts = str(anchor_id).split(":", 2)
    if len(parts) != 3:
        raise HTTPException(status_code=400, detail="Invalid anchor_id.")
    anchor_db_stem, anchor_table_name, anchor_local_id_str = parts
    try:
        anchor_local_id = int(anchor_local_id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid anchor_id.")

    account_dir = _resolve_account_dir(account)
    db_paths = _iter_message_db_paths(account_dir)
    contact_db_path = account_dir / "contact.db"
    head_image_db_path = account_dir / "head_image.db"
    message_resource_db_path = account_dir / "message_resource.db"
    base_url = str(request.base_url).rstrip("/")

    target_db: Optional[Path] = None
    for p in db_paths:
        if p.stem == anchor_db_stem:
            target_db = p
            break
    if target_db is None:
        raise HTTPException(status_code=404, detail="Anchor database not found.")

    resource_conn: Optional[sqlite3.Connection] = None
    resource_chat_id: Optional[int] = None
    try:
        if message_resource_db_path.exists():
            resource_conn = sqlite3.connect(str(message_resource_db_path))
            resource_conn.row_factory = sqlite3.Row
            resource_chat_id = _resource_lookup_chat_id(resource_conn, username)
    except Exception:
        if resource_conn is not None:
            try:
                resource_conn.close()
            except Exception:
                pass
        resource_conn = None
        resource_chat_id = None

    conn = sqlite3.connect(str(target_db))
    conn.row_factory = sqlite3.Row
    try:
        table_name = str(anchor_table_name).strip()
        if not table_name:
            raise HTTPException(status_code=404, detail="Anchor table not found.")

        # Normalize table name casing if needed
        try:
            trows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            lower_to_actual = {str(x[0]).lower(): str(x[0]) for x in trows if x and x[0]}
            table_name = lower_to_actual.get(table_name.lower(), table_name)
        except Exception:
            pass

        my_wxid = account_dir.name
        my_rowid = None
        try:
            r2 = conn.execute(
                "SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1",
                (my_wxid,),
            ).fetchone()
            if r2 is not None:
                my_rowid = int(r2[0])
        except Exception:
            my_rowid = None

        quoted_table = _quote_ident(table_name)
        sql_anchor_with_join = (
            "SELECT "
            "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
            "m.message_content, m.compress_content, n.user_name AS sender_username "
            f"FROM {quoted_table} m "
            "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
            "WHERE m.local_id = ? "
            "LIMIT 1"
        )
        sql_anchor_no_join = (
            "SELECT "
            "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
            "m.message_content, m.compress_content, '' AS sender_username "
            f"FROM {quoted_table} m "
            "WHERE m.local_id = ? "
            "LIMIT 1"
        )

        conn.text_factory = bytes

        try:
            anchor_row = conn.execute(sql_anchor_with_join, (anchor_local_id,)).fetchone()
        except Exception:
            anchor_row = conn.execute(sql_anchor_no_join, (anchor_local_id,)).fetchone()

        if anchor_row is None:
            raise HTTPException(status_code=404, detail="Anchor message not found.")

        anchor_ct = int(anchor_row["create_time"] or 0)
        anchor_ss = int(anchor_row["sort_seq"] or 0) if anchor_row["sort_seq"] is not None else 0

        where_before = (
            "WHERE ("
            "m.create_time < ? "
            "OR (m.create_time = ? AND COALESCE(m.sort_seq, 0) < ?) "
            "OR (m.create_time = ? AND COALESCE(m.sort_seq, 0) = ? AND m.local_id <= ?)"
            ")"
        )
        where_after = (
            "WHERE ("
            "m.create_time > ? "
            "OR (m.create_time = ? AND COALESCE(m.sort_seq, 0) > ?) "
            "OR (m.create_time = ? AND COALESCE(m.sort_seq, 0) = ? AND m.local_id >= ?)"
            ")"
        )

        sql_before_with_join = (
            "SELECT "
            "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
            "m.message_content, m.compress_content, n.user_name AS sender_username "
            f"FROM {quoted_table} m "
            "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
            f"{where_before} "
            "ORDER BY m.create_time DESC, COALESCE(m.sort_seq, 0) DESC, m.local_id DESC "
            "LIMIT ?"
        )
        sql_before_no_join = (
            "SELECT "
            "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
            "m.message_content, m.compress_content, '' AS sender_username "
            f"FROM {quoted_table} m "
            f"{where_before} "
            "ORDER BY m.create_time DESC, COALESCE(m.sort_seq, 0) DESC, m.local_id DESC "
            "LIMIT ?"
        )

        sql_after_with_join = (
            "SELECT "
            "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
            "m.message_content, m.compress_content, n.user_name AS sender_username "
            f"FROM {quoted_table} m "
            "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
            f"{where_after} "
            "ORDER BY m.create_time ASC, COALESCE(m.sort_seq, 0) ASC, m.local_id ASC "
            "LIMIT ?"
        )
        sql_after_no_join = (
            "SELECT "
            "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
            "m.message_content, m.compress_content, '' AS sender_username "
            f"FROM {quoted_table} m "
            f"{where_after} "
            "ORDER BY m.create_time ASC, COALESCE(m.sort_seq, 0) ASC, m.local_id ASC "
            "LIMIT ?"
        )

        params_before = (anchor_ct, anchor_ct, anchor_ss, anchor_ct, anchor_ss, anchor_local_id, int(before) + 1)
        params_after = (anchor_ct, anchor_ct, anchor_ss, anchor_ct, anchor_ss, anchor_local_id, int(after) + 1)

        try:
            before_rows = conn.execute(sql_before_with_join, params_before).fetchall()
        except Exception:
            before_rows = conn.execute(sql_before_no_join, params_before).fetchall()

        try:
            after_rows = conn.execute(sql_after_with_join, params_after).fetchall()
        except Exception:
            after_rows = conn.execute(sql_after_no_join, params_after).fetchall()

        seen_ids: set[str] = set()
        combined: list[sqlite3.Row] = []
        for rr in list(before_rows) + list(after_rows):
            lid = int(rr["local_id"] or 0)
            mid = f"{target_db.stem}:{table_name}:{lid}"
            if mid in seen_ids:
                continue
            seen_ids.add(mid)
            combined.append(rr)

        merged: list[dict[str, Any]] = []
        sender_usernames: list[str] = []
        quote_usernames: list[str] = []
        pat_usernames: set[str] = set()
        is_group = bool(username.endswith("@chatroom"))

        _append_full_messages_from_rows(
            merged=merged,
            sender_usernames=sender_usernames,
            quote_usernames=quote_usernames,
            pat_usernames=pat_usernames,
            rows=combined,
            db_path=target_db,
            table_name=table_name,
            username=username,
            account_dir=account_dir,
            is_group=is_group,
            my_rowid=my_rowid,
            resource_conn=resource_conn,
            resource_chat_id=resource_chat_id,
        )

        return_messages = merged
    finally:
        conn.close()
        if resource_conn is not None:
            try:
                resource_conn.close()
            except Exception:
                pass

    _postprocess_full_messages(
        merged=return_messages,
        sender_usernames=sender_usernames,
        quote_usernames=quote_usernames,
        pat_usernames=pat_usernames,
        account_dir=account_dir,
        username=username,
        base_url=base_url,
        contact_db_path=contact_db_path,
        head_image_db_path=head_image_db_path,
    )

    def sort_key(m: dict[str, Any]) -> tuple[int, int, int]:
        sseq = int(m.get("sortSeq") or 0)
        cts = int(m.get("createTime") or 0)
        lid = int(m.get("localId") or 0)
        return (cts, sseq, lid)

    return_messages.sort(key=sort_key, reverse=False)
    anchor_index = -1
    for i, m in enumerate(return_messages):
        if str(m.get("id") or "") == str(anchor_id):
            anchor_index = i
            break

    return {
        "status": "success",
        "account": account_dir.name,
        "username": username,
        "anchorId": anchor_id,
        "anchorIndex": anchor_index,
        "messages": return_messages,
    }
