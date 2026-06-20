import asyncio
import json as _json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import make_asgi_app
from sqlalchemy import text

from app.auth import require_admin_auth
from app.config import settings as app_settings
from app.db import engine
from app.logging_config import CorrelationIdMiddleware, init_logging

# Import all ORM models so they're available to routers and Alembic env
from app.models import (  # noqa: F401
    agent as agent_model,
)
from app.redis_utils import make_redis
from app.routers import (
    access_requests as access_requests_router,
)
from app.routers import (
    admin_auth as admin_auth_router,
)
from app.routers import (
    admin_champions as admin_champions_router,
)
from app.routers import (
    admin_ops as admin_ops_router,
)
from app.routers import (
    ai_help as ai_help_router,
)
from app.routers import (
    alerts as alerts_router,
)
from app.routers import (
    api_keys as api_keys_module,
)
from app.routers import (
    audit_log,
    budget,
    dashboard,
    dev_auth,
    model_registry,
    policies,
    pricing,
    system,
)
from app.routers import (
    champions as champions_router,
)
from app.routers import (
    codemate as codemate_router,
)
from app.routers import (
    config_api as config_api_router,
)
from app.routers import (
    copilot_catalog as copilot_catalog_router,
)
from app.routers import (
    developers as developers_router,
)
from app.routers import (
    devops_agent as devops_agent_router,
)
from app.routers import (
    entra as entra_router,
)
from app.routers import (
    genai_adoption as genai_adoption_router,
)
from app.routers import (
    guardrails as guardrails_router,
)
from app.routers import (
    identity as identity_router,
)
from app.routers import (
    insights as insights_router,
)
from app.routers import (
    mcp as mcp_router,
)
from app.routers import (
    memory_admin as memory_admin_router,
)
from app.routers import (
    nodes as nodes_router,
)
from app.routers import (
    plugins as plugins_router,
)
from app.routers import (
    prompts as prompts_router,
)
from app.routers import (
    reports as reports_router,
)
from app.routers import (
    requests as requests_router,
)
from app.routers import (
    scanner as scanner_router,
)
from app.routers import (
    scim as scim_router,
)
from app.routers import (
    settings as settings_router,
)
from app.routers import (
    skills as skills_router,
)
from app.routers import (
    tools as tools_router,
)
from app.routers import (
    transformation as transformation_router,
)
from app.routers import (
    unified_auth as unified_auth_router,
)
from app.routers import (
    users as users_router,
)
from app.routers import (
    workflows as workflows_router,
)

_GUARDRAIL_SEED = [
    (
        "PII Detector",
        "Blocks prompts containing personal identifiers: email, IBAN, credit card, CPR, SSN",
        "pii_detector",
        "input",
        "block",
        "critical",
        10,
        {"patterns": ["email", "iban", "credit_card", "cpr", "ssn", "phone_eu"]},
    ),
    (
        "Secrets Scanner",
        "Blocks API keys, JWTs, PEM fragments, and database connection strings",
        "secrets_scanner",
        "input",
        "block",
        "critical",
        20,
        {
            "patterns": [
                "aws_access_key",
                "github_token",
                "openai_key",
                "anthropic_key",
                "jwt",
                "private_key_header",
                "db_connstring",
            ]
        },
    ),
    (
        "Prompt Injection",
        "Flags known injection phrases and base64-obfuscated payloads",
        "prompt_injection",
        "input",
        "flag",
        "high",
        30,
        {"base64_payload_threshold_chars": 200},
    ),
    (
        "Topic Block — Trading Advice",
        "Blocks investment advice language outside the compliance team scope",
        "topic_block",
        "input",
        "block",
        "high",
        40,
        {
            "blocked_topics": [
                "trading recommendation",
                "investment advice",
                "buy signal",
                "sell signal",
                "short position",
            ]
        },
    ),
    (
        "MNPI Detector",
        "Blocks prompts combining ticker symbols with material non-public information keywords",
        "mnpi_detector",
        "input",
        "block",
        "critical",
        15,
        {
            "ticker_proximity_words": 30,
            "mnpi_keywords": [
                "not yet public",
                "earnings guidance",
                "merger",
                "acquisition",
                "take private",
            ],
        },
    ),
    (
        "Token Budget Cap",
        "Truncates prompts exceeding the per-call token limit",
        "token_budget_cap",
        "input",
        "truncate",
        "low",
        5,
        {"max_tokens": 8192},
    ),
    (
        "Output PII Redactor",
        "Redacts PII from model responses before returning to caller",
        "output_pii_redactor",
        "output",
        "redact",
        "critical",
        10,
        {"redact_token": "[REDACTED]", "patterns": ["email", "iban", "credit_card", "cpr"]},
    ),
    (
        "Hallucinated Citation Check",
        "Flags responses with numerical claims lacking a citation marker",
        "citation_check",
        "output",
        "flag",
        "medium",
        50,
        {"min_citation_words": 15},
    ),
    (
        "Toxicity Filter",
        "Blocks harmful or harassing output (multilingual: da, sv, en, de, fr)",
        "toxicity_filter",
        "output",
        "block",
        "high",
        20,
        {"languages": ["da", "sv", "en", "de", "fr"], "threshold": 0.85},
    ),
    (
        "Confidence Floor on Numbers",
        "Flags bare numerical claims without citation context",
        "confidence_floor",
        "output",
        "rewrite",
        "medium",
        60,
        {"flag_bare_numbers": True, "require_citation_pattern": True},
    ),
]

