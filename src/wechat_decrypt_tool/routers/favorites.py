from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree as ET

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from ..chat_accounts import resolve_chat_account_context
from ..chat_helpers import _resolve_msg_table_name_by_map
from ..wcdb_realtime import WCDB_REALTIME
from ..wcdb_realtime import exec_query as _wcdb_exec_query
from .chat import _append_full_messages_from_rows, _postprocess_full_messages
from .chat_media import _convert_silk_to_browser_audio
from .general import _coerce_blob_bytes, _open_db_source, _resolve_general_contacts, _source_meta


router = APIRouter()

_MAX_LIMIT = 200
_MAX_CONTENT_CHARS = 4 * 1024 * 1024
_UNSAFE_XML_RE = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
_INVALID_XML_CONTROL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")
_MD5_RE = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)
_INTERNAL_NOTE_FILE_RE = re.compile(r"^[0-9a-f]{32}\.html?$", re.IGNORECASE)

_FAVORITE_TYPE_LABELS = {
    1: "文本",
    2: "图片",
    3: "语音",
    4: "视频",
    5: "链接",
    6: "位置",
    7: "音乐",
    8: "文件",
    14: "聊天记录",
    16: "商品",
    18: "笔记",
    20: "视频号",
}

# 笔记和合并聊天记录里的 dataitem 使用 recorditem 编号；普通单条收藏的
# dataitem 则基本跟 favitem.type 一致。3/4/5/6/7 在两套编号里的语义不同。
_RECORD_DATA_TYPE_LABELS = {
    1: "文本",
    2: "图片",
    3: "名片",
    4: "语音",
    5: "视频",
    6: "链接",
    7: "位置",
    8: "文件",
    17: "聊天记录",
    19: "小程序",
    22: "视频号",
    23: "视频号直播",
    29: "音乐",
    36: "小程序/H5",
    37: "表情包",
}

_RECORD_DATA_RENDER_TYPES = {
    1: "text",
    2: "image",
    3: "contact",
    4: "voice",
    5: "video",
    6: "link",
    7: "location",
    8: "file",
    17: "chatHistory",
    19: "link",
    22: "link",
    23: "link",
    29: "link",
    36: "link",
    37: "emoji",
}

_DIRECT_DATA_TYPE_LABELS = {
    1: "文本",
    2: "图片",
    3: "语音",
    4: "视频",
    5: "链接",
    6: "位置",
    7: "音乐",
    8: "文件",
    14: "聊天记录",
    16: "商品",
    18: "笔记",
    20: "视频号",
    37: "表情包",
}

_DIRECT_DATA_RENDER_TYPES = {
    1: "text",
    2: "image",
    3: "voice",
    4: "video",
    5: "link",
    6: "location",
    7: "link",
    8: "file",
    14: "chatHistory",
    16: "link",
    18: "text",
    20: "link",
    37: "emoji",
}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except Exception:
        return default


def _text(value: Any, *, max_len: int = 20_000, preserve_lines: bool = False) -> str:
    if value is None:
        return ""
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, (bytes, bytearray)):
        value = bytes(value).decode("utf-8", "replace")
    text = str(value).replace("\x00", "")
    if preserve_lines:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = "\n".join(line.strip() for line in text.split("\n"))
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
    else:
        text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def _row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    try:
        return dict(row)
    except Exception:
        return {}


def _row_value(row: dict[str, Any], name: str, default: Any = None) -> Any:
    if name in row:
        return row.get(name)
    lower = name.lower()
    for key, value in row.items():
        if str(key).lower() == lower:
            return value
    return default


def _time_text(value: Any) -> str:
    timestamp = _safe_int(value, 0)
    if timestamp <= 0:
        return ""
    if timestamp > 10_000_000_000:
        timestamp //= 1000
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def _parse_xml(value: Any) -> ET.Element | None:
    text = _text(value, max_len=_MAX_CONTENT_CHARS, preserve_lines=True)
    if not text or _UNSAFE_XML_RE.search(text):
        return None
    try:
        return ET.fromstring(_INVALID_XML_CONTROL_RE.sub("", text))
    except Exception:
        return None


