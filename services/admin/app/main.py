from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis
from sqlalchemy import text

from app.auth import require_admin_auth
from app.config import settings as app_settings
from app.db import Base, engine

# Import all ORM models so their metadata is registered with Base before create_all
from app.models import (  # noqa: F401
    api_key,
    audit_log as audit_log_model,
    member,
    model_registry as model_registry_model,
    policy,
    pricing as pricing_model,
    team,
)

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

# Extra DDL for tables without ORM models (run idempotently via IF NOT EXISTS)
_EXTRA_DDL = [
    "CREATE EXTENSION IF NOT EXISTS \"pgcrypto\"",
    """CREATE TABLE IF NOT EXISTS cost_records (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        team_id UUID NOT NULL REFERENCES teams(id),
        project_id UUID REFERENCES projects(id),
        model TEXT NOT NULL,
        tokens_input INT NOT NULL DEFAULT 0,
        tokens_output INT NOT NULL DEFAULT 0,
        cost_usd NUMERIC(10,8) NOT NULL DEFAULT 0,
        cache_hit BOOLEAN NOT NULL DEFAULT FALSE,
        latency_ms INT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS cost_records_team_id_created_at_idx ON cost_records (team_id, created_at DESC)",
    """CREATE TABLE IF NOT EXISTS developers (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        email VARCHAR(255) NOT NULL UNIQUE,
        display_name VARCHAR(255),
        password_hash TEXT NOT NULL,
        status VARCHAR(50) NOT NULL DEFAULT 'pending',
        email_verified_at TIMESTAMPTZ,
        team_id UUID REFERENCES teams(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_developers_email ON developers(email)",
    "CREATE INDEX IF NOT EXISTS idx_developers_status ON developers(status)",
    "CREATE INDEX IF NOT EXISTS idx_developers_team   ON developers(team_id)",
    "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS developer_id UUID REFERENCES developers(id) ON DELETE SET NULL",
    "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMPTZ",
    "CREATE INDEX IF NOT EXISTS idx_api_keys_developer ON api_keys(developer_id)",
]

_auth = [Depends(require_admin_auth)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure all ORM-mapped tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Create tables not covered by ORM models
        for ddl in _EXTRA_DDL:
            try:
                await conn.execute(text(ddl))
            except Exception as exc:
                # Non-fatal: log and continue (e.g. index already exists)
                import logging
                logging.getLogger(__name__).warning("DDL skipped (%s): %s", type(exc).__name__, str(exc)[:120])

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
