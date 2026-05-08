from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from redis.asyncio import Redis

from app.config import settings
from app.router import router
from app.validators.jwt import _validate_jwks_uri  # noqa: F401 — used in lifespan


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        _validate_jwks_uri(settings.jwks_uri)
    except ValueError as exc:
        import logging
        logging.getLogger(__name__).error("Invalid JWKS_URI: %s", exc)
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.db = await asyncpg.create_pool(
        settings.database_url.replace("+asyncpg", ""),
        min_size=2,
        max_size=10,
    )
    yield
    await app.state.redis.aclose()
    await app.state.db.close()


app = FastAPI(title="AI Gateway — Auth Service", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
