import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from app.bus import make_bus
from app.config import settings
from app.github_webhook import router as github_router
from app.logging_config import CorrelationIdMiddleware, init_logging
from app.redis_utils import make_redis
from app.router import router
from app.workers import insights, postgres
from app.workers.budget_alert import run_budget_alert_loop
from app.workers.cost_anomaly import run_cost_anomaly_loop
from app.workers.session_cleanup import run_session_cleanup_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    bus = make_bus(settings)

    redis = make_redis(settings.redis_url)

    pg_handler, pg_pool = await postgres.make_handler(
        settings.database_url.replace("+asyncpg", ""),
        redis=redis,
    )
    bus.subscribe(pg_handler)
    bus.subscribe(insights.make_handler(settings.appinsights_connection_string))

    await bus.start()
    budget_task = asyncio.create_task(run_budget_alert_loop(pg_pool, redis))
    anomaly_task = asyncio.create_task(run_cost_anomaly_loop(pg_pool, redis))
    cleanup_task = asyncio.create_task(run_session_cleanup_loop(pg_pool))
    app.state.bus = bus
    app.state.redis = redis
    app.state.pg_pool = pg_pool
    app.state.settings = settings
    yield
    budget_task.cancel()
    anomaly_task.cancel()
    cleanup_task.cancel()
    await bus.stop()
    await pg_pool.close()
    await redis.aclose()


init_logging("observability")

app = FastAPI(title="AI Gateway — Observability Service", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)
app.mount("/metrics", make_asgi_app())
app.include_router(router)
app.include_router(github_router)


@app.get("/health")
async def health():
    """Liveness probe — returns 200 if the process is running."""
    return {"status": "ok"}


@app.get("/ready")
async def ready(request: Request):
    """Readiness probe — checks Redis and Postgres connectivity."""
    errors: dict[str, str] = {}

    try:
        await request.app.state.redis.ping()
    except Exception as exc:
        errors["redis"] = str(exc)

    try:
        async with request.app.state.pg_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception as exc:
        errors["postgres"] = str(exc)

    if errors:
        return JSONResponse({"status": "not_ready", "errors": errors}, status_code=503)
    return {"status": "ready"}