def _node_text(node: ET.Element | None, *paths: str, preserve_lines: bool = False) -> str:
    if node is None:
        return ""
    for path in paths:
        try:
            value = node.findtext(path)
        except Exception:
            value = None
        text = _text(value, preserve_lines=preserve_lines)
        if text:
            return text
    return ""


def _safe_http_url(value: Any) -> str:
    text = _text(value, max_len=2_000)
    return text if text.lower().startswith(("http://", "https://")) else ""


def _parse_location(item: ET.Element) -> dict[str, Any] | None:
    node = item.find("locitem")
    if node is None:
        return None
    latitude = _node_text(node, "lat", "latitude")
    longitude = _node_text(node, "lng", "longitude")
    poiname = _node_text(node, "poiname")
    label = _node_text(node, "label") or poiname
    address = _node_text(node, "address")
    if not any((latitude, longitude, poiname, label, address)):
        return None
    return {
        "latitude": latitude,
        "longitude": longitude,
        "poiname": poiname,
        "label": label,
        "address": address,
    }


def _parse_data_item(item: ET.Element, *, favorite_type: int) -> dict[str, Any]:
    data_type = _safe_int(item.get("datatype") or _node_text(item, "datatype"), 0)
    is_record_item = favorite_type in {14, 18}
    type_labels = _RECORD_DATA_TYPE_LABELS if is_record_item else _DIRECT_DATA_TYPE_LABELS
    render_types = _RECORD_DATA_RENDER_TYPES if is_record_item else _DIRECT_DATA_RENDER_TYPES
    title = _node_text(item, "datatitle", "title")
    description = _node_text(item, "datadesc", "description", preserve_lines=data_type == 1)
    data_format = _node_text(item, "datafmt", "fileext")
    media_extension = data_format.lower().lstrip(".")
    if media_extension in {"mp4", "mov", "m4v", "avi", "mkv", "webm"}:
        type_label = "视频"
        render_type = "video"
    elif media_extension in {"silk", "slk", "amr", "mp3", "m4a", "aac", "wav", "ogg", "opus"}:
        type_label = "语音"
        render_type = "voice"
    else:
        type_label = type_labels.get(data_type, f"类型 {data_type}" if data_type else "附件")
        render_type = render_types.get(data_type, "text")
    full_md5 = _node_text(item, "fullmd5", "md5").lower()
    if not _MD5_RE.fullmatch(full_md5):
        full_md5 = ""
    full_size = _safe_int(_node_text(item, "fullsize", "filesize"), 0)
    thumb_md5 = _node_text(item, "thumbfullmd5", "cdnthumbmd5", "thumbmd5").lower()
    if not _MD5_RE.fullmatch(thumb_md5):
        thumb_md5 = ""
    url = _safe_http_url(
        _node_text(
            item,
            "weburlitem/link",
            "weburlitem/url",
            "url",
            "stream_weburl",
        )
    )
    source_name = _node_text(item, "sourcename", "sourcedisplayname")
    source_username = _node_text(item, "sourceusername", "sourceusrname", "fromusr")
    source_avatar = _safe_http_url(
        _node_text(item, "sourceavatar", "sourceheadurl", "sourceheadimgurl", "avatar")
    )
    source_time = _node_text(item, "sourcetime")
    is_internal = bool(
        favorite_type == 18
        and data_type == 8
        and _INTERNAL_NOTE_FILE_RE.fullmatch(title)
    )
    return {
        "dataId": _text(item.get("dataid"), max_len=180),
        "htmlId": _text(item.get("htmlid"), max_len=180),
        "dataType": data_type,
        "typeLabel": type_label,
        "renderType": render_type,
        "title": title,
        "description": description,
        "dataFormat": data_format,
        "fullSize": full_size,
        "fullMd5": full_md5,
        "thumbMd5": thumb_md5,
        "url": url,
        "duration": _safe_int(
            _node_text(item, "duration", "voicelength", "voiceitem/voicelength", "videoduration"),
            0,
        ),
        "sourceName": source_name,
        "sourceUsername": source_username,
        "sourceAvatar": source_avatar,
        "sourceTime": source_time,
        "location": _parse_location(item),
        "hasRemoteResource": bool(_node_text(item, "cdn_dataurl", "cdn_thumburl")),
        "isInternal": is_internal,
    }


