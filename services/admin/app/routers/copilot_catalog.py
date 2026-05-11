"""Awesome Copilot catalog MCP provider.

Syncs content from https://github.com/github/awesome-copilot (agents/
instructions/skills directories) via the GitHub API and exposes it as:
  - A searchable catalog REST API
  - An MCP server endpoint (GET /mcp/copilot-catalog, POST /mcp/copilot-catalog/tools/*)

The catalog is cached in Redis and refreshed every 6 hours. On first
startup an immediate sync is performed as a background task.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.mcp_protocol import MCPServer

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp/copilot-catalog", tags=["copilot-catalog"])

_REPO = "github/awesome-copilot"
_DIRS = [
    ("agents",       "agent"),
    ("instructions", "instruction"),
    ("cookbook",     "recipe"),
]
_REDIS_KEY = "copilot_catalog:items"
_REDIS_META = "copilot_catalog:meta"
_SYNC_INTERVAL = 6 * 3600  # 6 hours

# ── GitHub fetch helpers ──────────────────────────────────────────────────────

async def _fetch_dir(client: httpx.AsyncClient, directory: str) -> list[dict]:
    r = await client.get(
        f"https://api.github.com/repos/{_REPO}/contents/{directory}",
        headers={"Accept": "application/vnd.github.v3+json"},
        timeout=20,
    )
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return [f for f in r.json() if isinstance(f, dict) and f.get("type") == "file"]


async def _fetch_file_content(client: httpx.AsyncClient, url: str) -> str:
    r = await client.get(url, timeout=20)
    r.raise_for_status()
    return r.text


def _parse_frontmatter(raw: str) -> dict[str, Any]:
    """Extract YAML-lite frontmatter fields from a markdown file."""
    meta: dict[str, Any] = {}
    if raw.startswith("---"):
        end = raw.find("---", 3)
        if end > 0:
            fm = raw[3:end].strip()
            for line in fm.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    meta[k.strip().lower()] = v.strip().strip('"\'')
    return meta


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


async def sync_catalog(redis) -> int:
    """Fetch the catalog from GitHub and cache in Redis. Returns item count."""
    items: list[dict[str, Any]] = []
    async with httpx.AsyncClient() as client:
        for directory, kind in _DIRS:
            try:
                files = await _fetch_dir(client, directory)
            except Exception as exc:
                _log.warning("failed to list %s: %s", directory, exc)
                continue
            for f in files:
                name = f.get("name", "")
                if not name.endswith(".md"):
                    continue
                try:
                    content = await _fetch_file_content(client, f["download_url"])
                except Exception as exc:
                    _log.debug("skipping %s: %s", name, exc)
                    continue
                fm = _parse_frontmatter(content)
                # Extract first non-frontmatter paragraph as description
                body = re.sub(r"^---.*?---\s*", "", content, flags=re.S).strip()
                first_para = re.search(r"^(?:#{1,3}\s+[^\n]+\n+)?([^#\n][^\n]{10,})", body)
                description = first_para.group(1).strip() if first_para else ""
                items.append({
                    "id": _slug(name.removesuffix(".md")),
                    "name": fm.get("name") or name.removesuffix(".md").replace("-", " ").title(),
                    "kind": kind,
                    "description": fm.get("description") or description[:300],
                    "tags": [t.strip() for t in fm.get("tags", "").split(",") if t.strip()],
                    "source_file": f"{directory}/{name}",
                    "github_url": f"https://github.com/{_REPO}/blob/main/{directory}/{name}",
                    "content_preview": body[:500],
                })

    if not items:
        _log.warning("copilot catalog sync returned 0 items")
        return 0

    if redis is not None:
        try:
            await redis.set(_REDIS_KEY, json.dumps(items))
            await redis.set(_REDIS_META, json.dumps({
                "synced_at": time.time(),
                "count": len(items),
            }))
        except Exception as exc:
            _log.warning("redis catalog cache write failed: %s", exc)
    return len(items)


async def _background_sync_loop(app):
    """Background task: sync immediately, then every _SYNC_INTERVAL seconds."""
    redis = getattr(app.state, "redis", None)
    while True:
        try:
            n = await sync_catalog(redis)
            _log.info("copilot catalog synced %d items", n)
        except Exception as exc:
            _log.warning("catalog sync error: %s", exc)
        await asyncio.sleep(_SYNC_INTERVAL)


def start_background_sync(app):
    """Call from lifespan after app.state.redis is available."""
    asyncio.create_task(_background_sync_loop(app))


# ── Catalog helpers ───────────────────────────────────────────────────────────

async def _get_items(redis) -> list[dict]:
    if redis is not None:
        try:
            raw = await redis.get(_REDIS_KEY)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    return []


def _search_items(items: list[dict], query: str, kind: str | None = None, limit: int = 10) -> list[dict]:
    q = query.lower()
    results = []
    for item in items:
        if kind and item["kind"] != kind:
            continue
        score = 0
        if q in item["id"]:
            score += 3
        if q in item["name"].lower():
            score += 2
        if q in item["description"].lower():
            score += 1
        if any(q in t for t in item["tags"]):
            score += 2
        if score > 0:
            results.append((score, item))
    results.sort(key=lambda x: -x[0])
    return [r[1] for r in results[:limit]]


# ── REST catalog API ─────────────────────────────────────────────────────────

@router.get("/items")
async def list_items(
    request: Request,
    kind: str | None = None,
    q: str | None = None,
    limit: int = 20,
) -> dict:
    redis = getattr(request.app.state, "redis", None)
    items = await _get_items(redis)
    if q:
        items = _search_items(items, q, kind=kind, limit=limit)
    elif kind:
        items = [i for i in items if i["kind"] == kind][:limit]
    else:
        items = items[:limit]
    return {"items": items, "total": len(items)}


@router.get("/items/{item_id}")
async def get_item(item_id: str, request: Request) -> dict:
    redis = getattr(request.app.state, "redis", None)
    items = await _get_items(redis)
    for item in items:
        if item["id"] == item_id:
            return item
    return JSONResponse({"detail": "not found"}, status_code=404)


@router.post("/sync")
async def trigger_sync(request: Request) -> dict:
    redis = getattr(request.app.state, "redis", None)
    n = await sync_catalog(redis)
    return {"synced": n}


@router.get("/meta")
async def catalog_meta(request: Request) -> dict:
    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        try:
            raw = await redis.get(_REDIS_META)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    return {"synced_at": None, "count": 0}


# ── MCP endpoint ─────────────────────────────────────────────────────────────

_MCP_MANIFEST = {
    "name": "awesome-copilot",
    "version": "1.0.0",
    "description": "Search and browse the Awesome GitHub Copilot catalog — community agents, instructions, and recipes.",
    "tools": [
        {
            "name": "search",
            "description": "Search the Awesome Copilot catalog by keyword",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keywords"},
                    "kind": {"type": "string", "enum": ["agent", "instruction", "recipe"], "description": "Filter by type"},
                    "limit": {"type": "integer", "default": 5, "description": "Max results"},
                },
                "required": ["query"],
            },
        },
        {
            "name": "list",
            "description": "List all items of a given type from the Awesome Copilot catalog",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["agent", "instruction", "recipe"]},
                    "limit": {"type": "integer", "default": 20},
                },
            },
        },
        {
            "name": "get",
            "description": "Get full details of a catalog item by its slug ID",
            "inputSchema": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
        },
    ],
}


@router.get("")
async def mcp_manifest() -> dict:
    return _MCP_MANIFEST


@router.get("/tools")
async def mcp_tools() -> dict:
    return {"tools": _MCP_MANIFEST["tools"]}


@router.post("/tools/search")
async def mcp_search(body: dict, request: Request) -> dict:
    redis = getattr(request.app.state, "redis", None)
    items = await _get_items(redis)
    results = _search_items(items, body.get("query", ""), kind=body.get("kind"), limit=body.get("limit", 5))
    return {"items": results, "count": len(results)}


@router.post("/tools/list")
async def mcp_list(body: dict, request: Request) -> dict:
    redis = getattr(request.app.state, "redis", None)
    items = await _get_items(redis)
    kind = body.get("kind")
    if kind:
        items = [i for i in items if i["kind"] == kind]
    limit = body.get("limit", 20)
    return {"items": items[:limit], "count": len(items[:limit])}


@router.post("/tools/get")
async def mcp_get(body: dict, request: Request) -> dict:
    redis = getattr(request.app.state, "redis", None)
    items = await _get_items(redis)
    for item in items:
        if item["id"] == body.get("id"):
            return item
    return JSONResponse({"detail": "not found"}, status_code=404)


# ── JSON-RPC 2.0 MCP endpoint ─────────────────────────────────────────────────

async def _tool_search(arguments: dict, request: Request) -> dict:
    redis = getattr(request.app.state, "redis", None)
    items = await _get_items(redis)
    results = _search_items(
        items,
        arguments.get("query", ""),
        kind=arguments.get("kind"),
        limit=arguments.get("limit", 5),
    )
    return {"items": results, "count": len(results)}


async def _tool_list(arguments: dict, request: Request) -> dict:
    redis = getattr(request.app.state, "redis", None)
    items = await _get_items(redis)
    kind = arguments.get("kind")
    if kind:
        items = [i for i in items if i["kind"] == kind]
    limit = arguments.get("limit", 20)
    result = items[:limit]
    return {"items": result, "count": len(result)}


async def _tool_get(arguments: dict, request: Request) -> dict:
    redis = getattr(request.app.state, "redis", None)
    items = await _get_items(redis)
    for item in items:
        if item["id"] == arguments.get("id"):
            return item
    return {"detail": "not found"}


_mcp_server = MCPServer(
    name="awesome-copilot",
    version="1.0.0",
    description="Search and browse the Awesome GitHub Copilot catalog — community agents, instructions, and recipes.",
)
_mcp_server.add_tool(
    name="search",
    description="Search the Awesome Copilot catalog by keyword",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search keywords"},
            "kind": {
                "type": "string",
                "enum": ["agent", "instruction", "recipe"],
                "description": "Filter by type",
            },
            "limit": {"type": "integer", "default": 5, "description": "Max results"},
        },
        "required": ["query"],
    },
    handler=_tool_search,
)
_mcp_server.add_tool(
    name="list",
    description="List all items of a given type from the Awesome Copilot catalog",
    input_schema={
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["agent", "instruction", "recipe"]},
            "limit": {"type": "integer", "default": 20},
        },
    },
    handler=_tool_list,
)
_mcp_server.add_tool(
    name="get",
    description="Get full details of a catalog item by its slug ID",
    input_schema={
        "type": "object",
        "properties": {"id": {"type": "string"}},
        "required": ["id"],
    },
    handler=_tool_get,
)


# POST /mcp/copilot-catalog — real MCP clients (VS Code Copilot, Claude Desktop)
# send JSON-RPC 2.0 bodies here.
@router.post("")
async def mcp_jsonrpc(body: dict, request: Request):
    return await _mcp_server.handle(body, request)
