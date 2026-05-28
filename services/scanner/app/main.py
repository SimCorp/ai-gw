import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.redis_utils import make_redis
from app.routers import jobs as jobs_router, internal as internal_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = make_redis(settings.redis_url)
    yield
    await app.state.redis.aclose()


app = FastAPI(title="AI Gateway Scanner", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs_router.router)
app.include_router(internal_router.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
