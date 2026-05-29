"""Memory Palace — hosted MemPalace-compatible MCP server.

Each developer gets their own isolated memory namespace, identified by their
existing gateway API key.  All MCP tool calls are authenticated per-request.
"""
from __future__ import annotations

import json
import logging
from collections import deque
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import date, datetime
from typing import Any, Awaitable, Callable

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from openai import AsyncOpenAI

import app.store as store
from app.auth import resolve_developer
from app.config import settings

_log = logging.getLogger(__name__)

# Per-request context variable — set in the /mcp route handler before tool dispatch
_current_developer: ContextVar[str] = ContextVar("developer_id")


# ── MCPServer (copied from services/admin/app/mcp_protocol.py) ────────────────


class MCPServer:
    """JSON-RPC 2.0 handler for MCP protocol."""

    MCP_PROTOCOL_VERSION = "2024-11-05"

    def __init__(self, name: str, version: str, description: str) -> None:
        self.name = name
        self.version = version
        self.description = description
        self._tools: list[dict[str, Any]] = []
        self._handlers: dict[str, Callable[..., Awaitable[Any]]] = {}

    def add_tool(
        self,
        name: str,
        description: str,
        input_schema: dict,
        handler: Callable[..., Awaitable[Any]],
    ) -> None:
        self._tools.append({"name": name, "description": description, "inputSchema": input_schema})
        self._handlers[name] = handler

    @staticmethod
    def _ok(request_id: Any, result: Any) -> dict:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    def _handle_initialize(self, params: dict, request_id: Any) -> dict:
        return self._ok(request_id, {
            "protocolVersion": self.MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": self.name, "version": self.version},
        })

    def _handle_tools_list(self, params: dict, request_id: Any) -> dict:
        return self._ok(request_id, {"tools": self._tools})

    async def _handle_tools_call(self, params: dict, request_id: Any, request: Request) -> dict:
        tool_name = params.get("name", "")
        arguments = params.get("arguments") or {}
        handler = self._handlers.get(tool_name)
        if handler is None:
            return self._error(request_id, -32601, f"Tool not found: {tool_name}")
        try:
            result = await handler(arguments, request)
        except Exception as exc:
            _log.exception("Tool %s raised an exception", tool_name)
            return self._error(request_id, -32603, f"Tool execution error: {exc}")
        return self._ok(request_id, {"content": [{"type": "text", "text": json.dumps(result)}]})

    def _handle_ping(self, params: dict, request_id: Any) -> dict:
        return self._ok(request_id, {})

    async def handle(self, body: dict, request: Request) -> Any:
        method: str = body.get("method", "")
        params: dict = body.get("params") or {}
        request_id = body.get("id")
        is_notification = "id" not in body

        if method == "initialize":
            return Response(status_code=204) if is_notification else self._handle_initialize(params, request_id)
        if method == "notifications/initialized":
            return Response(status_code=204)
        if method == "tools/list":
            return Response(status_code=204) if is_notification else self._handle_tools_list(params, request_id)
        if method == "tools/call":
            return Response(status_code=204) if is_notification else await self._handle_tools_call(params, request_id, request)
        if method == "ping":
            return Response(status_code=204) if is_notification else self._handle_ping(params, request_id)
        if is_notification:
            return Response(status_code=204)
        _log.debug("MCP unknown method: %s", method)
        return self._error(request_id, -32601, f"Method not found: {method}")


# ── Lifespan ───────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(application: FastAPI):
    pool = await asyncpg.create_pool(settings.database_url, min_size=2, max_size=10)
    http = httpx.AsyncClient()
    openai_client = AsyncOpenAI(
        api_key=settings.embedding_api_key,
        base_url=settings.embedding_base_url,
    )
    application.state.pool = pool
    application.state.http = http
    application.state.openai = openai_client
    yield
    await pool.close()
    await http.aclose()
    await openai_client.close()


app = FastAPI(title="Memory Palace", version="0.1.0", lifespan=lifespan)
mcp_server = MCPServer(
    name="memory-palace",
    version="0.1.0",
    description="Per-developer isolated memory with drawers, KG, diary, and tunnels",
)


