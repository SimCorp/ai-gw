"""
AI Librarian service — shared knowledge store with semantic search and an MCP server.

Architecture notes (per advisor review):
- Postgres-filter-first for topic/tag filtering, then fetch embeddings from Redis by key.
- Embedding done via AsyncOpenAI (same pattern as cache service).
- Health endpoint at /health (required by docker-compose healthcheck).
- CORS middleware to allow portal direct browser calls.
- MCP /mcp/tools endpoint (GET) so admin's ping_server can discover tools.
- Research agent calls internal function, not HTTP loopback.
"""

import asyncio
import json
import logging
import re
import uuid
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
import httpx
import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI
from prometheus_client import make_asgi_app
from pydantic import BaseModel
from redis.asyncio import Redis

from app.auth import AuthError, resolve_caller
from app.config import settings
from app.logging_config import CorrelationIdMiddleware, init_logging

_log = logging.getLogger(__name__)


async def _require_caller(request: Request) -> None:
    """Gate an MCP request on a valid sk-* Bearer; map AuthError → HTTP error."""
    try:
        await resolve_caller(request)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


# ---------------------------------------------------------------------------
# Embedding client (AsyncOpenAI — same pattern as cache service)
# ---------------------------------------------------------------------------

_openai = AsyncOpenAI(
    api_key=settings.embedding_api_key,
    base_url=settings.embedding_base_url,
)


async def _embed(text: str) -> list[float]:
    resp = await _openai.embeddings.create(
        input=text,
        model=settings.embedding_model,
    )
    return resp.data[0].embedding


def _cosine(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a, dtype=float), np.array(b, dtype=float)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(np.dot(va, vb) / denom) if denom else 0.0


# ---------------------------------------------------------------------------
# Database connection pool (asyncpg — raw, no SQLAlchemy overhead)
# ---------------------------------------------------------------------------

_pool: asyncpg.Pool | None = None
_redis: Redis | None = None


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised")
    return _pool


async def get_redis() -> Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialised")
    return _redis


# ---------------------------------------------------------------------------
# Ingest auth + content validation helpers
# ---------------------------------------------------------------------------

_SOURCE_URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)
_MAX_CONTENT_LEN = 50_000
_MAX_TAGS = 20
_MAX_TAG_LEN = 50


def _check_ingest_token(request: Request) -> None:
    """Verify X-Service-Token header for ingest endpoints.

    Fails open when LIBRARIAN_SERVICE_TOKEN is not configured (dev mode).
    """
    if not settings.librarian_service_token:
        return
    provided = request.headers.get("X-Service-Token", "")
    if provided != settings.librarian_service_token:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Service-Token")


def _validate_ingest_content(
    content: str,
    source_url: str | None,
    tags: list[str],
) -> None:
    """Validate ingest payload fields and raise 422 on violation."""
    if len(content) > _MAX_CONTENT_LEN:
        raise HTTPException(
            status_code=422,
            detail=f"content exceeds maximum length of {_MAX_CONTENT_LEN} characters",
        )
    if source_url is not None and not _SOURCE_URL_PATTERN.match(source_url):
        raise HTTPException(
            status_code=422,
            detail="source_url must start with http:// or https://",
        )
    if len(tags) > _MAX_TAGS:
        raise HTTPException(
            status_code=422,
            detail=f"tags list exceeds maximum of {_MAX_TAGS} items",
        )
    for tag in tags:
        if len(tag) > _MAX_TAG_LEN:
            raise HTTPException(
                status_code=422,
                detail=f"each tag must be at most {_MAX_TAG_LEN} characters",
            )


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source_url TEXT,
    topic TEXT,
    tags TEXT[] NOT NULL DEFAULT '{}',
    embedding_key TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS knowledge_items_topic_idx ON knowledge_items(topic);
CREATE INDEX IF NOT EXISTS knowledge_items_ingested_idx ON knowledge_items(ingested_at DESC);

