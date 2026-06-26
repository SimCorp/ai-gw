import asyncio
import logging
from contextlib import asynccontextmanager

import asyncpg
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from app.config import settings
from app.logging_config import CorrelationIdMiddleware, init_logging
from app.redis_utils import make_redis
from app.router import router

_log = logging.getLogger(__name__)


async def _expire_loop(pool: asyncpg.Pool) -> None:
    """Delete expired cache entries every 10 minutes."""
    while True:
        await asyncio.sleep(600)
        try:
            await pool.execute("DELETE FROM cache_entries WHERE expires_at < NOW()")
        except Exception:
            pass  # fail-open: missed cleanup isn't critical


async def _training_retention_loop(pool: asyncpg.Pool) -> None:
    """Delete unexported training candidates older than 90 days every 6 hours."""
    while True:
        await asyncio.sleep(6 * 60 * 60)
        try:
            result = await pool.execute(
                "DELETE FROM training_candidates "
                "WHERE captured_at < NOW() - INTERVAL '90 days' AND exported_at IS NULL"
            )
            if result and result != "DELETE 0":
                _log.info("training_retention: %s", result)
        except Exception:
            _log.warning("training_retention loop error", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = make_redis(settings.redis_url)
    app.state.http = httpx.AsyncClient()
    app.state.pool = await asyncpg.create_pool(settings.database_url, min_size=2, max_size=10)
    _expire_task = asyncio.create_task(_expire_loop(app.state.pool))
    _retention_task = asyncio.create_task(_training_retention_loop(app.state.pool))
    yield
    _expire_task.cancel()
    _retention_task.cancel()
    for t in (_expire_task, _retention_task):
        try:
            await t
        except asyncio.CancelledError:
            pass
    await app.state.pool.close()
    await app.state.redis.aclose()
    await app.state.http.aclose()


init_logging("cache")
app = FastAPI(title="AI Gateway — Cache Service", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)
app.mount("/metrics", make_asgi_app())

from app.observability import init_observability  # noqa: E402

init_observability(app, service_name="cache")

app.include_router(router)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-XSS-Protection", "1; mode=block")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


@app.get("/health")
async def health():
    """Liveness probe — returns 200 if the process is running."""
    return {"status": "ok"}


@app.get("/ready")
async def ready(request: Request):
    """Readiness probe — checks Redis, database, and upstream auth availability."""
    errors: dict[str, str] = {}

    # Check Redis
    try:
        await request.app.state.redis.ping()
    except Exception as exc:
        errors["redis"] = str(exc)

    # Check database
    try:
        await request.app.state.pool.fetchval("SELECT 1")
    except Exception as exc:
        errors["database"] = str(exc)

    # Check auth service reachability (soft — agents can survive brief auth outages via identity cache)
    try:
        resp = await request.app.state.http.get(f"{settings.auth_url}/health", timeout=2)
        if resp.status_code != 200:
            errors["auth"] = f"HTTP {resp.status_code}"
    except Exception as exc:
        errors["auth"] = str(exc)

    if errors:
        return JSONResponse({"status": "not_ready", "errors": errors}, status_code=503)
    return {"status": "ready"}
