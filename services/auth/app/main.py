from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from app.config import settings
from app.logging_config import CorrelationIdMiddleware, init_logging
from app.redis_utils import make_redis
from app.router import router
from app.validators.jwt import _validate_jwks_uri  # noqa: F401 — used in lifespan


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        _validate_jwks_uri(settings.jwks_uri)
    except ValueError as exc:
        import logging

        logging.getLogger(__name__).error("Invalid JWKS_URI: %s", exc)
    app.state.redis = make_redis(settings.redis_url)
    app.state.db = await asyncpg.create_pool(
        settings.database_url.replace("+asyncpg", ""),
        min_size=2,
        max_size=10,
    )
    yield
    await app.state.redis.aclose()
    await app.state.db.close()


init_logging("auth")
app = FastAPI(title="AI Gateway — Auth Service", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)
app.mount("/metrics", make_asgi_app())

from app.observability import init_observability  # noqa: E402

init_observability(app, service_name="auth")

app.include_router(router)


@app.get("/health")
async def health():
    """Liveness probe — returns 200 if the process is running."""
    return {"status": "ok"}


@app.get("/ready")
async def ready(request: Request):
    """Readiness probe — checks Redis and Postgres before accepting traffic."""
    errors: dict[str, str] = {}

    # Check Redis
    try:
        await request.app.state.redis.ping()
    except Exception as exc:
        errors["redis"] = str(exc)

    # Check Postgres
    try:
        async with request.app.state.db.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception as exc:
        errors["postgres"] = str(exc)

    if errors:
        return JSONResponse({"status": "not_ready", "errors": errors}, status_code=503)
    return {"status": "ready"}