def _merge_non_empty(target: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    for key, value in values.items():
        if value not in (None, "", [], {}):
            target[key] = value
    return target


def _top_level_display_items(
    root: ET.Element | None,
    *,
    favorite_type: int,
    data_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if root is None:
        return data_items

    if favorite_type == 5:
        item = next((row for row in data_items if _safe_int(row.get("dataType"), 0) == 5), None)
        if item is None:
            item = _parse_data_item(ET.Element("dataitem", {"datatype": "5"}), favorite_type=favorite_type)
            data_items.append(item)
        _merge_non_empty(
            item,
            {
                "title": _node_text(root, "weburlitem/pagetitle", "title"),
                "description": _node_text(root, "weburlitem/pagedesc", "desc", preserve_lines=True),
                "url": _safe_http_url(
                    _node_text(root, "weburlitem/clean_url", "weburlitem/link", "source/link", "link")
                ),
                "preview": _safe_http_url(
                    _node_text(root, "weburlitem/thumburl", "weburlitem/coverurl")
                ),
                "linkType": "link",
            },
        )

    if favorite_type == 6:
        location = _parse_location(root)
        if location:
            data_items.append(
                {
                    "dataId": "",
                    "htmlId": "",
                    "dataType": 6,
                    "typeLabel": "位置",
                    "renderType": "location",
                    "title": location.get("poiname") or location.get("label") or "位置",
                    "description": location.get("label") or location.get("address") or "",
                    "dataFormat": "",
                    "fullSize": 0,
                    "fullMd5": "",
                    "thumbMd5": "",
                    "url": "",
                    "duration": 0,
                    "sourceName": "",
                    "sourceTime": "",
                    "location": location,
                    "hasRemoteResource": False,
                    "isInternal": False,
                }
            )

    if favorite_type == 7:
        data_items.append(
            {
                "dataId": "",
                "htmlId": "",
                "dataType": 7,
                "typeLabel": "音乐",
                "renderType": "link",
                "title": _node_text(root, "musicitem/title", "title") or "音乐",
                "description": _node_text(root, "musicitem/desc", "musicitem/singer", "desc"),
                "dataFormat": "",
                "fullSize": 0,
                "fullMd5": "",
                "thumbMd5": "",
                "url": _safe_http_url(_node_text(root, "musicitem/link", "musicitem/url", "source/link")),
                "preview": _safe_http_url(_node_text(root, "musicitem/thumburl", "musicitem/coverurl")),
                "duration": 0,
                "sourceName": _node_text(root, "musicitem/singer"),
                "sourceTime": "",
                "location": None,
                "linkType": "music",
                "hasRemoteResource": False,
                "isInternal": False,
            }
        )

    if favorite_type == 20:
        finder = root.find("finderFeed")
        media = finder.find("mediaList/media") if finder is not None else None
        if finder is not None:
            media_url = _safe_http_url(_node_text(media, "url"))
            preview = _safe_http_url(_node_text(media, "coverUrl", "thumbUrl"))
            finder_username = _node_text(finder, "username")
            object_id = _node_text(finder, "objectId")
            profile_url = (
                "https://channels.weixin.qq.com/web/pages/profile?username=" + finder_username
                if finder_username
                else ""
            )
            data_items.append(
                {
                    "dataId": object_id,
                    "htmlId": "",
                    "dataType": 20,
                    "typeLabel": "视频号",
                    "renderType": "link",
                    "title": _node_text(finder, "desc") or _node_text(root, "title") or "视频号",
                    "description": _node_text(finder, "desc", preserve_lines=True),
                    "dataFormat": "",
                    "fullSize": 0,
                    "fullMd5": "",
                    "thumbMd5": "",
                    "url": media_url or profile_url,
                    "preview": preview,
                    "duration": _safe_int(_node_text(media, "videoPlayDuration"), 0),
                    "sourceName": _node_text(finder, "nickname") or "视频号",
                    "sourceAvatar": _safe_http_url(_node_text(finder, "avatar")),
                    "sourceTime": "",
                    "location": None,
                    "linkType": "finder",
                    "finderUsername": finder_username,
                    "objectId": object_id,
                    "mediaUrl": media_url,
                    "hasRemoteResource": bool(media_url or preview),
                    "isInternal": False,
                }
            )

    return data_items


def _quote_identifier(value: str) -> str:
    return '"' + str(value or "").replace('"', '""') + '"'


def _attach_original_messages(
    *,
    ctx: Any,
    items: list[dict[str, Any]],
    base_url: str,
) -> None:
    targets_by_conversation: dict[str, dict[int, dict[str, Any]]] = {}
    for item in items:
        conversation = _text(item.get("conversationUsername"), max_len=260)
        server_id = _safe_int(item.get("sourceId"), 0)
        if conversation and server_id > 0:
            targets_by_conversation.setdefault(conversation, {})[server_id] = item
    if not targets_by_conversation:
        return

    try:
        realtime = WCDB_REALTIME.ensure_connected(ctx.account_dir)
    except Exception:
        return

    pending = {
        (conversation, server_id)
        for conversation, rows in targets_by_conversation.items()
        for server_id in rows
    }
    message_dir = Path(realtime.db_storage_dir) / "message"
    db_paths = sorted(path for path in message_dir.glob("message_*.db") if path.is_file())
    parsed_by_conversation: dict[str, list[dict[str, Any]]] = {}

    for db_path in db_paths:
        if not pending:
            break
        try:
            with realtime.lock:
                table_rows = _wcdb_exec_query(
                    realtime.handle,
                    kind="message",
                    path=str(db_path),
                    sql="SELECT name FROM sqlite_master WHERE type='table'",
                )
        except Exception:
            continue
        table_map = {
            _text(row.get("name"), max_len=260).lower(): _text(row.get("name"), max_len=260)
            for row in table_rows
            if isinstance(row, dict) and _text(row.get("name"), max_len=260)
        }

        for conversation, server_map in targets_by_conversation.items():
            wanted = sorted(server_id for server_id in server_map if (conversation, server_id) in pending)
            if not wanted:
                continue
            table_name = _resolve_msg_table_name_by_map(table_map, conversation)
            if not table_name:
                continue
            sql = (
                f"SELECT * FROM {_quote_identifier(table_name)} WHERE server_id IN ("
                + ",".join(str(server_id) for server_id in wanted)
                + ")"
            )
            try:
                with realtime.lock:
                    rows = _wcdb_exec_query(
                        realtime.handle,
                        kind="message",
                        path=str(db_path),
                        sql=sql,
                    )
            except Exception:
                continue
            if not rows:
                continue
            normalized_rows = []
            for row in rows:
                normalized = dict(row)
                normalized.setdefault("sender_username", "")
                normalized.setdefault("computed_is_send", 0)
                normalized_rows.append(normalized)

            merged: list[dict[str, Any]] = []
            sender_usernames: list[str] = []
            quote_usernames: list[str] = []
            pat_usernames: set[str] = set()
            try:
                _append_full_messages_from_rows(
                    merged=merged,
                    sender_usernames=sender_usernames,
                    quote_usernames=quote_usernames,
                    pat_usernames=pat_usernames,
                    rows=normalized_rows,
                    db_path=db_path,
                    table_name=table_name,
                    username=conversation,
                    account_dir=ctx.account_dir,
                    is_group=conversation.endswith("@chatroom"),
                    my_rowid=None,
                    resource_conn=None,
                    resource_chat_id=None,
                )
                _postprocess_full_messages(
                    merged=merged,
                    sender_usernames=sender_usernames,
                    quote_usernames=quote_usernames,
                    pat_usernames=pat_usernames,
                    account_dir=ctx.account_dir,
                    username=conversation,
                    base_url=base_url,
                    contact_db_path=ctx.account_dir / "contact.db",
                    head_image_db_path=ctx.account_dir / "head_image.db",
                )
            except Exception:
                continue
            parsed_by_conversation.setdefault(conversation, []).extend(merged)
            for message in merged:
                server_id = _safe_int(message.get("serverId"), 0)
                target = server_map.get(server_id)
                if target is not None:
                    target["originalMessage"] = message
                    pending.discard((conversation, server_id))


def _favorite_text_parts(root: ET.Element | None, data_items: list[dict[str, Any]]) -> list[str]:
    parts: list[str] = []
    for item in data_items:
        if _safe_int(item.get("dataType"), 0) == 1:
            value = _text(item.get("description"), preserve_lines=True)
            if value and value not in parts:
                parts.append(value)
    for value in (
        _node_text(root, "desc", "description", "content", preserve_lines=True),
        _node_text(root, "weburlitem/desc", preserve_lines=True),
    ):
        if value and value not in parts:
            parts.append(value)
    return parts


def _favorite_title(root: ET.Element | None, favorite_type: int, data_items: list[dict[str, Any]]) -> str:
    title = _node_text(root, "title", "favtitle", "weburlitem/title", "musicitem/title")
    if title:
        return title
    if favorite_type != 18:
        for item in data_items:
            item_title = _text(item.get("title"), max_len=300)
            if item_title and not item.get("isInternal"):
                return item_title
    return _FAVORITE_TYPE_LABELS.get(favorite_type, "收藏内容")


def _parse_favorite_row(row: Any, tags: list[dict[str, Any]], *, account_name: str = "") -> dict[str, Any]:
    data = _row_dict(row)
    favorite_type = _safe_int(_row_value(data, "type"), 0)
    root = _parse_xml(_row_value(data, "content"))
    data_items = [
        _parse_data_item(node, favorite_type=favorite_type)
        for node in (root.findall(".//dataitem") if root is not None else [])
    ]
    data_items = _top_level_display_items(root, favorite_type=favorite_type, data_items=data_items)
    text_parts = _favorite_text_parts(root, data_items)
    attachments = [item for item in data_items if item.get("dataType") != 1 and not item.get("isInternal")]
    summary = _text("\n".join(text_parts), max_len=600, preserve_lines=True)
    if not summary:
        summary = next(
            (
                _text(item.get("description") or item.get("title"), max_len=600, preserve_lines=True)
                for item in attachments
                if _text(item.get("description") or item.get("title"), max_len=600)
            ),
            "",
        )

    from_user = _text(
        _row_value(data, "fromusr")
        or _node_text(root, "source/fromusr", "fromusr"),
        max_len=260,
    )
    source_chat = _text(
        _row_value(data, "realchatname")
        or _node_text(root, "source/realchatname", "realchatname"),
        max_len=260,
    )
    to_user = _text(_node_text(root, "source/tousr", "tousr"), max_len=260)
    if from_user.endswith("@chatroom"):
        conversation_username = from_user
        sender_username = source_chat or from_user
    elif to_user.endswith("@chatroom"):
        conversation_username = to_user
        sender_username = source_chat or from_user
    elif account_name and from_user == account_name:
        conversation_username = to_user or source_chat or from_user
        sender_username = from_user
    else:
        conversation_username = from_user or to_user or source_chat
        sender_username = source_chat or from_user or to_user
    source_name = _node_text(root, "source/sourcename", "sourcename")
    update_time = _safe_int(_row_value(data, "update_time"), 0)
    return {
        "localId": _safe_int(_row_value(data, "local_id"), 0),
        "serverId": _safe_int(_row_value(data, "server_id"), 0),
        "type": favorite_type,
        "typeLabel": _FAVORITE_TYPE_LABELS.get(
            favorite_type,
            f"其他类型 {favorite_type}" if favorite_type else "其他收藏",
        ),
        "title": _favorite_title(root, favorite_type, data_items),
        "summary": summary,
        "textBlocks": text_parts,
        "attachments": attachments,
        "displayItems": [item for item in data_items if not item.get("isInternal")],
        "itemCount": len(data_items),
        "updateTime": update_time,
        "updateTimeText": _time_text(update_time),
        "sourceUsername": from_user,
        "sourceChatUsername": source_chat,
        "sourceToUsername": to_user,
        "senderUsername": sender_username,
        "conversationUsername": conversation_username,
        "sourceName": source_name,
        "sourceId": _text(_row_value(data, "source_id"), max_len=260),
        "tags": tags,
        "tagIds": [_safe_int(tag.get("localId"), 0) for tag in tags],
        "syncStatus": _safe_int(_row_value(data, "sync_status"), 0),
        "uploadStatus": _safe_int(_row_value(data, "upload_status"), 0),
        "parsed": root is not None,
    }


def _optional_rows(conn: Any, sql: str) -> list[dict[str, Any]]:
    try:
        return [_row_dict(row) for row in conn.execute(sql).fetchall()]
    except Exception:
        return []


@router.get("/api/favorites/media/voice", summary="读取实时收藏语音")
def get_favorite_voice(server_id: int = Query(..., gt=0), account: Optional[str] = None):
    ctx = resolve_chat_account_context(account)
    try:
        realtime = WCDB_REALTIME.ensure_connected(ctx.account_dir)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"实时语音库不可用：{exc}") from exc

    media_dir = Path(realtime.db_storage_dir) / "message"
    db_names = sorted(path.name for path in media_dir.glob("media_*.db") if path.is_file())
    if not db_names:
        raise HTTPException(status_code=404, detail="实时 media 数据库不存在。")

    voice_data = b""
    for db_name in db_names:
        try:
            with _open_db_source(
                ctx,
                source="realtime",
                db_group="message",
                db_name=db_name,
                decrypted_name=db_name,
            ) as conn:
                row = conn.execute(
                    "SELECT voice_data FROM VoiceInfo "
                    f"WHERE svr_id = {int(server_id)} ORDER BY create_time DESC LIMIT 1"
                ).fetchone()
        except Exception:
            row = None
        if row:
            try:
                voice_data = _coerce_blob_bytes(row[0])
            except Exception:
                voice_data = b""
        if voice_data:
            break

    if not voice_data:
        raise HTTPException(status_code=404, detail="实时语音数据不存在或尚未缓存。")

    payload, extension, media_type = _convert_silk_to_browser_audio(voice_data, preferred_format="mp3")
    if not payload:
        payload, extension, media_type = voice_data, "silk", "application/octet-stream"
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f"inline; filename=favorite_voice_{int(server_id)}.{extension}"},
    )


