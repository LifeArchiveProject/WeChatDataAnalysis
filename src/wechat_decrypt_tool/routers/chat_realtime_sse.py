"""Message-level realtime SSE stream."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..chat_helpers import (
    _load_contact_rows,
    _pick_display_name,
    _resolve_account_dir,
)
from ..path_fix import PathFixRoute
from ..wcdb_realtime import (
    WCDB_REALTIME,
    get_display_names as _wcdb_get_display_names,
    get_sessions as _wcdb_get_sessions,
)

router = APIRouter(route_class=PathFixRoute)

_DEFAULT_INTERVAL_MS = 5
_MESSAGE_PAGE_SIZE = 500


def _message_local_id(message: Any) -> int:
    if not isinstance(message, dict):
        return 0
    try:
        return int(message.get("localId", message.get("local_id", 0)) or 0)
    except (TypeError, ValueError):
        return 0


def _session_username(row: Any) -> str:
    if not isinstance(row, dict):
        return ""
    for key in ("username", "user_name", "UserName"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _session_last_local_id(row: Any) -> int:
    if not isinstance(row, dict):
        return 0
    for key in (
        "last_msg_locald_id",
        "last_msg_local_id",
        "lastMsgLocaldId",
        "lastMsgLocalId",
    ):
        try:
            value = int(row.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    return 0


def _session_name(row: Any) -> str:
    if not isinstance(row, dict):
        return ""
    for key in (
        "conversationName",
        "conversation_name",
        "displayName",
        "display_name",
        "name",
        "nick_name",
        "nickname",
        "remark",
    ):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _json_default(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _sse_data(payload: dict[str, Any], *, event_id: str = "") -> str:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=_json_default)
    prefix = f"id: {event_id}\n" if event_id else ""
    return f"{prefix}data: {encoded}\n\n"


def _read_native_sessions(connection: Any) -> list[dict[str, Any]]:
    with connection.lock:
        rows = _wcdb_get_sessions(connection.handle)
    return [row for row in rows or [] if isinstance(row, dict)]


def _conversation_metadata(
    account_dir: Path,
    connection: Any,
    username: str,
    *,
    session_row: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Resolve the current conversation name without adding a native API."""

    conversation_id = str(username or "").strip()
    raw_name = _session_name(session_row)
    contact_row = _load_contact_rows(Path(account_dir) / "contact.db", [conversation_id]).get(
        conversation_id
    )
    local_name = _pick_display_name(contact_row, conversation_id)
    native_name = ""
    if conversation_id.endswith("@chatroom") or local_name == conversation_id:
        try:
            with connection.lock:
                native_name = str(
                    (_wcdb_get_display_names(connection.handle, [conversation_id]) or {}).get(conversation_id) or ""
                ).strip()
        except Exception:
            native_name = ""

    if conversation_id.endswith("@chatroom") and native_name and native_name != conversation_id:
        name, source = native_name, "native"
    elif raw_name and raw_name != conversation_id:
        name, source = raw_name, "native"
    elif native_name and native_name != conversation_id:
        name, source = native_name, "native"
    elif local_name and local_name != conversation_id:
        name, source = local_name, "contact.db"
    else:
        name, source = conversation_id, "username"

    return {
        "conversationId": conversation_id,
        "conversationName": name,
        "conversationNameReady": bool(name and name != conversation_id),
        "conversationNameSource": source,
    }


