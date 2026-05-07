from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from app.bus import make_bus
from app.config import settings
from app.router import router
from app.workers import insights, postgres


@asynccontextmanager
async def lifespan(app: FastAPI):
    bus = make_bus(settings)

    redis = Redis.from_url(settings.redis_url, decode_responses=True)

    pg_handler, pg_pool = await postgres.make_handler(
        settings.database_url.replace("+asyncpg", ""),
        redis=redis,
    )
    bus.subscribe(pg_handler)
    bus.subscribe(insights.make_handler(settings.appinsights_connection_string))

    await bus.start()
    app.state.bus = bus
    yield
    await bus.stop()
    await pg_pool.close()
    await redis.aclose()


app = FastAPI(title="AI Gateway — Observability Service", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
