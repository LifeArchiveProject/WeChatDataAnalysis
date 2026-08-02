from __future__ import annotations

import base64
import json
import secrets
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

ProductEventType = Literal[
    "app_open",
    "database_open",
    "conversation_list",
    "message_page",
    "search",
    "export_started",
    "export_completed",
    "export_failed",
]

_ALLOWED_EVENT_TYPES = frozenset(
    {
        "app_open",
        "database_open",
        "conversation_list",
        "message_page",
        "search",
        "export_started",
        "export_completed",
        "export_failed",
    }
)
_MAX_PENDING_EVENTS = 512
_MAX_BATCH_EVENTS = 64
_MAX_RESPONSE_BYTES = 16 * 1024
_MAX_EVENT_AGE_SECONDS = 29 * 24 * 60 * 60
_RETRY_INITIAL_SECONDS = 30.0
_RETRY_MAX_SECONDS = 15.0 * 60.0


@dataclass(frozen=True, slots=True)
class ProductTelemetryContext:
    events_url: str
    credential: str
    device_id: bytes
    build_id: bytes


class _RejectTelemetryRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        del new_url
        raise urllib.error.HTTPError(
            request.full_url,
            code,
            "Product telemetry redirects are not allowed.",
            headers,
            response,
        )


class _PermanentTelemetryRejection(Exception):
    pass


TelemetrySender = Callable[[ProductTelemetryContext, Sequence[dict[str, object]]], None]


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _events_url(license_url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(str(license_url or "").strip())
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("Native core telemetry service URL is invalid.") from exc
    suffix = "/v1/leases"
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or not parsed.path.endswith(suffix)
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Native core telemetry requires the HTTPS license service URL."
        )
    path = parsed.path[: -len(suffix)] + "/v1/events"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _bound_identifier(value: bytes, *, name: str) -> bytes:
    identifier = bytes(value)
    if len(identifier) != 32 or not any(identifier):
        raise ValueError(f"Native core telemetry {name} binding is invalid.")
    return identifier


def _device_credential(value: str) -> str:
    credential = str(value or "")
    try:
        encoded = credential.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("Native core telemetry credential is invalid.") from exc
    if (
        not credential.startswith("wcd1.")
        or credential != credential.strip()
        or len(encoded) < 32
        or len(encoded) > 4096
        or any(byte < 0x21 or byte > 0x7E for byte in encoded)
    ):
        raise ValueError("Native core telemetry requires a device credential.")
    return credential