async def _message_page(
    request: Request,
    *,
    account: str,
    username: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    # Import lazily to avoid an import cycle with the existing chat router.
    from .chat import list_chat_messages

    result = await asyncio.to_thread(
        list_chat_messages,
        request,
        username=username,
        account=account,
        limit=limit,
        offset=offset,
        order="desc",
        render_types=None,
        filter_mode=None,
        scan_offset=0,
        scan_limit=limit,
        source="realtime",
    )
    if str(result.get("source") or "").strip().lower() != "realtime":
        raise RuntimeError("realtime message source is unavailable")
    return result


async def _new_messages(
    request: Request,
    *,
    account: str,
    username: str,
    cursor: int,
    include_sent: bool,
) -> tuple[list[dict[str, Any]], int]:
    """Read pages newest-first, returning rows newer than ``cursor``.

    The cursor advances across sent rows too; otherwise an outgoing message
    would be scanned and rejected on every subsequent poll.
    """

    emitted: list[dict[str, Any]] = []
    next_cursor = int(cursor)
    offset = 0
    while True:
        result = await _message_page(
            request,
            account=account,
            username=username,
            limit=_MESSAGE_PAGE_SIZE,
            offset=offset,
        )
        page = [item for item in (result.get("messages") or []) if isinstance(item, dict)]
        if not page:
            break

        page_ids = [_message_local_id(item) for item in page]
        page_ids = [value for value in page_ids if value > 0]
        if page_ids:
            next_cursor = max(next_cursor, max(page_ids))

        for message in sorted(page, key=_message_local_id):
            local_id = _message_local_id(message)
            if local_id <= int(cursor):
                continue
            if not include_sent and bool(message.get("isSent")):
                continue
            emitted.append(message)

        oldest_id = min(page_ids) if page_ids else 0
        if oldest_id <= int(cursor) or not bool(result.get("hasMore")):
            break
        offset += len(page)
        if len(page) < _MESSAGE_PAGE_SIZE:
            break

    # A malformed/reordered page must never move a cursor backwards.
    emitted.sort(key=_message_local_id)
    return emitted, next_cursor


async def _initial_cursor(
    request: Request,
    *,
    account: str,
    username: str,
    since_local_id: int,
) -> int:
    if int(since_local_id) > 0:
        return int(since_local_id)
    result = await _message_page(
        request,
        account=account,
        username=username,
        limit=1,
        offset=0,
    )
    return max((_message_local_id(item) for item in result.get("messages") or []), default=0)


@router.get(
    "/api/chat/realtime/messages",
    summary="实时接收聊天消息（SSE）",
)
async def stream_chat_realtime_messages(
    request: Request,
    account: Optional[str] = None,
    username: Optional[str] = None,
    interval_ms: int = _DEFAULT_INTERVAL_MS,
    since_local_id: int = 0,
    include_sent: bool = False,
):
    """Keep one connection open and emit complete newly received messages.

    ``username`` limits the stream to one conversation.  When omitted, the
    native session list is checked and only conversations whose latest local
    id advanced are queried.  The default cursor is the latest row at connect
    time, so only messages arriving after the connection are emitted.
    """

    interval_ms = int(interval_ms)
    try:
        since_local_id = max(0, int(since_local_id or 0))
    except (TypeError, ValueError):
        since_local_id = 0

    account_dir = _resolve_account_dir(account)
    account_name = account_dir.name
    username_norm = str(username or "").strip() or None
    if since_local_id and not username_norm:
        raise HTTPException(status_code=400, detail="since_local_id requires username")
    if username_norm and since_local_id == 0:
        try:
            last_event_local_id = int(str(request.headers.get("last-event-id") or "").rsplit(":", 1)[-1])
        except (TypeError, ValueError):
            last_event_local_id = 0
        since_local_id = max(since_local_id, last_event_local_id)

    try:
        connection = await asyncio.to_thread(WCDB_REALTIME.ensure_connected, account_dir)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"realtime source unavailable: {exc}") from exc

    async def gen():
        cursors: dict[str, int] = {}
        metadata_by_name: dict[str, dict[str, Any]] = {}
        session_rows_by_name: dict[str, dict[str, Any]] = {}
        if username_norm:
            cursors[username_norm] = await _initial_cursor(
                request,
                account=account_name,
                username=username_norm,
                since_local_id=since_local_id,
            )
            metadata_by_name[username_norm] = await asyncio.to_thread(
                _conversation_metadata,
                account_dir,
                connection,
                username_norm,
            )
        else:
            for row in await asyncio.to_thread(_read_native_sessions, connection):
                name = _session_username(row)
                if name:
                    cursors[name] = _session_last_local_id(row)
                    session_rows_by_name[name] = row

        ready = {
            "type": "ready",
            "account": account_name,
            "username": username_norm,
            "mode": "incoming" if not include_sent else "all",
            "cursor": cursors.get(username_norm) if username_norm else None,
            "conversationCount": len(cursors),
            "intervalMs": interval_ms,
            "ts": int(time.time() * 1000),
        }
        ready.update(
            metadata_by_name.get(
                username_norm,
                {
                    "conversationId": None,
                    "conversationName": None,
                    "conversationNameReady": False,
                    "conversationNameSource": "none",
                },
            )
        )
        yield _sse_data(ready)

        last_error_at = 0.0
        last_heartbeat_at = time.monotonic()
        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    if username_norm:
                        names = [username_norm]
                    else:
                        names = []
                        current_connection = await asyncio.to_thread(
                            WCDB_REALTIME.ensure_connected,
                            account_dir,
                        )
                        session_rows_by_name = {}
                        for row in await asyncio.to_thread(_read_native_sessions, current_connection):
                            name = _session_username(row)
                            if not name:
                                continue
                            session_rows_by_name[name] = row
                            latest = _session_last_local_id(row)
                            if name not in cursors:
                                cursors[name] = since_local_id
                                names.append(name)
                            elif latest > int(cursors[name]):
                                names.append(name)

                    for name in dict.fromkeys(names):
                        before = int(cursors.get(name, since_local_id))
                        messages, after = await _new_messages(
                            request,
                            account=account_name,
                            username=name,
                            cursor=before,
                            include_sent=bool(include_sent),
                        )
                        cursors[name] = max(before, int(after))
                        metadata = await asyncio.to_thread(
                            _conversation_metadata,
                            account_dir,
                            current_connection if not username_norm else connection,
                            name,
                            session_row=session_rows_by_name.get(name),
                        )
                        previous_metadata = metadata_by_name.get(name)
                        metadata_by_name[name] = metadata
                        if (
                            previous_metadata is not None
                            and previous_metadata.get("conversationName") != metadata.get("conversationName")
                        ):
                            yield _sse_data(
                                {
                                    "type": "conversation_updated",
                                    "account": account_name,
                                    "username": name,
                                    "ts": int(time.time() * 1000),
                                    **metadata,
                                }
                            )
                        for message in messages:
                            local_id = _message_local_id(message)
                            payload = {
                                "type": "message",
                                "account": account_name,
                                "username": name,
                                "received": not bool(message.get("isSent")),
                                "cursor": local_id,
                                "ts": int(time.time() * 1000),
                                "message": message,
                                **metadata,
                            }
                            yield _sse_data(
                                payload,
                                event_id=f"{account_name}:{name}:{local_id}",
                            )
                except Exception:
                    now = time.monotonic()
                    if now - last_error_at >= 5.0:
                        last_error_at = now
                        logger_payload = {
                            "type": "error",
                            "code": "realtime_poll_failed",
                            "retryAfterMs": 1000,
                            "ts": int(time.time() * 1000),
                        }
                        yield _sse_data(logger_payload)
                    await asyncio.sleep(1.0)
                    continue

                if time.monotonic() - last_heartbeat_at >= 15.0:
                    yield ": ping\n\n"
                    last_heartbeat_at = time.monotonic()
                await asyncio.sleep(interval_ms / 1000.0)
        finally:
            # The cached WCDB connection is owned by WCDB_REALTIME and is not
            # closed per client stream; closing it here would break other users.
            pass

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
