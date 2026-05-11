"""
AI Gateway — Identity Pool service (Pillar 4)

Queryable agent registry / "DNS for agents".  Any workflow or agent can look
up peers by slug, capability tag, category, or partial name.

Table: agent_identities  (created on startup — no Alembic needed)
Redis heartbeat key: identity:online:{slug}  TTL 60 s
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from app.config import settings

log = logging.getLogger("identity")

# ---------------------------------------------------------------------------
# DDL — created once at startup
# ---------------------------------------------------------------------------

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS agent_identities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    category        TEXT,
    capabilities    TEXT[]  NOT NULL DEFAULT '{}',
    endpoint        TEXT    NOT NULL DEFAULT '',
    team_id         UUID,
    managed         BOOLEAN NOT NULL DEFAULT FALSE,
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

# Migration: add token_verified column if it doesn't exist yet (idempotent)
_ALTER_TOKEN_VERIFIED = """
ALTER TABLE agent_identities
    ADD COLUMN IF NOT EXISTS token_verified BOOLEAN NOT NULL DEFAULT FALSE;
"""

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class AgentIdentity(BaseModel):
    id: UUID
    slug: str
    name: str
    category: str | None
    capabilities: list[str]
    endpoint: str
    team_id: UUID | None
    managed: bool
    online: bool
    token_verified: bool = False
    registered_at: datetime
    last_seen: datetime


class RegisterRequest(BaseModel):
    slug: str
    name: str
    category: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    endpoint: str = ""
    team_id: UUID | None = None
    managed: bool = False
    identity_token: str | None = None  # optional DID-style signed JWT for verification


class AgentIdentitySummary(BaseModel):
    slug: str
    token_verified: bool
    capabilities: list[str]
    online: bool


class EndpointResponse(BaseModel):
    endpoint: str
    agent_id: str
    online: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HEARTBEAT_TTL = 60  # seconds


def _heartbeat_key(slug: str) -> str:
    return f"identity:online:{slug}"


async def _is_online(redis: Redis, slug: str) -> bool:
    return bool(await redis.exists(_heartbeat_key(slug)))


def _row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    return dict(row)


async def _to_identity(row: asyncpg.Record, redis: Redis) -> AgentIdentity:
    d = _row_to_dict(row)
    d["online"] = await _is_online(redis, d["slug"])
    return AgentIdentity(**d)


# ---------------------------------------------------------------------------
# Seed from admin service on startup
# ---------------------------------------------------------------------------


async def _verify_identity_token(token: str, admin_url: str) -> bool:
    """Verify a DID-style identity JWT against the admin service JWKS.

    Fetches the JWKS from ``{admin_url}/identity/jwks`` and verifies the
    token's RS256 signature.  Returns True on success, False on any failure
    (network error, bad signature, expiry, etc.).
    """
    try:
        import jwt as _jwt
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{admin_url}/identity/jwks")
            if resp.status_code != 200:
                log.warning("JWKS fetch returned %s", resp.status_code)
                return False
            jwks_data = resp.json()

        keys = jwks_data.get("keys", [])
        if not keys:
            log.warning("JWKS response contained no keys")
            return False

        # Try each key until one verifies successfully
        from cryptography.hazmat.primitives.asymmetric import rsa as _rsa
        import base64 as _b64

        def _decode_b64url(s: str) -> int:
            # Add padding if needed
            padded = s + "=" * (-len(s) % 4)
            return int.from_bytes(_b64.urlsafe_b64decode(padded), "big")

        for jwk in keys:
            if jwk.get("kty") != "RSA":
                continue
            try:
                from cryptography.hazmat.primitives.asymmetric.rsa import (
                    RSAPublicNumbers,
                )
                pub_numbers = RSAPublicNumbers(
                    e=_decode_b64url(jwk["e"]),
                    n=_decode_b64url(jwk["n"]),
                )
                pub_key = pub_numbers.public_key()
                _jwt.decode(
                    token,
                    pub_key,  # type: ignore[arg-type]
                    algorithms=["RS256"],
                    options={"require": ["sub", "iss", "iat", "exp"]},
                )
                return True
            except _jwt.PyJWTError:
                continue
        return False
    except Exception as exc:  # noqa: BLE001
        log.warning("Identity token verification failed: %s", exc)
        return False


async def _seed_from_admin(pool: asyncpg.Pool, admin_url: str) -> None:
    """Fetch managed agents from the admin service and register any missing ones."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{admin_url}/agents")
            if resp.status_code != 200:
                log.warning("Admin /agents returned %s — skipping seed", resp.status_code)
                return
            data = resp.json()
            agents = data.get("agents", data) if isinstance(data, dict) else data
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not reach admin service for seed: %s", exc)
        return

    for a in agents:
        slug = a.get("slug") or ""
        if not slug:
            continue
        async with pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id FROM agent_identities WHERE slug = $1", slug
            )
            if existing:
                continue
            endpoint = (
                f"http://workflow-worker:8000/invoke/{slug}"
                if a.get("managed")
                else ""
            )
            await conn.execute(
                """
                INSERT INTO agent_identities
                    (slug, name, category, capabilities, endpoint, managed)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (slug) DO NOTHING
                """,
                slug,
                a.get("name", slug),
                a.get("category"),
                a.get("capabilities") or [],
                endpoint,
                bool(a.get("managed", False)),
            )
    log.info("Seed from admin complete")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Strip +asyncpg prefix that asyncpg itself doesn't understand
    db_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    pool: asyncpg.Pool = await asyncpg.create_pool(db_url, min_size=2, max_size=10)
    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=True)

    async with pool.acquire() as conn:
        await conn.execute(_CREATE_TABLE)
        await conn.execute(_ALTER_TOKEN_VERIFIED)

    asyncio.create_task(_seed_from_admin(pool, settings.admin_url))

    app.state.pool = pool
    app.state.redis = redis
    yield
    await redis.aclose()
    await pool.close()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="AI Gateway — Identity Pool", version="0.1.0", lifespan=lifespan)


