import asyncio

from starlette.requests import Request

from wechat_decrypt_tool.perf_trace import (
    CHAT_REQUEST_PERF_PREFIX,
    ChatRequestPerfMiddleware,
    get_request_perf_context,
)


class _Logger:
    def __init__(self):
        self.records = []

    def info(self, message, *args):
        self.records.append(message % args)


def _run_request(logger, *, path="/api/chat/messages", headers=()):
    captured = {}

    async def app(scope, receive, send):
        captured.update(get_request_perf_context(Request(scope)))

    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"username=must-not-be-logged",
        "headers": list(headers),
        "state": {},
    }
    asyncio.run(ChatRequestPerfMiddleware(app, logger=logger)(scope, None, None))
    return captured


def test_chat_request_perf_probe_is_opt_in_and_query_free():
    logger = _Logger()

    context = _run_request(
        logger,
        headers=(
            (b"x-wcda-perf-trace", b"ui-123"),
            (b"x-wcda-perf-sent-ms", b"1700000000000.5"),
        ),
    )

    assert context["clientTraceId"] == "ui-123"
    assert context["clientSentEpochMs"] == 1700000000000.5
    assert context["traceId"].startswith("chat.messages-")
    assert len(logger.records) == 1
    assert logger.records[0].startswith(f"{CHAT_REQUEST_PERF_PREFIX} arrival ")
    assert "must-not-be-logged" not in logger.records[0]

    assert _run_request(logger) == {}
    assert _run_request(logger, path="/api/chat/sessions") == {}
    assert len(logger.records) == 1