# ── Embedding helper ───────────────────────────────────────────────────────────


async def _embed(text: str) -> list[float]:
    client: AsyncOpenAI = app.state.openai
    response = await client.embeddings.create(
        model=settings.embedding_model,
        input=text,
        dimensions=settings.embedding_dimensions,
    )
    return response.data[0].embedding


# ── Auth dependency ────────────────────────────────────────────────────────────


async def get_developer_id(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = auth_header[len("Bearer "):]
    return await resolve_developer(token, request.app.state.http, request.app.state.pool)


# ── Tool helpers ───────────────────────────────────────────────────────────────


def _pool() -> asyncpg.Pool:
    return app.state.pool


def _dev() -> str:
    """Retrieve the developer_id for the current request from the context var."""
    return _current_developer.get()


def _serialize(obj: Any) -> Any:
    """Make asyncpg row values JSON-serialisable."""
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj


# ── Tool handlers ──────────────────────────────────────────────────────────────


async def _status(args: dict, req: Request) -> dict:
    try:
        result = await store.palace_stats(_pool(), _dev())
        return _serialize(result)
    except Exception as exc:
        return {"error": str(exc)}


async def _add_drawer(args: dict, req: Request) -> dict:
    try:
        content = args["content"]
        embedding = await _embed(content)
        result = await store.add_drawer(
            _pool(), _dev(),
            wing=args.get("wing", "default"),
            room=args.get("room", "default"),
            content=content,
            summary=args.get("summary"),
            tags=args.get("tags") or [],
            source=args.get("source"),
            embedding=embedding,
        )
        return _serialize(result)
    except Exception as exc:
        return {"error": str(exc)}


async def _get_drawer(args: dict, req: Request) -> dict:
    try:
        result = await store.get_drawer(_pool(), _dev(), args["id"])
        if result is None:
            return {"error": "Drawer not found"}
        return _serialize(result)
    except Exception as exc:
        return {"error": str(exc)}


async def _update_drawer(args: dict, req: Request) -> dict:
    try:
        fields = {k: v for k, v in args.items() if k != "id"}
        if "content" in fields:
            fields["embedding"] = await _embed(fields["content"])
        result = await store.update_drawer(_pool(), _dev(), args["id"], **fields)
        if result is None:
            return {"error": "Drawer not found"}
        return _serialize(result)
    except Exception as exc:
        return {"error": str(exc)}


async def _delete_drawer(args: dict, req: Request) -> dict:
    try:
        deleted = await store.delete_drawer(_pool(), _dev(), args["id"])
        return {"deleted": deleted}
    except Exception as exc:
        return {"error": str(exc)}


async def _list_drawers(args: dict, req: Request) -> dict:
    try:
        result = await store.list_drawers(
            _pool(), _dev(),
            wing=args.get("wing"),
            room=args.get("room"),
            limit=args.get("limit", 20),
        )
        return {"drawers": _serialize(result)}
    except Exception as exc:
        return {"error": str(exc)}


async def _search(args: dict, req: Request) -> dict:
    try:
        query = args["query"]
        embedding = await _embed(query)
        result = await store.search_drawers(
            _pool(), _dev(),
            embedding=embedding,
            limit=args.get("limit", 10),
            threshold=args.get("threshold", 0.7),
        )
        return {"results": _serialize(result)}
    except Exception as exc:
        return {"error": str(exc)}


async def _check_duplicate(args: dict, req: Request) -> dict:
    try:
        content = args["content"]
        embedding = await _embed(content)
        result = await store.check_duplicate(
            _pool(), _dev(),
            embedding=embedding,
            threshold=args.get("threshold", 0.95),
        )
        return {"duplicate": _serialize(result)}
    except Exception as exc:
        return {"error": str(exc)}


async def _memories_filed_away(args: dict, req: Request) -> dict:
    try:
        stats = await store.palace_stats(_pool(), _dev())
        return {"drawers_by_wing": _serialize(stats["drawers_by_wing"])}
    except Exception as exc:
        return {"error": str(exc)}


async def _list_rooms(args: dict, req: Request) -> dict:
    try:
        pool = _pool()
        dev = _dev()
        wing = args.get("wing")
        if wing:
            rows = await pool.fetch(
                "SELECT DISTINCT room FROM memory_drawers WHERE developer_id = $1::uuid AND wing = $2 ORDER BY room",
                dev, wing,
            )
        else:
            rows = await pool.fetch(
                "SELECT DISTINCT room FROM memory_drawers WHERE developer_id = $1::uuid ORDER BY room",
                dev,
            )
        return {"rooms": [r["room"] for r in rows]}
    except Exception as exc:
        return {"error": str(exc)}


async def _list_wings(args: dict, req: Request) -> dict:
    try:
        rows = await _pool().fetch(
            "SELECT wing, COUNT(*) AS count FROM memory_drawers WHERE developer_id = $1::uuid GROUP BY wing ORDER BY wing",
            _dev(),
        )
        return {"wings": [{"wing": r["wing"], "count": r["count"]} for r in rows]}
    except Exception as exc:
        return {"error": str(exc)}


async def _get_taxonomy(args: dict, req: Request) -> dict:
    try:
        rows = await _pool().fetch(
            "SELECT wing, room, COUNT(*) AS count FROM memory_drawers WHERE developer_id = $1::uuid "
            "GROUP BY wing, room ORDER BY wing, room",
            _dev(),
        )
        taxonomy: dict[str, dict[str, int]] = {}
        for r in rows:
            taxonomy.setdefault(r["wing"], {})[r["room"]] = r["count"]
        return {"taxonomy": taxonomy}
    except Exception as exc:
        return {"error": str(exc)}


async def _kg_add(args: dict, req: Request) -> dict:
    try:
        kind = args.get("type", "node")
        if kind == "node":
            result = await store.kg_add_node(
                _pool(), _dev(),
                name=args["name"],
                entity_type=args.get("entity_type", "entity"),
                attributes=args.get("attributes") or {},
            )
        else:
            result = await store.kg_add_edge(
                _pool(), _dev(),
                from_id=args["from_id"],
                to_id=args["to_id"],
                relation=args.get("relation", "related"),
                attributes=args.get("attributes") or {},
            )
        return _serialize(result)
    except Exception as exc:
        return {"error": str(exc)}


async def _kg_query(args: dict, req: Request) -> dict:
    try:
        result = await store.kg_query(
            _pool(), _dev(),
            name=args.get("name"),
            entity_type=args.get("entity_type"),
            limit=args.get("limit", 20),
        )
        return {"nodes": _serialize(result)}
    except Exception as exc:
        return {"error": str(exc)}


async def _kg_invalidate(args: dict, req: Request) -> dict:
    try:
        invalidated = await store.kg_invalidate(_pool(), _dev(), args["node_id"])
        return {"invalidated": invalidated}
    except Exception as exc:
        return {"error": str(exc)}


async def _kg_stats(args: dict, req: Request) -> dict:
    try:
        result = await store.kg_stats(_pool(), _dev())
        return _serialize(result)
    except Exception as exc:
        return {"error": str(exc)}


async def _kg_timeline(args: dict, req: Request) -> dict:
    try:
        since = None
        until = None
        if args.get("since"):
            since = datetime.fromisoformat(args["since"])
        if args.get("until"):
            until = datetime.fromisoformat(args["until"])
        result = await store.kg_timeline(_pool(), _dev(), since=since, until=until)
        return {"nodes": _serialize(result)}
    except Exception as exc:
        return {"error": str(exc)}


async def _diary_read(args: dict, req: Request) -> dict:
    try:
        date_filter = None
        if args.get("date"):
            date_filter = date.fromisoformat(args["date"])
        result = await store.diary_read(_pool(), _dev(), date_filter=date_filter, limit=args.get("limit", 7))
        return {"entries": _serialize(result)}
    except Exception as exc:
        return {"error": str(exc)}


async def _diary_write(args: dict, req: Request) -> dict:
    try:
        entry_date = date.fromisoformat(args["date"]) if args.get("date") else date.today()
        result = await store.diary_write(_pool(), _dev(), entry_date=entry_date, entry=args["entry"])
        return _serialize(result)
    except Exception as exc:
        return {"error": str(exc)}


async def _create_tunnel(args: dict, req: Request) -> dict:
    try:
        result = await store.create_tunnel(
            _pool(), _dev(),
            from_wing=args["from_wing"],
            to_wing=args["to_wing"],
            label=args.get("label"),
            bidirectional=args.get("bidirectional", False),
        )
        return _serialize(result)
    except Exception as exc:
        return {"error": str(exc)}


async def _delete_tunnel(args: dict, req: Request) -> dict:
    try:
        deleted = await store.delete_tunnel(_pool(), _dev(), args["id"])
        return {"deleted": deleted}
    except Exception as exc:
        return {"error": str(exc)}


async def _list_tunnels(args: dict, req: Request) -> dict:
    try:
        result = await store.list_tunnels(_pool(), _dev())
        return {"tunnels": _serialize(result)}
    except Exception as exc:
        return {"error": str(exc)}


async def _find_tunnels(args: dict, req: Request) -> dict:
    try:
        result = await store.find_tunnels(_pool(), _dev(), args["from_wing"])
        return {"tunnels": _serialize(result)}
    except Exception as exc:
        return {"error": str(exc)}


async def _follow_tunnels(args: dict, req: Request) -> dict:
    """BFS traversal returning reachable wings from a starting wing."""
    try:
        from_wing = args["from_wing"]
        max_depth = args.get("depth", 3)
        pool = _pool()
        dev = _dev()

        visited: set[str] = {from_wing}
        queue: deque[tuple[str, int]] = deque([(from_wing, 0)])
        reachable: list[dict] = []

        while queue:
            current_wing, depth = queue.popleft()
            if depth >= max_depth:
                continue
            tunnels = await store.find_tunnels(pool, dev, current_wing)
            for t in tunnels:
                next_wing = t["to_wing"] if t["from_wing"] == current_wing else t["from_wing"]
                if next_wing not in visited:
                    visited.add(next_wing)
                    reachable.append({"wing": next_wing, "depth": depth + 1, "via": t["label"]})
                    queue.append((next_wing, depth + 1))

        return {"reachable": reachable}
    except Exception as exc:
        return {"error": str(exc)}


async def _traverse(args: dict, req: Request) -> dict:
    """Full wing graph traversal returning adjacency structure."""
    try:
        start_wing = args["start_wing"]
        max_depth = args.get("depth", 5)
        pool = _pool()
        dev = _dev()

        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(start_wing, 0)])
        graph: dict[str, list[str]] = {}

        while queue:
            current_wing, depth = queue.popleft()
            if current_wing in visited or depth > max_depth:
                continue
            visited.add(current_wing)
            tunnels = await store.find_tunnels(pool, dev, current_wing)
            neighbours = []
            for t in tunnels:
                next_wing = t["to_wing"] if t["from_wing"] == current_wing else t["from_wing"]
                neighbours.append(next_wing)
                if next_wing not in visited:
                    queue.append((next_wing, depth + 1))
            graph[current_wing] = neighbours

        return {"graph": graph, "visited": list(visited)}
    except Exception as exc:
        return {"error": str(exc)}


