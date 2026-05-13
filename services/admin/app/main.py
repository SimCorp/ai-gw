import asyncio
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
from app.db import engine

# Import all ORM models so they're available to routers and Alembic env
from app.models import (  # noqa: F401
    agent as agent_model,
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
    workflow as workflow_model,
    workflow_run as workflow_run_model,
)

from app.routers import (
    admin_auth as admin_auth_router,
    ai_help as ai_help_router,
    config_api as config_api_router,
    codemate as codemate_router,
    copilot_catalog as copilot_catalog_router,
    devops_agent as devops_agent_router,
    identity as identity_router,
    insights as insights_router,
    memory_admin as memory_admin_router,
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
    workflows as workflows_router,
    system,
    teams,
)


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

    # Schema is owned by Alembic (services/admin/migrations).
    # The db-migrate compose service runs `alembic upgrade head` before this
    # service starts; we do not run create_all() or DDL here anymore.

    # Seed default admin account only in dev/test/ci environments.
    # In production, admin accounts must be created explicitly via the provisioning script.
    if os.getenv("ENVIRONMENT", "production") in ("development", "test", "ci"):
        async with engine.begin() as conn:
            await conn.execute(text("""
                INSERT INTO admin_users (email, display_name, password_hash, role) VALUES
                    ('admin@simcorp.com', 'Default Admin',
                     '$2b$12$bUvzQRuY31dPXWEszjCKR.KZrm9DKO1GAb0t20IjNA92IpphK5JVK',
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
            # Azure OpenAI (via Azure AI Foundry)
            ("Azure GPT-4o", "azure-gpt-4o", "azure"),
            ("Azure GPT-4o mini", "azure-gpt-4o-mini", "azure"),
            ("Azure o3-mini", "azure-o3-mini", "azure"),
            ("Azure GPT-4.1", "azure-gpt-4.1", "azure"),
            # Azure AI Foundry — Microsoft Phi
            ("Phi-4", "phi-4", "azure-ai-foundry"),
            ("Phi-4 mini", "phi-4-mini", "azure-ai-foundry"),
            ("Phi-3.5 mini", "phi-3.5-mini", "azure-ai-foundry"),
            ("Phi-3.5 MoE", "phi-3.5-moe", "azure-ai-foundry"),
            # Azure AI Foundry — Open models
            ("Llama 3.3 70B", "llama-3.3-70b", "azure-ai-foundry"),
            ("Llama 3.1 405B", "llama-3.1-405b", "azure-ai-foundry"),
            ("Mistral Large 2", "mistral-large-2", "azure-ai-foundry"),
            ("DeepSeek R1", "deepseek-r1", "azure-ai-foundry"),
            ("Cohere Command R+", "cohere-command-r-plus", "azure-ai-foundry"),
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

    # Pre-generate the RSA identity signing key on startup so the first JWKS
    # request is served without a generation delay.
    from app.identity_signing import get_or_create_signing_key as _get_signing_key
    await _get_signing_key(app.state.redis)

    # Start Awesome Copilot catalog background sync (first sync + every 6h)
    from app.routers.copilot_catalog import start_background_sync as _start_catalog_sync
    _start_catalog_sync(app)

    # Auto-register gateway MCP servers (best-effort)
    _mcp_seeds = [
        ("Awesome Copilot", "Community agents, instructions, and recipes from Awesome GitHub Copilot",
         "http://admin:8005/mcp/copilot-catalog"),
        ("AI Librarian", "Shared research knowledge base with semantic search",
         "http://librarian:8008/mcp"),
        ("CodeMate Tools", "SimCorp codebase search tools — requires SimCorp network",
         "http://admin:8005/mcp/codemate"),
    ]
    try:
        async with engine.begin() as conn:
            for name, desc, url in _mcp_seeds:
                await conn.execute(text("""
                    INSERT INTO mcp_servers (name, description, url, auth_type, enabled, status)
                    VALUES (:name, :desc, :url, 'none', TRUE, 'active')
                    ON CONFLICT (url) DO NOTHING
                """), {"name": name, "desc": desc, "url": url})
    except Exception:
        pass  # table may not exist on first migration run

    # Start background optimization worker (runs every 6 hours)
    import asyncpg as _asyncpg
    from app.workers.optimization_worker import start_optimization_worker as _opt_worker
    _pg_dsn = app_settings.database_url.replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    _pool = await _asyncpg.create_pool(_pg_dsn, min_size=1, max_size=3)
    _worker_task = asyncio.create_task(_opt_worker(_pool))

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


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-XSS-Protection", "1; mode=block")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    return response
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
app.include_router(config_api_router.router, dependencies=_auth)
app.include_router(copilot_catalog_router.router, dependencies=_auth)
app.include_router(codemate_router.router, dependencies=_auth)
app.include_router(requests_router.router, dependencies=_auth)
app.include_router(guardrails_router.router, dependencies=_auth)
app.include_router(workflows_router.router, dependencies=_auth)
app.include_router(mcp_router.router, dependencies=_auth)
app.include_router(plugins_router.router, dependencies=_auth)
app.include_router(reports_router.router, dependencies=_auth)
app.include_router(ai_help_router.router)       # own auth per endpoint (admin or dev session)
app.include_router(devops_agent_router.router)  # own auth: require_admin_auth
app.include_router(insights_router.router)      # own auth per endpoint (admin or dev session)
app.include_router(identity_router.router, dependencies=_auth)  # POST /identity/tokens, POST /identity/verify
app.include_router(identity_router.public_router)  # GET /identity/jwks — no auth required
app.include_router(memory_admin_router.router, dependencies=_auth)


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
