from __future__ import annotations

import json
import sqlite3
import asyncio
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlencode

from fastapi import BackgroundTasks, Request

from .. import __version__ as APP_VERSION
from ..chat_export_service import CHAT_EXPORT_MANAGER, get_chat_export_targets_preview
from ..chat_helpers import (
    _iter_message_db_paths,
    _list_decrypted_accounts,
    _quote_ident,
    _resolve_account_dir,
    _resolve_msg_table_name,
)
from ..chat_search_index import get_chat_search_index_status, start_chat_search_index_build
from ..database_filters import list_countable_database_names
from ..session_last_message import build_session_last_message_table, get_session_last_message_status
from ..sns_export_service import SNS_EXPORT_MANAGER
from ..wcdb_realtime import WCDB_REALTIME
from .registry import (
    McpTool,
    McpToolContext,
    McpToolRegistry,
    array_schema,
    bool_schema,
    int_schema,
    object_schema,
    string_schema,
)


MCP_REGISTRY = McpToolRegistry()


def _chat_router():
    from ..routers import chat

    return chat


def _contacts_router():
    from ..routers import chat_contacts

    return chat_contacts


def _sns_router():
    from ..routers import sns

    return sns


def _biz_router():
    from ..routers import biz

    return biz


def _chat_media_router():
    from ..routers import chat_media

    return chat_media


def _account_archive_router():
    from ..routers import account_archive_export

    return account_archive_export


def _wechat_detection_router():
    from ..routers import wechat_detection

    return wechat_detection


def _decrypt_router():
    from ..routers import decrypt

    return decrypt


def _keys_router():
    from ..routers import keys

    return keys


def _media_router():
    from ..routers import media

    return media


def _import_decrypted_router():
    from ..routers import import_decrypted

    return import_decrypted


def _admin_router():
    from ..routers import admin

    return admin


def _system_router():
    from ..routers import system

    return system


def _health_router():
    from ..routers import health

    return health


def _wrapped_service():
    from ..wrapped import service

    return service


def _register(
    name: str,
    description: str,
    input_schema: dict[str, Any],
    handler: Callable[[dict[str, Any], McpToolContext], Any],
    *,
    package: str,
    read_only: bool = True,
    destructive: bool = False,
) -> None:
    MCP_REGISTRY.register(
        McpTool(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=handler,
            package=package,
            annotations={
                "package": package,
                "readOnlyHint": bool(read_only),
                "destructiveHint": bool(destructive),
            },
        )
    )


def _str(args: dict[str, Any], key: str, default: str = "") -> str:
    value = args.get(key, default)
    if value is None:
        return default
    return str(value).strip()


def _opt_str(args: dict[str, Any], key: str) -> Optional[str]:
    value = _str(args, key)
    return value or None


