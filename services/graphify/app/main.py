"""
Graphify service — knowledge-graph build + query for navigating repos.

Gives AI agents a token-efficient way to navigate repos: register a GitHub repo,
a background worker builds a knowledge graph (graphify extract, routing doc/PDF/
media extraction through the gateway's cache), and agents query it via REST + an
MCP surface instead of dumping raw files into context. Graph queries are pure
local retrieval (no LLM).

This module is the API container. The build loop runs in a separate worker
container (app.worker) so a heavy extraction can't OOM the query API.
"""

from __future__ import annotations

import logging
import os
import shutil
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from prometheus_client import make_asgi_app
from pydantic import BaseModel

from app import db, query
from app.auth import AuthError, resolve_caller
from app.config import settings
from app.logging_config import CorrelationIdMiddleware, init_logging

_log = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised")
    return _pool


async def _require_caller(request: Request) -> None:
    """Gate a request on a valid sk-* Bearer; map AuthError → HTTP error."""
    try:
        await resolve_caller(request)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


def _repo_public(row: asyncpg.Record) -> dict:
    return {
        "name": row["name"],
        "github_url": row["github_url"],
        "ref": row["ref"],
        "status": row["status"],
        "last_commit": row["last_commit"],
        "last_built_at": row["last_built_at"].isoformat() if row["last_built_at"] else None,
        "enabled": row["enabled"],
    }


def _build_public(row: asyncpg.Record) -> dict:
    return {
        "id": str(row["id"]),
        "status": row["status"],
        "nodes": row["nodes"],
        "edges": row["edges"],
        "error": row["error"],
        "queued_at": row["queued_at"].isoformat() if row["queued_at"] else None,
        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
    }


def _validate_repo_name(name: str) -> None:
    if not db.REPO_NAME_RE.match(name):
        raise HTTPException(
            status_code=422,
            detail="repo name must match ^[a-z0-9][a-z0-9._-]{0,99}$",
        )


def _normalize_github_url(name: str, github_url: str | None) -> str:
    """Accept a full https URL, or build one from the configured org + repo name."""
    if github_url:
        if not github_url.startswith("https://github.com/"):
            raise HTTPException(
                status_code=422, detail="github_url must start with https://github.com/"
            )
        return github_url
    return f"https://github.com/{settings.github_org}/{name}.git"


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    _pool = await db.create_pool()
    await db.bootstrap_schema(_pool)

    # Auto-register with admin MCP registry (best-effort).
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                "http://admin:8005/mcp/servers",
                json={
                    "name": "Graphify",
                    "description": "Query knowledge graphs of repos — navigate code without raw file dumps",
                    "url": "http://graphify:8012/mcp",
                    "auth_type": "none",
                },
            )
            _log.info("Registered graphify as MCP server in admin")
    except Exception:
        _log.info("Admin MCP auto-register skipped (admin not reachable yet)")

    yield

    await _pool.close()


init_logging("graphify")
app = FastAPI(title="Graphify", version="1.0.0", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)
app.mount("/metrics", make_asgi_app())

_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RepoCreate(BaseModel):
    name: str
    github_url: str | None = None
    ref: str = "main"


# ---------------------------------------------------------------------------
# Repo registry + build management
# ---------------------------------------------------------------------------


@app.post("/repos", status_code=201)
async def create_repo(body: RepoCreate, request: Request):
    await _require_caller(request)
    _validate_repo_name(body.name)
    github_url = _normalize_github_url(body.name, body.github_url)
    pool = await get_pool()
    try:
        row = await db.register_repo(pool, name=body.name, github_url=github_url, ref=body.ref)
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail=f"repo '{body.name}' already registered")
    await db.queue_build(pool, row["id"])
    return _repo_public(row)


@app.get("/repos")
async def get_repos(request: Request):
    await _require_caller(request)
    pool = await get_pool()
    rows = await db.list_repos(pool)
    return {"repos": [_repo_public(r) for r in rows]}


@app.post("/repos/{name}/rebuild", status_code=202)
async def rebuild_repo(name: str, request: Request):
    await _require_caller(request)
    pool = await get_pool()
    row = await db.get_repo(pool, name)
    if not row:
        raise HTTPException(status_code=404, detail=f"repo '{name}' not found")
    build = await db.queue_build(pool, row["id"])
    return {"status": "queued", "build_id": str(build["id"])}


@app.get("/repos/{name}/builds")
async def repo_builds(name: str, request: Request):
    await _require_caller(request)
    pool = await get_pool()
    row = await db.get_repo(pool, name)
    if not row:
        raise HTTPException(status_code=404, detail=f"repo '{name}' not found")
    builds = await db.list_builds(pool, row["id"])
    return {"builds": [_build_public(b) for b in builds]}


@app.delete("/repos/{name}", status_code=204)
async def remove_repo(name: str, request: Request):
    await _require_caller(request)
    _validate_repo_name(name)
    pool = await get_pool()
    deleted = await db.delete_repo(pool, name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"repo '{name}' not found")
    # Remove artefacts from the volume (best-effort).
    shutil.rmtree(db.repo_dir(name), ignore_errors=True)


