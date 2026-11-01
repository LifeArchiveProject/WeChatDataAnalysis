from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest
from starlette.requests import Request
from starlette.responses import Response

from wechat_decrypt_tool import api
from wechat_decrypt_tool.native_core_telemetry import ProductTelemetry

_LICENSE_URL = "https://license.example.invalid/v1/leases"
_CREDENTIAL = "wcd1." + ("c" * 64)


def _configure(telemetry: ProductTelemetry) -> None:
    telemetry.configure(
        license_url=_LICENSE_URL,
        credential=_CREDENTIAL,
        device_id=b"d" * 32,
        build_id=b"b" * 32,
    )


def test_content_free_events_wait_for_device_context_and_send_exact_schema() -> None:
    sent: list[tuple[object, list[dict[str, object]]]] = []

    def sender(context, events) -> None:
        sent.append((context, [dict(event) for event in events]))

    telemetry = ProductTelemetry(
        sender=sender,
        clock=lambda: 1_800_000_000,
        start_worker=False,
    )
    telemetry.record("app_open")
    telemetry.record("search")

    assert telemetry.pending_count == 2
    assert telemetry.flush_once() is False

    _configure(telemetry)
    assert telemetry.flush_once() is True
    assert telemetry.pending_count == 0
    assert len(sent) == 1
    context, events = sent[0]
    assert context.events_url == "https://license.example.invalid/v1/events"
    assert context.credential == _CREDENTIAL
    assert [event["eventType"] for event in events] == ["app_open", "search"]
    assert all(set(event) == {"eventId", "eventType", "occurredAt"} for event in events)
    assert all(len(str(event["eventId"])) == 22 for event in events)
    assert all(event["occurredAt"] == 1_800_000_000 for event in events)


def test_failed_delivery_keeps_the_same_idempotency_key_for_retry() -> None:
    attempts: list[list[dict[str, object]]] = []

    def sender(_context, events) -> None:
        attempts.append([dict(event) for event in events])
        if len(attempts) == 1:
            raise OSError("offline")

    telemetry = ProductTelemetry(sender=sender, start_worker=False)
    _configure(telemetry)
    telemetry.record("message_page")

    assert telemetry.flush_once() is False
    assert telemetry.pending_count == 1
    assert telemetry.flush_once() is True
    assert telemetry.pending_count == 0
    assert attempts[0][0]["eventId"] == attempts[1][0]["eventId"]


def test_recording_never_waits_for_the_network_sender() -> None:
    sender_entered = threading.Event()
    release_sender = threading.Event()

    def sender(_context, _events) -> None:
        sender_entered.set()
        release_sender.wait(timeout=2.0)

    telemetry = ProductTelemetry(sender=sender)
    try:
        _configure(telemetry)
        telemetry.record("conversation_list")
        assert sender_entered.wait(timeout=1.0)
        assert telemetry.pending_count == 1
    finally:
        release_sender.set()
        deadline = time.monotonic() + 1.0
        while telemetry.pending_count and time.monotonic() < deadline:
            time.sleep(0.01)
        telemetry.shutdown()

    assert telemetry.pending_count == 0


@pytest.mark.parametrize(
    ("license_url", "credential"),
    [
        ("http://license.example.invalid/v1/leases", _CREDENTIAL),
        ("https://license.example.invalid/v1/events", _CREDENTIAL),
        (_LICENSE_URL, "wcl1." + ("a" * 64)),
        (_LICENSE_URL, "wcd1.bad\nheader"),
    ],
)
def test_configuration_rejects_non_https_or_non_device_credentials(
    license_url: str,
    credential: str,
) -> None:
    telemetry = ProductTelemetry(start_worker=False)
    with pytest.raises(ValueError):
        telemetry.configure(
            license_url=license_url,
            credential=credential,
            device_id=b"d" * 32,
            build_id=b"b" * 32,
        )


def test_event_api_has_no_metadata_channel() -> None:
    telemetry = ProductTelemetry(start_worker=False)
    with pytest.raises(ValueError):
        telemetry.record("message_with_search_term")
    with pytest.raises(TypeError):
        telemetry.record("search", {"query": "must stay local"})  # type: ignore[call-arg]


def _request(method: str, path: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"secret=must-not-be-observed",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 10392),
        }
    )


def test_api_middleware_records_only_fixed_route_outcomes() -> None:
    recorded: list[str] = []

    async def success(_request: Request) -> Response:
        return Response(status_code=200)

    async def rejected(_request: Request) -> Response:
        return Response(status_code=500)

    with patch.object(api, "record_product_event", side_effect=recorded.append):
        import asyncio

        asyncio.run(
            api._record_content_free_product_events(
                _request("GET", "/api/chat/messages"), success
            )
        )
        asyncio.run(
            api._record_content_free_product_events(
                _request("GET", "/api/chat/search-index/status"), success
            )
        )
        asyncio.run(
            api._record_content_free_product_events(
                _request("POST", "/api/chat/contacts/export"), success
            )
        )
        asyncio.run(
            api._record_content_free_product_events(
                _request("POST", "/api/chat/exports"), success
            )
        )
        asyncio.run(
            api._record_content_free_product_events(
                _request("POST", "/api/sns/exports"), rejected
            )
        )

    assert recorded == [
        "message_page",
        "export_started",
        "export_completed",
        "export_started",
        "export_started",
        "export_failed",
    ]
