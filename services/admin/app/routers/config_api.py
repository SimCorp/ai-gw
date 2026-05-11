"""Dynamic gateway configuration API.

Clients (agents, portal) can poll or subscribe to configuration changes so they
pick up new model lists, rate-limit adjustments, and feature-flag updates without
a restart.

Redis keys:
  gateway:config          — current config JSON (includes ``version`` field)
  gateway:config:version  — monotonically incrementing int (faster reads)
  gateway:config:updates  — pub/sub channel; publish a version string on change

Endpoints:
  GET  /config              — current effective config
  GET  /config/stream       — SSE stream of config-change events
  POST /config/notify       — trigger a re-fetch broadcast (internal use)
  GET  /gateway-info        — gateway version, enabled features, models, autoroute
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import text

from app.db import engine

_log = logging.getLogger(__name__)

# Router has no built-in prefix — mounted in main.py with the prefix in include_router
router = APIRouter(tags=["config"])

_GATEWAY_VERSION = "1.0.0"
_FEATURES = ["workflow-designer", "auto-drive", "identity-pool"]
_CONFIG_KEY = "gateway:config"
_VERSION_KEY = "gateway:config:version"
_PUBSUB_CHANNEL = "gateway:config:updates"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _get_config(redis) -> dict:
    """Read gateway:config from Redis; return a minimal default if absent."""
    try:
        raw = await redis.get(_CONFIG_KEY)
        if raw:
            return json.loads(raw)
    except Exception as exc:
        _log.debug("Failed to read gateway config from Redis: %s", exc)
    return {"version": 0, "models": [], "rate_limits": {}, "features_enabled": _FEATURES}


async def _get_version(redis) -> int:
    try:
        v = await redis.get(_VERSION_KEY)
        return int(v) if v else 0
    except Exception:
        return 0


async def _enabled_models(session) -> list[str]:
    """Fetch enabled model IDs from Postgres."""
    try:
        result = await session.execute(text("SELECT model_id FROM model_registry WHERE enabled = TRUE ORDER BY model_id"))
        return [row[0] for row in result.fetchall()]
    except Exception as exc:
        _log.debug("Failed to fetch enabled models: %s", exc)
        return []


async def notify_config_change(redis) -> int:
    """Increment the config version and publish to the pub/sub channel.

    Returns the new version number.  Safe to call concurrently; Redis INCR is
    atomic.
    """
    try:
        new_version = await redis.incr(_VERSION_KEY)
        # Update the version field in the stored config blob as well
        raw = await redis.get(_CONFIG_KEY)
        cfg: dict = json.loads(raw) if raw else {}
        cfg["version"] = new_version
        await redis.set(_CONFIG_KEY, json.dumps(cfg))
        await redis.publish(_PUBSUB_CHANNEL, str(new_version))
        return new_version
    except Exception as exc:
        _log.warning("notify_config_change failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/config")
async def get_config(request: Request):
    """Return the current effective gateway configuration."""
    redis = request.app.state.redis
    cfg = await _get_config(redis)
    return JSONResponse(cfg)


@router.get("/config/stream")
async def stream_config(request: Request):
    """SSE stream that emits a ``config-change`` event whenever the config version
    increments.  Clients should re-fetch ``GET /config`` upon receipt.

    The stream sends an initial ``connected`` event and then one event per
    version bump.
    """
    redis = request.app.state.redis

    async def _event_generator() -> AsyncIterator[bytes]:
        # Send initial heartbeat so the client knows the connection is live
        version = await _get_version(redis)
        yield f"event: connected\ndata: {{\"config_version\": {version}}}\n\n".encode()

        pubsub = redis.pubsub()
        try:
            await pubsub.subscribe(_PUBSUB_CHANNEL)
            while True:
                # Check for client disconnect before blocking
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(pubsub.get_message(ignore_subscribe_messages=True), timeout=25.0)
                except asyncio.TimeoutError:
                    # Send a keepalive comment so the connection is not closed by proxies
                    yield b": keepalive\n\n"
                    continue
                if message and message["type"] == "message":
                    new_version = message["data"]
                    if isinstance(new_version, bytes):
                        new_version = new_version.decode()
                    yield f"event: config-change\ndata: {{\"config_version\": {new_version}}}\n\n".encode()
        finally:
            try:
                await pubsub.unsubscribe(_PUBSUB_CHANNEL)
                await pubsub.close()
            except Exception:
                pass

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )


@router.post("/config/notify")
async def trigger_config_notify(request: Request):
    """Internal endpoint — increments the config version and broadcasts a change
    event to all ``/config/stream`` subscribers.

    Called by the admin backend whenever team policies, model registry, or
    feature flags are changed.
    """
    redis = request.app.state.redis
    new_version = await notify_config_change(redis)
    return JSONResponse({"ok": True, "config_version": new_version})


@router.get("/gateway-info")
async def gateway_info(request: Request):
    """Return gateway version, enabled features, current model list, and autoroute
    status.  Consumed by the admin dashboard Performance section.
    """
    redis = request.app.state.redis

    config_version = await _get_version(redis)

    # Fetch enabled models from Postgres
    async with engine.connect() as conn:
        models = await _enabled_models(conn)

    # Autoroute stats — best model + its score from the 5-min rolling window
    autoroute_info: dict = {"enabled": False, "current_model": None, "score": None}
    try:
        from app.config import settings as _settings  # local import avoids circular
        if _settings.autoroute_enabled:
            # Import autoroute lazily — it lives in the cache service, not admin.
            # In the admin context we read the same Redis keys directly.
            candidates = [m.strip() for m in _settings.autoroute_models.split(",") if m.strip()]
            autoroute_info["enabled"] = True
            autoroute_info["candidates"] = candidates
    except Exception:
        pass

    # Workflow runs today — quick aggregate from Postgres
    workflow_runs_today = 0
    try:
        async with engine.connect() as conn:
            row = await conn.execute(
                text("SELECT COUNT(*) FROM workflow_runs WHERE created_at >= CURRENT_DATE")
            )
            workflow_runs_today = row.scalar() or 0
    except Exception:
        pass

    return JSONResponse({
        "version": _GATEWAY_VERSION,
        "features": _FEATURES,
        "models": models,
        "config_version": config_version,
        "autoroute": autoroute_info,
        "workflow_runs_today": workflow_runs_today,
    })