# ---------------------------------------------------------------------------
# Query + artefacts (all sk-* gated — graphs of private repos are sensitive)
# ---------------------------------------------------------------------------


@app.get("/query")
async def query_graph(
    request: Request,
    repo: str = Query(..., description="Registered repo name"),
    q: str = Query(..., description="Natural-language question"),
    budget: int = Query(2000, ge=200, le=20000),
    dfs: bool = False,
):
    await _require_caller(request)
    try:
        result = await query.query(repo, q, budget=budget, dfs=dfs)
    except query.GraphNotReady as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"query failed: {exc}")
    return {"repo": repo, "result": result}


@app.get("/repos/{name}/report")
async def repo_report(name: str, request: Request):
    await _require_caller(request)
    report_path = os.path.join(db.graph_dir(name), "GRAPH_REPORT.md")
    if not os.path.exists(report_path):
        raise HTTPException(status_code=404, detail="no report — build the graph first")
    return FileResponse(report_path, media_type="text/markdown")


@app.get("/repos/{name}/graph.html")
async def repo_graph_html(name: str, request: Request):
    await _require_caller(request)
    html_path = os.path.join(db.graph_dir(name), "graph.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="no graph.html — build the graph first")
    return FileResponse(html_path, media_type="text/html")


# ---------------------------------------------------------------------------
# MCP tool implementations (shared by REST + JSON-RPC surfaces)
# ---------------------------------------------------------------------------


async def _tool_list_repos(_args: dict) -> dict:
    pool = await get_pool()
    rows = await db.list_repos(pool)
    ready = [_repo_public(r) for r in rows if r["status"] == "ready"]
    return {"repos": ready}


async def _tool_graph_query(args: dict) -> dict:
    repo = args.get("repo")
    question = args.get("question")
    if not repo or not question:
        raise ValueError("repo and question are required")
    result = await query.query(
        repo, question, budget=int(args.get("budget", 2000)), dfs=bool(args.get("dfs", False))
    )
    return {"repo": repo, "result": result}


async def _tool_graph_path(args: dict) -> dict:
    repo, source, target = args.get("repo"), args.get("source"), args.get("target")
    if not repo or not source or not target:
        raise ValueError("repo, source and target are required")
    return {"repo": repo, "result": await query.path(repo, source, target)}


async def _tool_graph_explain(args: dict) -> dict:
    repo, node = args.get("repo"), args.get("node")
    if not repo or not node:
        raise ValueError("repo and node are required")
    return {"repo": repo, "result": await query.explain(repo, node)}


async def _tool_graph_stats(args: dict) -> dict:
    repo = args.get("repo")
    if not repo:
        raise ValueError("repo is required")
    return query.stats(repo, top_n=int(args.get("top_n", 10)))


_TOOL_HANDLERS = {
    "list_repos": _tool_list_repos,
    "graph_query": _tool_graph_query,
    "graph_path": _tool_graph_path,
    "graph_explain": _tool_graph_explain,
    "graph_stats": _tool_graph_stats,
}


def _input_schema(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}


_REPO_PROP = {"repo": {"type": "string", "description": "Registered repo name (e.g. 'ims')"}}

_TOOLS = [
    {
        "name": "list_repos",
        "description": "List repos with a ready knowledge graph",
        "schema": _input_schema({}, []),
    },
    {
        "name": "graph_query",
        "description": (
            "Ask a natural-language question about a repo and get a token-efficient "
            "subgraph (concepts + relationships) instead of raw files."
        ),
        "schema": _input_schema(
            {
                **_REPO_PROP,
                "question": {"type": "string"},
                "budget": {"type": "integer", "default": 2000},
                "dfs": {"type": "boolean", "default": False},
            },
            ["repo", "question"],
        ),
    },
    {
        "name": "graph_path",
        "description": "Find how two concepts/symbols in a repo are connected",
        "schema": _input_schema(
            {**_REPO_PROP, "source": {"type": "string"}, "target": {"type": "string"}},
            ["repo", "source", "target"],
        ),
    },
    {
        "name": "graph_explain",
        "description": "Explain a node (symbol/concept) and its neighborhood in a repo",
        "schema": _input_schema({**_REPO_PROP, "node": {"type": "string"}}, ["repo", "node"]),
    },
    {
        "name": "graph_stats",
        "description": "Node/edge counts and the most-connected 'god nodes' of a repo's graph",
        "schema": _input_schema(
            {**_REPO_PROP, "top_n": {"type": "integer", "default": 10}}, ["repo"]
        ),
    },
]

# Two shapes of the tool list: `input_schema` (manifest/REST) and `inputSchema`
# (JSON-RPC tools/list), matching librarian's conventions.
_MCP_TOOLS = [
    {"name": t["name"], "description": t["description"], "input_schema": t["schema"]}
    for t in _TOOLS
]
_MCP_JSONRPC_TOOLS = [
    {"name": t["name"], "description": t["description"], "inputSchema": t["schema"]} for t in _TOOLS
]

_MCP_MANIFEST = {
    "name": "graphify",
    "version": "1.0.0",
    "description": "Query knowledge graphs of repos. Navigate code by concepts and relationships, not raw files.",
    "tools": _MCP_TOOLS,
}

_MCP_PROTOCOL_VERSION = "2024-11-05"


# ---------------------------------------------------------------------------
# MCP discovery (public) + REST tools (sk-*)
# ---------------------------------------------------------------------------


@app.get("/mcp/manifest")
async def mcp_manifest():
    return _MCP_MANIFEST


@app.get("/mcp/tools")
async def mcp_tools_list():
    return _MCP_TOOLS


@app.get("/mcp")
async def mcp_root():
    return _MCP_MANIFEST


@app.post("/mcp/tools/{tool_name}")
async def mcp_rest_tool(tool_name: str, body: dict, request: Request):
    await _require_caller(request)
    handler = _TOOL_HANDLERS.get(tool_name)
    if handler is None:
        raise HTTPException(status_code=404, detail=f"unknown tool: {tool_name}")
    try:
        return await handler(body or {})
    except query.GraphNotReady as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 MCP endpoint + SSE transport (mirrors librarian)
# ---------------------------------------------------------------------------


@app.post("/mcp")
async def mcp_jsonrpc(body: dict, request: Request, session_id: str | None = None):
    import hashlib as _hashlib
    import json as _json_m

    method: str = body.get("method", "")
    params: dict = body.get("params") or {}
    request_id = body.get("id")
    is_notification = "id" not in body

    def _ok(result: Any) -> dict:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _err(code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    _raw_token = request.headers.get("Authorization", "")[len("Bearer ") :]
    _caller_hash = _hashlib.sha256(_raw_token.encode()).hexdigest()

    async def _relay_or_return(response: dict) -> Any:
        if session_id is not None:
            _sessions = getattr(app.state, "_mcp_sse_sessions", {})
            _entry = _sessions.get(session_id)
            if _entry is not None:
                if _entry["caller_hash"] != _caller_hash:
                    return Response(status_code=403)
                await _entry["queue"].put(_json_m.dumps(response))
                return Response(status_code=202)
        return response

    try:
        await resolve_caller(request)
    except AuthError as exc:
        return await _relay_or_return(_err(-32000, exc.detail))

    if method == "initialize":
        if is_notification:
            return Response(status_code=204)
        return await _relay_or_return(
            _ok(
                {
                    "protocolVersion": _MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "graphify", "version": "1.0.0"},
                }
            )
        )

    if method == "notifications/initialized":
        return Response(status_code=204)

    if method == "tools/list":
        if is_notification:
            return Response(status_code=204)
        return await _relay_or_return(_ok({"tools": _MCP_JSONRPC_TOOLS}))

    if method == "tools/call":
        if is_notification:
            return Response(status_code=204)
        tool_name = params.get("name", "")
        arguments = params.get("arguments") or {}
        handler = _TOOL_HANDLERS.get(tool_name)
        if handler is None:
            return await _relay_or_return(_err(-32601, f"Tool not found: {tool_name}"))
        try:
            result = await handler(arguments)
        except query.GraphNotReady as exc:
            return await _relay_or_return(_err(-32000, str(exc)))
        except ValueError as exc:
            return await _relay_or_return(_err(-32602, str(exc)))
        except Exception as exc:
            _log.exception("MCP tool %s error", tool_name)
            return await _relay_or_return(_err(-32603, f"Tool execution error: {exc}"))
        return await _relay_or_return(
            _ok({"content": [{"type": "text", "text": _json_m.dumps(result)}]})
        )

    if method == "ping":
        if is_notification:
            return Response(status_code=204)
        return await _relay_or_return(_ok({}))

    if is_notification:
        return Response(status_code=204)

    return await _relay_or_return(_err(-32601, f"Method not found: {method}"))


@app.get("/mcp/sse")
async def mcp_sse(request: Request):
    await _require_caller(request)
    import asyncio as _asyncio
    import hashlib as _hashlib
    import secrets as _secrets

    from fastapi.responses import StreamingResponse as _SSE

    queue: _asyncio.Queue[str | None] = _asyncio.Queue()
    conn_id = _secrets.token_urlsafe(32)

    raw_token = request.headers.get("Authorization", "")[len("Bearer ") :]
    caller_hash = _hashlib.sha256(raw_token.encode()).hexdigest()

    sessions = getattr(app.state, "_mcp_sse_sessions", {})
    sessions[conn_id] = {"queue": queue, "caller_hash": caller_hash}
    app.state._mcp_sse_sessions = sessions

    base = str(request.base_url).rstrip("/")
    post_url = f"{base}/mcp?session_id={conn_id}"

    async def _stream():
        yield f"event: endpoint\ndata: {post_url}\n\n"
        try:
            while True:
                try:
                    item = await _asyncio.wait_for(queue.get(), timeout=15.0)
                except _asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if item is None:
                    break
                yield f"event: message\ndata: {item}\n\n"
        finally:
            sessions.pop(conn_id, None)

    return _SSE(_stream(), media_type="text/event-stream")