_auth = [Depends(require_admin_auth)]


async def _collect_cache_snapshot():
    """Background: record a cache snapshot every 60 seconds for analytics."""
    import asyncio as _asyncio

    import httpx as _httpx

    from app.db import async_session_maker

    await _asyncio.sleep(30)  # wait for services to be ready
    while True:
        try:
            async with _httpx.AsyncClient(timeout=5) as client:
                r = await client.get("http://localhost:8005/system/health")
                if r.status_code == 200:
                    data = r.json()
                    gw = data.get("gateway", {})
                    redis = data.get("redis", {})
                    async with async_session_maker() as session:
                        from sqlalchemy import text as _text

                        await session.execute(
                            _text("""
                            INSERT INTO cache_snapshots (hit_rate, requests_60s, redis_mem_mb, redis_ping_ms)
                            VALUES (:hit_rate, :requests_60s, :redis_mem_mb, :redis_ping_ms)
                        """),
                            {
                                "hit_rate": gw.get("cache_hit_rate_last_60s"),
                                "requests_60s": gw.get("requests_last_60s"),
                                "redis_mem_mb": redis.get("used_memory_mb"),
                                "redis_ping_ms": redis.get("ping_ms"),
                            },
                        )
                        # Prune snapshots older than 30 days
                        await session.execute(
                            _text(
                                "DELETE FROM cache_snapshots WHERE captured_at < NOW() - INTERVAL '30 days'"
                            )
                        )
                        await session.commit()
        except Exception:
            pass  # fail silently — non-critical analytics
        await _asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is owned by Alembic (services/admin/migrations).
    # The db-migrate compose service runs `alembic upgrade head` before this
    # service starts; we do not run create_all() or DDL here anymore.
    # Accounts must be created explicitly via the provisioning script — no
    # default-account seeding.

    # Seed guardrails if table is empty
    async with engine.begin() as conn:
        count = (
            await conn.execute(text("SELECT COUNT(*) FROM guardrails WHERE team_id IS NULL"))
        ).scalar()
        if count == 0:
            for (
                name,
                desc,
                gtype,
                applies_to,
                action,
                severity,
                priority,
                config,
            ) in _GUARDRAIL_SEED:
                await conn.execute(
                    text("""
                        INSERT INTO guardrails (name, description, type, applies_to, action, severity, priority, config)
                        VALUES (:name, :desc, :type, :applies_to, :action, :severity, :priority, CAST(:config AS jsonb))
                        ON CONFLICT DO NOTHING
                    """),
                    {
                        "name": name,
                        "desc": desc,
                        "type": gtype,
                        "applies_to": applies_to,
                        "action": action,
                        "severity": severity,
                        "priority": priority,
                        "config": _json.dumps(config),
                    },
                )

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

    # Bootstrap root organization node (idempotent — creates only if missing)
    try:
        from app.db import async_session_maker as _asm
        from app.routers.nodes import ensure_root_node as _ensure_root

        async with _asm() as _ns:
            await _ensure_root(_ns)
    except Exception as _e:
        import logging as _logging

        _logging.getLogger(__name__).warning(f"Root node bootstrap skipped: {_e}")

    # Start Awesome Copilot catalog background sync (first sync + every 6h)
    from app.routers.copilot_catalog import start_background_sync as _start_catalog_sync

    _start_catalog_sync(app)

    # Auto-register gateway MCP servers (best-effort)
    _mcp_seeds = [
        (
            "Awesome Copilot",
            "Community agents, instructions, and recipes from Awesome GitHub Copilot",
            "http://admin:8005/mcp/copilot-catalog",
        ),
        (
            "AI Librarian",
            "Shared research knowledge base with semantic search",
            "http://librarian:8008/mcp",
        ),
        (
            "CodeMate Tools",
            "SimCorp codebase search tools — requires SimCorp network",
            "http://admin:8005/mcp/codemate",
        ),
    ]
    try:
        async with engine.begin() as conn:
            for name, desc, url in _mcp_seeds:
                await conn.execute(
                    text("""
                    INSERT INTO mcp_servers (name, description, url, auth_type, enabled, status)
                    VALUES (:name, :desc, :url, 'none', TRUE, 'active')
                    ON CONFLICT (url) DO NOTHING
                """),
                    {"name": name, "desc": desc, "url": url},
                )
    except Exception:
        pass  # table may not exist on first migration run

    # Start background optimization worker (runs every 6 hours)
    import asyncpg as _asyncpg

    from app.workers.optimization_worker import start_optimization_worker as _opt_worker

    _pg_dsn = app_settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    _pool = await _asyncpg.create_pool(_pg_dsn, min_size=1, max_size=3)
    _worker_task = asyncio.create_task(_opt_worker(_pool))

    # Start APScheduler for periodic background jobs
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    _scheduler = AsyncIOScheduler()

    async def _run_weekly_digest():
        from app.db import async_session_maker
        from app.jobs.weekly_digest import send_weekly_digests

        async with async_session_maker() as session:
            await send_weekly_digests(session)

    async def _run_workday_sync():
        from app.db import async_session_maker
        from app.jobs.workday_sync import run_workday_sync

        async with async_session_maker() as session:
            await run_workday_sync(session)

    async def _run_auto_confirm_asks():
        from app.jobs.auto_confirm_asks import run_auto_confirm

        await run_auto_confirm()

    _scheduler.add_job(
        _run_weekly_digest,
        CronTrigger(day_of_week="mon", hour=7, minute=0),
        id="weekly_digest",
        replace_existing=True,
    )
    _scheduler.add_job(
        _run_workday_sync,
        CronTrigger(hour=2, minute=0),
        id="workday_sync",
        replace_existing=True,
    )
    _scheduler.add_job(
        _run_auto_confirm_asks,
        CronTrigger(hour=3, minute=0),
        id="auto_confirm_asks",
        replace_existing=True,
    )
    _scheduler.start()

    yield

    _scheduler.shutdown(wait=False)
    _worker_task.cancel()
    try:
        await _worker_task
    except asyncio.CancelledError:
        pass
    await _pool.close()
    await app.state.redis.aclose()