CREATE TABLE IF NOT EXISTS research_topics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic TEXT NOT NULL UNIQUE,
    description TEXT,
    search_query TEXT NOT NULL,
    last_researched_at TIMESTAMPTZ,
    interval_seconds INT NOT NULL DEFAULT 3600,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);
"""

_DEFAULT_RESEARCH_TOPICS = [
    {
        "topic": "ai-coding",
        "description": "AI-assisted software development",
        "search_query": (
            "Latest developments in AI-assisted software development, coding tools, "
            "LLM-based coding agents, and best practices for 2026"
        ),
        "interval_seconds": 3600,
    },
    {
        "topic": "saas-best-practices",
        "description": "SaaS product architecture and developer experience",
        "search_query": (
            "Current best practices for SaaS product architecture, multi-tenancy, pricing models, "
            "and developer experience in 2026"
        ),
        "interval_seconds": 7200,
    },
    {
        "topic": "security-sdlc",
        "description": "Security in the software development lifecycle",
        "search_query": (
            "Security in the software development lifecycle: SAST, DAST, supply chain security, "
            "AI-assisted security review, and DevSecOps practices in 2026"
        ),
        "interval_seconds": 7200,
    },
    {
        "topic": "platform-engineering",
        "description": "Internal developer platforms and golden paths",
        "search_query": (
            "Internal developer platforms, golden paths, developer experience metrics (DORA/SPACE), "
            "and platform engineering patterns in 2026"
        ),
        "interval_seconds": 7200,
    },
]


async def _bootstrap_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA_SQL)

        # Seed default research topics if table is empty
        count = await conn.fetchval("SELECT COUNT(*) FROM research_topics")
        if count == 0:
            for topic in _DEFAULT_RESEARCH_TOPICS:
                await conn.execute(
                    """
                    INSERT INTO research_topics (topic, description, search_query, interval_seconds)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (topic) DO NOTHING
                    """,
                    topic["topic"],
                    topic.get("description"),
                    topic["search_query"],
                    topic["interval_seconds"],
                )
            _log.info("Seeded %d default research topics", len(_DEFAULT_RESEARCH_TOPICS))


# ---------------------------------------------------------------------------
# Core document store functions (shared between HTTP routes and research loop)
# ---------------------------------------------------------------------------


async def ingest_document(
    *,
    pool: asyncpg.Pool,
    redis: Redis,
    title: str,
    content: str,
    source_url: str | None = None,
    topic: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Embed a document and persist it to Postgres + Redis. Returns the item UUID."""
    tags = tags or []

    # Compute embedding
    try:
        embedding = await _embed(f"{title}\n\n{content}")
    except Exception:
        _log.exception("Embedding failed for document: %s", title)
        embedding = None

    doc_id = str(uuid.uuid4())
    embedding_key: str | None = None

    if embedding is not None:
        embedding_key = f"lib:embed:{doc_id}"
        await redis.set(embedding_key, json.dumps(embedding))

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO knowledge_items
                (id, title, content, source_url, topic, tags, embedding_key)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            uuid.UUID(doc_id),
            title,
            content,
            source_url,
            topic,
            tags,
            embedding_key,
        )

    _log.info("Ingested document id=%s topic=%s", doc_id, topic)
    return doc_id


