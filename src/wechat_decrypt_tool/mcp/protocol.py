from __future__ import annotations

from typing import Any

from .errors import (
    JSONRPC_INVALID_REQUEST,
    JSONRPC_METHOD_NOT_FOUND,
    JSONRPC_PARSE_ERROR,
    McpError,
    error_from_exception,
)
from .registry import McpToolContext, McpToolRegistry

PROTOCOL_VERSION = "2025-06-18"


def jsonrpc_result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def jsonrpc_error(request_id: Any, error: McpError) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": error.code, "message": error.message}
    if error.data is not None:
        payload["data"] = error.data
    return {"jsonrpc": "2.0", "id": request_id, "error": payload}


def initialize_result() -> dict[str, Any]:
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": "wechat-data-analysis-mcp", "version": "1.0.0"},
        "instructions": (
            "Use this MCP server to inspect local WeChatDataAnalysis data. "
            "Prefer resolve tools before broad message queries. Keep list limits small and expand details only when needed."
        ),
    }


async def handle_jsonrpc_payload(payload: Any, registry: McpToolRegistry, context: McpToolContext) -> Any:
    if isinstance(payload, list):
        if not payload:
            return jsonrpc_error(None, McpError(JSONRPC_INVALID_REQUEST, "Invalid Request"))
        responses = []
        for item in payload:
            response = await handle_jsonrpc_request(item, registry, context)
            if response is not None:
                responses.append(response)
        return responses or None
    return await handle_jsonrpc_request(payload, registry, context)


async def handle_jsonrpc_request(request_obj: Any, registry: McpToolRegistry, context: McpToolContext) -> dict[str, Any] | None:
    if not isinstance(request_obj, dict):
        return jsonrpc_error(None, McpError(JSONRPC_INVALID_REQUEST, "Invalid Request"))

    if "method" not in request_obj:
        if request_obj.get("jsonrpc") == "2.0" and ("result" in request_obj or "error" in request_obj):
            return None
        return jsonrpc_error(request_obj.get("id"), McpError(JSONRPC_INVALID_REQUEST, "Invalid Request"))

    request_id = request_obj.get("id")
    is_notification = "id" not in request_obj
    method_value = request_obj.get("method")
    method = method_value.strip() if isinstance(method_value, str) else ""
    if request_obj.get("jsonrpc") != "2.0" or not method:
        return None if is_notification else jsonrpc_error(request_id, McpError(JSONRPC_INVALID_REQUEST, "Invalid Request"))

    if is_notification and method == "notifications/initialized":
        return None

    try:
        params = request_obj.get("params")
        if method == "initialize":
            result = initialize_result()
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            params_dict = params if isinstance(params, dict) else {}
            result = registry.list_tools(
                cursor=params_dict.get("cursor"),
                limit=params_dict.get("limit"),
            )
        elif method == "tools/call":
            if not isinstance(params, dict):
                raise ValueError("params is required.")
            name = str(params.get("name") or "").strip()
            if not name:
                raise ValueError("Tool name is required.")
            arguments = params["arguments"] if "arguments" in params else {}
            result = await registry.call_tool(name, arguments, context)
        elif registry.has_tool(method):
            result = await registry.call_tool(method, {} if params is None else params, context)
        else:
            raise McpError(JSONRPC_METHOD_NOT_FOUND, "Method not found")
        return None if is_notification else jsonrpc_result(request_id, result)
    except Exception as exc:
        return None if is_notification else jsonrpc_error(request_id, error_from_exception(exc))


def parse_error_response() -> dict[str, Any]:
    return jsonrpc_error(None, McpError(JSONRPC_PARSE_ERROR, "Parse error"))