async def _reconnect(args: dict, req: Request) -> dict:
    try:
        return {"status": "connected", "developer_id": _dev()}
    except Exception as exc:
        return {"error": str(exc)}


async def _hook_settings(args: dict, req: Request) -> dict:
    return {"auto_save": False, "embed_on_add": True}


async def _get_aaak_spec(args: dict, req: Request) -> dict:
    return {
        "spec_version": "1.0",
        "server": "memory-palace",
        "tools": [t["name"] for t in mcp_server._tools],
        "description": "MemPalace-compatible hosted memory server. Each tool call is scoped to the authenticated developer.",
    }


async def _graph_stats(args: dict, req: Request) -> dict:
    try:
        stats = await store.kg_stats(_pool(), _dev())
        nodes = stats["total_nodes"]
        edges = stats["total_edges"]
        # Components: crude estimate — connected components not computed, return 1 if any nodes
        components = 1 if nodes > 0 else 0
        return {"nodes": nodes, "edges": edges, "components": components}
    except Exception as exc:
        return {"error": str(exc)}


# ── Register tools ─────────────────────────────────────────────────────────────


mcp_server.add_tool("mempalace_status", "Return palace stats for the current developer", {}, _status)

mcp_server.add_tool("mempalace_add_drawer", "Add a memory drawer (content is embedded automatically)", {
    "type": "object",
    "properties": {
        "wing": {"type": "string", "description": "Wing name (top-level category)"},
        "room": {"type": "string", "description": "Room name within the wing"},
        "content": {"type": "string", "description": "Content to store"},
        "summary": {"type": "string", "description": "Optional short summary"},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags"},
        "source": {"type": "string", "description": "Optional source reference"},
    },
    "required": ["content"],
}, _add_drawer)