_is_dev = os.getenv("ENVIRONMENT", "production") in ("development", "test", "ci")

init_logging("admin")

app = FastAPI(
    title="AI Gateway — Admin Portal",
    lifespan=lifespan,
    docs_url="/docs" if _is_dev else None,
    redoc_url="/redoc" if _is_dev else None,
    openapi_url="/openapi.json" if _is_dev else None,
)

app.add_middleware(CorrelationIdMiddleware)
app.mount("/metrics", make_asgi_app())

from app.observability import init_observability  # noqa: E402

init_observability(app, service_name="admin")

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
app.include_router(unified_auth_router.router)  # public — unified /auth/* endpoints
app.include_router(unified_auth_router.oidc_router)  # public — OIDC SSO flow
app.include_router(users_router.router, dependencies=_auth)  # admin user management UI
app.include_router(settings_router.router, dependencies=_auth)
app.include_router(dashboard.router, dependencies=_auth)
app.include_router(nodes_router.router, dependencies=_auth)
# members.py router (legacy /teams/{id}/members) is omitted — teams table removed.
# Use /nodes/{id}/members instead.
app.include_router(developers_router.router, dependencies=_auth)
app.include_router(api_keys_module.router, dependencies=_auth)
app.include_router(
    api_keys_module.portal_keys_router
)  # portal: authenticated via dev session, no admin token
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
app.include_router(entra_router.router, dependencies=_auth)
app.include_router(guardrails_router.router, dependencies=_auth)
app.include_router(workflows_router.router, dependencies=_auth)
app.include_router(mcp_router.router, dependencies=_auth)
app.include_router(plugins_router.router, dependencies=_auth)
app.include_router(reports_router.router, dependencies=_auth)
app.include_router(ai_help_router.router)  # own auth per endpoint (admin or dev session)
app.include_router(devops_agent_router.router)  # own auth: require_admin_auth
app.include_router(insights_router.router)  # own auth per endpoint (admin or dev session)
app.include_router(
    identity_router.router, dependencies=_auth
)  # POST /identity/tokens, POST /identity/verify
app.include_router(identity_router.public_router)  # GET /identity/jwks — no auth required
app.include_router(memory_admin_router.router, dependencies=_auth)
app.include_router(transformation_router.dev_router)  # own auth: dev session
app.include_router(transformation_router.admin_router, dependencies=_auth)
app.include_router(genai_adoption_router.router, dependencies=_auth)
app.include_router(alerts_router.router, dependencies=_auth)
app.include_router(access_requests_router.router, dependencies=_auth)
app.include_router(scim_router.router)  # SCIM uses its own SCIM_BEARER_TOKEN auth
app.include_router(tools_router.router)  # per-route auth: GET any user, PATCH admin-only
app.include_router(skills_router.router)  # own auth per endpoint
app.include_router(prompts_router.router)  # own auth per endpoint
app.include_router(admin_ops_router.router, dependencies=_auth)
app.include_router(admin_champions_router.router)  # own auth: require_admin_auth
app.include_router(champions_router.router)  # developer-facing — no admin token required
app.include_router(scanner_router.router, dependencies=_auth)


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