def _post_events(
    context: ProductTelemetryContext,
    events: Sequence[dict[str, object]],
) -> None:
    encoded = json.dumps(
        {"events": list(events)},
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    request = urllib.request.Request(
        context.events_url,
        data=encoded,
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {context.credential}",
            "Content-Type": "application/json",
            "User-Agent": "WeChatDataAnalysis-NativeCore/2",
        },
    )
    opener = urllib.request.build_opener(
        _RejectTelemetryRedirects(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
    )
    try:
        with opener.open(request, timeout=5.0) as response:
            content_type = str(response.headers.get("Content-Type", "") or "")
            if content_type.split(";", 1)[0].strip().lower() != "application/json":
                raise OSError("Product telemetry returned a non-JSON response.")
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise _PermanentTelemetryRejection from None
        raise OSError("Product telemetry request failed.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OSError("Product telemetry service is unavailable.") from exc
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise OSError("Product telemetry response is too large.")
    try:
        payload = json.loads(raw.decode("utf-8"))
        accepted = payload["accepted"]
        duplicates = payload["duplicates"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise OSError("Product telemetry response is invalid.") from exc
    if (
        type(accepted) is not int
        or type(duplicates) is not int
        or accepted < 0
        or duplicates < 0
        or accepted + duplicates != len(events)
    ):
        raise OSError("Product telemetry response is invalid.")


class ProductTelemetry:
    """Best-effort, content-free product events sent outside request threads."""

    def __init__(
        self,
        *,
        sender: TelemetrySender = _post_events,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
        start_worker: bool = True,
    ) -> None:
        self._sender = sender
        self._clock = clock
        self._monotonic = monotonic
        self._start_worker_enabled = bool(start_worker)
        self._condition = threading.Condition(threading.RLock())
        self._pending: deque[dict[str, object]] = deque(maxlen=_MAX_PENDING_EVENTS)
        self._context: ProductTelemetryContext | None = None
        self._worker: threading.Thread | None = None
        self._stopped = False
        self._retry_seconds = _RETRY_INITIAL_SECONDS
        self._next_attempt_monotonic = 0.0

    @property
    def pending_count(self) -> int:
        with self._condition:
            return len(self._pending)

    def configure(
        self,
        *,
        license_url: str,
        credential: str,
        device_id: bytes,
        build_id: bytes,
    ) -> None:
        context = ProductTelemetryContext(
            events_url=_events_url(license_url),
            credential=_device_credential(credential),
            device_id=_bound_identifier(device_id, name="device"),
            build_id=_bound_identifier(build_id, name="build"),
        )
        with self._condition:
            if self._stopped:
                return
            if self._context != context:
                self._context = context
                self._retry_seconds = _RETRY_INITIAL_SECONDS
                self._next_attempt_monotonic = 0.0
            self._ensure_worker_locked()
            self._condition.notify_all()

    def clear_context(self) -> None:
        with self._condition:
            self._context = None
            self._next_attempt_monotonic = 0.0
            self._condition.notify_all()

    def record(self, event_type: ProductEventType | str) -> None:
        normalized = str(event_type or "")
        if normalized not in _ALLOWED_EVENT_TYPES:
            raise ValueError("Unsupported product event type.")
        event = {
            "eventId": _base64url(secrets.token_bytes(16)),
            "eventType": normalized,
            "occurredAt": int(self._clock()),
        }
        with self._condition:
            if self._stopped:
                return
            self._pending.append(event)
            self._ensure_worker_locked()
            self._condition.notify_all()

    def flush_once(self) -> bool:
        with self._condition:
            context = self._context
            now = int(self._clock())
            oldest = now - _MAX_EVENT_AGE_SECONDS
            while self._pending and int(self._pending[0]["occurredAt"]) < oldest:
                self._pending.popleft()
            batch = list(self._pending)[:_MAX_BATCH_EVENTS]
        if context is None or not batch:
            return False
        event_ids = {str(event["eventId"]) for event in batch}
        try:
            self._sender(context, batch)
        except _PermanentTelemetryRejection:
            with self._condition:
                if self._context == context:
                    self._context = None
            return False
        except OSError:
            return False
        with self._condition:
            self._pending = deque(
                (
                    event
                    for event in self._pending
                    if str(event.get("eventId") or "") not in event_ids
                ),
                maxlen=_MAX_PENDING_EVENTS,
            )
        return True

    def shutdown(self, *, timeout: float = 1.0) -> None:
        with self._condition:
            self._stopped = True
            worker = self._worker
            self._condition.notify_all()
        if (
            worker is not None
            and worker is not threading.current_thread()
            and worker.is_alive()
        ):
            worker.join(timeout=max(0.0, float(timeout)))

    def _ensure_worker_locked(self) -> None:
        if not self._start_worker_enabled or self._stopped:
            return
        if self._worker is not None and self._worker.is_alive():
            return
        self._worker = threading.Thread(
            target=self._worker_main,
            name="wechatdb-product-telemetry",
            daemon=True,
        )
        self._worker.start()

    def _worker_main(self) -> None:
        while True:
            with self._condition:
                while not self._stopped:
                    ready = self._context is not None and bool(self._pending)
                    if ready:
                        delay = self._next_attempt_monotonic - self._monotonic()
                        if delay <= 0:
                            break
                        self._condition.wait(delay)
                    else:
                        self._condition.wait()
                if self._stopped:
                    return
            if self.flush_once():
                with self._condition:
                    self._retry_seconds = _RETRY_INITIAL_SECONDS
                    self._next_attempt_monotonic = 0.0
                continue
            with self._condition:
                if self._context is None or not self._pending:
                    self._next_attempt_monotonic = 0.0
                    continue
                self._next_attempt_monotonic = self._monotonic() + self._retry_seconds
                self._retry_seconds = min(
                    _RETRY_MAX_SECONDS,
                    self._retry_seconds * 2.0,
                )


_PRODUCT_TELEMETRY = ProductTelemetry()


def configure_product_telemetry(
    *,
    license_url: str,
    credential: str,
    device_id: bytes,
    build_id: bytes,
) -> None:
    try:
        _PRODUCT_TELEMETRY.configure(
            license_url=license_url,
            credential=credential,
            device_id=device_id,
            build_id=build_id,
        )
    except Exception:  # noqa: BLE001 - telemetry must never fail a licensed operation.
        return


def clear_product_telemetry_context() -> None:
    try:
        _PRODUCT_TELEMETRY.clear_context()
    except Exception:  # noqa: BLE001 - teardown is strictly best effort.
        return


def record_product_event(event_type: ProductEventType) -> None:
    try:
        _PRODUCT_TELEMETRY.record(event_type)
    except Exception:  # noqa: BLE001 - recording is outside the product hot path.
        return


def shutdown_product_telemetry() -> None:
    try:
        _PRODUCT_TELEMETRY.shutdown()
    except Exception:  # noqa: BLE001 - application shutdown must continue.
        return


def _reset_product_telemetry_for_tests() -> None:
    global _PRODUCT_TELEMETRY
    _PRODUCT_TELEMETRY.shutdown()
    _PRODUCT_TELEMETRY = ProductTelemetry()


__all__ = [
    "ProductEventType",
    "ProductTelemetry",
    "ProductTelemetryContext",
    "clear_product_telemetry_context",
    "configure_product_telemetry",
    "record_product_event",
    "shutdown_product_telemetry",
]