mcp_server.add_tool("mempalace_get_drawer", "Fetch a drawer by ID", {
    "type": "object",
    "properties": {"id": {"type": "string"}},
    "required": ["id"],
}, _get_drawer)

mcp_server.add_tool("mempalace_update_drawer", "Update a drawer", {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "wing": {"type": "string"},
        "room": {"type": "string"},
        "content": {"type": "string"},
        "summary": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "source": {"type": "string"},
    },
    "required": ["id"],
}, _update_drawer)

mcp_server.add_tool("mempalace_delete_drawer", "Delete a drawer", {
    "type": "object",
    "properties": {"id": {"type": "string"}},
    "required": ["id"],
}, _delete_drawer)

mcp_server.add_tool("mempalace_list_drawers", "List drawers, optionally filtered by wing/room", {
    "type": "object",
    "properties": {
        "wing": {"type": "string"},
        "room": {"type": "string"},
        "limit": {"type": "integer", "default": 20},
    },
}, _list_drawers)

mcp_server.add_tool("mempalace_search", "Semantic search over drawers", {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "limit": {"type": "integer", "default": 10},
        "threshold": {"type": "number", "default": 0.7},
    },
    "required": ["query"],
}, _search)

mcp_server.add_tool("mempalace_check_duplicate", "Check if a near-duplicate drawer already exists", {
    "type": "object",
    "properties": {
        "content": {"type": "string"},
        "threshold": {"type": "number", "default": 0.95},
    },
    "required": ["content"],
}, _check_duplicate)

