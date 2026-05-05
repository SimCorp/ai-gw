from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from app.config import settings
from app.routers import api_keys, dashboard, policies, teams


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    yield
    await app.state.redis.aclose()


app = FastAPI(title="AI Gateway — Admin Portal", lifespan=lifespan)
app.include_router(dashboard.router)
app.include_router(teams.router)
app.include_router(api_keys.router)
app.include_router(policies.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
