from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from fastapi.encoders import jsonable_encoder

from .errors import JSONRPC_METHOD_NOT_FOUND, McpError


ToolHandler = Callable[[dict[str, Any], "McpToolContext"], Any | Awaitable[Any]]


@dataclass(frozen=True)
class McpToolContext:
    request: Any

    @property
    def base_url(self) -> str:
        try:
            return str(self.request.base_url).rstrip("/")
        except Exception:
            return ""


@dataclass(frozen=True)
class McpTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler
    package: str = "wechat"
    annotations: dict[str, Any] | None = None

    def to_public_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }
        if self.annotations:
            payload["annotations"] = self.annotations
        return payload


class McpToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, McpTool] = {}

    def register(self, tool: McpTool) -> None:
        if not tool.name:
            raise ValueError("Tool name is required.")
        if tool.name in self._tools:
            raise ValueError(f"Duplicate MCP tool: {tool.name}")
        self._tools[tool.name] = tool

    def tool_names(self) -> list[str]:
        return sorted(self._tools)

    def list_tools(self, *, cursor: str | None = None, limit: int | None = None) -> dict[str, Any]:
        names = sorted(self._tools)
        start = 0
        if cursor:
            try:
                start = int(cursor)
            except Exception as exc:
                raise ValueError("Invalid cursor.") from exc
            if start < 0 or start > len(names):
                raise ValueError("Invalid cursor.")

        if limit is None:
            page_names = names[start:]
            next_cursor = None
        else:
            page_size = max(1, min(100, int(limit)))
            page_names = names[start : start + page_size]
            next_index = start + page_size
            next_cursor = str(next_index) if next_index < len(names) else None

        payload: dict[str, Any] = {
            "tools": [self._tools[name].to_public_dict() for name in page_names],
            "count": len(page_names),
            "total": len(names),
        }
        if next_cursor is not None:
            payload["nextCursor"] = next_cursor
        return payload

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    async def call_tool(self, name: str, arguments: Any, context: McpToolContext) -> dict[str, Any]:
        tool = self._tools.get(str(name or "").strip())
        if tool is None:
            raise McpError(JSONRPC_METHOD_NOT_FOUND, f"Unknown tool: {name}")
        if arguments is None:
            args: dict[str, Any] = {}
        elif isinstance(arguments, dict):
            args = dict(arguments)
        else:
            raise ValueError("Tool arguments must be an object.")

        result = tool.handler(args, context)
        if inspect.isawaitable(result):
            result = await result
        encoded = jsonable_encoder(result)
        text = json.dumps(encoded, ensure_ascii=False, indent=2)
        is_error = isinstance(encoded, dict) and str(encoded.get("status") or "").lower() == "error"
        return {
            "content": [{"type": "text", "text": text}],
            "structuredContent": encoded,
            "isError": is_error,
        }


def object_schema(
    properties: dict[str, Any] | None = None,
    *,
    required: list[str] | None = None,
    additional_properties: bool = False,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": additional_properties,
    }
    if required:
        schema["required"] = required
    return schema


def string_schema(description: str, *, enum: list[str] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"type": "string", "description": description}
    if enum:
        out["enum"] = enum
    return out


def int_schema(description: str, *, minimum: int | None = None, maximum: int | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"type": "integer", "description": description}
    if minimum is not None:
        out["minimum"] = minimum
    if maximum is not None:
        out["maximum"] = maximum
    return out


def bool_schema(description: str, *, default: bool | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"type": "boolean", "description": description}
    if default is not None:
        out["default"] = default
    return out


def array_schema(description: str, items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "description": description, "items": items}
