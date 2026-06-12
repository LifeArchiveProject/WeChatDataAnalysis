from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable, Optional
from urllib.parse import urlencode

from fastapi import Request

from .. import __version__ as APP_VERSION
from ..chat_helpers import (
    _iter_message_db_paths,
    _list_decrypted_accounts,
    _quote_ident,
    _resolve_account_dir,
    _resolve_msg_table_name,
)
from ..database_filters import list_countable_database_names
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


def _request(ctx: McpToolContext, payload: dict[str, Any] | None = None) -> Request | _JsonRequest:
    if payload is None:
        return ctx.request
    return _JsonRequest(payload, base_url=(ctx.base_url + "/") if ctx.base_url else "http://127.0.0.1/")


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
    svc = _wrapped_service()
    account_dir = _resolve_account_dir(_account_arg(args))
    year = _wrapped_cache_year(account_dir, _opt_int(args, "year"), svc)
    return {
        "status": "success",
        "account": account_dir.name,
        "year": year,
        "scope": "global",
        "cacheOnly": True,
        "availableYears": _wrapped_available_cache_years(account_dir, svc),
        "cards": [dict(c) for c in getattr(svc, "_WRAPPED_CARD_MANIFEST", ())],
    }


def _wrapped_card(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    svc = _wrapped_service()
    account_dir = _resolve_account_dir(_account_arg(args))
    year = _wrapped_cache_year(account_dir, _opt_int(args, "year"), svc)
    card_id = _int(args, "card_id", minimum=0)
    card = _read_wrapped_card_cache(account_dir, year, card_id, svc)
    if card is None:
        return _wrapped_cache_missing(account_dir, year, f"card {card_id}", svc)
    return _clip_deep(card, max_items=80)


def _wrapped_annual(args: dict[str, Any], _: McpToolContext) -> dict[str, Any]:
    svc = _wrapped_service()
    account_dir = _resolve_account_dir(_account_arg(args))
    year = _wrapped_cache_year(account_dir, _opt_int(args, "year"), svc)
    payload = _read_json_file(_wrapped_full_cache_path(account_dir, year, svc))
    if not isinstance(payload, dict):
        return _wrapped_cache_missing(account_dir, year, "annual wrapped data", svc)
    payload = {**payload, "cached": True, "cacheOnly": True, "availableYears": _wrapped_available_cache_years(account_dir, svc)}
    return _clip_deep(payload, max_items=80)


def _wrapped_cache_dir_readonly(account_dir: Any) -> Any:
    return account_dir / "_wrapped" / "cache"


def _wrapped_cache_version(svc: Any) -> int:
    return int(getattr(svc, "_CACHE_VERSION", 0))


def _wrapped_implemented_upto(svc: Any) -> int:
    return int(getattr(svc, "_IMPLEMENTED_UPTO_ID", 0))


def _wrapped_default_year(svc: Any) -> int:
    try:
        return int(svc._default_year())
    except Exception:
        from datetime import datetime

        return int(datetime.now().year)


def _wrapped_full_cache_path(account_dir: Any, year: int, svc: Any) -> Any:
    version = _wrapped_cache_version(svc)
    upto = _wrapped_implemented_upto(svc)
    return _wrapped_cache_dir_readonly(account_dir) / f"global_{int(year)}_upto_{upto}_v{version}.json"


def _wrapped_card_cache_path(account_dir: Any, year: int, card_id: int, svc: Any) -> Any:
    version = _wrapped_cache_version(svc)
    return _wrapped_cache_dir_readonly(account_dir) / f"global_{int(year)}_card_{int(card_id)}_v{version}.json"


def _read_json_file(path: Any) -> Any:
    try:
        if not path.exists() or not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _wrapped_available_cache_years(account_dir: Any, svc: Any) -> list[int]:
    cache_dir = _wrapped_cache_dir_readonly(account_dir)
    if not cache_dir.exists() or not cache_dir.is_dir():
        return []
    version = _wrapped_cache_version(svc)
    upto = _wrapped_implemented_upto(svc)
    years: set[int] = set()
    patterns = [
        f"global_*_upto_{upto}_v{version}.json",
        f"global_*_card_*_v{version}.json",
    ]
    for pattern in patterns:
        try:
            paths = list(cache_dir.glob(pattern))
        except Exception:
            paths = []
        for path in paths:
            parts = str(path.stem or "").split("_")
            if len(parts) < 2:
                continue
            try:
                year = int(parts[1])
            except Exception:
                continue
            if year > 0:
                years.add(year)
    return sorted(years, reverse=True)


def _wrapped_cache_year(account_dir: Any, requested_year: Optional[int], svc: Any) -> int:
    years = _wrapped_available_cache_years(account_dir, svc)
    year = int(requested_year or _wrapped_default_year(svc))
    if years and year not in years:
        return int(years[0])
    return year


def _read_wrapped_card_cache(account_dir: Any, year: int, card_id: int, svc: Any) -> dict[str, Any] | None:
    card_payload = _read_json_file(_wrapped_card_cache_path(account_dir, year, card_id, svc))
    if isinstance(card_payload, dict):
        return card_payload
    annual_payload = _read_json_file(_wrapped_full_cache_path(account_dir, year, svc))
    if isinstance(annual_payload, dict):
        for card in annual_payload.get("cards") or []:
            if not isinstance(card, dict):
                continue
            try:
                if int(card.get("id") or -1) == int(card_id):
                    return card
            except Exception:
                continue
    return None


def _wrapped_cache_missing(account_dir: Any, year: int, target: str, svc: Any) -> dict[str, Any]:
    return {
        "status": "error",
        "message": "Wrapped cache not found. Open the app to generate it first.",
        "account": account_dir.name,
        "year": int(year),
        "target": target,
        "cacheOnly": True,
        "availableYears": _wrapped_available_cache_years(account_dir, svc),
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


def _decrypted_media_resource_url(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    md5 = _str(args, "md5").lower()
    if len(md5) != 32:
        raise ValueError("md5 must be 32 characters.")
    return _url_result(ctx, f"/api/media/resource/{md5}", {"account": _account_arg(args)}, kind="url")


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


def _safe_call(label: str, func: Callable[[], Any]) -> dict[str, Any]:
    try:
        return {"ok": True, "data": func()}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "section": label}


async def _mobile_home_snapshot(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
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


async def _mobile_session_bundle(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
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


async def _mobile_overview(args: dict[str, Any], ctx: McpToolContext) -> dict[str, Any]:
    snapshot = await _mobile_home_snapshot(
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
            },
            "suggestedTools": [
                "wechat.mobile.resolve_target",
                "wechat.mobile.search_chat",
                "wechat.mobile.get_chat_context",
                "wechat.mobile.get_media_links",
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
        data = _wrapped_meta({"account": account, "year": _opt_int(args, "year")}, ctx)
    return _clip_deep({"status": "success", "ok": True, "account": account, "metric": metric, "basis": {"year": _opt_int(args, "year"), "username": _opt_str(args, "username"), "month": _opt_int(args, "month")}, "data": data}, max_items=100)


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

    _register("wechat.contacts.list_contacts", "List contacts, groups, and official accounts with optional fuzzy keyword filtering.", object_schema({**COMMON_ACCOUNT, **PAGING, "keyword": string_schema("Optional fuzzy keyword."), "include_friends": bool_schema("Include friends.", default=True), "include_groups": bool_schema("Include groups.", default=True), "include_officials": bool_schema("Include official accounts.", default=True)}), _list_contacts, package="wechat.contacts")
    _register("wechat.contacts.resolve_contact", "Resolve a fuzzy person/group/official-account clue to contact candidates.", object_schema({**COMMON_ACCOUNT, "query": string_schema("Fuzzy contact clue."), "limit": int_schema("Maximum candidates.", minimum=1, maximum=50)}, required=["query"]), _resolve_contact, package="wechat.contacts")

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

    _register("wechat.moments.get_self_info", "Return Moments self wxid and display name.", object_schema(COMMON_ACCOUNT), _sns_self_info, package="wechat.moments")
    _register("wechat.moments.list_timeline", "List Moments timeline by users, keyword, and pagination.", object_schema({**COMMON_ACCOUNT, **PAGING, "usernames": array_schema("Optional poster usernames.", string_schema("Username.")), "keyword": string_schema("Optional content keyword.")}), _sns_timeline, package="wechat.moments")
    _register("wechat.moments.search_moments", "Alias for timeline keyword/user search.", object_schema({**COMMON_ACCOUNT, **PAGING, "usernames": array_schema("Optional poster usernames.", string_schema("Username.")), "query": string_schema("Content keyword.")}), _sns_timeline, package="wechat.moments")
    _register("wechat.moments.list_users", "List Moments posters with post counts.", object_schema({**COMMON_ACCOUNT, "keyword": string_schema("Optional poster keyword."), "limit": int_schema("Maximum users.", minimum=1, maximum=500)}), _sns_users, package="wechat.moments")
    _register("wechat.moments.get_media_url", "Build a URL for a Moments image resource.", object_schema(additional_properties=True), _sns_media_url, package="wechat.media")
    _register("wechat.moments.get_article_thumb_url", "Build a URL for an official-article thumbnail image.", object_schema({"url": string_schema("Article URL.")}, required=["url"]), _sns_article_thumb_url, package="wechat.media")
    _register("wechat.moments.get_remote_video_url", "Build a URL for a remote Moments video/live-photo resource.", object_schema(additional_properties=True), _sns_video_remote_url, package="wechat.media")
    _register("wechat.moments.get_local_video_url", "Build a URL for a local cached Moments video resource.", object_schema({**COMMON_ACCOUNT, "post_id": string_schema("Moments post id."), "media_id": string_schema("Media id.")}, required=["post_id", "media_id"]), _sns_video_url, package="wechat.media")

    _register("wechat.biz.list_accounts", "List official account/service account message sources.", object_schema(COMMON_ACCOUNT), _biz_accounts, package="wechat.biz")
    _register("wechat.biz.get_messages", "Get official account messages.", object_schema({**COMMON_ACCOUNT, **PAGING, "username": string_schema("Official account username.")}, required=["username"]), _biz_messages, package="wechat.biz")
    _register("wechat.biz.get_pay_records", "Get WeChat Pay records from the pay official account.", object_schema({**COMMON_ACCOUNT, **PAGING}), _pay_records, package="wechat.biz")

    _register("wechat.analytics.get_wrapped_meta", "Return annual wrapped manifest.", object_schema({**COMMON_ACCOUNT, "year": int_schema("Optional year.")}), _wrapped_meta, package="wechat.analytics")
    _register("wechat.analytics.get_wrapped_card", "Return one annual wrapped card.", object_schema({**COMMON_ACCOUNT, "year": int_schema("Optional year."), "card_id": int_schema("Card id.", minimum=0)}, required=["card_id"]), _wrapped_card, package="wechat.analytics")
    _register("wechat.analytics.get_wrapped_annual", "Return full annual wrapped data. Prefer meta/card for mobile clients.", object_schema({**COMMON_ACCOUNT, "year": int_schema("Optional year.")}), _wrapped_annual, package="wechat.analytics")

    _register("wechat.media.get_avatar_url", "Build a URL for a contact avatar.", object_schema({**COMMON_ACCOUNT, "username": string_schema("Contact username.")}, required=["username"]), _avatar_url, package="wechat.media")
    _register("wechat.media.get_chat_image_url", "Build a URL for a chat image message resource.", object_schema(additional_properties=True), _chat_image_url, package="wechat.media")
    _register("wechat.media.get_chat_emoji_url", "Build a URL for a chat emoji message resource.", object_schema(additional_properties=True), _chat_emoji_url, package="wechat.media")
    _register("wechat.media.get_chat_video_thumb_url", "Build a URL for a chat video thumbnail.", object_schema(additional_properties=True), _chat_video_thumb_url, package="wechat.media")
    _register("wechat.media.get_chat_video_url", "Build a URL for a chat video resource.", object_schema(additional_properties=True), _chat_video_url, package="wechat.media")
    _register("wechat.media.get_chat_voice_url", "Build a URL for a chat voice file. This does not transcribe audio.", object_schema(additional_properties=True), _chat_voice_url, package="wechat.media")
    _register("wechat.media.get_decrypted_resource_url", "Build a URL for a previously decrypted resource by MD5.", object_schema({**COMMON_ACCOUNT, "md5": string_schema("32-character resource md5.")}, required=["md5"]), _decrypted_media_resource_url, package="wechat.media")
    _register("wechat.media.get_proxy_image_url", "Build a backend proxy URL for a remote chat image.", object_schema({"url": string_schema("Remote image URL.")}, required=["url"]), _chat_proxy_image_url, package="wechat.media")
    _register("wechat.media.get_favicon_url", "Build a backend URL for a web page favicon.", object_schema({"url": string_schema("Page URL.")}, required=["url"]), _chat_favicon_url, package="wechat.media")
    _register("wechat.biz.get_proxy_image_url", "Build a backend proxy URL for an official-account image.", object_schema({"url": string_schema("Remote image URL.")}, required=["url"]), _biz_proxy_image_url, package="wechat.biz")

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


_install_tools()
