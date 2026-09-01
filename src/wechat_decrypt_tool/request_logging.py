from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import unquote_plus

from starlette.requests import Request
from starlette.responses import Response


_CONTENT_LOG_KEYS = {
    "contentbase64",
    "contentb64",
    "database64",
    "datab64",
    "filebase64",
    "fileb64",
    "protectedcontentbase64",
}
_SECRET_LOG_KEYS = {
    "apikey",
    "aeskey",
    "auth",
    "authorization",
    "cookie",
    "cookies",
    "credential",
    "databasekey",
    "dbkey",
    "encryptionkey",
    "key",
    "keyhex",
    "imageaeskey",
    "imagexorkey",
    "mcptoken",
    "password",
    "privatekey",
    "refreshtoken",
    "secret",
    "secretkey",
    "setcookie",
    "token",
    "xorkey",
}


def _normalized_log_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key or "").lower())


def _redacted_content_marker(value: Any) -> str:
    try:
        length = len(value)
    except Exception:
        return "<redacted>"
    return f"<redacted length={length}>"


def _is_sensitive_log_key(key: Any) -> bool:
    normalized = _normalized_log_key(key)
    return bool(
        normalized in _SECRET_LOG_KEYS
        or normalized.endswith("password")
        or normalized.endswith("secret")
        or normalized.endswith("token")
    )


def redact_sensitive_log_data(value: Any, *, _depth: int = 0) -> Any:
    """Return a log-safe copy of structured request or error data."""
    if _depth >= 20:
        return "<redacted max-depth>"
    if isinstance(value, Mapping):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            normalized = _normalized_log_key(key)
            if normalized in _CONTENT_LOG_KEYS or normalized.endswith(("base64", "b64")):
                redacted[key] = _redacted_content_marker(item)
            elif _is_sensitive_log_key(key):
                redacted[key] = "<redacted>"
            else:
                redacted[key] = redact_sensitive_log_data(item, _depth=_depth + 1)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive_log_data(item, _depth=_depth + 1) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_log_data(item, _depth=_depth + 1) for item in value)
    return value


def redact_sensitive_query_text(value: Any) -> str:
    """Redact sensitive query values without decoding or rewriting unrelated values."""
    text = str(value or "")
    if "?" not in text:
        return text

    prefix, query = text.split("?", 1)
    redacted_parts: list[str] = []
    for part in query.split("&"):
        raw_key, separator, raw_value = part.partition("=")
        try:
            decoded_key = unquote_plus(raw_key)
        except Exception:
            decoded_key = raw_key
        if separator and _is_sensitive_log_key(decoded_key):
            redacted_parts.append(f"{raw_key}=<redacted>")
        else:
            redacted_parts.append(part)
    return f"{prefix}?{'&'.join(redacted_parts)}"


class SensitiveQueryLogFilter(logging.Filter):
    """Redact the path argument used by Uvicorn's access-log record."""

    _wda_sensitive_query_filter = True

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3:
            updated = list(args)
            updated[2] = redact_sensitive_query_text(updated[2])
            record.args = tuple(updated)
        return True


def _stringify_detail(detail: Any) -> str:
    if detail is None:
        return ""
    if isinstance(detail, str):
        return detail.strip()
    safe_detail = redact_sensitive_log_data(detail)
    try:
        return json.dumps(safe_detail, ensure_ascii=False)
    except Exception:
        return str(safe_detail).strip()


def _extract_response_detail(response: Response) -> str:
    body = getattr(response, "body", None)
    if body is None:
        return ""

    try:
        raw = body.tobytes() if isinstance(body, memoryview) else body
    except Exception:
        raw = body

    if isinstance(raw, bytes):
        text = raw.decode("utf-8", errors="ignore").strip()
    else:
        text = str(raw).strip()
    if not text:
        return ""

    content_type = str(response.headers.get("content-type") or "").lower()
    if "json" not in content_type:
        return ""

    try:
        payload = json.loads(text)
    except Exception:
        return ""

    if not isinstance(payload, dict):
        return ""
    return _stringify_detail(payload.get("detail"))


async def _buffer_response_body(response: Response) -> tuple[Response, bytes]:
    body = getattr(response, "body", None)
    if body is not None:
        try:
            raw = body.tobytes() if isinstance(body, memoryview) else body
        except Exception:
            raw = body
        if isinstance(raw, bytes):
            return response, raw
        if isinstance(raw, str):
            return response, raw.encode("utf-8")
        return response, bytes(raw)

    chunks: list[bytes] = []
    body_iterator = getattr(response, "body_iterator", None)
    if body_iterator is not None:
        async for chunk in body_iterator:
            if isinstance(chunk, memoryview):
                chunks.append(chunk.tobytes())
            elif isinstance(chunk, bytes):
                chunks.append(chunk)
            else:
                chunks.append(str(chunk).encode("utf-8"))

    body_bytes = b"".join(chunks)
    rebuilt = Response(
        content=body_bytes,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type,
        background=response.background,
    )
    return rebuilt, body_bytes


def _extract_response_detail_from_body(response: Response, body: bytes) -> str:
    if not body:
        return ""

    try:
        text = body.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""
    if not text:
        return ""

    content_type = str(response.headers.get("content-type") or "").lower()
    if "json" not in content_type:
        return ""

    try:
        payload = json.loads(text)
    except Exception:
        return ""

    if not isinstance(payload, dict):
        return ""
    return _stringify_detail(payload.get("detail"))


async def log_server_errors_middleware(logger, request: Request, call_next):
    method = str(request.method or "").upper() or "GET"
    path = str(request.url.path or "").strip() or "/"

    try:
        response = await call_next(request)
    except Exception as exc:
        logger.exception("[server-exception] method=%s path=%s error=%s", method, path, exc)
        raise

    status = int(getattr(response, "status_code", 0) or 0)
    if status >= 500:
        response, body = await _buffer_response_body(response)
        detail = _extract_response_detail_from_body(response, body) or _extract_response_detail(response)
        if detail:
            logger.error("[server-5xx] status=%s method=%s path=%s detail=%s", status, method, path, detail)
        else:
            logger.error("[server-5xx] status=%s method=%s path=%s", status, method, path)

    return response
