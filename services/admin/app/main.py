import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.redis_utils import make_redis
from sqlalchemy import text

from app.auth import require_admin_auth
from app.config import settings as app_settings
from app.db import Base, engine

# Import all ORM models so their metadata is registered with Base before create_all
from app.models import (  # noqa: F401
    api_key,
    area as area_model,
    area_policy as area_policy_model,
    audit_log as audit_log_model,
    mcp as mcp_model,
    member,
    plugin as plugin_model,
    model_registry as model_registry_model,
    policy,
    pricing as pricing_model,
    team,
)

from app.routers import (
    admin_auth as admin_auth_router,
    ai_help as ai_help_router,
    devops_agent as devops_agent_router,
    insights as insights_router,
    api_keys as api_keys_module,
    areas as areas_router,
    audit_log,
    budget,
    dashboard,
    dev_auth,
    developers as developers_router,
    guardrails as guardrails_router,
    mcp as mcp_router,
    members,
    plugins as plugins_router,
    model_registry,
    policies,
    pricing,
    reports as reports_router,
    requests as requests_router,
    settings as settings_router,
    system,
    teams,
)

# Extra DDL for tables without ORM models (run idempotently via IF NOT EXISTS)
_EXTRA_DDL = [
    "CREATE EXTENSION IF NOT EXISTS \"pgcrypto\"",
    # Areas (must come before any FK reference in teams)
    """CREATE TABLE IF NOT EXISTS areas (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name TEXT NOT NULL,
        slug TEXT NOT NULL,
        description TEXT,
        color TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (slug)
    )""",
    "ALTER TABLE teams ADD COLUMN IF NOT EXISTS area_id UUID REFERENCES areas(id) ON DELETE SET NULL",
    "CREATE INDEX IF NOT EXISTS idx_teams_area_id ON teams(area_id)",
    """CREATE TABLE IF NOT EXISTS projects (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        slug TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (team_id, slug)
    )""",
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
    # Budget fields on teams
    "ALTER TABLE teams ADD COLUMN IF NOT EXISTS monthly_budget_usd NUMERIC(14,8)",
    "ALTER TABLE teams ADD COLUMN IF NOT EXISTS budget_alert_pct FLOAT NOT NULL DEFAULT 0.8",
    "ALTER TABLE teams ADD COLUMN IF NOT EXISTS budget_action TEXT NOT NULL DEFAULT 'alert'",
    # Widen precision if column was previously created with NUMERIC(12,4)
    "ALTER TABLE teams ALTER COLUMN monthly_budget_usd TYPE NUMERIC(14,8)",
    # Per-key budget cap
    "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS monthly_budget_usd NUMERIC(14,8)",
    "ALTER TABLE api_keys ALTER COLUMN monthly_budget_usd TYPE NUMERIC(14,8)",
    # Track which key was used on each cost record
    "ALTER TABLE cost_records ADD COLUMN IF NOT EXISTS api_key_id UUID REFERENCES api_keys(id) ON DELETE SET NULL",
    "CREATE INDEX IF NOT EXISTS idx_cost_records_api_key_id ON cost_records(api_key_id, created_at DESC)",
    # Developer attribution + enhanced telemetry on cost records
    "ALTER TABLE cost_records ADD COLUMN IF NOT EXISTS developer_id UUID REFERENCES developers(id) ON DELETE SET NULL",
    "CREATE INDEX IF NOT EXISTS idx_cost_records_developer_id ON cost_records(developer_id, created_at DESC)",
    "ALTER TABLE cost_records ADD COLUMN IF NOT EXISTS session_trace_id TEXT",
    "ALTER TABLE cost_records ADD COLUMN IF NOT EXISTS tool_invocation_count INT NOT NULL DEFAULT 0",
    "ALTER TABLE cost_records ADD COLUMN IF NOT EXISTS retry_count INT NOT NULL DEFAULT 0",
    "ALTER TABLE cost_records ADD COLUMN IF NOT EXISTS request_error_type TEXT",
    "ALTER TABLE cost_records ADD COLUMN IF NOT EXISTS cache_namespace TEXT",
    "ALTER TABLE cost_records ADD COLUMN IF NOT EXISTS repo TEXT",
    "ALTER TABLE cost_records ADD COLUMN IF NOT EXISTS session_purpose TEXT",
    # Daily developer activity rollup
    """CREATE TABLE IF NOT EXISTS developer_activity_log (
        developer_id UUID NOT NULL REFERENCES developers(id) ON DELETE CASCADE,
        date DATE NOT NULL,
        request_count INT NOT NULL DEFAULT 0,
        tokens_input BIGINT NOT NULL DEFAULT 0,
        tokens_output BIGINT NOT NULL DEFAULT 0,
        cost_usd NUMERIC(12,6) NOT NULL DEFAULT 0,
        cache_hits INT NOT NULL DEFAULT 0,
        tool_invocations INT NOT NULL DEFAULT 0,
        error_count INT NOT NULL DEFAULT 0,
        PRIMARY KEY (developer_id, date)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_dev_activity_developer_date ON developer_activity_log(developer_id, date DESC)",
    "CREATE INDEX IF NOT EXISTS idx_dev_activity_date ON developer_activity_log(date DESC)",
    # GitHub output events
    """CREATE TABLE IF NOT EXISTS developer_output_events (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        developer_id UUID REFERENCES developers(id) ON DELETE SET NULL,
        repo TEXT NOT NULL,
        event_type TEXT NOT NULL,
        github_user TEXT,
        commit_count INT NOT NULL DEFAULT 0,
        lines_added INT NOT NULL DEFAULT 0,
        lines_removed INT NOT NULL DEFAULT 0,
        pr_number INT,
        occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        raw JSONB
    )""",
    "CREATE INDEX IF NOT EXISTS idx_dev_output_developer ON developer_output_events(developer_id, occurred_at DESC)",
    # Session-level quality tracking
    """CREATE TABLE IF NOT EXISTS sessions (
        session_trace_id TEXT PRIMARY KEY,
        developer_id UUID REFERENCES developers(id) ON DELETE SET NULL,
        team_id TEXT NOT NULL,
        first_request_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_request_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        turn_count INT NOT NULL DEFAULT 1,
        total_tokens BIGINT NOT NULL DEFAULT 0,
        total_cost NUMERIC(12,8) NOT NULL DEFAULT 0,
        retry_count INT NOT NULL DEFAULT 0,
        error_count INT NOT NULL DEFAULT 0,
        tool_invocations INT NOT NULL DEFAULT 0,
        session_purpose TEXT,
        repo TEXT,
        primary_model TEXT,
        quality_score INT,
        avg_inter_request_s FLOAT,
        produced_commit BOOLEAN,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_sessions_developer ON sessions(developer_id, first_request_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_team ON sessions(team_id, first_request_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_first_request ON sessions(first_request_at DESC)",
    "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS dominant_intent TEXT",
    # Link team_members to developers
    "ALTER TABLE team_members ADD COLUMN IF NOT EXISTS developer_id UUID REFERENCES developers(id) ON DELETE CASCADE",
    "CREATE INDEX IF NOT EXISTS idx_team_members_developer_id ON team_members(developer_id)",
    # Org-level global budget ceiling
    """CREATE TABLE IF NOT EXISTS org_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "INSERT INTO org_settings (key, value) VALUES ('monthly_budget_usd', '0') ON CONFLICT (key) DO NOTHING",
    "INSERT INTO org_settings (key, value) VALUES ('budget_alert_pct', '0.8') ON CONFLICT (key) DO NOTHING",
    "INSERT INTO org_settings (key, value) VALUES ('budget_action', 'alert') ON CONFLICT (key) DO NOTHING",
    "INSERT INTO org_settings (key, value) VALUES ('notification_webhook_url', '') ON CONFLICT (key) DO NOTHING",
    "INSERT INTO org_settings (key, value) VALUES ('semantic_similarity_threshold', '0.85') ON CONFLICT (key) DO NOTHING",
    # AI insights — generated by optimization_worker every 6h
    """CREATE TABLE IF NOT EXISTS ai_insights (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        category TEXT NOT NULL,
        severity TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        action TEXT,
        team_id UUID REFERENCES teams(id) ON DELETE CASCADE,
        team_name TEXT,
        developer_id UUID REFERENCES developers(id) ON DELETE CASCADE,
        dismissed BOOLEAN NOT NULL DEFAULT FALSE,
        auto_applied BOOLEAN NOT NULL DEFAULT FALSE,
        source TEXT NOT NULL DEFAULT 'optimization_worker'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_ai_insights_generated_at ON ai_insights(generated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_ai_insights_team_id ON ai_insights(team_id)",
    "CREATE INDEX IF NOT EXISTS idx_ai_insights_developer_id ON ai_insights(developer_id)",
    # Guardrails
    """CREATE TABLE IF NOT EXISTS guardrails (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        team_id UUID REFERENCES teams(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        description TEXT,
        type TEXT NOT NULL,
        applies_to TEXT NOT NULL CHECK (applies_to IN ('input','output','both')),
        action TEXT NOT NULL CHECK (action IN ('block','flag','redact','rewrite','truncate','route')),
        severity TEXT NOT NULL DEFAULT 'high' CHECK (severity IN ('low','medium','high','critical')),
        priority INT NOT NULL DEFAULT 100,
        config JSONB NOT NULL DEFAULT '{}',
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        version INT NOT NULL DEFAULT 1,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        created_by TEXT NOT NULL DEFAULT 'system',
        updated_by TEXT NOT NULL DEFAULT 'system'
    )""",
    "CREATE INDEX IF NOT EXISTS guardrails_priority_idx ON guardrails (priority ASC) WHERE enabled = TRUE",
    """CREATE TABLE IF NOT EXISTS guardrail_hits (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        guardrail_id UUID NOT NULL REFERENCES guardrails(id) ON DELETE CASCADE,
        guardrail_version INT NOT NULL DEFAULT 1,
        guardrail_type TEXT NOT NULL,
        team_id UUID REFERENCES teams(id) ON DELETE SET NULL,
        api_key_id UUID REFERENCES api_keys(id) ON DELETE SET NULL,
        request_id TEXT,
        model TEXT,
        input_or_output TEXT NOT NULL CHECK (input_or_output IN ('input','output')),
        action_taken TEXT NOT NULL,
        severity TEXT NOT NULL,
        match_count INT NOT NULL DEFAULT 1,
        match_hash TEXT,
        redacted_excerpt TEXT,
        match_offsets JSONB,
        false_positive BOOLEAN,
        reviewed_by TEXT,
        reviewed_at TIMESTAMPTZ
    )""",
    "CREATE INDEX IF NOT EXISTS guardrail_hits_guardrail_created_idx ON guardrail_hits (guardrail_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS guardrail_hits_team_created_idx ON guardrail_hits (team_id, created_at DESC)",
    "CREATE UNIQUE INDEX IF NOT EXISTS guardrails_name_org_uidx ON guardrails (name) WHERE team_id IS NULL",
    # Ensure policy upsert ON CONFLICT target is valid
    "CREATE UNIQUE INDEX IF NOT EXISTS policies_team_null_proj_uidx ON policies (team_id) WHERE project_id IS NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS policies_team_proj_uidx ON policies (team_id, project_id) WHERE project_id IS NOT NULL",
    # Area-level policies
    """CREATE TABLE IF NOT EXISTS area_policies (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        area_id UUID NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
        cache_ttl_seconds INT NOT NULL DEFAULT 3600,
        cache_similarity_threshold FLOAT NOT NULL DEFAULT 0.95,
        cache_opt_out BOOLEAN NOT NULL DEFAULT FALSE,
        embedding_model TEXT NOT NULL DEFAULT 'text-embedding-3-small',
        rate_limit_rpm INT NOT NULL DEFAULT 1000,
        allowed_models TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (area_id)
    )""",
    # Admin portal users (separate from developer portal users)
    """CREATE TABLE IF NOT EXISTS admin_users (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        email VARCHAR(255) NOT NULL UNIQUE,
        display_name VARCHAR(255),
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'admin' CHECK (role IN ('superadmin', 'admin', 'viewer')),
        last_login_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_admin_users_email ON admin_users(email)",
]

import json as _json

_GUARDRAIL_SEED = [
    ("PII Detector", "Blocks prompts containing personal identifiers: email, IBAN, credit card, CPR, SSN", "pii_detector", "input", "block", "critical", 10, {"patterns": ["email", "iban", "credit_card", "cpr", "ssn", "phone_eu"]}),
    ("Secrets Scanner", "Blocks API keys, JWTs, PEM fragments, and database connection strings", "secrets_scanner", "input", "block", "critical", 20, {"patterns": ["aws_access_key", "github_token", "openai_key", "anthropic_key", "jwt", "private_key_header", "db_connstring"]}),
    ("Prompt Injection", "Flags known injection phrases and base64-obfuscated payloads", "prompt_injection", "input", "flag", "high", 30, {"base64_payload_threshold_chars": 200}),
    ("Topic Block — Trading Advice", "Blocks investment advice language outside the compliance team scope", "topic_block", "input", "block", "high", 40, {"blocked_topics": ["trading recommendation", "investment advice", "buy signal", "sell signal", "short position"]}),
    ("MNPI Detector", "Blocks prompts combining ticker symbols with material non-public information keywords", "mnpi_detector", "input", "block", "critical", 15, {"ticker_proximity_words": 30, "mnpi_keywords": ["not yet public", "earnings guidance", "merger", "acquisition", "take private"]}),
    ("Token Budget Cap", "Truncates prompts exceeding the per-call token limit", "token_budget_cap", "input", "truncate", "low", 5, {"max_tokens": 8192}),
    ("Output PII Redactor", "Redacts PII from model responses before returning to caller", "output_pii_redactor", "output", "redact", "critical", 10, {"redact_token": "[REDACTED]", "patterns": ["email", "iban", "credit_card", "cpr"]}),
    ("Hallucinated Citation Check", "Flags responses with numerical claims lacking a citation marker", "citation_check", "output", "flag", "medium", 50, {"min_citation_words": 15}),
    ("Toxicity Filter", "Blocks harmful or harassing output (multilingual: da, sv, en, de, fr)", "toxicity_filter", "output", "block", "high", 20, {"languages": ["da", "sv", "en", "de", "fr"], "threshold": 0.85}),
    ("Confidence Floor on Numbers", "Flags bare numerical claims without citation context", "confidence_floor", "output", "rewrite", "medium", 60, {"flag_bare_numbers": True, "require_citation_pattern": True}),
]

_auth = [Depends(require_admin_auth)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Guard: DEV_BYPASS_AUTH must not be enabled outside dev/test/ci environments.
    # Default to "production" so that an unset ENVIRONMENT var triggers the guard
    # rather than silently suppressing it.
    env = os.getenv("ENVIRONMENT", "production")
    if app_settings.dev_bypass_auth:
        if env not in ("development", "test", "ci"):
            raise RuntimeError(
                "DEV_BYPASS_AUTH=true is not allowed outside development/test environments. "
                f"Current ENVIRONMENT={env!r}. Set ENVIRONMENT=development to suppress."
            )
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "DEV_BYPASS_AUTH is active — all admin auth checks are skipped. "
            "Never enable this in staging or production."
        )

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

    # Seed default admin account only in dev/test/ci environments.
    # In production, admin accounts must be created explicitly via the provisioning script.
    if os.getenv("ENVIRONMENT", "production") in ("development", "test", "ci"):
        async with engine.begin() as conn:
            await conn.execute(text("""
                INSERT INTO admin_users (email, display_name, password_hash, role) VALUES
                    ('admin@simcorp.com', 'Default Admin',
                     '$2b$12$GwGtCW6GNoGJlD5lhF8xLeZPEZO8W5eDXr6TO7u3zm3SiHe1uZK3S',
                     'superadmin')
                ON CONFLICT (email) DO NOTHING
            """))

    # Seed a default team if none exists (dev convenience)
    async with engine.begin() as conn:
        team_count = (await conn.execute(text("SELECT COUNT(*) FROM teams"))).scalar()
        if team_count == 0:
            await conn.execute(text("""
                INSERT INTO teams (id, name, slug)
                VALUES (gen_random_uuid(), 'Engineering', 'engineering')
                ON CONFLICT DO NOTHING
            """))

    # Seed guardrails if table is empty
    async with engine.begin() as conn:
        count = (await conn.execute(text("SELECT COUNT(*) FROM guardrails WHERE team_id IS NULL"))).scalar()
        if count == 0:
            for name, desc, gtype, applies_to, action, severity, priority, config in _GUARDRAIL_SEED:
                await conn.execute(
                    text("""
                        INSERT INTO guardrails (name, description, type, applies_to, action, severity, priority, config)
                        VALUES (:name, :desc, :type, :applies_to, :action, :severity, :priority, CAST(:config AS jsonb))
                        ON CONFLICT DO NOTHING
                    """),
                    {
                        "name": name, "desc": desc, "type": gtype, "applies_to": applies_to,
                        "action": action, "severity": severity, "priority": priority,
                        "config": _json.dumps(config),
                    },
                )

    # Seed default areas if table is empty
    async with engine.begin() as conn:
        count = (await conn.execute(text("SELECT COUNT(*) FROM areas"))).scalar()
        if count == 0:
            for name, slug, description, color in [
                ("Engineering", "engineering", "Software engineering teams", "#0A7BD7"),
                ("Risk & Compliance", "risk-compliance", "Risk management and compliance teams", "#EF3E4A"),
                ("Finance", "finance", "Finance and treasury teams", "#1D958E"),
            ]:
                await conn.execute(text("""
                    INSERT INTO areas (name, slug, description, color)
                    VALUES (:name, :slug, :description, :color)
                    ON CONFLICT DO NOTHING
                """), {"name": name, "slug": slug, "description": description, "color": color})

    # Seed model registry — always upsert so new entries are added without wiping existing ones
    async with engine.begin() as conn:
        models_to_seed = [
            # Anthropic
            ("Claude Sonnet 4.6", "claude-sonnet-4-6", "anthropic"),
            ("Claude Opus 4.7", "claude-opus-4-7", "anthropic"),
            ("Claude Haiku 4.5", "claude-haiku-4-5", "anthropic"),
            # OpenAI via LiteLLM
            ("GPT-4o", "gpt-4o", "openai"),
            ("GPT-4o mini", "gpt-4o-mini", "openai"),
            # GitHub Copilot
            ("Copilot GPT-4o", "copilot-gpt-4o", "github-copilot"),
            ("Copilot GPT-4o mini", "copilot-gpt-4o-mini", "github-copilot"),
            ("Copilot o3-mini", "copilot-o3-mini", "github-copilot"),
            ("Copilot Claude 3.5 Sonnet", "copilot-claude-3.5-sonnet", "github-copilot"),
            # Azure AI Foundry
            ("Azure GPT-4o", "azure-gpt-4o", "azure"),
            ("Azure GPT-4o mini", "azure-gpt-4o-mini", "azure"),
            ("Azure o3-mini", "azure-o3-mini", "azure"),
            ("Azure GPT-4.1", "azure-gpt-4.1", "azure"),
            # GitHub Models
            ("GitHub GPT-4o", "github-gpt-4o", "github-models"),
            # Gemini
            ("Gemini 1.5 Pro", "gemini-1.5-pro", "google"),
            # Local
            ("Llama 3.2 (local)", "local", "ollama"),
        ]
        for name, model_id, provider in models_to_seed:
            await conn.execute(
                text("""
                    INSERT INTO model_registry (name, model_id, provider, enabled)
                    VALUES (:name, :model_id, :provider, TRUE)
                    ON CONFLICT (model_id) DO NOTHING
                """),
                {"name": name, "model_id": model_id, "provider": provider},
            )

    app.state.redis = make_redis(app_settings.redis_url)

    # Start background optimization worker (runs every 6 hours)
    import asyncpg as _asyncpg
    from app.workers.optimization_worker import optimization_loop as _opt_loop
    _pg_dsn = app_settings.database_url.replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    _pool = await _asyncpg.create_pool(_pg_dsn, min_size=1, max_size=3)
    _worker_task = asyncio.create_task(_opt_loop(_pool))

    yield

    _worker_task.cancel()
    try:
        await _worker_task
    except asyncio.CancelledError:
        pass
    await _pool.close()
    await app.state.redis.aclose()


_is_dev = os.getenv("ENVIRONMENT", "production") in ("development", "test", "ci")

app = FastAPI(
    title="AI Gateway — Admin Portal",
    lifespan=lifespan,
    docs_url="/docs" if _is_dev else None,
    redoc_url="/redoc" if _is_dev else None,
    openapi_url="/openapi.json" if _is_dev else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.cors_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Admin-Token"],
    allow_credentials=True,
)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.include_router(dev_auth.router)  # public — no admin auth
app.include_router(admin_auth_router.router)  # public — IS the auth, no token required
app.include_router(settings_router.router, dependencies=_auth)
app.include_router(dashboard.router, dependencies=_auth)
app.include_router(areas_router.router, dependencies=_auth)
app.include_router(teams.router, dependencies=_auth)
app.include_router(members.router, dependencies=_auth)
app.include_router(developers_router.router, dependencies=_auth)
app.include_router(api_keys_module.router, dependencies=_auth)
app.include_router(api_keys_module.portal_keys_router)  # portal: authenticated via dev session, no admin token
app.include_router(policies.router, dependencies=_auth)
app.include_router(policies.summary_router, dependencies=_auth)
app.include_router(pricing.router, dependencies=_auth)
app.include_router(model_registry.router, dependencies=_auth)
app.include_router(system.router, dependencies=_auth)
app.include_router(audit_log.router, dependencies=_auth)
app.include_router(budget.router, dependencies=_auth)
app.include_router(requests_router.router, dependencies=_auth)
app.include_router(guardrails_router.router, dependencies=_auth)
app.include_router(mcp_router.router, dependencies=_auth)
app.include_router(plugins_router.router, dependencies=_auth)
app.include_router(reports_router.router, dependencies=_auth)
app.include_router(ai_help_router.router)       # own auth per endpoint (admin or dev session)
app.include_router(devops_agent_router.router)  # own auth: require_admin_auth
app.include_router(insights_router.router)      # own auth per endpoint (admin or dev session)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["health"])
async def health():
    """Liveness probe — returns 200 if the process is running."""
    return {"status": "ok"}


@app.get("/ready", tags=["health"])
async def ready(request: Request):
    """Readiness probe — checks Redis and Postgres before accepting traffic."""
    errors: dict[str, str] = {}

    try:
        await request.app.state.redis.ping()
    except Exception as exc:
        errors["redis"] = str(exc)

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        errors["postgres"] = str(exc)

    if errors:
        return JSONResponse({"status": "not_ready", "errors": errors}, status_code=503)
    return {"status": "ready"}
