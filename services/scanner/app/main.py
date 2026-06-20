import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.config import settings
from app.logging_config import CorrelationIdMiddleware, init_logging
from app.redis_utils import make_redis
from app.routers import internal as internal_router
from app.routers import jobs as jobs_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = make_redis(settings.redis_url)
    from app.worker.runner import run_worker

    worker_task = asyncio.create_task(run_worker(app.state.redis))
    yield
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    await app.state.redis.aclose()


init_logging("scanner")
app = FastAPI(title="AI Gateway Scanner", lifespan=lifespan)

app.add_middleware(CorrelationIdMiddleware)
app.mount("/metrics", make_asgi_app())

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
