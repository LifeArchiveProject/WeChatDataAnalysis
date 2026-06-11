from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException


JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603


@dataclass
class McpError(Exception):
    code: int
    message: str
    data: Any = None


def error_from_exception(exc: Exception) -> McpError:
    if isinstance(exc, McpError):
        return exc
    if isinstance(exc, HTTPException):
        return McpError(
            JSONRPC_INVALID_PARAMS if int(exc.status_code or 500) < 500 else JSONRPC_INTERNAL_ERROR,
            str(exc.detail or "HTTP error"),
            {"httpStatus": int(exc.status_code or 500)},
        )
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        return McpError(JSONRPC_INVALID_PARAMS, str(exc) or "Invalid params")
    return McpError(JSONRPC_INTERNAL_ERROR, "Internal error", {"detail": str(exc)})

