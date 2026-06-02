"""Agent Relay service — v1.0.

WebSocket-based relay that allows laptop-hosted agents to register and receive
invocations through the gateway.

Protocol:
  POST /register                 → register a relay agent (returns relay_token)
  WS   /connect/{relay_token}    → laptop agent connects here via WebSocket
  POST /invoke/{agent_slug}      → workflow-worker calls this to invoke a relay agent
  GET  /agents                   → list currently connected relay agents
  GET  /health                   → {"status": "ok"}

Flow:
  1. Laptop agent POSTs /register with {slug, name, capabilities: []} → gets relay_token (UUID)
  2. Laptop agent connects WS to /connect/{relay_token} — connection is kept alive
  3. Relay stores relay_token → websocket mapping in memory, plus slug in Redis
     (relay:agent:{slug}:token) which the identity service reads to gate
     heartbeats. NOTE: this service is single-instance — invocations are routed
     only via in-process connection state; the Redis key is not used to route
     /invoke across instances.
  4. When workflow-worker wants to invoke, it POSTs /invoke/{slug} with
     {inputs: {}, env: {}} → relay forwards to WS, waits for response, returns
     {outputs: {}, exit_code: 0}
  5. On WS disconnect, agent is unregistered
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from redis.asyncio import Redis

from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
_log = logging.getLogger("agent-relay")

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------

# relay_token (str) → {slug, name, capabilities, websocket}
_registered_agents: dict[str, dict[str, Any]] = {}

# relay_token → WebSocket (active connections)
_connections: dict[str, WebSocket] = {}

# invocation_id (str) → asyncio.Future[dict]
_pending: dict[str, asyncio.Future] = {}

# slug → relay_token (for fast lookup by slug)
_slug_to_token: dict[str, str] = {}

# ---------------------------------------------------------------------------
# Redis client (module-level, initialised in lifespan)
# ---------------------------------------------------------------------------

_redis: Redis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis
    cfg = get_settings()
    _redis = Redis.from_url(cfg.redis_url, decode_responses=True)
    _log.info("agent-relay started, redis=%s", cfg.redis_url)
    yield
    if _redis:
        await _redis.aclose()


app = FastAPI(title="AI Gateway Agent Relay", version="0.1.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


def _check_relay_secret(request: Request) -> None:
    """Verify X-Relay-Secret header if relay_secret is configured.

    Fails open (allows) when relay_secret is empty — dev mode.
    Raises HTTP 401 when the secret is configured but the header is missing
    or does not match.
    """
    cfg = get_settings()
    if not cfg.relay_secret:
        return  # dev mode — no auth required
    provided = request.headers.get("X-Relay-Secret", "")
    if provided != cfg.relay_secret:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Relay-Secret")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    slug: str
    name: str
    capabilities: list[str] = []


class RegisterResponse(BaseModel):
    relay_token: str
    slug: str


class InvokeRequest(BaseModel):
    inputs: dict[str, Any] = {}
    env: dict[str, str] = {}
    run_id: str = ""
    node_id: str = ""


class InvokeResponse(BaseModel):
    outputs: dict[str, Any]
    exit_code: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/agents")
async def list_agents():
    """Return metadata for all currently connected relay agents.

    The relay_token is intentionally omitted from this response — callers
    only need slug, name, capabilities, and connected_at.
    """
    return [
        {
            "slug": info["slug"],
            "name": info["name"],
            "capabilities": info["capabilities"],
            "connected_at": info.get("connected_at"),
        }
        for token, info in _registered_agents.items()
        if token in _connections
    ]


@app.post("/register", response_model=RegisterResponse)
async def register(req: RegisterRequest, request: Request):
    """Register a relay agent. Returns a relay_token for the subsequent WS connection."""
    _check_relay_secret(request)
    relay_token = str(uuid.uuid4())
    _registered_agents[relay_token] = {
        "slug": req.slug,
        "name": req.name,
        "capabilities": req.capabilities,
    }
    _slug_to_token[req.slug] = relay_token

    # Persist slug → token in Redis so the identity service can gate heartbeats.
    if _redis:
        try:
            await _redis.set(f"relay:agent:{req.slug}:token", relay_token, ex=3600)
        except Exception as exc:
            _log.warning("redis write failed for slug=%s: %s", req.slug, exc)

    _log.info("registered agent slug=%s token=%s", req.slug, relay_token)
    return RegisterResponse(relay_token=relay_token, slug=req.slug)


@app.websocket("/connect/{relay_token}")
async def connect(websocket: WebSocket, relay_token: str):
    """Laptop agent connects here. Connection is kept alive until the agent disconnects."""
    if relay_token not in _registered_agents:
        await websocket.close(code=4004, reason="unknown relay_token")
        return

    await websocket.accept()
    _connections[relay_token] = websocket
    slug = _registered_agents[relay_token]["slug"]
    _registered_agents[relay_token]["connected_at"] = datetime.now(timezone.utc).isoformat()
    _log.info("agent connected slug=%s token=%s", slug, relay_token)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                _log.warning("invalid JSON from agent slug=%s: %r", slug, raw[:200])
                continue

            invocation_id = msg.get("invocation_id")
            if not invocation_id:
                _log.warning("message without invocation_id from slug=%s", slug)
                continue

            fut = _pending.get(invocation_id)
            if fut is None:
                _log.warning("no pending future for invocation_id=%s", invocation_id)
                continue

            if not fut.done():
                fut.set_result(msg)

    except WebSocketDisconnect:
        _log.info("agent disconnected slug=%s token=%s", slug, relay_token)
    except Exception as exc:
        _log.error("WS error for slug=%s: %s", slug, exc)
    finally:
        _connections.pop(relay_token, None)
        # Remove slug→token mapping if still pointing to this token
        if _slug_to_token.get(slug) == relay_token:
            _slug_to_token.pop(slug, None)
        if _redis:
            try:
                await _redis.delete(f"relay:agent:{slug}:token")
            except Exception:
                pass
        _log.info("agent unregistered slug=%s", slug)


@app.post("/invoke/{agent_slug}", response_model=InvokeResponse)
async def invoke(agent_slug: str, req: InvokeRequest, request: Request):
    """Invoke a relay agent by slug. Forwards to the agent's WS and waits for the response."""
    _check_relay_secret(request)
    relay_token = _slug_to_token.get(agent_slug)

    if relay_token is None or relay_token not in _connections:
        raise HTTPException(status_code=503, detail=f"agent '{agent_slug}' not connected")

    ws = _connections[relay_token]
    invocation_id = str(uuid.uuid4())

    payload = {
        "invocation_id": invocation_id,
        "inputs": req.inputs,
        "env": req.env,
        "run_id": req.run_id,
        "node_id": req.node_id,
    }

    loop = asyncio.get_event_loop()
    fut: asyncio.Future = loop.create_future()
    _pending[invocation_id] = fut

    try:
        await ws.send_text(json.dumps(payload))

        # Wait for the agent to respond (timeout derived from caller; default 300 s)
        timeout_s = 300.0
        try:
            response = await asyncio.wait_for(fut, timeout=timeout_s)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail=f"agent '{agent_slug}' timed out")

        outputs = response.get("outputs") or {}
        exit_code = int(response.get("exit_code", 0))
        return InvokeResponse(outputs=outputs, exit_code=exit_code)

    except HTTPException:
        raise
    except Exception as exc:
        _log.error("invoke error for slug=%s: %s", agent_slug, exc)
        raise HTTPException(status_code=502, detail=str(exc))
    finally:
        _pending.pop(invocation_id, None)