def _load_tags(conn: Any) -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    tag_rows = _optional_rows(
        conn,
        "SELECT local_id, server_id, name, seq FROM fav_tag_db_item ORDER BY seq ASC, local_id ASC",
    )
    tags: list[dict[str, Any]] = []
    tags_by_local_id: dict[int, dict[str, Any]] = {}
    for row in tag_rows:
        tag = {
            "localId": _safe_int(_row_value(row, "local_id"), 0),
            "serverId": _safe_int(_row_value(row, "server_id"), 0),
            "name": _text(_row_value(row, "name"), max_len=160),
            "seq": _safe_int(_row_value(row, "seq"), 0),
        }
        tags.append(tag)
        if tag["localId"]:
            tags_by_local_id[tag["localId"]] = tag

    bindings = _optional_rows(
        conn,
        "SELECT tag_local_id, tag_server_id, fav_local_id, fav_server_id, op_code "
        "FROM fav_bind_tag_db_item",
    )
    by_favorite: dict[int, list[dict[str, Any]]] = {}
    for row in bindings:
        favorite_id = _safe_int(_row_value(row, "fav_local_id"), 0)
        tag_id = _safe_int(_row_value(row, "tag_local_id"), 0)
        tag = tags_by_local_id.get(tag_id)
        if favorite_id and tag and tag not in by_favorite.setdefault(favorite_id, []):
            by_favorite[favorite_id].append(tag)
    return tags, by_favorite