async def search_knowledge(
    *,
    pool: asyncpg.Pool,
    redis: Redis,
    query: str,
    topic: str | None = None,
    tags: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """Semantic search: Postgres-filter first, then cosine similarity on Redis embeddings."""
    try:
        query_embedding = await _embed(query)
    except Exception:
        _log.exception("Embedding query failed")
        return []

    # Postgres-first: filter by topic / tags
    async with pool.acquire() as conn:
        if topic and tags:
            rows = await conn.fetch(
                """
                SELECT id, title, content, source_url, topic, tags, embedding_key, ingested_at
                FROM knowledge_items
                WHERE topic = $1 AND tags && $2
                ORDER BY ingested_at DESC
                """,
                topic,
                tags,
            )
        elif topic:
            rows = await conn.fetch(
                """
                SELECT id, title, content, source_url, topic, tags, embedding_key, ingested_at
                FROM knowledge_items
                WHERE topic = $1
                ORDER BY ingested_at DESC
                """,
                topic,
            )
        elif tags:
            rows = await conn.fetch(
                """
                SELECT id, title, content, source_url, topic, tags, embedding_key, ingested_at
                FROM knowledge_items
                WHERE tags && $1
                ORDER BY ingested_at DESC
                """,
                tags,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, title, content, source_url, topic, tags, embedding_key, ingested_at
                FROM knowledge_items
                ORDER BY ingested_at DESC
                LIMIT 500
                """
            )

    if not rows:
        return []

    # Fetch embeddings from Redis in batch using MGET
    keys = [r["embedding_key"] for r in rows if r["embedding_key"]]
    key_to_embedding: dict[str, list[float]] = {}

    if keys:
        values = await redis.mget(*keys)
        for key, raw in zip(keys, values):
            if raw:
                key_to_embedding[key] = json.loads(raw)

    # Score each row
    scored: list[tuple[float, dict]] = []
    for row in rows:
        emb_key = row["embedding_key"]
        if emb_key and emb_key in key_to_embedding:
            score = _cosine(query_embedding, key_to_embedding[emb_key])
        else:
            score = 0.0

        scored.append(
            (
                score,
                {
                    "id": str(row["id"]),
                    "title": row["title"],
                    "content": row["content"],
                    "source_url": row["source_url"],
                    "topic": row["topic"],
                    "tags": list(row["tags"]),
                    "ingested_at": row["ingested_at"].isoformat() if row["ingested_at"] else None,
                    "score": round(score, 4),
                },
            )
        )

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:limit]]


# ---------------------------------------------------------------------------
# Research agent background task
# ---------------------------------------------------------------------------

_RESEARCH_SYSTEM_PROMPT = (
    "You are a research agent. Given the following research query, write a structured summary "
    "covering the latest concepts, best practices, and key insights. Be thorough but concise. "
    'Return a JSON object: {"title": "...", "content": "...", "tags": ["...", "..."]}'
)


async def _run_research_for_topic(pool: asyncpg.Pool, redis: Redis, topic_row: dict) -> None:
    """Run a single research cycle for one topic."""
    topic = topic_row["topic"]
    search_query = topic_row["search_query"]

    _log.info("Researching topic: %s", topic)

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.cache_url}/v1/chat/completions",
                json={
                    "model": "gpt-4o-mini",  # gateway will route appropriately
                    "messages": [
                        {"role": "system", "content": _RESEARCH_SYSTEM_PROMPT},
                        {"role": "user", "content": search_query},
                    ],
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
    except Exception:
        _log.exception("LLM call failed for research topic: %s", topic)
        return

    try:
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        result = json.loads(text)
    except Exception:
        _log.exception("Failed to parse LLM response for topic: %s", topic)
        return

    title = result.get("title") or f"Research: {topic}"
    content = result.get("content") or ""
    tags: list[str] = result.get("tags") or []

    if not content:
        _log.warning("Empty content for research topic: %s — skipping ingest", topic)
        return

    await ingest_document(
        pool=pool,
        redis=redis,
        title=title,
        content=content,
        topic=topic,
        tags=tags,
    )

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE research_topics SET last_researched_at = NOW() WHERE topic = $1",
            topic,
        )

    _log.info("Research complete for topic: %s", topic)


async def _research_loop(pool: asyncpg.Pool, redis: Redis) -> None:
    """Background loop: poll for stale research topics and update them."""
    # Give other services time to start up before first research run
    await asyncio.sleep(30)

    while True:
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT topic, search_query, interval_seconds, last_researched_at
                    FROM research_topics
                    WHERE enabled = TRUE
                      AND (
                          last_researched_at IS NULL
                          OR last_researched_at < NOW() - (interval_seconds || ' seconds')::interval
                      )
                    """
                )

            for row in rows:
                try:
                    await _run_research_for_topic(pool, redis, dict(row))
                except Exception:
                    _log.exception("Unhandled error researching topic: %s", row["topic"])

        except Exception:
            _log.exception("Research loop iteration failed")

        await asyncio.sleep(settings.research_interval_seconds)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool, _redis

    # Strip asyncpg scheme qualifier for asyncpg (it wants postgresql:// not postgresql+asyncpg://)
    db_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    _pool = await asyncpg.create_pool(db_url, min_size=2, max_size=10)
    _redis = Redis.from_url(settings.redis_url, decode_responses=True)

    await _bootstrap_schema(_pool)

    # Start background research loop
    research_task = asyncio.create_task(_research_loop(_pool, _redis))

    # Auto-register with admin MCP registry (fail silently)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                "http://admin:8005/mcp/servers",
                json={
                    "name": "AI Librarian",
                    "description": "Shared research knowledge base with semantic search",
                    "url": "http://librarian:8008/mcp",
                    "auth_type": "none",
                },
            )
            _log.info("Registered librarian as MCP server in admin")
    except Exception:
        _log.info("Admin MCP auto-register skipped (admin not reachable yet)")

    yield

    research_task.cancel()
    try:
        await research_task
    except asyncio.CancelledError:
        pass

    await _pool.close()
    await _redis.aclose()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

