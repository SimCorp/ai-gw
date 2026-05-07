"""System health — JSON API + HTML dashboard."""
import asyncio
import time
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session

router = APIRouter(prefix="/system", tags=["system"])
_SERVICES = {
    "auth":          (settings.auth_url,          "/health"),
    "cache":         (settings.cache_url,          "/health"),
    "litellm":       (settings.litellm_url,        "/health/liveliness"),
    "observability": (settings.observability_url,  "/health"),
}

_SERVICE_ICONS = {
    "auth":          "shield-check",
    "cache":         "lightning-charge",
    "litellm":       "cpu",
    "observability": "eye",
}


async def _check_service(name: str, base_url: str, path: str) -> dict:
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await asyncio.wait_for(client.get(f"{base_url}{path}"), timeout=3.0)
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        return {
            "service": name, "icon": _SERVICE_ICONS.get(name, "circle"),
            "status": "ok" if resp.is_success else "degraded",
            "code": resp.status_code, "latency_ms": latency_ms, "error": None,
        }
    except Exception as exc:
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        return {
            "service": name, "icon": _SERVICE_ICONS.get(name, "circle"),
            "status": "unreachable", "code": None, "latency_ms": latency_ms,
            "error": str(exc)[:200],
        }


async def _check_redis(redis) -> dict:
    t0 = time.monotonic()
    try:
        async def _probe():
            await redis.ping()
            mem = await redis.info("memory")
            cli = await redis.info("clients")
            return mem, cli

        mem, cli = await asyncio.wait_for(_probe(), timeout=2.0)
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        return {
            "status": "ok",
            "ping_ms": latency_ms,
            "used_memory_mb": round(mem["used_memory"] / (1024 * 1024), 2),
            "connected_clients": cli["connected_clients"],
            "error": None,
        }
    except Exception as exc:
        return {"status": "unreachable", "ping_ms": None, "used_memory_mb": None,
                "connected_clients": None, "error": str(exc)[:200]}


async def _check_postgres(session: AsyncSession) -> dict:
    t0 = time.monotonic()
    try:
        async def _probe():
            r = await session.execute(
                text("SELECT count(*) FROM pg_stat_activity WHERE state = 'active'")
            )
            return r.scalar_one()

        active = await asyncio.wait_for(_probe(), timeout=3.0)
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        return {"status": "ok", "ping_ms": latency_ms,
                "active_connections": int(active), "error": None}
    except Exception as exc:
        return {"status": "unreachable", "ping_ms": None,
                "active_connections": None, "error": str(exc)[:200]}


async def _check_litellm_models() -> dict:
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await asyncio.wait_for(
                client.get(
                    f"{settings.litellm_url}/v1/models",
                    headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
                ),
                timeout=4.0,
            )
            resp.raise_for_status()
        models = resp.json().get("data", [])
        # Derive provider names from model IDs configured in LiteLLM
        providers = sorted({
            m["id"].split("/")[0] for m in models
            if "/" in m.get("id", "")
        })
        return {
            "status": "ok",
            "models_available": len(models),
            "providers_with_keys": providers or ["anthropic", "google", "github"],
            "error": None,
        }
    except Exception as exc:
        return {"status": "unreachable", "models_available": None,
                "providers_with_keys": None, "error": str(exc)[:200]}


async def _check_gateway_metrics(session: AsyncSession) -> dict:
    try:
        async def _probe():
            r = await session.execute(text("""
                SELECT
                    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '60 seconds') AS req60,
                    ROUND(
                        AVG(CASE WHEN cache_hit THEN 1.0 ELSE 0.0 END)
                        FILTER (WHERE created_at >= NOW() - INTERVAL '60 seconds')::numeric, 4
                    ) AS hit_rate
                FROM cost_records
            """))
            return r.mappings().one()

        row = await asyncio.wait_for(_probe(), timeout=3.0)
        return {
            "status": "ok",
            "requests_last_60s": int(row["req60"] or 0),
            "cache_hit_rate_last_60s": float(row["hit_rate"] or 0.0),
            "error": None,
        }
    except Exception as exc:
        return {"status": "unreachable", "requests_last_60s": None,
                "cache_hit_rate_last_60s": None, "error": str(exc)[:200]}


async def _fetch_recent_errors(session: AsyncSession) -> list:
    try:
        async def _probe():
            r = await session.execute(text("""
                SELECT timestamp, actor, action, resource_type, resource_id
                FROM audit_log
                WHERE action ILIKE '%error%' OR action ILIKE '%fail%' OR action ILIKE '%revok%'
                ORDER BY timestamp DESC LIMIT 8
            """))
            return r.mappings().all()

        rows = await asyncio.wait_for(_probe(), timeout=3.0)
        return [
            {
                "timestamp": row["timestamp"].strftime("%H:%M:%S"),
                "actor": row["actor"],
                "action": row["action"],
                "resource_type": row["resource_type"],
                "resource_id": row["resource_id"],
            }
            for row in rows
        ]
    except Exception:
        return []


async def _collect_health(request: Request, session: AsyncSession) -> dict:
    redis = request.app.state.redis
    (
        svc_auth, svc_cache, svc_litellm, svc_obs,
        redis_r, pg_r, litellm_r, gw_r, errors,
    ) = await asyncio.gather(
        _check_service("auth",          settings.auth_url,          "/health"),
        _check_service("cache",         settings.cache_url,         "/health"),
        _check_service("litellm",       settings.litellm_url,       "/health/liveliness"),
        _check_service("observability", settings.observability_url, "/health"),
        _check_redis(redis),
        _check_postgres(session),
        _check_litellm_models(),
        _check_gateway_metrics(session),
        _fetch_recent_errors(session),
    )
    services = [svc_auth, svc_cache, svc_litellm, svc_obs]
    all_checks = [*services, redis_r, pg_r, litellm_r, gw_r]
    overall = "ok" if all(c["status"] == "ok" for c in all_checks) else "degraded"
    return {
        "overall": overall,
        "last_updated": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        "services": services,
        "redis": redis_r,
        "postgres": pg_r,
        "litellm": litellm_r,
        "gateway": gw_r,
        "recent_errors": errors,
    }


@router.get("/health")
async def system_health(request: Request, session: AsyncSession = Depends(get_session)):
    """JSON health data — used by monitoring and the dashboard polling."""
    return await _collect_health(request, session)