def _pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool


def _redis(request: Request) -> Redis:
    return request.app.state.redis


def _check_service_token(request: Request) -> None:
    """Verify X-Service-Token header if identity_service_token is configured.

    Fails open (allows) when identity_service_token is empty — dev mode.
    Raises HTTP 401 when the token is configured but missing or wrong.
    """
    if not settings.identity_service_token:
        return  # dev mode — no auth required
    provided = request.headers.get("X-Service-Token", "")
    if provided != settings.identity_service_token:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Service-Token")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── List agents ──────────────────────────────────────────────────────────────


@app.get("/agents", response_model=list[AgentIdentity])
async def list_agents(
    request: Request,
    capability: str | None = Query(None, description="Filter by capability tag"),
    category: str | None = Query(None),
    team_id: UUID | None = Query(None),
    managed: bool | None = Query(None),
):
    conditions: list[str] = []
    params: list[Any] = []

    # Build parameterized conditions using only hardcoded column names and $N
    # placeholders — never interpolate user-supplied values into the SQL string.
    if capability is not None:
        params.append(capability)
        conditions.append(f"${len(params)} = ANY(capabilities)")

    if category is not None:
        params.append(category)
        conditions.append(f"category = ${len(params)}")

    if team_id is not None:
        params.append(team_id)
        conditions.append(f"team_id = ${len(params)}")

    if managed is not None:
        params.append(managed)
        conditions.append(f"managed = ${len(params)}")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    # Column names and table name are hardcoded; only values go through params.
    sql = "SELECT * FROM agent_identities " + where + " ORDER BY name"

    async with _pool(request).acquire() as conn:
        rows = await conn.fetch(sql, *params)

    redis = _redis(request)
    return [await _to_identity(r, redis) for r in rows]


# ── Get by slug ───────────────────────────────────────────────────────────────


@app.get("/agents/{slug}", response_model=AgentIdentity)
async def get_agent(slug: str, request: Request):
    async with _pool(request).acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM agent_identities WHERE slug = $1", slug
        )
    if not row:
        raise HTTPException(status_code=404, detail=f"Agent '{slug}' not found")
    return await _to_identity(row, _redis(request))


# ── Identity summary ──────────────────────────────────────────────────────────


@app.get("/agents/{slug}/identity", response_model=AgentIdentitySummary)
async def get_agent_identity(slug: str, request: Request):
    """Return a lightweight identity summary: verification status, capabilities, online."""
    async with _pool(request).acquire() as conn:
        row = await conn.fetchrow(
            "SELECT slug, token_verified, capabilities FROM agent_identities WHERE slug = $1",
            slug,
        )
    if not row:
        raise HTTPException(status_code=404, detail=f"Agent '{slug}' not found")
    online = await _is_online(_redis(request), slug)
    return AgentIdentitySummary(
        slug=row["slug"],
        token_verified=row["token_verified"],
        capabilities=row["capabilities"],
        online=online,
    )


# ── Endpoint lookup ───────────────────────────────────────────────────────────


@app.get("/agents/{slug}/endpoint", response_model=EndpointResponse)
async def get_endpoint(slug: str, request: Request):
    async with _pool(request).acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, endpoint FROM agent_identities WHERE slug = $1", slug
        )
    if not row:
        raise HTTPException(status_code=404, detail=f"Agent '{slug}' not found")
    online = await _is_online(_redis(request), slug)
    return EndpointResponse(endpoint=row["endpoint"], agent_id=str(row["id"]), online=online)


