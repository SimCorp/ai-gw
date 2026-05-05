from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from redis.asyncio import Redis

from app.config import settings
from app.router import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.db = await asyncpg.connect(settings.database_url.replace("+asyncpg", ""))
    yield
    await app.state.redis.aclose()
    await app.state.db.close()


app = FastAPI(title="AI Gateway — Auth Service", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