def _int(args: dict[str, Any], key: str, default: int = 0, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        value = int(args.get(key, default))
    except Exception:
        value = int(default)
    if minimum is not None and value < minimum:
        value = minimum
    if maximum is not None and value > maximum:
        value = maximum
    return value


def _opt_int(args: dict[str, Any], key: str) -> Optional[int]:
    value = args.get(key)
    if value is None or value == "":
        return None
    return int(value)


def _bool(args: dict[str, Any], key: str, default: bool = False) -> bool:
    value = args.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _list_str(args: dict[str, Any], key: str) -> list[str]:
    value = args.get(key)
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [p.strip() for p in value.split(",") if p.strip()]
    return []


def _csv(args: dict[str, Any], key: str) -> Optional[str]:
    items = _list_str(args, key)
    return ",".join(items) if items else _opt_str(args, key)


def _clip_text(value: Any, max_chars: int = 800) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _clip_deep(value: Any, *, max_string: int = 1200, max_items: int = 80, depth: int = 0) -> Any:
    if depth > 8:
        return "<truncated>"
    if isinstance(value, str):
        return _clip_text(value, max_string)
    if isinstance(value, bytes):
        return f"<bytes {len(value)}>"
    if isinstance(value, dict):
        return {str(k): _clip_deep(v, max_string=max_string, max_items=max_items, depth=depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        out = [_clip_deep(v, max_string=max_string, max_items=max_items, depth=depth + 1) for v in list(value)[:max_items]]
        if len(value) > max_items:
            out.append({"truncated": True, "remaining": len(value) - max_items})
        return out
    return value


def _download_url(ctx: McpToolContext, path: str) -> str:
    base = ctx.base_url
    if not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}" if base else path


class _JsonRequest:
    def __init__(self, payload: dict[str, Any], base_url: str = "http://127.0.0.1/") -> None:
        self._payload = payload
        self._base_url = base_url

    @property
    def base_url(self) -> str:
        return self._base_url

    async def json(self) -> dict[str, Any]:
        return self._payload


class _LoopbackRequest:
    client = type("_Client", (), {"host": "127.0.0.1"})()


def _request(ctx: McpToolContext, payload: dict[str, Any] | None = None) -> Request | _JsonRequest:
    if payload is None:
        return ctx.request
    return _JsonRequest(payload, base_url=(ctx.base_url + "/") if ctx.base_url else "http://127.0.0.1/")


def _job_payload(job: Any) -> dict[str, Any]:
    if job is None:
        raise ValueError("Job not found.")
    return job.to_public_dict()


def _account_arg(args: dict[str, Any]) -> Optional[str]:
    return _opt_str(args, "account")


def _status(_: dict[str, Any], __: McpToolContext) -> dict[str, Any]:
    accounts = _list_decrypted_accounts()
    warnings: list[str] = []
    if not accounts:
        warnings.append("No decrypted accounts found.")
    return {
        "status": "success",
        "version": APP_VERSION,
        "dbReady": bool(accounts),
        "accounts": accounts,
        "defaultAccount": accounts[0] if accounts else None,
        "toolCount": len(MCP_REGISTRY.tool_names()),
        "packages": sorted({tool.split(".")[1] if tool.startswith("wechat.") and "." in tool else "core" for tool in MCP_REGISTRY.tool_names()}),
        "warnings": warnings,
    }


def _list_accounts(_: dict[str, Any], __: McpToolContext) -> dict[str, Any]:
    accounts = _list_decrypted_accounts()
    return {
        "status": "success" if accounts else "error",
        "accounts": accounts,
        "defaultAccount": accounts[0] if accounts else None,
        "message": "" if accounts else "No decrypted databases found. Please decrypt first.",
    }


def _get_account_info(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    account_dir = _resolve_account_dir(_account_arg(args))
    db_files = list_countable_database_names(account_dir)
    return {
        "status": "success",
        "account": account_dir.name,
        "path": str(account_dir),
        "databaseCount": len(db_files),
        "databases": db_files,
        "hasSnsDb": (account_dir / "sns.db").exists(),
        "messageDbCount": len(_iter_message_db_paths(account_dir)),
    }


def _wechat_detection(args: dict[str, Any], _: McpToolContext) -> Any:
    return _wechat_detection_router().detect_wechat_detailed(_opt_str(args, "data_root_path"))


async def _current_wechat_account(args: dict[str, Any], _: McpToolContext) -> Any:
    return await _wechat_detection_router().detect_current_account(_opt_str(args, "data_root_path"))


async def _wechat_runtime_status(_: dict[str, Any], __: McpToolContext) -> Any:
    return await _wechat_detection_router().check_wechat_status()


def _list_contacts(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    result = _contacts_router().list_chat_contacts(
        _request(ctx),
        account=_account_arg(args),
        keyword=_opt_str(args, "keyword") or _opt_str(args, "query"),
        include_friends=_bool(args, "include_friends", True),
        include_groups=_bool(args, "include_groups", True),
        include_officials=_bool(args, "include_officials", True),
    )
    contacts = list(result.get("contacts") or [])
    limit = _int(args, "limit", 50, minimum=1, maximum=200)
    offset = _int(args, "offset", 0, minimum=0)
    page = contacts[offset : offset + limit]
    return {**result, "contacts": _clip_deep(page), "offset": offset, "limit": limit, "hasMore": offset + limit < len(contacts)}


def _resolve_contact(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    query = _str(args, "query")
    if not query:
        raise ValueError("query is required.")
    base = _list_contacts({**args, "keyword": query, "limit": _int(args, "limit", 10, minimum=1, maximum=50)}, ctx)
    candidates = []
    q_lower = query.lower()
    for item in list(base.get("contacts") or []):
        hay = " ".join(str(item.get(k) or "") for k in ("username", "remark", "nickname", "name", "displayName", "alias")).lower()
        score = 0
        if query in hay:
            score += 60
        if hay.startswith(q_lower):
            score += 20
        if str(item.get("username") or "") == query:
            score += 30
        candidates.append({**item, "confidence": min(100, score or 20)})
    candidates.sort(key=lambda x: int(x.get("confidence") or 0), reverse=True)
    return {"status": "success", "query": query, "count": len(candidates), "candidates": _clip_deep(candidates, max_items=50)}


def _export_contacts(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    contact_types_raw = args.get("contact_types")
    contact_types = contact_types_raw if isinstance(contact_types_raw, dict) else {}
    merged_flags = {**contact_types, **args}
    contacts_router = _contacts_router()
    req = contacts_router.ContactExportRequest(
        account=_account_arg(args),
        output_dir=_str(args, "output_dir"),
        format=_str(args, "format", "json") or "json",
        include_avatar_link=_bool(args, "include_avatar_link", True),
        contact_types=contacts_router.ContactTypeFilter(
            friends=_bool(merged_flags, "friends", True),
            groups=_bool(merged_flags, "groups", True),
            officials=_bool(merged_flags, "officials", True),
        ),
        keyword=_opt_str(args, "keyword") or _opt_str(args, "query"),
    )
    return contacts_router.export_chat_contacts(_request(ctx), req)


def _list_sessions(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    result = _chat_router().list_chat_sessions(
        _request(ctx),
        account=_account_arg(args),
        limit=_int(args, "limit", 50, minimum=1, maximum=200),
        include_hidden=_bool(args, "include_hidden", False),
        include_official=_bool(args, "include_official", False),
        preview=_str(args, "preview", "latest") or "latest",
        source=_opt_str(args, "source"),
    )
    items = list(result.get("sessions") or result.get("items") or [])
    query = (_opt_str(args, "query") or _opt_str(args, "keyword") or "").lower()
    if query:
        items = [
            item
            for item in items
            if query in " ".join(str(item.get(k) or "") for k in ("username", "name", "remark", "nickname", "displayName", "lastMessage")).lower()
        ]
    offset = _int(args, "offset", 0, minimum=0)
    limit = _int(args, "limit", 50, minimum=1, maximum=200)
    return {**result, "sessions": _clip_deep(items[offset : offset + limit]), "offset": offset, "limit": limit, "hasMore": offset + limit < len(items)}


def _resolve_session(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    query = _str(args, "query")
    if not query:
        raise ValueError("query is required.")
    result = _list_sessions({**args, "query": query, "limit": _int(args, "limit", 10, minimum=1, maximum=50)}, ctx)
    candidates = []
    for item in list(result.get("sessions") or []):
        hay = " ".join(str(item.get(k) or "") for k in ("username", "name", "remark", "nickname", "displayName", "lastMessage")).lower()
        score = 20
        if query.lower() in hay:
            score += 60
        if str(item.get("username") or "") == query:
            score += 30
        candidates.append({**item, "confidence": min(100, score)})
    candidates.sort(key=lambda x: int(x.get("confidence") or 0), reverse=True)
    return {"status": "success", "query": query, "count": len(candidates), "candidates": _clip_deep(candidates, max_items=50)}


def _list_messages(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    username = _str(args, "username") or _str(args, "session_id")
    if not username:
        raise ValueError("username is required.")
    result = _chat_router().list_chat_messages(
        _request(ctx),
        username=username,
        account=_account_arg(args),
        limit=_int(args, "limit", 30, minimum=1, maximum=100),
        offset=_int(args, "offset", 0, minimum=0),
        order=_str(args, "order", "asc") or "asc",
        render_types=_opt_str(args, "render_types"),
        source=_opt_str(args, "source"),
    )
    return _clip_deep(result, max_items=120)


async def _search_messages(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    query = _str(args, "query") or _str(args, "q")
    if not query:
        raise ValueError("query is required.")
    result = await _chat_router().search_chat_messages(
        _request(ctx),
        q=query,
        account=_account_arg(args),
        username=_opt_str(args, "username") or _opt_str(args, "session_id"),
        sender=_opt_str(args, "sender"),
        session_type=_opt_str(args, "session_type"),
        limit=_int(args, "limit", 20, minimum=1, maximum=100),
        offset=_int(args, "offset", 0, minimum=0),
        start_time=_opt_int(args, "start_time"),
        end_time=_opt_int(args, "end_time"),
        render_types=_opt_str(args, "render_types"),
        include_hidden=_bool(args, "include_hidden", False),
        include_official=_bool(args, "include_official", False),
    )
    return _clip_deep(result, max_items=80)


async def _search_index_senders(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    result = await _chat_router().chat_search_index_senders(
        account=_account_arg(args),
        username=_opt_str(args, "username") or _opt_str(args, "session_id"),
        session_type=_opt_str(args, "session_type"),
        message_q=_opt_str(args, "message_q") or _opt_str(args, "query"),
        limit=_int(args, "limit", 200, minimum=1, maximum=2000),
        q=_opt_str(args, "sender_q") or _opt_str(args, "q"),
        start_time=_opt_int(args, "start_time"),
        end_time=_opt_int(args, "end_time"),
        render_types=_opt_str(args, "render_types"),
        include_hidden=_bool(args, "include_hidden", False),
        include_official=_bool(args, "include_official", False),
    )
    return _clip_deep(result, max_items=120)


async def _messages_around(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    username = _str(args, "username") or _str(args, "session_id")
    anchor_id = _str(args, "anchor_id") or _str(args, "message_id")
    if not username or not anchor_id:
        raise ValueError("username and anchor_id are required.")
    return await _chat_router().get_chat_messages_around(
        _request(ctx),
        username=username,
        anchor_id=anchor_id,
        account=_account_arg(args),
        before=_int(args, "before", 10, minimum=0, maximum=50),
        after=_int(args, "after", 10, minimum=0, maximum=50),
    )


def _message_anchor(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return _chat_router().get_chat_message_anchor(
        username=_str(args, "username"),
        kind=_str(args, "kind", "day"),
        account=_account_arg(args),
        date=_opt_str(args, "date"),
    )


def _message_daily_counts(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return _chat_router().get_chat_message_daily_counts(
        username=_str(args, "username"),
        year=_int(args, "year"),
        month=_int(args, "month"),
        account=_account_arg(args),
    )


def _message_raw(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return _clip_deep(
        _chat_router().get_chat_message_raw(
            account=_account_arg(args),
            username=_str(args, "username"),
            message_id=_str(args, "message_id"),
        ),
        max_string=1600,
        max_items=120,
    )


async def _resolve_chat_history(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    server_id = _opt_int(args, "server_id")
    if not server_id:
        raise ValueError("server_id is required.")
    return await _chat_router().resolve_nested_chat_history(
        _request(ctx),
        server_id=max(1, int(server_id)),
        account=_account_arg(args),
    )


async def _resolve_app_message(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    server_id = _opt_int(args, "server_id")
    if not server_id:
        raise ValueError("server_id is required.")
    return await _chat_router().resolve_app_message(
        _request(ctx),
        server_id=max(1, int(server_id)),
        account=_account_arg(args),
    )


def _search_index_status(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return get_chat_search_index_status(_resolve_account_dir(_account_arg(args)))


def _build_search_index(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return start_chat_search_index_build(_resolve_account_dir(_account_arg(args)), rebuild=_bool(args, "rebuild", False))


def _session_last_message_status(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return get_session_last_message_status(_resolve_account_dir(_account_arg(args)))


def _build_session_last_message(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return build_session_last_message_table(
        _resolve_account_dir(_account_arg(args)),
        rebuild=_bool(args, "rebuild", False),
        include_hidden=_bool(args, "include_hidden", True),
        include_official=_bool(args, "include_official", True),
    )


def _chat_realtime_status(args: dict[str, Any], _: McpToolContext) -> Any:
    return _chat_router().get_chat_realtime_status(account=_account_arg(args))


def _chat_realtime_sync(args: dict[str, Any], ctx: McpToolContext) -> Any:
    username = _str(args, "username") or _str(args, "session_id")
    if not username:
        raise ValueError("username is required.")
    return _chat_router().sync_chat_realtime_messages(
        _request(ctx),
        account=_account_arg(args),
        username=username,
        max_scan=_int(args, "max_scan", _int(args, "limit", 600), minimum=50, maximum=5000),
        backfill_limit=_int(args, "backfill_limit", 200, minimum=0, maximum=5000),
    )


def _chat_realtime_sync_all(args: dict[str, Any], ctx: McpToolContext) -> Any:
    return _chat_router().sync_chat_realtime_messages_all(
        _request(ctx),
        account=_account_arg(args),
        max_scan=_int(args, "max_scan", _int(args, "limit_per_session", 200), minimum=50, maximum=5000),
        priority_username=_opt_str(args, "priority_username"),
        priority_max_scan=_int(args, "priority_max_scan", 600, minimum=50, maximum=5000),
        include_hidden=_bool(args, "include_hidden", True),
        include_official=_bool(args, "include_official", True),
        only_official=_bool(args, "only_official", False),
        backfill_limit=_int(args, "backfill_limit", 200, minimum=0, maximum=5000),
    )


def _edit_status(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return _chat_router().get_chat_edit_status(account=_account_arg(args), username=_str(args, "username"), message_id=_str(args, "message_id"))


def _list_edited_sessions(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    return _chat_router().list_chat_edited_sessions(_request(ctx), account=_account_arg(args))


def _list_edited_messages(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    return _chat_router().list_chat_edited_messages(_request(ctx), username=_str(args, "username"), account=_account_arg(args))


async def _edit_message(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    return await _chat_router().edit_chat_message(_request(ctx, args))


async def _repair_sender(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    return await _chat_router().repair_chat_message_sender(_request(ctx, args))


async def _flip_direction(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    return await _chat_router().flip_chat_message_direction(_request(ctx, args))


async def _reset_message_edit(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    return await _chat_router().reset_chat_edited_message(_request(ctx, args))


async def _reset_session_edits(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    return await _chat_router().reset_chat_edited_session(_request(ctx, args))


def _sns_self_info(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return _sns_router().api_sns_self_info(account=_account_arg(args))


def _sns_timeline(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return _clip_deep(
        _sns_router().list_sns_timeline(
            account=_account_arg(args),
            limit=_int(args, "limit", 10, minimum=1, maximum=50),
            offset=_int(args, "offset", 0, minimum=0),
            usernames=_csv(args, "usernames"),
            keyword=_opt_str(args, "keyword") or _opt_str(args, "query"),
        ),
        max_items=80,
    )


def _sns_users(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    result = _sns_router().list_sns_users(
        account=_account_arg(args),
        keyword=_opt_str(args, "keyword") or _opt_str(args, "query"),
        limit=_int(args, "limit", 50, minimum=1, maximum=500),
    )
    return _clip_deep(result, max_items=100)


def _sns_sync_latest(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return _sns_router().sync_sns_realtime_timeline_latest(
        account=_account_arg(args),
        max_scan=_int(args, "max_scan", 200, minimum=1, maximum=2000),
        force=_int(args, "force", 0),
    )


def _sns_media_url(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    post_id = _opt_str(args, "post_id") or _opt_str(args, "tid")
    params = {
        k: v
        for k, v in {
            "account": _account_arg(args),
            "post_id": post_id,
            "media_id": _opt_str(args, "media_id"),
            "create_time": _opt_int(args, "create_time"),
            "width": _opt_int(args, "width"),
            "height": _opt_int(args, "height"),
            "total_size": _opt_int(args, "total_size"),
            "idx": _opt_int(args, "idx"),
            "post_type": _opt_int(args, "post_type"),
            "media_type": _opt_int(args, "media_type"),
            "md5": _opt_str(args, "md5"),
            "token": _opt_str(args, "token"),
            "url": _opt_str(args, "url"),
            "key": _opt_str(args, "key"),
            "use_cache": _opt_int(args, "use_cache"),
        }.items()
        if v not in (None, "")
    }
    query = urlencode(params)
    return {"status": "success", "url": _download_url(ctx, f"/api/sns/media?{query}"), "params": params}


def _sns_article_thumb_url(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    url = _str(args, "url")
    if not url:
        raise ValueError("url is required.")
    query = urlencode({"url": url})
    return {"status": "success", "url": _download_url(ctx, f"/api/sns/article_thumb?{query}"), "params": {"url": url}}


def _sns_video_remote_url(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    params = {
        k: v
        for k, v in {
            "account": _account_arg(args),
            "url": _opt_str(args, "url"),
            "token": _opt_str(args, "token"),
            "key": _opt_str(args, "key"),
            "use_cache": _opt_int(args, "use_cache"),
        }.items()
        if v not in (None, "")
    }
    query = urlencode(params)
    return {"status": "success", "url": _download_url(ctx, f"/api/sns/video_remote?{query}"), "params": params}


def _sns_video_url(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    params = {
        k: v
        for k, v in {
            "account": _account_arg(args),
            "post_id": _opt_str(args, "post_id") or _opt_str(args, "tid"),
            "media_id": _opt_str(args, "media_id"),
        }.items()
        if v not in (None, "")
    }
    query = urlencode(params)
    return {"status": "success", "url": _download_url(ctx, f"/api/sns/video?{query}"), "params": params}


def _biz_accounts(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return _clip_deep(_biz_router().get_biz_account_list(account=_account_arg(args)), max_items=100)


def _biz_messages(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return _clip_deep(
        _biz_router().get_biz_messages(
            username=_str(args, "username"),
            account=_account_arg(args),
            limit=_int(args, "limit", 30, minimum=1, maximum=100),
            offset=_int(args, "offset", 0, minimum=0),
        ),
        max_items=100,
    )


def _pay_records(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return _clip_deep(
        _biz_router().get_wechat_pay_records(
            account=_account_arg(args),
            limit=_int(args, "limit", 30, minimum=1, maximum=100),
            offset=_int(args, "offset", 0, minimum=0),
        ),
        max_items=100,
    )


def _wrapped_meta(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return _wrapped_service().build_wrapped_annual_meta(account=_account_arg(args), year=_opt_int(args, "year"), refresh=_bool(args, "refresh", False))


def _wrapped_card(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return _clip_deep(
        _wrapped_service().build_wrapped_annual_card(
            account=_account_arg(args),
            year=_opt_int(args, "year"),
            card_id=_int(args, "card_id", minimum=0),
            refresh=_bool(args, "refresh", False),
        ),
        max_items=80,
    )


def _wrapped_annual(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return _clip_deep(_wrapped_service().build_wrapped_annual_response(account=_account_arg(args), year=_opt_int(args, "year"), refresh=_bool(args, "refresh", False)), max_items=80)


def _chat_export_targets(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    return _clip_deep(
        get_chat_export_targets_preview(
            account=_account_arg(args),
            include_hidden=_bool(args, "include_hidden", True),
            include_official=_bool(args, "include_official", False),
            base_url=ctx.base_url,
        ),
        max_items=120,
    )


def _create_chat_export(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    job = CHAT_EXPORT_MANAGER.create_job(
        account=_account_arg(args),
        scope=_str(args, "scope", "selected") or "selected",
        usernames=_list_str(args, "usernames"),
        export_format=_str(args, "format", "json") or "json",
        start_time=_opt_int(args, "start_time"),
        end_time=_opt_int(args, "end_time"),
        include_hidden=_bool(args, "include_hidden", False),
        include_official=_bool(args, "include_official", False),
        include_media=_bool(args, "include_media", True),
        media_kinds=_list_str(args, "media_kinds") or ["image", "emoji", "video", "video_thumb", "voice", "file"],
        message_types=_list_str(args, "message_types"),
        output_dir=_opt_str(args, "output_dir"),
        allow_process_key_extract=_bool(args, "allow_process_key_extract", False),
        download_remote_media=_bool(args, "download_remote_media", False),
        html_page_size=_int(args, "html_page_size", 1000, minimum=0, maximum=10000),
        privacy_mode=_bool(args, "privacy_mode", False),
        file_name=_opt_str(args, "file_name"),
    )
    return {"status": "success", "job": _job_payload(job)}


def _list_chat_exports(_: dict[str, Any], __: McpToolContext) -> dict[str, Any]:
    jobs = [j.to_public_dict() for j in CHAT_EXPORT_MANAGER.list_jobs()]
    jobs.sort(key=lambda x: int(x.get("createdAt") or 0), reverse=True)
    return {"status": "success", "jobs": jobs}


def _get_chat_export(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return {"status": "success", "job": _job_payload(CHAT_EXPORT_MANAGER.get_job(_str(args, "export_id")))}


def _cancel_chat_export(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    ok = CHAT_EXPORT_MANAGER.cancel_job(_str(args, "export_id"))
    if not ok:
        raise ValueError("Export not found.")
    return {"status": "success"}


def _download_chat_export(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    export_id = _str(args, "export_id")
    job = CHAT_EXPORT_MANAGER.get_job(export_id)
    if not job:
        raise ValueError("Export not found.")
    return {
        "status": "success",
        "ready": bool(job.zip_path and job.zip_path.exists()),
        "job": job.to_public_dict(),
        "downloadUrl": _download_url(ctx, f"/api/chat/exports/{export_id}/download"),
    }


def _create_sns_export(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    job = SNS_EXPORT_MANAGER.create_job(
        account=_account_arg(args),
        scope=_str(args, "scope", "selected") or "selected",
        usernames=_list_str(args, "usernames"),
        export_format=_str(args, "format", "html") or "html",
        use_cache=_bool(args, "use_cache", True),
        output_dir=_opt_str(args, "output_dir"),
        file_name=_opt_str(args, "file_name"),
    )
    return {"status": "success", "job": _job_payload(job)}


def _list_sns_exports(_: dict[str, Any], __: McpToolContext) -> dict[str, Any]:
    jobs = [j.to_public_dict() for j in SNS_EXPORT_MANAGER.list_jobs()]
    jobs.sort(key=lambda x: int(x.get("createdAt") or 0), reverse=True)
    return {"status": "success", "jobs": jobs}


def _get_sns_export(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return {"status": "success", "job": _job_payload(SNS_EXPORT_MANAGER.get_job(_str(args, "export_id")))}


def _cancel_sns_export(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    ok = SNS_EXPORT_MANAGER.cancel_job(_str(args, "export_id"))
    if not ok:
        raise ValueError("Export not found.")
    return {"status": "success"}


def _download_sns_export(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    export_id = _str(args, "export_id")
    job = SNS_EXPORT_MANAGER.get_job(export_id)
    if not job:
        raise ValueError("Export not found.")
    return {
        "status": "success",
        "ready": bool(job.zip_path and job.zip_path.exists()),
        "job": job.to_public_dict(),
        "downloadUrl": _download_url(ctx, f"/api/sns/exports/{export_id}/download"),
    }


async def _create_account_archive(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    account_archive_router = _account_archive_router()
    req = account_archive_router.AccountArchiveExportRequest(
        account=_account_arg(args),
        output_dir=_opt_str(args, "output_dir"),
        include_databases=_bool(args, "include_databases", True),
        include_resources=_bool(args, "include_resources", True),
        file_name=_opt_str(args, "file_name"),
    )
    return await account_archive_router.export_account_archive(req)


async def _get_account_archive(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return await _account_archive_router().get_account_archive_export(_str(args, "export_id"))


async def _cancel_account_archive(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return await _account_archive_router().cancel_account_archive_export(_str(args, "export_id"))


async def _download_account_archive(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    result = await _account_archive_router().get_account_archive_export(_str(args, "export_id"))
    job = dict(result.get("job") or {})
    zip_path = str(job.get("zipPath") or "").strip()
    download_url = ""
    if zip_path:
        download_url = _download_url(ctx, f"/api/account/archive_export/download?{urlencode({'path': zip_path})}")
    return {
        "status": "success",
        "ready": bool(zip_path and Path(zip_path).exists()),
        "job": job,
        "downloadUrl": download_url,
    }


def _media_url(path: str, args: dict[str, Any], ctx: McpToolContext, keys: list[str]) -> dict[str, Any]:
    if "msg_svr_id" in args and "server_id" not in args:
        args = {**args, "server_id": args.get("msg_svr_id")}
    params = {key: args[key] for key in keys if key in args and args[key] not in (None, "")}
    query = urlencode(params)
    return {"status": "success", "url": _download_url(ctx, f"{path}?{query}"), "params": params}


def _url_result(ctx: McpToolContext, path: str, params: dict[str, Any] | None = None, *, kind: str = "url") -> dict[str, Any]:
    clean = {k: v for k, v in dict(params or {}).items() if v not in (None, "")}
    query = urlencode(clean)
    suffix = f"?{query}" if query else ""
    return {"status": "success", kind: _download_url(ctx, f"{path}{suffix}"), "params": clean}


async def _api_root(_: dict[str, Any], __: McpToolContext) -> dict[str, Any]:
    return await _health_router().api_root()


async def _health_check(_: dict[str, Any], __: McpToolContext) -> dict[str, Any]:
    return await _health_router().health_check()


async def _decrypt_databases(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    decrypt_router = _decrypt_router()
    req = decrypt_router.DecryptRequest(
        key=_str(args, "key"),
        db_storage_path=_str(args, "db_storage_path"),
    )
    return await decrypt_router.decrypt_databases(req)


def _decrypt_stream_url(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    return _url_result(
        ctx,
        "/api/decrypt_stream",
        {"key": _str(args, "key"), "db_storage_path": _str(args, "db_storage_path")},
        kind="streamUrl",
    )


async def _get_saved_keys(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return await _keys_router().get_saved_keys(
        account=_account_arg(args),
        db_storage_path=_opt_str(args, "db_storage_path"),
        wxid_dir=_opt_str(args, "wxid_dir"),
    )


async def _get_wechat_db_key(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return await _keys_router().get_wechat_db_key(wechat_install_path=_opt_str(args, "wechat_install_path"))


async def _get_image_key(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return await _keys_router().get_image_key(
        account=_account_arg(args),
        db_storage_path=_opt_str(args, "db_storage_path"),
        wxid_dir=_opt_str(args, "wxid_dir"),
    )


async def _save_media_keys(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    media_router = _media_router()
    req = media_router.MediaKeysSaveRequest(
        account=_account_arg(args),
        xor_key=_str(args, "xor_key"),
        aes_key=_opt_str(args, "aes_key"),
    )
    return await media_router.save_media_keys_api(req)


async def _decrypt_all_media(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    media_router = _media_router()
    req = media_router.MediaDecryptRequest(
        account=_account_arg(args),
        xor_key=_opt_str(args, "xor_key"),
        aes_key=_opt_str(args, "aes_key"),
    )
    return await media_router.decrypt_all_media(req)


def _decrypt_all_media_stream_url(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    return _url_result(
        ctx,
        "/api/media/decrypt_all_stream",
        {
            "account": _account_arg(args),
            "xor_key": _opt_str(args, "xor_key"),
            "aes_key": _opt_str(args, "aes_key"),
            "concurrency": _int(args, "concurrency", 10, minimum=1, maximum=64),
        },
        kind="streamUrl",
    )


def _download_all_emojis_stream_url(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    return _url_result(
        ctx,
        "/api/media/emoji/download_all_stream",
        {
            "account": _account_arg(args),
            "force": _bool(args, "force", False),
            "concurrency": _int(args, "concurrency", 20, minimum=1, maximum=100),
        },
        kind="streamUrl",
    )


def _decrypted_media_resource_url(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    md5 = _str(args, "md5").lower()
    if len(md5) != 32:
        raise ValueError("md5 must be 32 characters.")
    return _url_result(ctx, f"/api/media/resource/{md5}", {"account": _account_arg(args)}, kind="url")


async def _import_preview(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    import_router = _import_decrypted_router()
    return await import_router.preview_import(import_router.ImportRequest(import_path=_str(args, "import_path")))


async def _import_cancel(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return await _import_decrypted_router().cancel_import_decrypted(job_id=_str(args, "job_id"))


def _import_stream_url(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    return _url_result(
        ctx,
        "/api/import_decrypted",
        {"import_path": _str(args, "import_path"), "job_id": _opt_str(args, "job_id")},
        kind="streamUrl",
    )


async def _admin_log_file(_: dict[str, Any], __: McpToolContext) -> dict[str, Any]:
    return await _admin_router().get_backend_log_file()


def _admin_open_log_file(_: dict[str, Any], __: McpToolContext) -> dict[str, Any]:
    admin_router = _admin_router()
    log_file = admin_router._get_current_log_file_path()
    admin_router._open_path_with_default_app(log_file)
    return {"status": "success", "path": str(log_file), "exists": log_file.exists()}


async def _admin_log_frontend_error(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return await _admin_router().log_frontend_server_error(args)


async def _admin_port(_: dict[str, Any], __: McpToolContext) -> dict[str, Any]:
    return await _admin_router().get_backend_port()


async def _admin_mcp_access(_: dict[str, Any], __: McpToolContext) -> dict[str, Any]:
    return await _admin_router().get_mcp_access()


async def _admin_set_port_setting(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    admin_router = _admin_router()
    port = _int(args, "port", 0, minimum=1, maximum=65535)
    current_port, source = admin_router.read_effective_backend_port(default=admin_router.DEFAULT_BACKEND_PORT)
    admin_router.write_backend_port_setting(port)
    env_file = admin_router.write_backend_port_env_file(port)
    return {
        "status": "success",
        "changed": int(current_port) != int(port),
        "port": port,
        "previousPort": int(current_port),
        "previousSource": source,
        "defaultPort": admin_router.DEFAULT_BACKEND_PORT,
        "restartRequired": int(current_port) != int(port),
        "envFile": str(env_file) if env_file else None,
    }


async def _admin_set_port_and_restart(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    admin_router = _admin_router()
    port = _int(args, "port", 0, minimum=1, maximum=65535)
    background_tasks = BackgroundTasks()
    result = await admin_router.set_backend_port({"port": port}, _LoopbackRequest(), background_tasks)
    try:
        if bool(result.get("changed")):
            asyncio.create_task(background_tasks())
            result["restartScheduled"] = True
    except Exception:
        result["restartScheduled"] = False
    return result


async def _admin_set_mcp_access(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    admin_router = _admin_router()
    enabled = _bool(args, "enabled", False)
    background_tasks = BackgroundTasks()
    result = await admin_router.set_mcp_access({"enabled": enabled}, _LoopbackRequest(), background_tasks)
    try:
        if bool(result.get("changed")):
            asyncio.create_task(background_tasks())
            result["restartScheduled"] = True
    except Exception:
        result["restartScheduled"] = False
    return result


async def _img_helper_status(_: dict[str, Any], __: McpToolContext) -> dict[str, Any]:
    return await _system_router().get_img_helper_status()


async def _img_helper_toggle(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    system_router = _system_router()
    return await system_router.toggle_img_helper(system_router.ImgHelperToggleRequest(enabled=_bool(args, "enabled", False)))


async def _pick_directory(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return await _system_router().pick_directory(
        title=_str(args, "title", "请选择目录") or "请选择目录",
        initial_dir=_str(args, "initial_dir"),
    )


def _chat_proxy_image_url(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    url = _str(args, "url")
    if not url:
        raise ValueError("url is required.")
    return _url_result(ctx, "/api/chat/media/proxy_image", {"url": url}, kind="url")


def _chat_favicon_url(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    url = _str(args, "url")
    if not url:
        raise ValueError("url is required.")
    return _url_result(ctx, "/api/chat/media/favicon", {"url": url}, kind="url")


def _biz_proxy_image_url(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    url = _str(args, "url")
    if not url:
        raise ValueError("url is required.")
    return _url_result(ctx, "/api/biz/proxy_image", {"url": url}, kind="url")


def _chat_export_events_url(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    export_id = _str(args, "export_id")
    if not export_id:
        raise ValueError("export_id is required.")
    return {"status": "success", "streamUrl": _download_url(ctx, f"/api/chat/exports/{export_id}/events"), "exportId": export_id}


def _moments_export_events_url(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    export_id = _str(args, "export_id")
    if not export_id:
        raise ValueError("export_id is required.")
    return {"status": "success", "streamUrl": _download_url(ctx, f"/api/sns/exports/{export_id}/events"), "exportId": export_id}


def _chat_realtime_events_url(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    return _url_result(
        ctx,
        "/api/chat/realtime/stream",
        {
            "account": _account_arg(args),
            "interval_ms": _int(args, "interval_ms", 500, minimum=100, maximum=5000),
        },
        kind="streamUrl",
    )


def _delete_account_data(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return _chat_router().delete_chat_account(account=_str(args, "account"))


async def _open_chat_media_folder(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    return await _chat_media_router().open_chat_media_folder(
        kind=_str(args, "kind"),
        md5=_opt_str(args, "md5"),
        file_id=_opt_str(args, "file_id"),
        server_id=_opt_int(args, "server_id") or _opt_int(args, "msg_svr_id"),
        account=_account_arg(args),
        username=_opt_str(args, "username") or _opt_str(args, "session_id"),
    )


def _safe_call(label: str, func: Callable[[], Any]) -> dict[str, Any]:
    try:
        return {"ok": True, "data": func()}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "section": label}


def _mobile_home_snapshot(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    account = _account_arg(args)
    session_limit = _int(args, "session_limit", 20, minimum=1, maximum=80)
    moments_limit = _int(args, "moments_limit", 6, minimum=0, maximum=30)
    include_moments = _bool(args, "include_moments", True)
    include_official = _bool(args, "include_official", False)
    include_hidden = _bool(args, "include_hidden", False)

    status = _status({}, ctx)
    payload: dict[str, Any] = {
        "status": "success",
        "service": status,
        "accounts": _list_accounts({}, ctx),
        "accountInfo": None,
        "sessions": None,
        "moments": None,
        "realtime": None,
        "indexes": None,
        "warnings": [],
    }

    account_info = _safe_call("accountInfo", lambda: _get_account_info({"account": account} if account else {}, ctx))
    if account_info["ok"]:
        payload["accountInfo"] = account_info["data"]
    else:
        payload["warnings"].append(account_info)

    sessions = _safe_call(
        "sessions",
        lambda: _list_sessions(
            {
                "account": account,
                "limit": session_limit,
                "offset": 0,
                "include_hidden": include_hidden,
                "include_official": include_official,
                "preview": _str(args, "preview", "latest") or "latest",
            },
            ctx,
        ),
    )
    if sessions["ok"]:
        payload["sessions"] = sessions["data"]
    else:
        payload["warnings"].append(sessions)

    if include_moments and moments_limit > 0:
        moments = _safe_call("moments", lambda: _sns_timeline({"account": account, "limit": moments_limit, "offset": 0}, ctx))
        if moments["ok"]:
            payload["moments"] = moments["data"]
        else:
            payload["warnings"].append(moments)

    realtime = _safe_call("realtime", lambda: _chat_realtime_status({"account": account}, ctx))
    if realtime["ok"]:
        payload["realtime"] = realtime["data"]
    else:
        payload["warnings"].append(realtime)

    indexes = _safe_call(
        "indexes",
        lambda: {
            "searchIndex": _search_index_status({"account": account}, ctx),
            "sessionLastMessage": _session_last_message_status({"account": account}, ctx),
        },
    )
    if indexes["ok"]:
        payload["indexes"] = indexes["data"]
    else:
        payload["warnings"].append(indexes)

    return _clip_deep(payload, max_items=120)


async def _mobile_search_context(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    query = _str(args, "query") or _str(args, "q")
    if not query:
        raise ValueError("query is required.")
    account = _account_arg(args)
    limit = _int(args, "limit", 10, minimum=1, maximum=50)
    include_moments = _bool(args, "include_moments", True)
    include_contacts = _bool(args, "include_contacts", True)

    payload: dict[str, Any] = {
        "status": "success",
        "query": query,
        "messages": None,
        "sessions": None,
        "contacts": None,
        "moments": None,
        "warnings": [],
    }

    messages = _safe_call("messages", lambda: None)
    try:
        messages["data"] = await _search_messages({"account": account, "query": query, "limit": limit, "offset": _int(args, "offset", 0, minimum=0)}, ctx)
        messages["ok"] = True
    except Exception as exc:
        messages = {"ok": False, "error": str(exc), "section": "messages"}
    if messages["ok"]:
        payload["messages"] = messages["data"]
    else:
        payload["warnings"].append(messages)

    sessions = _safe_call("sessions", lambda: _resolve_session({"account": account, "query": query, "limit": limit}, ctx))
    if sessions["ok"]:
        payload["sessions"] = sessions["data"]
    else:
        payload["warnings"].append(sessions)

    if include_contacts:
        contacts = _safe_call("contacts", lambda: _resolve_contact({"account": account, "query": query, "limit": limit}, ctx))
        if contacts["ok"]:
            payload["contacts"] = contacts["data"]
        else:
            payload["warnings"].append(contacts)

    if include_moments:
        moments = _safe_call("moments", lambda: _sns_timeline({"account": account, "query": query, "limit": limit, "offset": 0}, ctx))
        if moments["ok"]:
            payload["moments"] = moments["data"]
        else:
            payload["warnings"].append(moments)

    return _clip_deep(payload, max_items=120)


def _mobile_session_bundle(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    username = _str(args, "username") or _str(args, "session_id")
    if not username:
        raise ValueError("username is required.")
    account = _account_arg(args)
    limit = _int(args, "limit", 30, minimum=1, maximum=100)
    offset = _int(args, "offset", 0, minimum=0)

    payload: dict[str, Any] = {
        "status": "success",
        "account": account,
        "username": username,
        "session": None,
        "messages": None,
        "dailyCounts": None,
        "realtime": None,
        "warnings": [],
    }

    session = _safe_call("session", lambda: _resolve_session({"account": account, "query": username, "limit": 5}, ctx))
    if session["ok"]:
        payload["session"] = session["data"]
    else:
        payload["warnings"].append(session)

    messages = _safe_call(
        "messages",
        lambda: _list_messages(
            {
                "account": account,
                "username": username,
                "limit": limit,
                "offset": offset,
                "order": _str(args, "order", "desc") or "desc",
                "render_types": _opt_str(args, "render_types"),
            },
            ctx,
        ),
    )
    if messages["ok"]:
        payload["messages"] = messages["data"]
    else:
        payload["warnings"].append(messages)

    if args.get("year") not in (None, "") and args.get("month") not in (None, ""):
        daily = _safe_call(
            "dailyCounts",
            lambda: _message_daily_counts(
                {"account": account, "username": username, "year": _int(args, "year"), "month": _int(args, "month")},
                ctx,
            ),
        )
        if daily["ok"]:
            payload["dailyCounts"] = daily["data"]
        else:
            payload["warnings"].append(daily)

    realtime = _safe_call("realtime", lambda: _chat_realtime_status({"account": account}, ctx))
    if realtime["ok"]:
        payload["realtime"] = realtime["data"]
    else:
        payload["warnings"].append(realtime)

    return _clip_deep(payload, max_items=140)


def _mobile_message_media_bundle(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    account = _account_arg(args)
    username = _opt_str(args, "username") or _opt_str(args, "session_id")
    server_id = _opt_int(args, "server_id") or _opt_int(args, "msg_svr_id")
    md5 = _opt_str(args, "md5")
    file_id = _opt_str(args, "file_id")
    emoji_url = _opt_str(args, "emoji_url")
    aes_key = _opt_str(args, "aes_key")
    link_url = _opt_str(args, "url") or _opt_str(args, "link_url")

    urls: dict[str, Any] = {}
    warnings: list[dict[str, Any]] = []

    def add(name: str, func: Callable[[], Any]) -> None:
        result = _safe_call(name, func)
        if result["ok"]:
            urls[name] = result["data"]
        else:
            warnings.append(result)

    if username:
        add("avatar", lambda: _avatar_url({"account": account, "username": username}, ctx))
    if md5 or file_id or server_id:
        add("image", lambda: _chat_image_url({"account": account, "username": username, "md5": md5, "file_id": file_id, "server_id": server_id}, ctx))
    if md5 or file_id:
        add("video", lambda: _chat_video_url({"account": account, "username": username, "md5": md5, "file_id": file_id}, ctx))
        add("videoThumb", lambda: _chat_video_thumb_url({"account": account, "username": username, "md5": md5, "file_id": file_id}, ctx))
    if server_id:
        add("voice", lambda: _chat_voice_url({"account": account, "server_id": server_id}, ctx))
    if md5 or emoji_url:
        add("emoji", lambda: _chat_emoji_url({"account": account, "username": username, "md5": md5, "emoji_url": emoji_url, "aes_key": aes_key}, ctx))
    if link_url:
        add("proxyImage", lambda: _chat_proxy_image_url({"url": link_url}, ctx))
        add("favicon", lambda: _chat_favicon_url({"url": link_url}, ctx))

    return {
        "status": "success",
        "account": account,
        "username": username,
        "serverId": server_id,
        "md5": md5,
        "urls": urls,
        "warnings": warnings,
    }


def _first_list(payload: Any, keys: tuple[str, ...] = ("results", "messages", "items", "sessions", "contacts", "posts", "timeline", "data")) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _first_list(value, keys)
            if nested:
                return nested
    return []


def _candidate_display(item: dict[str, Any]) -> str:
    for key in ("displayName", "name", "remark", "nickname", "nickName", "nick", "alias", "username"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""


def _mobile_overview(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    snapshot = _mobile_home_snapshot(
        {
            **args,
            "session_limit": _int(args, "session_limit", 8, minimum=1, maximum=30),
            "moments_limit": _int(args, "moments_limit", 0, minimum=0, maximum=10),
            "include_moments": _bool(args, "include_moments", False),
        },
        ctx,
    )
    accounts_payload = snapshot.get("accounts") or {}
    accounts = list(accounts_payload.get("accounts") or [])
    return _clip_deep(
        {
            "status": "success",
            "ok": True,
            "ready": bool(snapshot.get("service", {}).get("dbReady")),
            "defaultAccount": snapshot.get("service", {}).get("defaultAccount"),
            "accounts": accounts,
            "health": {
                "service": snapshot.get("service"),
                "accountInfo": snapshot.get("accountInfo"),
                "indexes": snapshot.get("indexes"),
                "realtime": snapshot.get("realtime"),
            },
            "suggestedTools": [
                "wechat.mobile.resolve_target",
                "wechat.mobile.search_chat",
                "wechat.mobile.get_chat_context",
                "wechat.mobile.get_media_links",
                "wechat.mobile.export_job",
            ],
            "warnings": snapshot.get("warnings") or [],
        },
        max_items=80,
    )


def _mobile_resolve_target(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    query = _str(args, "query")
    if not query:
        raise ValueError("query is required.")
    account = _account_arg(args)
    target_type = (_str(args, "target_type", "auto") or "auto").lower()
    limit = _int(args, "limit", 8, minimum=1, maximum=20)
    candidates: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def extend(kind: str, result: dict[str, Any]) -> None:
        for idx, item in enumerate(_first_list(result, ("candidates", "users", "accounts", "sessions", "contacts", "items"))[:limit]):
            if not isinstance(item, dict):
                continue
            username = str(item.get("username") or item.get("id") or item.get("userName") or "").strip()
            display = _candidate_display(item)
            confidence = int(item.get("confidence") or max(20, 80 - idx * 8))
            candidates.append(
                {
                    "kind": kind,
                    "id": username or display,
                    "username": username,
                    "displayName": display,
                    "aliases": [v for v in [item.get("alias"), item.get("remark"), item.get("nickname")] if v],
                    "confidence": min(100, confidence),
                    "evidence": _clip_deep(item, max_string=220, max_items=12),
                }
            )

    tasks = []
    if target_type in {"auto", "contact"}:
        tasks.append(("contact", lambda: _resolve_contact({"account": account, "query": query, "limit": limit}, ctx)))
    if target_type in {"auto", "session"}:
        tasks.append(("session", lambda: _resolve_session({"account": account, "query": query, "limit": limit}, ctx)))
    if target_type in {"auto", "moments_user"}:
        tasks.append(("moments_user", lambda: _sns_users({"account": account, "keyword": query, "limit": limit}, ctx)))
    if target_type in {"auto", "biz"}:
        tasks.append(("biz", lambda: _biz_accounts({"account": account}, ctx)))

    for kind, func in tasks:
        result = _safe_call(kind, func)
        if result["ok"]:
            extend(kind, result["data"])
        else:
            warnings.append(result)

    if target_type in {"auto", "biz"} and query:
        q = query.lower()
        candidates = [
            c
            for c in candidates
            if c["kind"] != "biz" or q in " ".join(str(v or "") for v in [c.get("username"), c.get("displayName"), c.get("evidence")]).lower()
        ]

    candidates.sort(key=lambda x: int(x.get("confidence") or 0), reverse=True)
    candidates = candidates[:limit]
    best = candidates[0] if candidates else None
    ambiguous = len(candidates) > 1 and best is not None and int(best.get("confidence") or 0) - int(candidates[1].get("confidence") or 0) < 15
    return {"status": "success", "ok": True, "query": query, "targetType": target_type, "count": len(candidates), "best": best, "ambiguous": ambiguous, "candidates": candidates, "warnings": warnings}


async def _mobile_search_chat(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    query = _str(args, "query") or _str(args, "q")
    if not query:
        raise ValueError("query is required.")
    account = _account_arg(args)
    limit = _int(args, "limit", 12, minimum=1, maximum=50)
    offset = _int(args, "offset", 0, minimum=0)
    context_mode = (_str(args, "context_mode", "none") or "none").lower()
    search_payload = await _search_messages(
        {
            "account": account,
            "query": query,
            "username": _opt_str(args, "username"),
            "sender": _opt_str(args, "sender"),
            "session_type": _opt_str(args, "session_type"),
            "start_time": _opt_int(args, "start_time"),
            "end_time": _opt_int(args, "end_time"),
            "render_types": _opt_str(args, "render_types"),
            "include_hidden": _bool(args, "include_hidden", False),
            "include_official": _bool(args, "include_official", False),
            "limit": limit,
            "offset": offset,
        },
        ctx,
    )
    hits = _first_list(search_payload)
    contexts: list[Any] = []
    warnings: list[dict[str, Any]] = []
    if context_mode in {"top_hits", "selected"}:
        selected = hits[: min(3, len(hits))]
        if context_mode == "selected" and args.get("anchor_id"):
            selected = [{"username": _opt_str(args, "username"), "message_id": _str(args, "anchor_id")}]
        for item in selected:
            if not isinstance(item, dict):
                continue
            username = str(item.get("username") or item.get("session") or item.get("talker") or _opt_str(args, "username") or "").strip()
            anchor_id = str(item.get("message_id") or item.get("msg_id") or item.get("id") or item.get("local_id") or item.get("anchor_id") or "").strip()
            if not username or not anchor_id:
                continue
            try:
                contexts.append(
                    await _messages_around(
                        {
                            "account": account,
                            "username": username,
                            "anchor_id": anchor_id,
                            "before": _int(args, "before", 3, minimum=0, maximum=5),
                            "after": _int(args, "after", 3, minimum=0, maximum=5),
                        },
                        ctx,
                    )
                )
            except Exception as exc:
                warnings.append({"section": "context", "ok": False, "error": str(exc), "username": username, "anchorId": anchor_id})
    return _clip_deep(
        {
            "status": "success",
            "ok": True,
            "account": account,
            "query": query,
            "limit": limit,
            "offset": offset,
            "hasMore": len(hits) >= limit,
            "nextCursor": str(offset + limit) if len(hits) >= limit else None,
            "hits": hits,
            "raw": search_payload,
            "contexts": contexts,
            "warnings": warnings,
        },
        max_items=120,
    )


async def _mobile_get_chat_context(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    username = _str(args, "username") or _str(args, "session_id")
    target = _str(args, "target")
    if not username and target:
        resolved = _mobile_resolve_target({"account": _account_arg(args), "query": target, "target_type": "session", "limit": 1}, ctx)
        best = resolved.get("best") or {}
        username = str(best.get("username") or best.get("id") or "").strip()
    if not username:
        raise ValueError("username or target is required.")

    mode = (_str(args, "mode", "recent") or "recent").lower()
    account = _account_arg(args)
    anchor = None
    if mode == "around":
        messages = await _messages_around(
            {
                "account": account,
                "username": username,
                "anchor_id": _str(args, "anchor_id") or _str(args, "message_id"),
                "before": _int(args, "before", 8, minimum=0, maximum=30),
                "after": _int(args, "after", 8, minimum=0, maximum=30),
            },
            ctx,
        )
    elif mode == "day":
        anchor = _message_anchor({"account": account, "username": username, "kind": "day", "date": _str(args, "date")}, ctx)
        anchor_id = str(anchor.get("anchor_id") or anchor.get("message_id") or anchor.get("id") or "").strip()
        if anchor_id:
            messages = await _messages_around({"account": account, "username": username, "anchor_id": anchor_id, "before": 0, "after": _int(args, "limit", 30, minimum=1, maximum=60)}, ctx)
        else:
            messages = {"status": "success", "messages": []}
    else:
        messages = _list_messages(
            {
                "account": account,
                "username": username,
                "limit": _int(args, "limit", 30, minimum=1, maximum=100),
                "offset": _int(args, "offset", 0, minimum=0),
                "order": _str(args, "order", "desc") or "desc",
                "render_types": _opt_str(args, "render_types"),
            },
            ctx,
        )
    return _clip_deep(
        {
            "status": "success",
            "ok": True,
            "account": account,
            "username": username,
            "mode": mode,
            "session": _resolve_session({"account": account, "query": username, "limit": 1}, ctx),
            "anchor": anchor,
            "messages": messages,
        },
        max_items=120,
    )


def _mobile_search_moments(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    account = _account_arg(args)
    query = _opt_str(args, "query") or _opt_str(args, "q")
    usernames = _list_str(args, "usernames")
    poster = _opt_str(args, "poster")
    warnings: list[dict[str, Any]] = []
    if poster and not usernames:
        resolved = _safe_call("poster", lambda: _mobile_resolve_target({"account": account, "query": poster, "target_type": "moments_user", "limit": 5}, ctx))
        if resolved["ok"]:
            usernames = [str(c.get("username") or c.get("id") or "").strip() for c in (resolved["data"].get("candidates") or []) if str(c.get("username") or c.get("id") or "").strip()]
        else:
            warnings.append(resolved)
    result = _sns_timeline(
        {
            "account": account,
            "query": query,
            "usernames": usernames,
            "limit": _int(args, "limit", 10, minimum=1, maximum=30),
            "offset": _int(args, "offset", 0, minimum=0),
        },
        ctx,
    )
    return _clip_deep({"status": "success", "ok": True, "account": account, "query": query, "usernames": usernames, "posts": _first_list(result), "raw": result, "warnings": warnings}, max_items=100)


def _mobile_get_media_links(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    kind = (_str(args, "kind", "auto") or "auto").lower()
    resources: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def add(source: str, func: Callable[[], dict[str, Any]]) -> None:
        result = _safe_call(source, func)
        if result["ok"]:
            resources.append({"kind": source, **dict(result["data"])})
        else:
            warnings.append(result)

    if kind in {"auto", "avatar"} and (_opt_str(args, "username") or _opt_str(args, "session_id")):
        add("avatar", lambda: _avatar_url(args, ctx))
    has_chat_image_id = bool(_opt_str(args, "md5") or _opt_str(args, "file_id") or _opt_int(args, "server_id") or _opt_int(args, "msg_svr_id"))
    has_chat_file_id = bool(_opt_str(args, "md5") or _opt_str(args, "file_id"))
    has_voice_id = bool(_opt_int(args, "server_id") or _opt_int(args, "msg_svr_id"))
    has_emoji_id = bool(_opt_str(args, "md5") or _opt_str(args, "emoji_url"))
    if kind in {"chat_image", "image"} or (kind == "auto" and has_chat_image_id):
        add("chat_image", lambda: _chat_image_url(args, ctx))
    if kind in {"emoji", "chat_emoji"} or (kind == "auto" and has_emoji_id):
        add("chat_emoji", lambda: _chat_emoji_url(args, ctx))
    if kind in {"video_thumb", "chat_video_thumb"} or (kind == "auto" and has_chat_file_id):
        add("chat_video_thumb", lambda: _chat_video_thumb_url(args, ctx))
    if kind in {"video", "chat_video"} or (kind == "auto" and has_chat_file_id):
        add("chat_video", lambda: _chat_video_url(args, ctx))
    if kind in {"voice", "chat_voice"} or (kind == "auto" and has_voice_id):
        add("chat_voice", lambda: _chat_voice_url(args, ctx))
    if kind in {"moments", "moments_image"}:
        add("moments_image", lambda: _sns_media_url(args, ctx))
    if kind in {"moments_video", "remote_video"}:
        add("moments_video", lambda: _sns_video_remote_url(args, ctx) if _opt_str(args, "url") else _sns_video_url(args, ctx))
    if kind in {"favicon"}:
        add("favicon", lambda: _chat_favicon_url(args, ctx))
    if kind in {"proxy_image"}:
        add("proxy_image", lambda: _chat_proxy_image_url(args, ctx))

    return {"status": "success", "ok": True, "account": _account_arg(args), "kind": kind, "count": len(resources), "resources": resources[: _int(args, "max_items", 20, minimum=1, maximum=20)], "warnings": warnings}


def _mobile_get_analytics(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    metric = (_str(args, "metric", "digest") or "digest").lower()
    account = _account_arg(args)
    if metric == "card":
        data = _wrapped_card(args, ctx)
    elif metric == "daily_counts":
        data = _message_daily_counts(args, ctx)
    elif metric == "pay":
        data = _pay_records({"account": account, "limit": _int(args, "limit", 20, minimum=1, maximum=100), "offset": _int(args, "offset", 0, minimum=0)}, ctx)
    else:
        data = _wrapped_meta({"account": account, "year": _opt_int(args, "year"), "refresh": _bool(args, "refresh", False)}, ctx)
    return _clip_deep({"status": "success", "ok": True, "account": account, "metric": metric, "basis": {"year": _opt_int(args, "year"), "username": _opt_str(args, "username"), "month": _opt_int(args, "month")}, "data": data}, max_items=100)


async def _mobile_export_job(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    action = (_str(args, "action", "status") or "status").lower()
    kind = (_str(args, "kind", "chat") or "chat").lower()
    if action == "preview" and kind == "chat":
        data = _chat_export_targets(args, ctx)
    elif action == "create" and kind == "chat":
        data = _create_chat_export(args, ctx)
    elif action == "create" and kind == "moments":
        data = _create_sns_export(args, ctx)
    elif action == "create" and kind == "archive":
        data = await _create_account_archive(args, ctx)
    elif action == "status" and kind == "chat":
        data = _get_chat_export(args, ctx)
    elif action == "status" and kind == "moments":
        data = _get_sns_export(args, ctx)
    elif action == "status" and kind == "archive":
        data = await _get_account_archive(args, ctx)
    elif action == "download" and kind == "chat":
        data = _download_chat_export(args, ctx)
    elif action == "download" and kind == "moments":
        data = _download_sns_export(args, ctx)
    elif action == "download" and kind == "archive":
        data = await _download_account_archive(args, ctx)
    elif action == "cancel" and kind == "chat":
        data = _cancel_chat_export(args, ctx)
    elif action == "cancel" and kind == "moments":
        data = _cancel_sns_export(args, ctx)
    elif action == "cancel" and kind == "archive":
        data = await _cancel_account_archive(args, ctx)
    else:
        raise ValueError("Unsupported export action/kind.")
    return _clip_deep({"status": "success", "ok": True, "action": action, "kind": kind, "nextPollAfterMs": 1000 if action in {"create", "status"} else None, "data": data}, max_items=100)


def _avatar_url(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    return _media_url("/api/chat/avatar", args, ctx, ["username", "account"])


def _chat_image_url(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    return _media_url("/api/chat/media/image", args, ctx, ["md5", "file_id", "server_id", "account", "username", "deep_scan", "prefer_live"])


def _chat_emoji_url(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    return _media_url("/api/chat/media/emoji", args, ctx, ["md5", "account", "username", "emoji_url", "aes_key"])


def _chat_video_thumb_url(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    return _media_url("/api/chat/media/video_thumb", args, ctx, ["md5", "file_id", "account", "username", "deep_scan"])


def _chat_video_url(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    return _media_url("/api/chat/media/video", args, ctx, ["md5", "file_id", "account", "username", "deep_scan"])


def _chat_voice_url(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    return _media_url("/api/chat/media/voice", args, ctx, ["server_id", "account"])


def _download_emoji(args: dict[str, Any], ctx: McpToolContext) -> Any:
    chat_media_router = _chat_media_router()
    req = chat_media_router.EmojiDownloadRequest(**args)
    return chat_media_router.download_chat_emoji(req)


def _tools_catalog(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    package = _opt_str(args, "package")
    tools = MCP_REGISTRY.list_tools()["tools"]
    if package:
        tools = [t for t in tools if str((t.get("annotations") or {}).get("package") or "") == package]
    cursor = _int(args, "cursor", 0, minimum=0)
    limit_raw = args.get("limit")
    limit = None if limit_raw in (None, "") else _int(args, "limit", 100, minimum=1, maximum=100)
    page = tools[cursor:] if limit is None else tools[cursor : cursor + limit]
    payload: dict[str, Any] = {"status": "success", "count": len(page), "total": len(tools), "tools": page}
    if limit is not None and cursor + limit < len(tools):
        payload["nextCursor"] = str(cursor + limit)
    return payload


COMMON_ACCOUNT = {"account": string_schema("Optional decrypted account directory name.")}
PAGING = {
    "limit": int_schema("Maximum records to return.", minimum=1, maximum=200),
    "offset": int_schema("Pagination offset.", minimum=0),
}


def _install_tools() -> None:
    _register("wechat.core.get_status", "Return MCP service readiness, account availability, and package list.", object_schema(), _status, package="wechat.core")
    _register("wechat.core.list_tools", "List WeChat MCP tools, optionally filtered by package.", object_schema({"package": string_schema("Optional package name."), "cursor": string_schema("Optional numeric cursor."), "limit": int_schema("Maximum tools to return.", minimum=1, maximum=100)}), _tools_catalog, package="wechat.core")
    _register("wechat.core.list_accounts", "List decrypted WeChat accounts available to WeChatDataAnalysis.", object_schema(), _list_accounts, package="wechat.core")
    _register("wechat.core.get_account_info", "Return database and account metadata for one decrypted account.", object_schema(COMMON_ACCOUNT), _get_account_info, package="wechat.core")
    _register("wechat.admin.detect_wechat_installation", "Detect local WeChat installation and data directories.", object_schema({"data_root_path": string_schema("Optional WeChat data root path.")}), _wechat_detection, package="wechat.admin")
    _register("wechat.admin.get_current_wechat_account", "Detect the currently logged-in WeChat account.", object_schema({"data_root_path": string_schema("Optional WeChat data root path.")}), _current_wechat_account, package="wechat.admin")
    _register("wechat.admin.get_wechat_runtime_status", "Return whether the WeChat process is running.", object_schema(), _wechat_runtime_status, package="wechat.admin")
    _register("wechat.system.api_root", "Return the API root metadata.", object_schema(), _api_root, package="wechat.system")
    _register("wechat.system.health_check", "Return backend health status.", object_schema(), _health_check, package="wechat.system")
    _register("wechat.system.get_backend_log_file", "Return the current backend log file path.", object_schema(), _admin_log_file, package="wechat.system")
    _register("wechat.system.open_backend_log_file", "Open the current backend log file on the desktop host.", object_schema(), _admin_open_log_file, package="wechat.system", read_only=False)
    _register("wechat.system.log_frontend_server_error", "Append a frontend-observed server error to the backend log.", object_schema(additional_properties=True), _admin_log_frontend_error, package="wechat.system", read_only=False)
    _register("wechat.system.get_backend_port", "Return the configured backend port.", object_schema(), _admin_port, package="wechat.system")
    _register("wechat.system.set_backend_port_setting", "Persist a backend port setting without restarting the current MCP response.", object_schema({"port": int_schema("Backend port.", minimum=1, maximum=65535)}, required=["port"]), _admin_set_port_setting, package="wechat.system", read_only=False)
    _register("wechat.system.set_backend_port_and_restart", "Change the backend port using the desktop router flow and restart the backend process.", object_schema({"port": int_schema("Backend port.", minimum=1, maximum=65535)}, required=["port"]), _admin_set_port_and_restart, package="wechat.system", read_only=False, destructive=True)
    _register("wechat.system.get_mcp_lan_access", "Return whether phone/LAN clients can reach the MCP endpoint.", object_schema(), _admin_mcp_access, package="wechat.system")
    _register("wechat.system.set_mcp_lan_access", "Enable or disable LAN access for the MCP endpoint and restart the backend if needed.", object_schema({"enabled": bool_schema("Whether LAN MCP access should be enabled.", default=False)}, required=["enabled"]), _admin_set_mcp_access, package="wechat.system", read_only=False, destructive=True)
    _register("wechat.system.get_img_helper_status", "Return the large-image helper plugin status.", object_schema(), _img_helper_status, package="wechat.system")
    _register("wechat.system.toggle_img_helper", "Enable or disable the local large-image helper plugin.", object_schema({"enabled": bool_schema("Whether the helper should be enabled.", default=False)}, required=["enabled"]), _img_helper_toggle, package="wechat.system", read_only=False)
    _register("wechat.system.pick_directory", "Open a native directory picker on the desktop host.", object_schema({"title": string_schema("Dialog title."), "initial_dir": string_schema("Initial directory.")}), _pick_directory, package="wechat.system", read_only=False)

    _register("wechat.setup.get_saved_keys", "Return saved database and media keys for an account or wxid directory.", object_schema({**COMMON_ACCOUNT, "db_storage_path": string_schema("Optional WeChat db_storage path."), "wxid_dir": string_schema("Optional WeChat wxid directory.")}), _get_saved_keys, package="wechat.setup")
    _register("wechat.setup.get_database_key", "Run the local desktop workflow that extracts the WeChat database key.", object_schema({"wechat_install_path": string_schema("Optional WeChat install path.")}), _get_wechat_db_key, package="wechat.setup", read_only=False)
    _register("wechat.setup.get_image_key", "Fetch and save WeChat image AES/XOR keys for an account or wxid directory.", object_schema({**COMMON_ACCOUNT, "db_storage_path": string_schema("Optional WeChat db_storage path."), "wxid_dir": string_schema("Optional WeChat wxid directory.")}), _get_image_key, package="wechat.setup", read_only=False)
    _register("wechat.setup.decrypt_databases", "Decrypt WeChat databases from a db_storage path with a 64-character database key.", object_schema({"key": string_schema("64-character hex database key."), "db_storage_path": string_schema("Absolute db_storage path.")}, required=["key", "db_storage_path"]), _decrypt_databases, package="wechat.setup", read_only=False)
    _register("wechat.setup.get_decrypt_stream_url", "Build an SSE URL for database decryption progress.", object_schema({"key": string_schema("64-character hex database key."), "db_storage_path": string_schema("Absolute db_storage path.")}, required=["key", "db_storage_path"]), _decrypt_stream_url, package="wechat.setup", read_only=False)
    _register("wechat.setup.preview_import_decrypted", "Preview an already-decrypted account directory before import.", object_schema({"import_path": string_schema("Absolute decrypted account/export directory.")}, required=["import_path"]), _import_preview, package="wechat.setup")
    _register("wechat.setup.get_import_decrypted_stream_url", "Build an SSE URL that imports an already-decrypted account directory.", object_schema({"import_path": string_schema("Absolute decrypted account/export directory."), "job_id": string_schema("Optional cancellation job id.")}, required=["import_path"]), _import_stream_url, package="wechat.setup", read_only=False)
    _register("wechat.setup.cancel_import_decrypted", "Cancel an in-memory decrypted-account import job.", object_schema({"job_id": string_schema("Import job id.")}, required=["job_id"]), _import_cancel, package="wechat.setup", read_only=False)
    _register("wechat.setup.save_media_keys", "Save image XOR/AES media keys for an account.", object_schema({**COMMON_ACCOUNT, "xor_key": string_schema("XOR key such as 0xA5."), "aes_key": string_schema("Optional AES key.")}, required=["xor_key"]), _save_media_keys, package="wechat.setup", read_only=False)
    _register("wechat.setup.decrypt_all_media", "Decrypt all local .dat image resources for an account.", object_schema({**COMMON_ACCOUNT, "xor_key": string_schema("Optional XOR key."), "aes_key": string_schema("Optional AES key.")}), _decrypt_all_media, package="wechat.setup", read_only=False)
    _register("wechat.setup.get_decrypt_all_media_stream_url", "Build an SSE URL for bulk media decryption progress.", object_schema({**COMMON_ACCOUNT, "xor_key": string_schema("Optional XOR key."), "aes_key": string_schema("Optional AES key."), "concurrency": int_schema("Worker count.", minimum=1, maximum=64)}), _decrypt_all_media_stream_url, package="wechat.setup", read_only=False)
    _register("wechat.setup.get_download_all_emojis_stream_url", "Build an SSE URL for bulk emoji download progress.", object_schema({**COMMON_ACCOUNT, "force": bool_schema("Download even when cached.", default=False), "concurrency": int_schema("Worker count.", minimum=1, maximum=100)}), _download_all_emojis_stream_url, package="wechat.setup", read_only=False)

    _register("wechat.contacts.list_contacts", "List contacts, groups, and official accounts with optional fuzzy keyword filtering.", object_schema({**COMMON_ACCOUNT, **PAGING, "keyword": string_schema("Optional fuzzy keyword."), "include_friends": bool_schema("Include friends.", default=True), "include_groups": bool_schema("Include groups.", default=True), "include_officials": bool_schema("Include official accounts.", default=True)}), _list_contacts, package="wechat.contacts")
    _register("wechat.contacts.resolve_contact", "Resolve a fuzzy person/group/official-account clue to contact candidates.", object_schema({**COMMON_ACCOUNT, "query": string_schema("Fuzzy contact clue."), "limit": int_schema("Maximum candidates.", minimum=1, maximum=50)}, required=["query"]), _resolve_contact, package="wechat.contacts")
    _register("wechat.contacts.export_contacts", "Export contacts to a local JSON or CSV file.", object_schema({**COMMON_ACCOUNT, "output_dir": string_schema("Absolute output directory."), "format": string_schema("json or csv."), "include_avatar_link": bool_schema("Include avatar links.", default=True), "friends": bool_schema("Include friends.", default=True), "groups": bool_schema("Include groups.", default=True), "officials": bool_schema("Include official accounts.", default=True), "keyword": string_schema("Optional fuzzy keyword.")}, required=["output_dir"]), _export_contacts, package="wechat.contacts", read_only=False)

    _register("wechat.chat.list_sessions", "List chat sessions with preview and optional fuzzy filtering.", object_schema({**COMMON_ACCOUNT, **PAGING, "query": string_schema("Optional fuzzy session keyword."), "include_hidden": bool_schema("Include hidden sessions.", default=False), "include_official": bool_schema("Include official account sessions.", default=False), "preview": string_schema("Preview mode.")}), _list_sessions, package="wechat.chat")
    _register("wechat.chat.resolve_session", "Resolve a fuzzy clue to chat session candidates.", object_schema({**COMMON_ACCOUNT, "query": string_schema("Fuzzy session clue."), "limit": int_schema("Maximum candidates.", minimum=1, maximum=50)}, required=["query"]), _resolve_session, package="wechat.chat")
    _register("wechat.chat.get_messages", "Read one chat session page.", object_schema({**COMMON_ACCOUNT, **PAGING, "username": string_schema("Session username."), "order": string_schema("asc or desc."), "render_types": string_schema("Optional comma-separated render type filter.")}, required=["username"]), _list_messages, package="wechat.chat")
    _register("wechat.chat.search_messages", "Search messages globally or within one session. Uses the search index when available.", object_schema({**COMMON_ACCOUNT, **PAGING, "query": string_schema("Message keyword query."), "username": string_schema("Optional session username."), "sender": string_schema("Optional sender username."), "session_type": string_schema("group or single."), "start_time": int_schema("Optional Unix seconds start.", minimum=0), "end_time": int_schema("Optional Unix seconds end.", minimum=0), "render_types": string_schema("Optional comma-separated render type filter.")}, required=["query"]), _search_messages, package="wechat.chat")
    _register("wechat.chat.list_search_senders", "List sender facets from the chat search index for a global or session query.", object_schema({**COMMON_ACCOUNT, "username": string_schema("Optional session username."), "session_type": string_schema("group or single."), "message_q": string_schema("Optional message keyword filter."), "sender_q": string_schema("Optional sender keyword filter."), "limit": int_schema("Maximum senders.", minimum=1, maximum=2000), "start_time": int_schema("Optional Unix seconds start.", minimum=0), "end_time": int_schema("Optional Unix seconds end.", minimum=0), "render_types": string_schema("Optional comma-separated render type filter."), "include_hidden": bool_schema("Include hidden sessions.", default=False), "include_official": bool_schema("Include official sessions.", default=False)}), _search_index_senders, package="wechat.chat")
    _register("wechat.chat.get_message_around", "Return context around a message anchor id.", object_schema({**COMMON_ACCOUNT, "username": string_schema("Session username."), "anchor_id": string_schema("Message anchor id."), "before": int_schema("Messages before anchor.", minimum=0, maximum=50), "after": int_schema("Messages after anchor.", minimum=0, maximum=50)}, required=["username", "anchor_id"]), _messages_around, package="wechat.chat")
    _register("wechat.chat.get_message_anchor", "Get a session anchor for a day or first message.", object_schema({**COMMON_ACCOUNT, "username": string_schema("Session username."), "kind": string_schema("day or first."), "date": string_schema("YYYY-MM-DD when kind=day.")}, required=["username", "kind"]), _message_anchor, package="wechat.chat")
    _register("wechat.chat.get_daily_message_counts", "Return daily message counts for one session month.", object_schema({**COMMON_ACCOUNT, "username": string_schema("Session username."), "year": int_schema("Year."), "month": int_schema("Month.", minimum=1, maximum=12)}, required=["username", "year", "month"]), _message_daily_counts, package="wechat.chat")
    _register("wechat.chat.get_message_raw", "Return raw decrypted fields for one message. Use only for debugging or missing structured fields.", object_schema({**COMMON_ACCOUNT, "username": string_schema("Session username."), "message_id": string_schema("Message id.")}, required=["username", "message_id"]), _message_raw, package="wechat.chat")
    _register("wechat.chat.resolve_chat_history", "Resolve a merged-forward chat history AppMsg by server_id.", object_schema({**COMMON_ACCOUNT, "server_id": int_schema("Message server id.", minimum=1)}, required=["server_id"]), _resolve_chat_history, package="wechat.chat")
    _register("wechat.chat.resolve_app_message", "Resolve an AppMsg/card/miniprogram message by server_id.", object_schema({**COMMON_ACCOUNT, "server_id": int_schema("Message server id.", minimum=1)}, required=["server_id"]), _resolve_app_message, package="wechat.chat")
    _register("wechat.chat.get_search_index_status", "Return chat search index status.", object_schema(COMMON_ACCOUNT), _search_index_status, package="wechat.admin")
    _register("wechat.chat.build_search_index", "Build or rebuild chat search index.", object_schema({**COMMON_ACCOUNT, "rebuild": bool_schema("Rebuild even if index exists.", default=False)}), _build_search_index, package="wechat.admin", read_only=False)
    _register("wechat.chat.get_session_last_message_cache_status", "Return session last-message cache status.", object_schema(COMMON_ACCOUNT), _session_last_message_status, package="wechat.admin")
    _register("wechat.chat.build_session_last_message_cache", "Build session last-message cache.", object_schema({**COMMON_ACCOUNT, "rebuild": bool_schema("Rebuild cache.", default=False), "include_hidden": bool_schema("Include hidden sessions.", default=True), "include_official": bool_schema("Include official sessions.", default=True)}), _build_session_last_message, package="wechat.admin", read_only=False)
    _register("wechat.chat.get_realtime_status", "Return chat realtime sync status.", object_schema(COMMON_ACCOUNT), _chat_realtime_status, package="wechat.admin")
    _register("wechat.chat.sync_realtime_session", "Sync realtime messages for one session.", object_schema({**COMMON_ACCOUNT, "username": string_schema("Session username."), "max_scan": int_schema("Maximum realtime rows to scan.", minimum=50, maximum=5000), "backfill_limit": int_schema("Maximum old rows to backfill.", minimum=0, maximum=5000)}, required=["username"]), _chat_realtime_sync, package="wechat.admin", read_only=False)
    _register("wechat.chat.sync_realtime_all_sessions", "Sync realtime messages for all sessions.", object_schema({**COMMON_ACCOUNT, "max_scan": int_schema("Maximum realtime rows per session.", minimum=50, maximum=5000), "priority_username": string_schema("Optional username to sync first."), "priority_max_scan": int_schema("Priority session max scan.", minimum=50, maximum=5000), "include_hidden": bool_schema("Include hidden sessions.", default=True), "include_official": bool_schema("Include official sessions.", default=True), "only_official": bool_schema("Only sync official sessions.", default=False), "backfill_limit": int_schema("Maximum old rows to backfill.", minimum=0, maximum=5000)}), _chat_realtime_sync_all, package="wechat.admin", read_only=False)
    _register("wechat.chat.get_realtime_events_url", "Build an SSE URL for realtime db_storage change events.", object_schema({**COMMON_ACCOUNT, "interval_ms": int_schema("Polling interval in milliseconds.", minimum=100, maximum=5000)}), _chat_realtime_events_url, package="wechat.admin")
    _register("wechat.admin.delete_account_data", "Delete one account's local WeChatDataAnalysis data from this project.", object_schema({"account": string_schema("Account directory name.")}, required=["account"]), _delete_account_data, package="wechat.admin", read_only=False, destructive=True)

    _register("wechat.editing.list_edited_sessions", "List sessions with local message edits.", object_schema(COMMON_ACCOUNT), _list_edited_sessions, package="wechat.editing")
    _register("wechat.editing.list_edited_messages", "List edited messages for one session.", object_schema({**COMMON_ACCOUNT, "username": string_schema("Session username.")}, required=["username"]), _list_edited_messages, package="wechat.editing")
    _register("wechat.editing.get_message_edit_status", "Return whether one message has been edited.", object_schema({**COMMON_ACCOUNT, "username": string_schema("Session username."), "message_id": string_schema("Message id.")}, required=["username", "message_id"]), _edit_status, package="wechat.editing")
    _register("wechat.editing.edit_message", "Edit one message in the real WeChat database and output cache.", object_schema(additional_properties=True), _edit_message, package="wechat.editing", read_only=False)
    _register("wechat.editing.repair_message_sender", "Repair one message sender metadata.", object_schema(additional_properties=True), _repair_sender, package="wechat.editing", read_only=False)
    _register("wechat.editing.flip_message_direction", "Flip one message display direction.", object_schema(additional_properties=True), _flip_direction, package="wechat.editing", read_only=False)
    _register("wechat.editing.reset_message_edit", "Restore one edited message from its first snapshot.", object_schema(additional_properties=True), _reset_message_edit, package="wechat.editing", read_only=False)
    _register("wechat.editing.reset_session_edits", "Restore all edited messages in one session.", object_schema(additional_properties=True), _reset_session_edits, package="wechat.editing", read_only=False)

    _register("wechat.moments.get_self_info", "Return Moments self wxid and display name.", object_schema(COMMON_ACCOUNT), _sns_self_info, package="wechat.moments")
    _register("wechat.moments.list_timeline", "List Moments timeline by users, keyword, and pagination.", object_schema({**COMMON_ACCOUNT, **PAGING, "usernames": array_schema("Optional poster usernames.", string_schema("Username.")), "keyword": string_schema("Optional content keyword.")}), _sns_timeline, package="wechat.moments")
    _register("wechat.moments.search_moments", "Alias for timeline keyword/user search.", object_schema({**COMMON_ACCOUNT, **PAGING, "usernames": array_schema("Optional poster usernames.", string_schema("Username.")), "query": string_schema("Content keyword.")}), _sns_timeline, package="wechat.moments")
    _register("wechat.moments.list_users", "List Moments posters with post counts.", object_schema({**COMMON_ACCOUNT, "keyword": string_schema("Optional poster keyword."), "limit": int_schema("Maximum users.", minimum=1, maximum=500)}), _sns_users, package="wechat.moments")
    _register("wechat.moments.sync_latest", "Sync latest visible Moments into decrypted sns.db.", object_schema({**COMMON_ACCOUNT, "max_scan": int_schema("Maximum rows to scan.", minimum=1, maximum=2000), "force": int_schema("Force flag 0/1.", minimum=0, maximum=1)}), _sns_sync_latest, package="wechat.admin", read_only=False)
    _register("wechat.moments.get_media_url", "Build a URL for a Moments image resource.", object_schema(additional_properties=True), _sns_media_url, package="wechat.media")
    _register("wechat.moments.get_article_thumb_url", "Build a URL for an official-article thumbnail image.", object_schema({"url": string_schema("Article URL.")}, required=["url"]), _sns_article_thumb_url, package="wechat.media")
    _register("wechat.moments.get_remote_video_url", "Build a URL for a remote Moments video/live-photo resource.", object_schema(additional_properties=True), _sns_video_remote_url, package="wechat.media")
    _register("wechat.moments.get_local_video_url", "Build a URL for a local cached Moments video resource.", object_schema({**COMMON_ACCOUNT, "post_id": string_schema("Moments post id."), "media_id": string_schema("Media id.")}, required=["post_id", "media_id"]), _sns_video_url, package="wechat.media")

    _register("wechat.biz.list_accounts", "List official account/service account message sources.", object_schema(COMMON_ACCOUNT), _biz_accounts, package="wechat.biz")
    _register("wechat.biz.get_messages", "Get official account messages.", object_schema({**COMMON_ACCOUNT, **PAGING, "username": string_schema("Official account username.")}, required=["username"]), _biz_messages, package="wechat.biz")
    _register("wechat.biz.get_pay_records", "Get WeChat Pay records from the pay official account.", object_schema({**COMMON_ACCOUNT, **PAGING}), _pay_records, package="wechat.biz")

    _register("wechat.analytics.get_wrapped_meta", "Return annual wrapped manifest.", object_schema({**COMMON_ACCOUNT, "year": int_schema("Optional year."), "refresh": bool_schema("Refresh cache.", default=False)}), _wrapped_meta, package="wechat.analytics")
    _register("wechat.analytics.get_wrapped_card", "Return one annual wrapped card.", object_schema({**COMMON_ACCOUNT, "year": int_schema("Optional year."), "card_id": int_schema("Card id.", minimum=0), "refresh": bool_schema("Refresh cache.", default=False)}, required=["card_id"]), _wrapped_card, package="wechat.analytics")
    _register("wechat.analytics.get_wrapped_annual", "Return full annual wrapped data. Prefer meta/card for mobile clients.", object_schema({**COMMON_ACCOUNT, "year": int_schema("Optional year."), "refresh": bool_schema("Refresh cache.", default=False)}), _wrapped_annual, package="wechat.analytics")

    _register("wechat.media.get_avatar_url", "Build a URL for a contact avatar.", object_schema({**COMMON_ACCOUNT, "username": string_schema("Contact username.")}, required=["username"]), _avatar_url, package="wechat.media")
    _register("wechat.media.get_chat_image_url", "Build a URL for a chat image message resource.", object_schema(additional_properties=True), _chat_image_url, package="wechat.media")
    _register("wechat.media.get_chat_emoji_url", "Build a URL for a chat emoji message resource.", object_schema(additional_properties=True), _chat_emoji_url, package="wechat.media")
    _register("wechat.media.get_chat_video_thumb_url", "Build a URL for a chat video thumbnail.", object_schema(additional_properties=True), _chat_video_thumb_url, package="wechat.media")
    _register("wechat.media.get_chat_video_url", "Build a URL for a chat video resource.", object_schema(additional_properties=True), _chat_video_url, package="wechat.media")
    _register("wechat.media.get_chat_voice_url", "Build a URL for a chat voice file. This does not transcribe audio.", object_schema(additional_properties=True), _chat_voice_url, package="wechat.media")
    _register("wechat.media.download_chat_emoji", "Download one emoji resource into local cache.", object_schema(additional_properties=True), _download_emoji, package="wechat.media", read_only=False)
    _register("wechat.media.get_decrypted_resource_url", "Build a URL for a previously decrypted resource by MD5.", object_schema({**COMMON_ACCOUNT, "md5": string_schema("32-character resource md5.")}, required=["md5"]), _decrypted_media_resource_url, package="wechat.media")
    _register("wechat.media.get_proxy_image_url", "Build a backend proxy URL for a remote chat image.", object_schema({"url": string_schema("Remote image URL.")}, required=["url"]), _chat_proxy_image_url, package="wechat.media")
    _register("wechat.media.get_favicon_url", "Build a backend URL for a web page favicon.", object_schema({"url": string_schema("Page URL.")}, required=["url"]), _chat_favicon_url, package="wechat.media")
    _register("wechat.media.open_chat_media_folder", "Open a chat media file or folder on the desktop host.", object_schema(additional_properties=True), _open_chat_media_folder, package="wechat.media", read_only=False)
    _register("wechat.biz.get_proxy_image_url", "Build a backend proxy URL for an official-account image.", object_schema({"url": string_schema("Remote image URL.")}, required=["url"]), _biz_proxy_image_url, package="wechat.biz")

    _register("wechat.export.preview_chat_targets", "Preview chat export targets.", object_schema({**COMMON_ACCOUNT, "include_hidden": bool_schema("Include hidden sessions.", default=True), "include_official": bool_schema("Include official sessions.", default=False)}), _chat_export_targets, package="wechat.export")
    _register("wechat.export.create_chat_export", "Create a chat export job.", object_schema(additional_properties=True), _create_chat_export, package="wechat.export", read_only=False)
    _register("wechat.export.list_chat_exports", "List chat export jobs.", object_schema(), _list_chat_exports, package="wechat.export")
    _register("wechat.export.get_chat_export", "Get one chat export job.", object_schema({"export_id": string_schema("Export id.")}, required=["export_id"]), _get_chat_export, package="wechat.export")
    _register("wechat.export.cancel_chat_export", "Cancel one chat export job.", object_schema({"export_id": string_schema("Export id.")}, required=["export_id"]), _cancel_chat_export, package="wechat.export", read_only=False)
    _register("wechat.export.get_chat_export_download", "Return chat export download URL when ready.", object_schema({"export_id": string_schema("Export id.")}, required=["export_id"]), _download_chat_export, package="wechat.export")
    _register("wechat.export.get_chat_export_events_url", "Build an SSE URL for chat export progress events.", object_schema({"export_id": string_schema("Export id.")}, required=["export_id"]), _chat_export_events_url, package="wechat.export")
    _register("wechat.export.create_moments_export", "Create a Moments export job.", object_schema(additional_properties=True), _create_sns_export, package="wechat.export", read_only=False)
    _register("wechat.export.list_moments_exports", "List Moments export jobs.", object_schema(), _list_sns_exports, package="wechat.export")
    _register("wechat.export.get_moments_export", "Get one Moments export job.", object_schema({"export_id": string_schema("Export id.")}, required=["export_id"]), _get_sns_export, package="wechat.export")
    _register("wechat.export.cancel_moments_export", "Cancel one Moments export job.", object_schema({"export_id": string_schema("Export id.")}, required=["export_id"]), _cancel_sns_export, package="wechat.export", read_only=False)
    _register("wechat.export.get_moments_export_download", "Return Moments export download URL when ready.", object_schema({"export_id": string_schema("Export id.")}, required=["export_id"]), _download_sns_export, package="wechat.export")
    _register("wechat.export.get_moments_export_events_url", "Build an SSE URL for Moments export progress events.", object_schema({"export_id": string_schema("Export id.")}, required=["export_id"]), _moments_export_events_url, package="wechat.export")
    _register("wechat.export.create_account_archive", "Create a full account archive export job.", object_schema(additional_properties=True), _create_account_archive, package="wechat.export", read_only=False)
    _register("wechat.export.get_account_archive", "Get account archive export job.", object_schema({"export_id": string_schema("Export id.")}, required=["export_id"]), _get_account_archive, package="wechat.export")
    _register("wechat.export.cancel_account_archive", "Cancel account archive export job.", object_schema({"export_id": string_schema("Export id.")}, required=["export_id"]), _cancel_account_archive, package="wechat.export", read_only=False)
    _register("wechat.export.get_account_archive_download", "Return account archive download URL when ready.", object_schema({"export_id": string_schema("Export id.")}, required=["export_id"]), _download_account_archive, package="wechat.export")

    _register("wechat.mobile.get_overview", "Return a compact mobile overview and suggested next tools.", object_schema({**COMMON_ACCOUNT, "session_limit": int_schema("Session count.", minimum=1, maximum=30), "moments_limit": int_schema("Moments count.", minimum=0, maximum=10), "include_moments": bool_schema("Include Moments preview.", default=False)}), _mobile_overview, package="wechat.mobile")
    _register("wechat.mobile.get_home_snapshot", "Return a mobile-friendly account/session/Moments readiness snapshot.", object_schema({**COMMON_ACCOUNT, "session_limit": int_schema("Session count.", minimum=1, maximum=80), "moments_limit": int_schema("Moments count.", minimum=0, maximum=30), "include_moments": bool_schema("Include Moments preview.", default=True), "include_hidden": bool_schema("Include hidden sessions.", default=False), "include_official": bool_schema("Include official sessions.", default=False), "preview": string_schema("Session preview mode.")}), _mobile_home_snapshot, package="wechat.mobile")
    _register("wechat.mobile.resolve_target", "Resolve a fuzzy target to contacts, sessions, Moments users, or official accounts.", object_schema({**COMMON_ACCOUNT, "query": string_schema("Target clue."), "target_type": string_schema("auto, contact, session, moments_user, or biz."), "limit": int_schema("Maximum candidates.", minimum=1, maximum=20)}, required=["query"]), _mobile_resolve_target, package="wechat.mobile")
    _register("wechat.mobile.search_context", "Search messages plus lightweight session/contact/Moments context for mobile UI.", object_schema({**COMMON_ACCOUNT, "query": string_schema("Search text."), "limit": int_schema("Per-section result count.", minimum=1, maximum=50), "offset": int_schema("Message result offset.", minimum=0), "include_moments": bool_schema("Include Moments matches.", default=True), "include_contacts": bool_schema("Include contact matches.", default=True)}, required=["query"]), _mobile_search_context, package="wechat.mobile")
    _register("wechat.mobile.search_chat", "Search chat messages with optional small context windows.", object_schema({**COMMON_ACCOUNT, "query": string_schema("Search text."), "username": string_schema("Optional session username."), "sender": string_schema("Optional sender username."), "session_type": string_schema("group or single."), "start_time": int_schema("Optional Unix seconds start.", minimum=0), "end_time": int_schema("Optional Unix seconds end.", minimum=0), "render_types": string_schema("Optional render types."), "limit": int_schema("Hit count.", minimum=1, maximum=50), "offset": int_schema("Offset cursor.", minimum=0), "context_mode": string_schema("none, top_hits, or selected."), "before": int_schema("Context messages before.", minimum=0, maximum=5), "after": int_schema("Context messages after.", minimum=0, maximum=5), "anchor_id": string_schema("Selected anchor id.")}, required=["query"]), _mobile_search_chat, package="wechat.mobile")
    _register("wechat.mobile.get_chat_context", "Return a compact chat context by recent page, anchor, or day.", object_schema({**COMMON_ACCOUNT, "username": string_schema("Session username."), "target": string_schema("Optional fuzzy session clue."), "mode": string_schema("recent, around, or day."), "anchor_id": string_schema("Message anchor id."), "message_id": string_schema("Alias for anchor_id."), "date": string_schema("YYYY-MM-DD for day mode."), "limit": int_schema("Message count.", minimum=1, maximum=100), "offset": int_schema("Message offset.", minimum=0), "order": string_schema("asc or desc."), "render_types": string_schema("Optional render type filter."), "before": int_schema("Messages before anchor.", minimum=0, maximum=30), "after": int_schema("Messages after anchor.", minimum=0, maximum=30)}), _mobile_get_chat_context, package="wechat.mobile")
    _register("wechat.mobile.get_session_bundle", "Return one session's metadata, messages, and optional calendar counts for mobile UI.", object_schema({**COMMON_ACCOUNT, "username": string_schema("Session username."), "limit": int_schema("Message count.", minimum=1, maximum=100), "offset": int_schema("Message offset.", minimum=0), "order": string_schema("asc or desc."), "render_types": string_schema("Optional render type filter."), "year": int_schema("Optional year for daily counts."), "month": int_schema("Optional month for daily counts.", minimum=1, maximum=12)}, required=["username"]), _mobile_session_bundle, package="wechat.mobile")
    _register("wechat.mobile.search_moments", "Search Moments posts with compact media references.", object_schema({**COMMON_ACCOUNT, "query": string_schema("Content keyword."), "poster": string_schema("Optional poster clue."), "usernames": array_schema("Poster usernames.", string_schema("Username.")), "limit": int_schema("Post count.", minimum=1, maximum=30), "offset": int_schema("Offset cursor.", minimum=0)}), _mobile_search_moments, package="wechat.mobile")
    _register("wechat.mobile.get_media_links", "Return URL resources for chat, Moments, avatar, link, or emoji media.", object_schema(additional_properties=True), _mobile_get_media_links, package="wechat.mobile")
    _register("wechat.mobile.get_message_media_bundle", "Return likely media URLs for a message or link without fetching binary content.", object_schema(additional_properties=True), _mobile_message_media_bundle, package="wechat.mobile")
    _register("wechat.mobile.get_analytics", "Return compact analytics data by metric without loading full annual payloads.", object_schema(additional_properties=True), _mobile_get_analytics, package="wechat.mobile")
    _register("wechat.mobile.export_job", "Preview, create, poll, download, or cancel chat/Moments/archive export jobs.", object_schema(additional_properties=True), _mobile_export_job, package="wechat.mobile", read_only=False)


_install_tools()