mcp_server.add_tool("mempalace_memories_filed_away", "Count drawers grouped by wing", {}, _memories_filed_away)

mcp_server.add_tool("mempalace_list_rooms", "List distinct rooms, optionally filtered by wing", {
    "type": "object",
    "properties": {"wing": {"type": "string"}},
}, _list_rooms)

mcp_server.add_tool("mempalace_list_wings", "List wings with drawer counts", {}, _list_wings)

mcp_server.add_tool("mempalace_get_taxonomy", "Get hierarchical wings → rooms structure", {}, _get_taxonomy)

mcp_server.add_tool("mempalace_kg_add", "Add a KG node or edge", {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ["node", "edge"]},
        "name": {"type": "string"},
        "entity_type": {"type": "string"},
        "attributes": {"type": "object"},
        "from_id": {"type": "string"},
        "to_id": {"type": "string"},
        "relation": {"type": "string"},
    },
    "required": ["type"],
}, _kg_add)

mcp_server.add_tool("mempalace_kg_query", "Search KG nodes", {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "entity_type": {"type": "string"},
        "limit": {"type": "integer", "default": 20},
    },
}, _kg_query)

mcp_server.add_tool("mempalace_kg_invalidate", "Mark a KG node as invalid (set valid_to = now)", {
    "type": "object",
    "properties": {"node_id": {"type": "string"}},
    "required": ["node_id"],
}, _kg_invalidate)

