from __future__ import annotations

import json
import math
import threading
import time
from typing import Any, Callable


CHAT_REQUEST_PERF_PREFIX = "[perf.chat.request-boundary]"
_CHAT_MESSAGES_PATH = "/api/chat/messages"
_REQUEST_PERF_STATE_KEY = "wcda_request_perf"


def create_perf_trace(
    logger: Any,
    category: str,
    *,
    trace_id: str | None = None,
    started_at: float | None = None,
    **base_fields: Any,
) -> tuple[str, Callable[[str], None]]:
    trace_id = trace_id or f"{category}-{int(time.time() * 1000)}-{threading.get_ident()}"
    started_at = started_at if started_at is not None else time.perf_counter()
    last_at = started_at

    def log(phase: str, **fields: Any) -> None:
        nonlocal last_at
        now = time.perf_counter()
        payload = {
            **base_fields,
            **fields,
            "elapsedMs": round((now - started_at) * 1000.0, 1),
            "deltaMs": round((now - last_at) * 1000.0, 1),
        }
        last_at = now
        try:
            payload_text = json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:
            payload_text = str(payload)
        logger.info("[%s] %s %s %s", trace_id, category, phase, payload_text)

    return trace_id, log


def get_request_perf_context(request: Any) -> dict[str, Any]:
    state = getattr(request, "state", None)
    value = getattr(state, _REQUEST_PERF_STATE_KEY, None) if state is not None else None
    return value if isinstance(value, dict) else {}


class ChatRequestPerfMiddleware:
    """Opt-in ASGI boundary timing for instrumented chat message requests."""

    def __init__(self, app: Any, *, logger: Any) -> None:
        self.app = app
        self.logger = logger

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if (
            scope.get("type") == "http"
            and str(scope.get("method") or "").upper() == "GET"
            and scope.get("path") == _CHAT_MESSAGES_PATH
        ):
            headers = dict(scope.get("headers") or ())
            raw_client_trace_id = headers.get(b"x-wcda-perf-trace", b"")
            if raw_client_trace_id:
                client_trace_id = raw_client_trace_id.decode("latin-1", errors="replace")[:128]
                raw_client_sent_ms = headers.get(b"x-wcda-perf-sent-ms", b"")
                try:
                    client_sent_ms = float(raw_client_sent_ms.decode("ascii"))
                    if not math.isfinite(client_sent_ms):
                        client_sent_ms = None
                except (UnicodeDecodeError, ValueError):
                    client_sent_ms = None

                arrived_perf = time.perf_counter()
                arrived_epoch_ms = time.time_ns() / 1_000_000
                server_trace_id = f"chat.messages-{time.time_ns()}"
                state = scope.setdefault("state", {})
                state[_REQUEST_PERF_STATE_KEY] = {
                    "traceId": server_trace_id,
                    "clientTraceId": client_trace_id,
                    "clientSentEpochMs": client_sent_ms,
                    "asgiArrivedEpochMs": arrived_epoch_ms,
                    "asgiArrivedPerf": arrived_perf,
                }
                payload = {
                    "traceId": server_trace_id,
                    "clientTraceId": client_trace_id,
                    "clientSentEpochMs": client_sent_ms,
                    "asgiArrivedEpochMs": round(arrived_epoch_ms, 3),
                    "clientToAsgiMs": (
                        round(arrived_epoch_ms - client_sent_ms, 1)
                        if client_sent_ms is not None
                        else None
                    ),
                    "method": "GET",
                    "path": _CHAT_MESSAGES_PATH,
                }
                self.logger.info(
                    "%s arrival %s",
                    CHAT_REQUEST_PERF_PREFIX,
                    json.dumps(payload, ensure_ascii=False),
                )

        await self.app(scope, receive, send)
