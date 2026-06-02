from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.redis_utils import make_redis
from app.router import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = make_redis(settings.redis_url)
    app.state.http = httpx.AsyncClient()
    yield
    await app.state.redis.aclose()
    await app.state.http.aclose()


app = FastAPI(title="AI Gateway — Cache Service", lifespan=lifespan)
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
    """Readiness probe — checks Redis and upstream auth availability."""
    errors: dict[str, str] = {}

    # Check Redis
    try:
        await request.app.state.redis.ping()
    except Exception as exc:
        errors["redis"] = str(exc)

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