mcp_server.add_tool("mempalace_kg_stats", "KG node/edge counts by type", {}, _kg_stats)

mcp_server.add_tool("mempalace_kg_timeline", "KG nodes created/invalidated in a time range", {
    "type": "object",
    "properties": {
        "since": {"type": "string", "description": "ISO datetime"},
        "until": {"type": "string", "description": "ISO datetime"},
    },
}, _kg_timeline)

mcp_server.add_tool("mempalace_diary_read", "Read diary entries", {
    "type": "object",
    "properties": {
        "date": {"type": "string", "description": "ISO date (YYYY-MM-DD)"},
        "limit": {"type": "integer", "default": 7},
    },
}, _diary_read)

mcp_server.add_tool("mempalace_diary_write", "Write or update a diary entry", {
    "type": "object",
    "properties": {
        "entry": {"type": "string"},
        "date": {"type": "string", "description": "ISO date (YYYY-MM-DD), defaults to today"},
    },
    "required": ["entry"],
}, _diary_write)

mcp_server.add_tool("mempalace_create_tunnel", "Create a tunnel between wings", {
    "type": "object",
    "properties": {
        "from_wing": {"type": "string"},
        "to_wing": {"type": "string"},
        "label": {"type": "string"},
        "bidirectional": {"type": "boolean", "default": False},
    },
    "required": ["from_wing", "to_wing"],
}, _create_tunnel)

mcp_server.add_tool("mempalace_delete_tunnel", "Delete a tunnel", {
    "type": "object",
    "properties": {"id": {"type": "string"}},
    "required": ["id"],
}, _delete_tunnel)

mcp_server.add_tool("mempalace_list_tunnels", "List all tunnels", {}, _list_tunnels)

mcp_server.add_tool("mempalace_find_tunnels", "Find tunnels from a wing", {
    "type": "object",
    "properties": {"from_wing": {"type": "string"}},
    "required": ["from_wing"],
}, _find_tunnels)

mcp_server.add_tool("mempalace_follow_tunnels", "BFS traversal returning reachable wings", {
    "type": "object",
    "properties": {
        "from_wing": {"type": "string"},
        "depth": {"type": "integer", "default": 3},
    },
    "required": ["from_wing"],
}, _follow_tunnels)

mcp_server.add_tool("mempalace_traverse", "Full wing graph traversal", {
    "type": "object",
    "properties": {
        "start_wing": {"type": "string"},
        "depth": {"type": "integer", "default": 5},
    },
    "required": ["start_wing"],
}, _traverse)

mcp_server.add_tool("mempalace_reconnect", "Ping/reconnect check returning developer_id", {}, _reconnect)

mcp_server.add_tool("mempalace_hook_settings", "Return hook configuration", {}, _hook_settings)

mcp_server.add_tool("mempalace_get_aaak_spec", "Return JSON spec describing available tools", {}, _get_aaak_spec)

mcp_server.add_tool("mempalace_graph_stats", "Return KG graph statistics", {}, _graph_stats)


# ── Routes ─────────────────────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/mcp/tools")
async def mcp_tools_list() -> dict:
    return {"tools": mcp_server._tools}


@app.get("/mcp/manifest")
async def mcp_manifest() -> dict:
    return {
        "name": mcp_server.name,
        "version": mcp_server.version,
        "description": mcp_server.description,
        "protocol_version": mcp_server.MCP_PROTOCOL_VERSION,
        "tool_count": len(mcp_server._tools),
    }


@app.post("/mcp")
async def mcp_endpoint(request: Request):
    # Authenticate every MCP request
    developer_id = await get_developer_id(request)

    # Store developer_id in context var so tool handlers can read it
    token = _current_developer.set(developer_id)
    try:
        body = await request.json()
        return await mcp_server.handle(body, request)
    finally:
        _current_developer.reset(token)