init_logging("librarian")
app = FastAPI(title="AI Librarian", version="1.0.0", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)
app.mount("/metrics", make_asgi_app())

# CORS — allow portal browser calls (advisor point #4)
_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    errors: dict[str, str] = {}
    try:
        redis = await get_redis()
        await redis.ping()
    except Exception:
        errors["redis"] = "connection failed"
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception:
        errors["postgres"] = "connection failed"
    if errors:
        return JSONResponse({"status": "not_ready", "errors": errors}, status_code=503)
    return {"status": "ready"}


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class IngestRequest(BaseModel):
    title: str
    content: str
    source_url: str | None = None
    topic: str | None = None
    tags: list[str] = []


class ResearchTopicCreate(BaseModel):
    topic: str
    description: str | None = None
    search_query: str
    interval_seconds: int = 3600


# ---------------------------------------------------------------------------
# Document store routes
# ---------------------------------------------------------------------------


@app.post("/ingest", status_code=201)
async def ingest(body: IngestRequest, request: Request):
    _check_ingest_token(request)
    _validate_ingest_content(body.content, body.source_url, body.tags)
    pool = await get_pool()
    redis = await get_redis()
    doc_id = await ingest_document(
        pool=pool,
        redis=redis,
        title=body.title,
        content=body.content,
        source_url=body.source_url,
        topic=body.topic,
        tags=body.tags,
    )
    return {"id": doc_id}


@app.get("/search")
async def search(
    q: str = Query(..., description="Search query"),
    topic: str | None = None,
    tags: str | None = Query(None, description="Comma-separated tag filter"),
    limit: int = Query(10, ge=1, le=100),
):
    pool = await get_pool()
    redis = await get_redis()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    results = await search_knowledge(
        pool=pool,
        redis=redis,
        query=q,
        topic=topic,
        tags=tag_list,
        limit=limit,
    )
    return {"results": results, "count": len(results)}


@app.get("/topics")
async def list_topics():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT topic, COUNT(*) AS item_count, MAX(ingested_at) AS last_ingested_at
            FROM knowledge_items
            GROUP BY topic
            ORDER BY topic
            """
        )
    return [
        {
            "topic": r["topic"],
            "item_count": r["item_count"],
            "last_ingested_at": r["last_ingested_at"].isoformat()
            if r["last_ingested_at"]
            else None,
        }
        for r in rows
    ]


@app.get("/topics/{topic}")
async def get_topic_items(topic: str, limit: int = Query(20, ge=1, le=200)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, title, content, source_url, tags, ingested_at
            FROM knowledge_items
            WHERE topic = $1
            ORDER BY ingested_at DESC
            LIMIT $2
            """,
            topic,
            limit,
        )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No items for topic '{topic}'")
    return [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "content": r["content"],
            "source_url": r["source_url"],
            "tags": list(r["tags"]),
            "ingested_at": r["ingested_at"].isoformat() if r["ingested_at"] else None,
        }
        for r in rows
    ]


