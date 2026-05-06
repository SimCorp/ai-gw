from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis

from app.auth import require_admin_auth
from app.config import settings as app_settings
from app.routers import (
    api_keys,
    audit_log,
    dashboard,
    members,
    model_registry,
    policies,
    portal,
    pricing,
    settings as settings_router,
    system,
    teams,
    ui,
)

_auth = [Depends(require_admin_auth)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = Redis.from_url(app_settings.redis_url, decode_responses=True)
    yield
    await app.state.redis.aclose()


app = FastAPI(
    title="AI Gateway — Admin Portal",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(ui.router, dependencies=_auth)
app.include_router(settings_router.router, dependencies=_auth)
app.include_router(dashboard.router, dependencies=_auth)
app.include_router(teams.router, dependencies=_auth)
app.include_router(members.router, dependencies=_auth)
app.include_router(api_keys.router, dependencies=_auth)
app.include_router(policies.router, dependencies=_auth)
app.include_router(pricing.router, dependencies=_auth)
app.include_router(model_registry.router, dependencies=_auth)
app.include_router(system.router, dependencies=_auth)
app.include_router(audit_log.router, dependencies=_auth)
app.include_router(portal.router)  # no admin auth — portal manages its own sessions


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