def _matches_query(item: dict[str, Any], query: str) -> bool:
    needle = _text(query, max_len=300).lower()
    if not needle:
        return True
    haystack = json.dumps(
        {
            "type": item.get("typeLabel"),
            "title": item.get("title"),
            "summary": item.get("summary"),
            "text": item.get("textBlocks"),
            "attachments": item.get("attachments"),
            "source": item.get("sourceName"),
            "sourceContact": item.get("sourceContact"),
            "sourceChatContact": item.get("sourceChatContact"),
            "tags": item.get("tags"),
        },
        ensure_ascii=False,
        default=str,
    ).lower()
    return needle in haystack


@router.get("/api/favorites", summary="获取微信收藏列表")
def list_favorites(
    request: Request,
    account: Optional[str] = None,
    q: str = "",
    kind: str = "all",
    tag_id: int = Query(0, ge=0),
    source: str = Query("realtime", pattern="^(realtime|decrypted)$"),
    limit: int = Query(80, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    ctx = resolve_chat_account_context(account)
    with _open_db_source(
        ctx,
        source=source,
        db_group="favorite",
        db_name="favorite.db",
        decrypted_name="favorite.db",
    ) as conn:
        meta = _source_meta(conn)
        tags, tags_by_favorite = _load_tags(conn)
        try:
            rows = conn.execute(
                "SELECT local_id, server_id, type, update_time, content, source_id, "
                "sync_status, upload_status, fromusr, realchatname "
                "FROM fav_db_item ORDER BY update_time DESC, local_id DESC"
            ).fetchall()
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"favorite.db schema is not supported: {exc}",
            ) from exc

    items = []
    for row in rows:
        row_dict = _row_dict(row)
        local_id = _safe_int(_row_value(row_dict, "local_id"), 0)
        items.append(
            _parse_favorite_row(
                row_dict,
                tags_by_favorite.get(local_id, []),
                account_name=ctx.name,
            )
        )

    usernames = [
        username
        for item in items
        for username in (
            item.get("sourceUsername"),
            item.get("sourceChatUsername"),
            item.get("sourceToUsername"),
            item.get("senderUsername"),
            item.get("conversationUsername"),
        )
        if _text(username, max_len=260)
    ]
    contact_map = _resolve_general_contacts(
        account_dir=ctx.account_dir,
        account_name=ctx.name,
        usernames=usernames,
        base_url=str(request.base_url).rstrip("/"),
    )
    for item in items:
        source_username = _text(item.get("sourceUsername"), max_len=260)
        source_chat = _text(item.get("sourceChatUsername"), max_len=260)
        if source_username and source_username in contact_map:
            item["sourceContact"] = contact_map[source_username]
        if source_chat and source_chat in contact_map:
            item["sourceChatContact"] = contact_map[source_chat]
        sender_username = _text(item.get("senderUsername"), max_len=260)
        conversation_username = _text(item.get("conversationUsername"), max_len=260)
        if sender_username and sender_username in contact_map:
            item["senderContact"] = contact_map[sender_username]
        if conversation_username and conversation_username in contact_map:
            item["conversationContact"] = contact_map[conversation_username]

    _attach_original_messages(
        ctx=ctx,
        items=items,
        base_url=str(request.base_url).rstrip("/"),
    )

    type_counts: dict[str, int] = {}
    for item in items:
        key = str(_safe_int(item.get("type"), 0))
        type_counts[key] = type_counts.get(key, 0) + 1

    kind_norm = _text(kind, max_len=40).lower() or "all"
    if kind_norm != "all":
        try:
            wanted_type = int(kind_norm)
        except Exception:
            wanted_type = -1
        items = [item for item in items if _safe_int(item.get("type"), 0) == wanted_type]
    if tag_id > 0:
        items = [item for item in items if tag_id in (item.get("tagIds") or [])]
    items = [item for item in items if _matches_query(item, q)]

    total = len(items)
    page_items = items[offset:offset + limit]
    return {
        "status": "success",
        "account": ctx.name,
        "total": total,
        "databaseTotal": sum(type_counts.values()),
        "hasMore": offset + limit < total,
        "items": page_items,
        "tags": tags,
        "typeCounts": type_counts,
        **meta,
    }