@app.delete("/items/{item_id}", status_code=204)
async def delete_item(item_id: str, request: Request):
    await _require_caller(request)
    pool = await get_pool()
    redis = await get_redis()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "DELETE FROM knowledge_items WHERE id = $1 RETURNING id, embedding_key",
            uuid.UUID(item_id),
        )
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")
    if row["embedding_key"]:
        await redis.delete(row["embedding_key"])


# ---------------------------------------------------------------------------
# Research topic routes
# ---------------------------------------------------------------------------


@app.get("/research/topics")
async def list_research_topics():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM research_topics ORDER BY topic")
    return [
        {
            "id": str(r["id"]),
            "topic": r["topic"],
            "description": r["description"],
            "search_query": r["search_query"],
            "last_researched_at": r["last_researched_at"].isoformat()
            if r["last_researched_at"]
            else None,
            "interval_seconds": r["interval_seconds"],
            "enabled": r["enabled"],
        }
        for r in rows
    ]


@app.post("/research/topics", status_code=201)
async def create_research_topic(body: ResearchTopicCreate, request: Request):
    await _require_caller(request)
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO research_topics (topic, description, search_query, interval_seconds)
                VALUES ($1, $2, $3, $4)
                RETURNING *
                """,
                body.topic,
                body.description,
                body.search_query,
                body.interval_seconds,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(status_code=409, detail=f"Topic '{body.topic}' already exists")

    return {
        "id": str(row["id"]),
        "topic": row["topic"],
        "description": row["description"],
        "search_query": row["search_query"],
        "interval_seconds": row["interval_seconds"],
        "enabled": row["enabled"],
    }


@app.post("/research/topics/{topic}/trigger")
async def trigger_research(topic: str, request: Request):
    await _require_caller(request)
    pool = await get_pool()
    redis = await get_redis()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM research_topics WHERE topic = $1",
            topic,
        )
    if not row:
        raise HTTPException(status_code=404, detail=f"Topic '{topic}' not found")

    # Run async in background so HTTP returns immediately
    asyncio.create_task(_run_research_for_topic(pool, redis, dict(row)))
    return {"status": "triggered", "topic": topic}


@app.delete("/research/topics/{topic}", status_code=204)
async def delete_research_topic(topic: str, request: Request):
    await _require_caller(request)
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM research_topics WHERE topic = $1",
            topic,
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail=f"Topic '{topic}' not found")


# ---------------------------------------------------------------------------
# MCP server endpoints
# ---------------------------------------------------------------------------

_MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "search",
        "description": "Search the knowledge base semantically",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "topic": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "ingest",
        "description": "Add a document to the knowledge base",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "topic": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "topics",
        "description": "List all research topics",
        "input_schema": {"type": "object"},
    },
]

_MCP_MANIFEST = {
    "name": "ai-librarian",
    "version": "1.0.0",
    "description": "Shared AI knowledge base. Search and ingest research findings across topics.",
    "tools": _MCP_TOOLS,
}


@app.get("/mcp/manifest")
async def mcp_manifest():
    return _MCP_MANIFEST


# GET /mcp/tools — allows admin's ping_server to discover tools (advisor point #2)
@app.get("/mcp/tools")
async def mcp_tools_list():
    return _MCP_TOOLS


# GET /mcp — fallback for admin ping_server
@app.get("/mcp")
async def mcp_root():
    return _MCP_MANIFEST


@app.post("/mcp/tools/search")
async def mcp_search(body: dict, request: Request):
    await _require_caller(request)
    query = body.get("query", "")
    if not query:
        raise HTTPException(status_code=422, detail="query is required")
    topic = body.get("topic")
    limit = int(body.get("limit", 5))

    pool = await get_pool()
    redis = await get_redis()
    items = await search_knowledge(
        pool=pool,
        redis=redis,
        query=query,
        topic=topic,
        limit=limit,
    )
    return {"items": items}


@app.post("/mcp/tools/ingest")
async def mcp_ingest(body: dict, request: Request):
    _check_ingest_token(request)
    title = body.get("title", "")
    content = body.get("content", "")
    if not title or not content:
        raise HTTPException(status_code=422, detail="title and content are required")

    tags = body.get("tags") or []
    _validate_ingest_content(content, body.get("source_url"), tags)

    pool = await get_pool()
    redis = await get_redis()
    doc_id = await ingest_document(
        pool=pool,
        redis=redis,
        title=title,
        content=content,
        topic=body.get("topic"),
        tags=tags,
    )
    return {"id": doc_id}


@app.post("/mcp/tools/topics")
async def mcp_topics(request: Request):
    await _require_caller(request)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT topic, COUNT(*) AS item_count, MAX(ingested_at) AS last_ingested_at
            FROM knowledge_items
            GROUP BY topic
            ORDER BY topic
            """
        )
    return {
        "topics": [
            {
                "topic": r["topic"],
                "item_count": r["item_count"],
                "last_ingested_at": r["last_ingested_at"].isoformat()
                if r["last_ingested_at"]
                else None,
            }
            for r in rows
        ]
    }


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 MCP endpoint — for real MCP clients (VS Code, Claude Desktop)
#
# The librarian service cannot import from the admin package, so this
# implements the same MCPServer pattern inline using a minimal dispatcher.
# POST /mcp receives JSON-RPC 2.0 bodies and returns compliant responses.
# ---------------------------------------------------------------------------

