from __future__ import annotations

import hmac
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from ..mcp.protocol import handle_jsonrpc_payload, parse_error_response
from ..mcp.registry import McpToolContext
from ..mcp.tools import MCP_REGISTRY
from ..path_fix import PathFixRoute
from ..runtime_settings import ensure_mcp_token

router = APIRouter(route_class=PathFixRoute)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = PROJECT_ROOT / "skills" / "wechat-mcp-copilot"


def _extract_mcp_token(request: Request) -> str:
    auth = str(request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()

    header_token = str(request.headers.get("x-mcp-token") or "").strip()
    if header_token:
        return header_token

    return str(request.query_params.get("token") or "").strip()


def _mcp_unauthorized() -> JSONResponse:
    return JSONResponse(
        {"status": "error", "message": "Invalid or missing MCP token."},
        status_code=401,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _verify_mcp_token(request: Request) -> bool:
    expected, _ = ensure_mcp_token()
    provided = _extract_mcp_token(request)
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided, expected)


def _read_skill_bundle() -> dict[str, Any]:
    entry_path = SKILL_ROOT / "SKILL.md"
    if not entry_path.is_file():
        return {
            "status": "error",
            "message": "Skill not found.",
            "path": str(entry_path),
        }

    references = []
    bundle_parts = [entry_path.read_text(encoding="utf-8")]
    references_dir = SKILL_ROOT / "references"
    if references_dir.is_dir():
        for ref_path in sorted(references_dir.glob("*.md")):
            content = ref_path.read_text(encoding="utf-8")
            rel_path = ref_path.relative_to(SKILL_ROOT).as_posix()
            references.append({"path": rel_path, "content": content})
            bundle_parts.append(f"\n\n---\n# {rel_path}\n\n{content}")

    return {
        "status": "success",
        "name": "wechat-mcp-copilot",
        "version": "1.0.0",
        "entry": "SKILL.md",
        "entryContent": bundle_parts[0],
        "references": references,
        "bundleText": "".join(bundle_parts),
    }


@router.get("/mcp", summary="MCP endpoint")
async def mcp_get(request: Request):
    if not _verify_mcp_token(request):
        return _mcp_unauthorized()
    return PlainTextResponse("Use POST with JSON-RPC 2.0.", status_code=405, headers={"Allow": "POST"})


@router.get("/mcp/skill/bundle", summary="MCP skill bundle")
async def mcp_skill_bundle(request: Request):
    if not _verify_mcp_token(request):
        return _mcp_unauthorized()
    payload = _read_skill_bundle()
    status_code = 200 if payload.get("status") == "success" else 404
    return JSONResponse(payload, status_code=status_code)


@router.get("/mcp/skill", summary="MCP skill text")
async def mcp_skill_text(request: Request):
    if not _verify_mcp_token(request):
        return _mcp_unauthorized()
    payload = _read_skill_bundle()
    if payload.get("status") != "success":
        return PlainTextResponse(str(payload.get("message") or "Skill not found."), status_code=404)
    return PlainTextResponse(str(payload.get("bundleText") or ""), media_type="text/markdown; charset=utf-8")


@router.post("/mcp", summary="MCP JSON-RPC endpoint")
async def mcp_post(request: Request):
    if not _verify_mcp_token(request):
        return _mcp_unauthorized()

    try:
        payload: Any = await request.json()
    except Exception:
        return JSONResponse(parse_error_response(), status_code=400)

    result = await handle_jsonrpc_payload(payload, MCP_REGISTRY, McpToolContext(request=request))
    if result is None:
        return PlainTextResponse("", status_code=202)
    return JSONResponse(result)
