"""CodeMate MCP proxy for the AI Gateway.

Registers the SimCorp CodeMate codebase-search server
(https://mcp.prod.codemate.az.scdom.net/tools/api/mcp) as a proxied MCP
endpoint so internal agents can call CodeMate tools through the gateway
with unified auth and audit logging.

The gateway acts as an authenticated proxy: it forwards tool calls to the
upstream CodeMate server, which requires SimCorp network access.

Endpoints:
  GET  /mcp/codemate           → manifest / tool list
  POST /mcp/codemate/tools/{tool_name}  → proxied tool call
"""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.mcp_protocol import MCPServer

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp/codemate", tags=["codemate"])

_UPSTREAM = "https://mcp.prod.codemate.az.scdom.net/tools/api/mcp"

# Documented tools from the CodeMate server (used when upstream is unreachable)
_FALLBACK_TOOLS = [
    {
        "name": "codebase_search__search_code",
        "description": "Search SimCorp codebase by natural language or symbol",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "codebase_search__find_system_objects_by_caption",
        "description": "Find SimCorp system objects (forms, views, workflows) by caption",
        "inputSchema": {
            "type": "object",
            "properties": {"caption": {"type": "string"}},
            "required": ["caption"],
        },
    },
]


@router.get("")
async def manifest() -> dict:
    """Return the CodeMate MCP manifest, fetching from upstream if reachable."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(_UPSTREAM)
            if r.status_code == 200:
                return r.json()
    except Exception as exc:
        _log.debug("CodeMate upstream unreachable: %s", exc)
    return {
        "name": "codematetools",
        "version": "1.0.0",
        "description": "SimCorp CodeMate codebase search tools. Requires SimCorp network access.",
        "upstream": _UPSTREAM,
        "tools": _FALLBACK_TOOLS,
    }


@router.get("/tools")
async def tools() -> dict:
    info = await manifest()
    return {"tools": info.get("tools", _FALLBACK_TOOLS)}


@router.post("/tools/{tool_name}")
async def proxy_tool(tool_name: str, body: dict, request: Request) -> dict:
    """Proxy a tool call to the upstream CodeMate server."""
    payload = {"tool": tool_name, "input": body}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(_UPSTREAM, json=payload)
            r.raise_for_status()
            return r.json()
    except httpx.ConnectError:
        raise HTTPException(
            503,
            detail="CodeMate server unreachable. Ensure your device is connected to the SimCorp network.",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(exc.response.status_code, detail=exc.response.text)


# ── JSON-RPC 2.0 MCP endpoint ─────────────────────────────────────────────────

async def _upstream_tool_call(tool_name: str, arguments: dict) -> dict:
    """Proxy a call to the upstream CodeMate server; return a result dict."""
    payload = {"tool": tool_name, "input": arguments}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(_UPSTREAM, json=payload)
            r.raise_for_status()
            return r.json()
    except httpx.ConnectError:
        return {
            "error": "CodeMate server unreachable. Ensure your device is connected to the SimCorp network."
        }
    except Exception as exc:
        return {"error": str(exc)}


async def _tool_search_code(arguments: dict, request: Request) -> dict:
    return await _upstream_tool_call("codebase_search__search_code", arguments)


async def _tool_find_system_objects(arguments: dict, request: Request) -> dict:
    return await _upstream_tool_call(
        "codebase_search__find_system_objects_by_caption", arguments
    )


_mcp_server = MCPServer(
    name="codematetools",
    version="1.0.0",
    description="SimCorp CodeMate codebase search tools. Requires SimCorp network access.",
)
_mcp_server.add_tool(
    name="codebase_search__search_code",
    description="Search SimCorp codebase by natural language or symbol",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "limit": {"type": "integer", "default": 10},
        },
        "required": ["query"],
    },
    handler=_tool_search_code,
)
_mcp_server.add_tool(
    name="codebase_search__find_system_objects_by_caption",
    description="Find SimCorp system objects (forms, views, workflows) by caption",
    input_schema={
        "type": "object",
        "properties": {"caption": {"type": "string"}},
        "required": ["caption"],
    },
    handler=_tool_find_system_objects,
)


# POST /mcp/codemate — real MCP clients (VS Code Copilot, Claude Desktop)
# send JSON-RPC 2.0 bodies here.
@router.post("")
async def mcp_jsonrpc(body: dict, request: Request):
    return await _mcp_server.handle(body, request)


router.get("/sse")(_mcp_server.sse_endpoint())