# ── Heartbeat ─────────────────────────────────────────────────────────────────


@app.post("/agents/{slug}/heartbeat")
async def heartbeat(slug: str, request: Request):
    async with _pool(request).acquire() as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM agent_identities WHERE slug = $1", slug
        )
    if not exists:
        raise HTTPException(status_code=404, detail=f"Agent '{slug}' not found")

    redis = _redis(request)

    # Soft relay-token check — fail open to avoid breaking managed agents that
    # don't supply a token.  If a relay token is registered for this slug in
    # Redis (written by agent-relay on /register), the caller must present it.
    relay_token_key = f"relay:agent:{slug}:token"
    try:
        stored_token = await redis.get(relay_token_key)
        if stored_token:
            provided = request.headers.get("X-Relay-Token", "")
            if provided != stored_token:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid or missing X-Relay-Token for heartbeat",
                )
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("heartbeat relay-token check failed (fail open) slug=%s: %s", slug, exc)

    await redis.setex(_heartbeat_key(slug), _HEARTBEAT_TTL, "1")

    async with _pool(request).acquire() as conn:
        await conn.execute(
            "UPDATE agent_identities SET last_seen = NOW() WHERE slug = $1", slug
        )
    return {"ok": True, "ttl": _HEARTBEAT_TTL}


# ── Register ──────────────────────────────────────────────────────────────────


@app.post("/agents/register", response_model=AgentIdentity, status_code=201)
async def register_agent(body: RegisterRequest, request: Request):
    _check_service_token(request)
    # Verify the optional identity token against the admin JWKS
    token_verified = False
    if body.identity_token:
        token_verified = await _verify_identity_token(
            body.identity_token, settings.admin_url
        )
        if not token_verified:
            log.warning("Agent '%s' supplied an invalid identity token during registration", body.slug)

    async with _pool(request).acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO agent_identities
                (slug, name, category, capabilities, endpoint, team_id, managed, token_verified)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (slug) DO UPDATE
                SET name           = EXCLUDED.name,
                    category       = EXCLUDED.category,
                    capabilities   = EXCLUDED.capabilities,
                    endpoint       = EXCLUDED.endpoint,
                    team_id        = EXCLUDED.team_id,
                    managed        = EXCLUDED.managed,
                    token_verified = EXCLUDED.token_verified,
                    last_seen      = NOW()
            RETURNING *
            """,
            body.slug,
            body.name,
            body.category,
            body.capabilities,
            body.endpoint,
            body.team_id,
            body.managed,
            token_verified,
        )
    result = await _to_identity(row, _redis(request))
    return result


# ── Deregister ────────────────────────────────────────────────────────────────


@app.delete("/agents/{slug}", status_code=204)
async def deregister_agent(slug: str, request: Request):
    _check_service_token(request)
    async with _pool(request).acquire() as conn:
        deleted = await conn.fetchval(
            "DELETE FROM agent_identities WHERE slug = $1 RETURNING id", slug
        )
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Agent '{slug}' not found")
    await _redis(request).delete(_heartbeat_key(slug))


# ── DNS-style resolve ─────────────────────────────────────────────────────────


@app.get("/resolve/{name}", response_model=list[AgentIdentity])
async def resolve(name: str, request: Request):
    """
    Resolve an agent by:
    1. Exact slug match
    2. Capability tag match
    3. Partial name/slug ILIKE match

    Returns a ranked list (exact first).
    """
    pool = _pool(request)
    redis = _redis(request)

    async with pool.acquire() as conn:
        # Exact slug
        exact = await conn.fetch(
            "SELECT * FROM agent_identities WHERE slug = $1", name
        )
        # Capability tag
        cap = await conn.fetch(
            "SELECT * FROM agent_identities WHERE $1 = ANY(capabilities) AND slug != $2",
            name,
            name,  # avoid duplicates if slug == capability
        )
        # Partial ILIKE
        pattern = f"%{name}%"
        partial = await conn.fetch(
            """
            SELECT * FROM agent_identities
            WHERE (slug ILIKE $1 OR name ILIKE $1)
              AND slug != $2
              AND NOT ($2 = ANY(capabilities))
            """,
            pattern,
            name,
        )

    seen: set[str] = set()
    results: list[AgentIdentity] = []
    for row in [*exact, *cap, *partial]:
        slug = row["slug"]
        if slug in seen:
            continue
        seen.add(slug)
        results.append(await _to_identity(row, redis))
    return results


# ── Capabilities ──────────────────────────────────────────────────────────────


@app.get("/capabilities")
async def list_capabilities(request: Request):
    async with _pool(request).acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT UNNEST(capabilities) AS cap FROM agent_identities ORDER BY cap"
        )
    return {"capabilities": [r["cap"] for r in rows]}