_MCP_PROTOCOL_VERSION = "2024-11-05"
_MCP_JSONRPC_TOOLS = [
    {
        "name": "search",
        "description": "Search the knowledge base semantically",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "topic": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "ingest",
        "description": "Add a document to the knowledge base",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "topic": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "topics",
        "description": "List all research topics",
        "inputSchema": {"type": "object"},
    },
]


async def _jsonrpc_tool_search(arguments: dict) -> dict:
    query = arguments.get("query", "")
    if not query:
        raise ValueError("query is required")
    pool = await get_pool()
    redis = await get_redis()
    items = await search_knowledge(
        pool=pool,
        redis=redis,
        query=query,
        topic=arguments.get("topic"),
        limit=int(arguments.get("limit", 5)),
    )
    return {"items": items}


async def _jsonrpc_tool_ingest(arguments: dict) -> dict:
    title = arguments.get("title", "")
    content = arguments.get("content", "")
    if not title or not content:
        raise ValueError("title and content are required")
    pool = await get_pool()
    redis = await get_redis()
    doc_id = await ingest_document(
        pool=pool,
        redis=redis,
        title=title,
        content=content,
        topic=arguments.get("topic"),
        tags=arguments.get("tags") or [],
    )
    return {"id": doc_id}


async def _jsonrpc_tool_topics(_arguments: dict) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT topic, COUNT(*) AS item_count, MAX(ingested_at) AS last_ingested_at
            FROM knowledge_items
            GROUP BY topic
            ORDER BY topic
            """
        )
    return {
        "topics": [
            {
                "topic": r["topic"],
                "item_count": r["item_count"],
                "last_ingested_at": (
                    r["last_ingested_at"].isoformat() if r["last_ingested_at"] else None
                ),
            }
            for r in rows
        ]
    }


_JSONRPC_TOOL_HANDLERS = {
    "search": _jsonrpc_tool_search,
    "ingest": _jsonrpc_tool_ingest,
    "topics": _jsonrpc_tool_topics,
}


from fastapi.responses import Response as _Response  # noqa: E402


@app.post("/mcp")
async def mcp_jsonrpc(body: dict, request: Request, session_id: str | None = None):
    """JSON-RPC 2.0 MCP endpoint consumed by real MCP clients."""
    method: str = body.get("method", "")
    params: dict = body.get("params") or {}
    request_id = body.get("id")
    is_notification = "id" not in body

    def _ok(result: Any) -> dict:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _err(code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    import hashlib as _hashlib
    import json as _json_m

    # Hash the current caller's token once for session-binding verification.
    _raw_token = request.headers.get("Authorization", "")[len("Bearer ") :]
    _caller_hash = _hashlib.sha256(_raw_token.encode()).hexdigest()

    async def _relay_or_return(response: dict) -> Any:
        """Push response to SSE queue if a valid session_id is bound, else return directly.

        Verifies that the caller posting to this session is the same principal
        that opened the SSE connection, preventing cross-session injection.
        """
        if session_id is not None:
            _sessions = getattr(app.state, "_mcp_sse_sessions", {})
            _entry = _sessions.get(session_id)  # str key — no int() conversion
            if _entry is not None:
                if _entry["caller_hash"] != _caller_hash:
                    # Different caller trying to inject into another session — reject.
                    return _Response(status_code=403)
                await _entry["queue"].put(_json_m.dumps(response))
                return _Response(status_code=202)
        return response

    # Authenticate every JSON-RPC call (incl. initialize) — auth failures map to
    # -32000 so the MCP client surfaces them cleanly.
    try:
        await resolve_caller(request)
    except AuthError as exc:
        return await _relay_or_return(_err(-32000, exc.detail))

    if method == "initialize":
        if is_notification:
            return _Response(status_code=204)
        return await _relay_or_return(
            _ok(
                {
                    "protocolVersion": _MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "ai-librarian", "version": "1.0.0"},
                }
            )
        )

    if method == "notifications/initialized":
        return _Response(status_code=204)

    if method == "tools/list":
        if is_notification:
            return _Response(status_code=204)
        return await _relay_or_return(_ok({"tools": _MCP_JSONRPC_TOOLS}))

    if method == "tools/call":
        if is_notification:
            return _Response(status_code=204)
        tool_name = params.get("name", "")
        arguments = params.get("arguments") or {}
        handler = _JSONRPC_TOOL_HANDLERS.get(tool_name)
        if handler is None:
            return await _relay_or_return(_err(-32601, f"Tool not found: {tool_name}"))
        try:
            result = await handler(arguments)
        except Exception:
            _log.exception("MCP tool %s error", tool_name)
            return await _relay_or_return(_err(-32603, "Tool execution error"))

        return await _relay_or_return(
            _ok({"content": [{"type": "text", "text": _json_m.dumps(result)}]})
        )

    if method == "ping":
        if is_notification:
            return _Response(status_code=204)
        return await _relay_or_return(_ok({}))

    if is_notification:
        return _Response(status_code=204)

    _log.debug("MCP unknown method: %s", method)
    return await _relay_or_return(_err(-32601, f"Method not found: {method}"))


# GET /mcp/sse — HTTP+SSE transport for MCP clients that require it
@app.get("/mcp/sse")
async def mcp_sse(request: Request):
    """HTTP+SSE MCP transport.

    Sends an 'endpoint' event pointing to POST /mcp, then relays responses
    for any JSON-RPC calls the client makes to that URL.
    """
    await _require_caller(request)
    import asyncio as _asyncio
    import hashlib as _hashlib
    import secrets as _secrets

    from fastapi.responses import StreamingResponse as _SSE

    # Use a cryptographically random session token — NOT id(queue) which is a
    # predictable memory address and can be enumerated by authenticated callers.
    queue: _asyncio.Queue[str | None] = _asyncio.Queue()
    conn_id = _secrets.token_urlsafe(32)

    # Bind session to the caller's token so only the originating client can POST to it.
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
