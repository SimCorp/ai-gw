# Security Scanner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a developer self-service security scanning platform — target registration, scan job orchestration (Garak + Nuclei + Nmap), guardrail enforcement, CI/CD API, and portal UI.

**Architecture:** New `scanner` service (FastAPI, port :8011) owns job queuing, Docker-based scan execution, and result storage. The existing `admin` service gains target registration and quota management endpoints. Both portals get a Security section.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Redis (LPUSH/BRPOP queue), Docker SDK for Python, Garak (NVIDIA), Nuclei (ProjectDiscovery), Nmap, Next.js 14 with @tanstack/react-query.

---

## File Map

### New files
| Path | Purpose |
|---|---|
| `services/scanner/pyproject.toml` | Package definition |
| `services/scanner/Dockerfile` | Scanner service container |
| `services/scanner/docker/Dockerfile.garak` | Custom Garak image (pip install) |
| `services/scanner/app/__init__.py` | |
| `services/scanner/app/main.py` | FastAPI app, lifespan, CORS |
| `services/scanner/app/config.py` | Settings (DB, Redis, auth URL, worker secret) |
| `services/scanner/app/db.py` | Async SQLAlchemy engine + session factory |
| `services/scanner/app/redis_utils.py` | Redis client factory (copied from admin pattern) |
| `services/scanner/app/auth.py` | Token validation via auth service |
| `services/scanner/app/routers/__init__.py` | |
| `services/scanner/app/routers/jobs.py` | POST/GET/DELETE /jobs, GET /jobs/{id}/results |
| `services/scanner/app/routers/internal.py` | Worker protocol: progress, findings, complete |
| `services/scanner/app/worker/__init__.py` | |
| `services/scanner/app/worker/runner.py` | Redis queue poller + Docker container executor |
| `services/scanner/app/worker/parsers/__init__.py` | |
| `services/scanner/app/worker/parsers/garak.py` | JSONL → findings |
| `services/scanner/app/worker/parsers/nuclei.py` | JSON → findings |
| `services/scanner/app/worker/parsers/nmap.py` | XML → findings |
| `services/scanner/tests/conftest.py` | Pytest fixtures |
| `services/scanner/tests/test_jobs.py` | Job submission + quota enforcement tests |
| `services/scanner/tests/test_parsers.py` | Parser unit tests |
| `services/admin/app/routers/scanner.py` | Target CRUD, approval, quota management |
| `services/admin/migrations/versions/0025_security_scanner.py` | New tables + scanner_quota column |
| `apps/admin/app/admin/security/page.tsx` | Admin Security root (redirect to targets) |
| `apps/admin/app/admin/security/targets/page.tsx` | Target approval queue |
| `apps/admin/app/admin/security/jobs/page.tsx` | All jobs view + cancel |
| `apps/admin/app/admin/security/quotas/page.tsx` | Per-team quota editor |
| `apps/portal/app/portal/security/page.tsx` | Developer Security root (redirect to scans) |
| `apps/portal/app/portal/security/targets/page.tsx` | Register and view targets |
| `apps/portal/app/portal/security/scans/page.tsx` | Run scan, job list |
| `apps/portal/app/portal/security/scans/[jobId]/page.tsx` | Results view + SARIF download |

### Modified files
| Path | Change |
|---|---|
| `services/admin/app/main.py` | Import and mount scanner router |
| `infra/docker-compose.yml` | Add scanner service |
| `infra/nginx/default.conf` | Add `/scanner/` location block |

---

## Task 1: Database Migration

**Files:**
- Create: `services/admin/migrations/versions/0025_security_scanner.py`

- [ ] **Step 1: Write the migration**

```python
# services/admin/migrations/versions/0025_security_scanner.py
"""Add security scanner tables"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY, TEXT
from typing import Sequence, Union

revision = "0025"
down_revision = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        "scan_targets",
        sa.Column("id", UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("team_id", UUID(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("openapi_spec_url", sa.Text(), nullable=True),
        sa.Column("allowed_scan_types", ARRAY(TEXT), nullable=False, server_default=sa.text("ARRAY['ai','api','network']::text[]")),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending_approval"),
        sa.Column("approved_by", UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.TIMESTAMPTZ(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMPTZ(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_table(
        "scan_jobs",
        sa.Column("id", UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("team_id", UUID(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("target_id", UUID(), sa.ForeignKey("scan_targets.id"), nullable=False),
        sa.Column("requested_by", UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scan_types", ARRAY(TEXT), nullable=False),
        sa.Column("tier", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("trigger", sa.Text(), nullable=False, server_default="manual"),
        sa.Column("ci_ref", sa.Text(), nullable=True),
        sa.Column("queued_at", sa.TIMESTAMPTZ(), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.TIMESTAMPTZ(), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMPTZ(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("worker_id", sa.Text(), nullable=True),
        sa.Column("partial_results", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_table(
        "scan_findings",
        sa.Column("id", UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("job_id", UUID(), sa.ForeignKey("scan_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scanner", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", JSONB(), nullable=True),
        sa.Column("remediation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMPTZ(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_scan_findings_job_id", "scan_findings", ["job_id"])
    op.create_index("ix_scan_findings_severity", "scan_findings", ["severity"])
    op.create_index("ix_scan_jobs_team_id", "scan_jobs", ["team_id"])
    op.add_column(
        "teams",
        sa.Column(
            "scanner_quota",
            JSONB(),
            nullable=False,
            server_default=sa.text('\'{"daily_limit": 3, "allow_external_targets": false, "max_tier": "quick"}\'::jsonb'),
        ),
    )


def downgrade():
    op.drop_column("teams", "scanner_quota")
    op.drop_index("ix_scan_findings_severity")
    op.drop_index("ix_scan_findings_job_id")
    op.drop_index("ix_scan_jobs_team_id")
    op.drop_table("scan_findings")
    op.drop_table("scan_jobs")
    op.drop_table("scan_targets")
```

- [ ] **Step 2: Run the migration**

```bash
cd services/admin
pip install -e ".[dev]"
alembic upgrade head
```

Expected: `Running upgrade 0024 -> 0025, Add security scanner tables`

- [ ] **Step 3: Verify tables exist**

```bash
psql $DATABASE_URL -c "\dt scan_*" && psql $DATABASE_URL -c "\d teams" | grep scanner_quota
```

Expected: `scan_findings`, `scan_jobs`, `scan_targets` listed; `scanner_quota` column shown.

- [ ] **Step 4: Commit**

```bash
git add services/admin/migrations/versions/0025_security_scanner.py
git commit -m "feat(scanner): add scan_targets, scan_jobs, scan_findings tables"
```

---

## Task 2: Admin Service — Scanner Router

**Files:**
- Create: `services/admin/app/routers/scanner.py`
- Modify: `services/admin/app/main.py`

- [ ] **Step 1: Write tests first**

Create `services/admin/tests/test_scanner_router.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from app.main import app

@pytest.fixture
def mock_session(monkeypatch):
    from unittest.mock import MagicMock
    session = AsyncMock()
    monkeypatch.setattr("app.routers.scanner.get_session", lambda: session)
    return session

@pytest.mark.asyncio
async def test_list_targets_empty(mock_session):
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(return_value=AsyncMock(mappings=lambda: AsyncMock(all=lambda: [])))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/scanner/targets", headers={"x-internal-key": "test"})
    assert resp.status_code == 200
    assert resp.json() == []

@pytest.mark.asyncio
async def test_approve_target_not_found(mock_session):
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(return_value=AsyncMock(mappings=lambda: AsyncMock(first=lambda: None)))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/scanner/targets/nonexistent/approve",
            json={"allowed_scan_types": ["ai"]},
            headers={"x-internal-key": "test"},
        )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd services/admin && pytest tests/test_scanner_router.py -v
```

Expected: `ImportError` or `404` route not found — router not yet created.

- [ ] **Step 3: Create the scanner router**

```python
# services/admin/app/routers/scanner.py
import json
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_session

router = APIRouter(prefix="/scanner", tags=["scanner"])


class TargetCreate(BaseModel):
    url: str
    label: str
    openapi_spec_url: str | None = None
    requested_scan_types: list[str] = ["ai", "api", "network"]
    team_id: str
    created_by: str


class TargetApprove(BaseModel):
    allowed_scan_types: list[str]
    notes: str | None = None
    approved_by: str | None = None


class QuotaUpdate(BaseModel):
    daily_limit: int | None = None
    allow_external_targets: bool | None = None
    max_tier: str | None = None


_INTERNAL_IP_PREFIXES = ("10.", "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.", "172.26.",
    "172.27.", "172.28.", "172.29.", "172.30.", "172.31.", "192.168.", "127.")


def _is_external(url: str) -> bool:
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    if host.endswith(".simcorp.internal"):
        return False
    return not any(host.startswith(pfx) for pfx in _INTERNAL_IP_PREFIXES)


# ---- Targets ----

@router.get("/targets")
async def list_targets(
    team_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    where_clauses, params = [], {}
    if team_id:
        where_clauses.append("team_id = CAST(:team_id AS uuid)")
        params["team_id"] = team_id
    if status:
        where_clauses.append("status = :status")
        params["status"] = status
    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    rows = (await session.execute(
        text(f"SELECT * FROM scan_targets {where} ORDER BY created_at DESC"),
        params,
    )).mappings().all()
    return [dict(r) for r in rows]


@router.post("/targets", status_code=201)
async def register_target(body: TargetCreate, session: AsyncSession = Depends(get_session)):
    # Check team quota for external target permission
    if _is_external(body.url):
        quota_row = (await session.execute(
            text("SELECT scanner_quota FROM teams WHERE id = CAST(:tid AS uuid)"),
            {"tid": body.team_id},
        )).mappings().first()
        quota = quota_row["scanner_quota"] if quota_row else {}
        if not quota.get("allow_external_targets", False):
            raise HTTPException(status_code=403, detail="Team is not permitted to register external targets")
    result = await session.execute(
        text("""
            INSERT INTO scan_targets (team_id, url, label, openapi_spec_url, allowed_scan_types, created_by)
            VALUES (CAST(:team_id AS uuid), :url, :label, :openapi_spec_url,
                    CAST(:scan_types AS text[]), CAST(:created_by AS uuid))
            RETURNING *
        """),
        {
            "team_id": body.team_id,
            "url": body.url,
            "label": body.label,
            "openapi_spec_url": body.openapi_spec_url,
            "scan_types": "{" + ",".join(body.requested_scan_types) + "}",
            "created_by": body.created_by,
        },
    )
    await session.commit()
    return dict(result.mappings().first())


@router.post("/targets/{target_id}/approve")
async def approve_target(
    target_id: str, body: TargetApprove, session: AsyncSession = Depends(get_session)
):
    row = (await session.execute(
        text("SELECT id FROM scan_targets WHERE id = CAST(:id AS uuid)"),
        {"id": target_id},
    )).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Target not found")
    await session.execute(
        text("""
            UPDATE scan_targets
            SET status = 'approved',
                allowed_scan_types = CAST(:types AS text[]),
                approved_by = CAST(:approved_by AS uuid),
                approved_at = NOW(),
                notes = :notes
            WHERE id = CAST(:id AS uuid)
        """),
        {
            "id": target_id,
            "types": "{" + ",".join(body.allowed_scan_types) + "}",
            "approved_by": body.approved_by,
            "notes": body.notes,
        },
    )
    await session.commit()
    return {"status": "approved"}


@router.post("/targets/{target_id}/revoke")
async def revoke_target(
    target_id: str,
    body: dict = {},
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        text("""
            UPDATE scan_targets SET status = 'revoked', notes = :notes
            WHERE id = CAST(:id AS uuid) RETURNING id
        """),
        {"id": target_id, "notes": body.get("notes")},
    )
    if not result.mappings().first():
        raise HTTPException(status_code=404, detail="Target not found")
    await session.commit()
    return {"status": "revoked"}


# ---- Quotas ----

@router.get("/quotas")
async def list_quotas(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        text("SELECT id, name, scanner_quota FROM teams ORDER BY name")
    )).mappings().all()
    return [dict(r) for r in rows]


@router.patch("/quotas/{team_id}")
async def update_quota(
    team_id: str, body: QuotaUpdate, session: AsyncSession = Depends(get_session)
):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    set_parts = ", ".join(
        f"scanner_quota = scanner_quota || jsonb_build_object('{k}', :{k}::jsonb)"
        for k in updates
    )
    params: dict[str, Any] = {"team_id": team_id}
    for k, v in updates.items():
        params[k] = json.dumps(v)
    result = await session.execute(
        text(f"UPDATE teams SET {set_parts} WHERE id = CAST(:team_id AS uuid) RETURNING scanner_quota"),
        params,
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Team not found")
    await session.commit()
    return {"scanner_quota": row["scanner_quota"]}


# ---- Global kill switch ----

@router.post("/kill-switch")
async def set_kill_switch(request: Request, enabled: bool = True):
    redis = request.app.state.redis
    if enabled:
        await redis.set("scanner:disabled", "1")
    else:
        await redis.delete("scanner:disabled")
    return {"scanner_disabled": enabled}
```

- [ ] **Step 4: Mount the router in admin main.py**

In `services/admin/app/main.py`, add to the existing imports block:
```python
from app.routers import scanner as scanner_router
```

Then in the router registration section (after the last `app.include_router(...)` call):
```python
app.include_router(scanner_router.router)
```

- [ ] **Step 5: Run the tests**

```bash
cd services/admin && pytest tests/test_scanner_router.py -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add services/admin/app/routers/scanner.py services/admin/app/main.py \
        services/admin/tests/test_scanner_router.py
git commit -m "feat(scanner): add target registration and quota management to admin service"
```

---

## Task 3: Scanner Service — Skeleton

**Files:**
- Create: `services/scanner/pyproject.toml`
- Create: `services/scanner/Dockerfile`
- Create: `services/scanner/app/__init__.py`
- Create: `services/scanner/app/config.py`
- Create: `services/scanner/app/db.py`
- Create: `services/scanner/app/redis_utils.py`
- Create: `services/scanner/app/main.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
# services/scanner/pyproject.toml
[project]
name = "ai-gateway-scanner"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi~=0.111",
    "uvicorn[standard]>=0.30",
    "pydantic-settings>=2.4",
    "sqlalchemy[asyncio]~=2.0",
    "asyncpg>=0.29",
    "alembic>=1.13",
    "httpx>=0.27",
    "redis[hiredis]>=5.0",
    "docker>=7.0",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "httpx", "pytest-mock"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 2: Create config.py**

```python
# services/scanner/app/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://gateway:gateway@localhost:5432/gateway"
    redis_url: str = "redis://localhost:6379/0"
    auth_url: str = "http://localhost:8001"
    internal_api_key: str = "dev-internal-key"
    scanner_worker_secret: str = "dev-worker-secret"
    scan_job_queue_key: str = "scanner:jobs:queue"
    max_container_timeout_seconds: int = 900  # 15 minutes
    environment: str = "development"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
```

- [ ] **Step 3: Create db.py**

```python
# services/scanner/app/db.py
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with async_session_maker() as session:
        yield session
```

- [ ] **Step 4: Create redis_utils.py** (identical pattern to admin service)

```python
# services/scanner/app/redis_utils.py
import os
from redis.asyncio import Redis


def make_redis(redis_url: str) -> Redis:
    sentinel_hosts_env = os.getenv("REDIS_SENTINEL_HOSTS", "")
    if sentinel_hosts_env:
        from redis.asyncio.sentinel import Sentinel
        hosts = [
            (h.split(":")[0], int(h.split(":")[1]))
            for h in sentinel_hosts_env.split(",")
            if ":" in h
        ]
        master_name = os.getenv("REDIS_SENTINEL_MASTER", "mymaster")
        sentinel = Sentinel(hosts, socket_timeout=0.5)
        return sentinel.master_for(master_name, decode_responses=True)
    return Redis.from_url(redis_url, decode_responses=True)
```

- [ ] **Step 5: Create auth.py**

```python
# services/scanner/app/auth.py
import asyncio
from typing import Any
import httpx
from fastapi import Request, HTTPException
from app.config import settings

_auth_cache: dict[str, tuple[dict, float]] = {}
_CACHE_TTL = 45.0


async def validate_token(request: Request, token: str) -> dict[str, Any]:
    """Validate bearer token via auth service. Returns identity dict or raises 401."""
    import time
    cached = _auth_cache.get(token)
    if cached and (time.monotonic() - cached[1]) < _CACHE_TTL:
        return cached[0]
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.auth_url}/validate",
                headers={
                    "Authorization": f"Bearer {token}",
                    "x-internal-key": settings.internal_api_key,
                },
            )
        if resp.status_code in (401, 403):
            _auth_cache.pop(token, None)
            raise HTTPException(status_code=401, detail="Unauthorized")
        resp.raise_for_status()
        identity = resp.json()
        _auth_cache[token] = (identity, time.monotonic())
        return identity
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Auth service unavailable")


async def get_identity(request: Request) -> dict[str, Any]:
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return await validate_token(request, token)


def require_worker_auth(request: Request) -> None:
    auth_header = request.headers.get("Authorization", "")
    secret = auth_header.removeprefix("Bearer ").strip()
    if secret != settings.scanner_worker_secret:
        raise HTTPException(status_code=403, detail="Forbidden")
```

- [ ] **Step 6: Create main.py**

```python
# services/scanner/app/main.py
from contextlib import asynccontextmanager
import asyncio
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
```

- [ ] **Step 7: Create empty router stubs so the app starts**

```python
# services/scanner/app/routers/__init__.py
```

```python
# services/scanner/app/routers/jobs.py
from fastapi import APIRouter
router = APIRouter(prefix="/jobs", tags=["jobs"])
```

```python
# services/scanner/app/routers/internal.py
from fastapi import APIRouter
router = APIRouter(prefix="/internal/jobs", tags=["internal"])
```

- [ ] **Step 8: Create Dockerfile**

```dockerfile
# services/scanner/Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .
COPY app/ app/
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8011"]
```

- [ ] **Step 9: Verify the service starts**

```bash
cd services/scanner && pip install -e ".[dev]" && uvicorn app.main:app --port 8011
# In another terminal:
curl http://localhost:8011/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 10: Commit**

```bash
git add services/scanner/
git commit -m "feat(scanner): add scanner service skeleton"
```

---

## Task 4: Scanner Service — Job Submission with Guardrails

**Files:**
- Modify: `services/scanner/app/routers/jobs.py`
- Create: `services/scanner/tests/conftest.py`
- Create: `services/scanner/tests/test_jobs.py`

- [ ] **Step 1: Write failing tests for job submission**

```python
# services/scanner/tests/conftest.py
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch
from app.main import app


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.incr = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.lpush = AsyncMock(return_value=1)
    return redis


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.fixture
def client(mock_redis, mock_session):
    app.state.redis = mock_redis
    with patch("app.routers.jobs.get_session", return_value=mock_session):
        with patch("app.routers.jobs.get_identity", return_value={
            "team_id": "aaaaaaaa-0000-0000-0000-000000000001",
            "user_id": "bbbbbbbb-0000-0000-0000-000000000001",
            "api_key_id": "cccccccc-0000-0000-0000-000000000001",
        }):
            yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
```

```python
# services/scanner/tests/test_jobs.py
import pytest
from unittest.mock import AsyncMock, MagicMock


def _approved_target(scan_types=None):
    return {
        "id": "dddddddd-0000-0000-0000-000000000001",
        "team_id": "aaaaaaaa-0000-0000-0000-000000000001",
        "status": "approved",
        "allowed_scan_types": scan_types or ["ai", "api", "network"],
        "url": "http://myapp.simcorp.internal",
        "openapi_spec_url": None,
    }


def _quota(daily_limit=3, max_tier="quick"):
    return {"daily_limit": daily_limit, "allow_external_targets": False, "max_tier": max_tier}


@pytest.mark.asyncio
async def test_submit_job_success(client, mock_session, mock_redis):
    mock_session.execute = AsyncMock(side_effect=[
        MagicMock(mappings=lambda: MagicMock(first=lambda: _approved_target())),  # target lookup
        MagicMock(mappings=lambda: MagicMock(first=lambda: {"scanner_quota": _quota()})),  # quota
        MagicMock(mappings=lambda: MagicMock(first=lambda: {"id": "job-uuid-123"})),  # INSERT
    ])
    mock_redis.get = AsyncMock(return_value=None)  # kill switch off
    mock_redis.incr = AsyncMock(return_value=1)    # first job of day

    async with client as c:
        resp = await c.post("/jobs", json={
            "target_id": "dddddddd-0000-0000-0000-000000000001",
            "tier": "quick",
        }, headers={"Authorization": "Bearer test-token"})

    assert resp.status_code == 202
    assert resp.json()["status"] == "queued"


@pytest.mark.asyncio
async def test_submit_job_blocked_by_kill_switch(client, mock_session, mock_redis):
    mock_redis.get = AsyncMock(return_value="1")  # kill switch ON
    async with client as c:
        resp = await c.post("/jobs", json={
            "target_id": "dddddddd-0000-0000-0000-000000000001",
            "tier": "quick",
        }, headers={"Authorization": "Bearer test-token"})
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_submit_job_quota_exceeded(client, mock_session, mock_redis):
    mock_session.execute = AsyncMock(side_effect=[
        MagicMock(mappings=lambda: MagicMock(first=lambda: _approved_target())),
        MagicMock(mappings=lambda: MagicMock(first=lambda: {"scanner_quota": _quota(daily_limit=3)})),
    ])
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.incr = AsyncMock(return_value=4)  # over limit
    async with client as c:
        resp = await c.post("/jobs", json={
            "target_id": "dddddddd-0000-0000-0000-000000000001",
            "tier": "quick",
        }, headers={"Authorization": "Bearer test-token"})
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_submit_job_target_not_approved(client, mock_session, mock_redis):
    mock_session.execute = AsyncMock(side_effect=[
        MagicMock(mappings=lambda: MagicMock(first=lambda: None)),  # target not found
    ])
    mock_redis.get = AsyncMock(return_value=None)
    async with client as c:
        resp = await c.post("/jobs", json={
            "target_id": "dddddddd-0000-0000-0000-000000000001",
            "tier": "quick",
        }, headers={"Authorization": "Bearer test-token"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_submit_job_tier_not_allowed(client, mock_session, mock_redis):
    mock_session.execute = AsyncMock(side_effect=[
        MagicMock(mappings=lambda: MagicMock(first=lambda: _approved_target())),
        MagicMock(mappings=lambda: MagicMock(first=lambda: {"scanner_quota": _quota(max_tier="quick")})),
    ])
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.incr = AsyncMock(return_value=1)
    async with client as c:
        resp = await c.post("/jobs", json={
            "target_id": "dddddddd-0000-0000-0000-000000000001",
            "tier": "deep",  # not allowed by quota
        }, headers={"Authorization": "Bearer test-token"})
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd services/scanner && pytest tests/test_jobs.py -v
```

Expected: 5 failures — router has no logic yet.

- [ ] **Step 3: Implement the jobs router**

```python
# services/scanner/app/routers/jobs.py
import json
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import get_identity
from app.config import settings
from app.db import get_session

router = APIRouter(prefix="/jobs", tags=["jobs"])

_TIER_ORDER = {"quick": 0, "standard": 1, "deep": 2}
_TIER_DURATIONS = {"quick": 5, "standard": 15, "deep": 45}


class JobCreate(BaseModel):
    target_id: str
    scan_types: list[str] | None = None
    tier: str = "quick"
    trigger: str = "manual"
    ci_ref: str | None = None


async def _check_kill_switch(redis) -> None:
    if await redis.get("scanner:disabled"):
        raise HTTPException(status_code=503, detail="Security scanning is temporarily disabled")


async def _load_target(session: AsyncSession, target_id: str, team_id: str) -> dict:
    row = (await session.execute(
        text("""
            SELECT id, team_id, url, status, allowed_scan_types, openapi_spec_url
            FROM scan_targets
            WHERE id = CAST(:id AS uuid) AND team_id = CAST(:team_id AS uuid) AND status = 'approved'
        """),
        {"id": target_id, "team_id": team_id},
    )).mappings().first()
    if not row:
        raise HTTPException(status_code=403, detail="Target not found or not approved for this team")
    return dict(row)


async def _check_quota(redis, session: AsyncSession, team_id: str, tier: str) -> None:
    quota_row = (await session.execute(
        text("SELECT scanner_quota FROM teams WHERE id = CAST(:id AS uuid)"),
        {"id": team_id},
    )).mappings().first()
    quota: dict = quota_row["scanner_quota"] if quota_row else {}
    daily_limit: int = quota.get("daily_limit", 3)
    max_tier: str = quota.get("max_tier", "quick")

    if _TIER_ORDER.get(tier, 0) > _TIER_ORDER.get(max_tier, 0):
        raise HTTPException(
            status_code=403,
            detail=f"Tier '{tier}' not allowed; team quota permits up to '{max_tier}'",
        )

    # Concurrent job limit: max 2 running jobs per team at once
    running = (await session.execute(
        text("SELECT COUNT(*) AS n FROM scan_jobs WHERE team_id = CAST(:tid AS uuid) AND status = 'running'"),
        {"tid": team_id},
    )).mappings().first()
    if running and running["n"] >= 2:
        raise HTTPException(status_code=429, detail="Concurrent job limit reached (max 2 running jobs per team)")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    counter_key = f"scanner:quota:{team_id}:{today}"
    current = await redis.incr(counter_key)
    if current == 1:
        # Set TTL on first increment so it expires at next midnight
        import time
        from datetime import date, timedelta
        tomorrow = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0) + timedelta(days=1)
        ttl = int(tomorrow.timestamp() - time.time())
        await redis.expire(counter_key, ttl)

    if current > daily_limit:
        await redis.decr(counter_key)  # roll back increment
        from datetime import date, timedelta
        tomorrow = (date.today() + timedelta(days=1)).isoformat() + "T00:00:00Z"
        raise HTTPException(
            status_code=429,
            headers={"X-Quota-Resets-At": tomorrow},
            detail={
                "error": "quota_exceeded",
                "daily_used": daily_limit,
                "daily_limit": daily_limit,
                "resets_at": tomorrow,
            },
        )


@router.post("", status_code=202)
async def submit_job(
    body: JobCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    identity = await get_identity(request)
    team_id: str = identity["team_id"]
    user_id: str = identity.get("user_id") or identity.get("sub") or "unknown"
    redis = request.app.state.redis

    await _check_kill_switch(redis)
    target = await _load_target(session, body.target_id, team_id)
    await _check_quota(redis, session, team_id, body.tier)

    scan_types = body.scan_types or list(target["allowed_scan_types"])
    disallowed = set(scan_types) - set(target["allowed_scan_types"])
    if disallowed:
        raise HTTPException(status_code=403, detail=f"Scan types not allowed for this target: {disallowed}")

    result = await session.execute(
        text("""
            INSERT INTO scan_jobs
                (team_id, target_id, requested_by, scan_types, tier, trigger, ci_ref)
            VALUES
                (CAST(:team_id AS uuid), CAST(:target_id AS uuid), CAST(:user_id AS uuid),
                 CAST(:scan_types AS text[]), :tier, :trigger, :ci_ref)
            RETURNING id
        """),
        {
            "team_id": team_id,
            "target_id": body.target_id,
            "user_id": user_id,
            "scan_types": "{" + ",".join(scan_types) + "}",
            "tier": body.tier,
            "trigger": body.trigger,
            "ci_ref": body.ci_ref,
        },
    )
    await session.commit()
    job_id = str(result.mappings().first()["id"])

    await redis.lpush(settings.scan_job_queue_key, json.dumps({
        "job_id": job_id,
        "target_url": target["url"],
        "openapi_spec_url": target.get("openapi_spec_url"),
        "scan_types": scan_types,
        "tier": body.tier,
        "team_id": team_id,
    }))

    return {
        "job_id": job_id,
        "status": "queued",
        "estimated_duration_minutes": _TIER_DURATIONS[body.tier],
    }


@router.get("")
async def list_jobs(
    request: Request,
    team_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    session: AsyncSession = Depends(get_session),
):
    identity = await get_identity(request)
    effective_team_id = team_id or identity["team_id"]
    where_clauses = ["team_id = CAST(:team_id AS uuid)"]
    params: dict[str, Any] = {"team_id": effective_team_id, "limit": limit}
    if status:
        where_clauses.append("status = :status")
        params["status"] = status
    where = "WHERE " + " AND ".join(where_clauses)
    rows = (await session.execute(
        text(f"SELECT * FROM scan_jobs {where} ORDER BY queued_at DESC LIMIT :limit"),
        params,
    )).mappings().all()
    return [dict(r) for r in rows]


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    identity = await get_identity(request)
    row = (await session.execute(
        text("SELECT * FROM scan_jobs WHERE id = CAST(:id AS uuid) AND team_id = CAST(:team_id AS uuid)"),
        {"id": job_id, "team_id": identity["team_id"]},
    )).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return dict(row)


@router.delete("/{job_id}", status_code=204)
async def cancel_job(
    job_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    identity = await get_identity(request)
    result = await session.execute(
        text("""
            UPDATE scan_jobs SET status = 'cancelled', finished_at = NOW()
            WHERE id = CAST(:id AS uuid)
              AND team_id = CAST(:team_id AS uuid)
              AND status IN ('queued', 'running')
            RETURNING id
        """),
        {"id": job_id, "team_id": identity["team_id"]},
    )
    if not result.mappings().first():
        raise HTTPException(status_code=404, detail="Job not found or not cancellable")
    await session.commit()


@router.get("/{job_id}/results")
async def get_results(
    job_id: str,
    request: Request,
    severity: str | None = Query(default=None),
    format: str | None = Query(default=None),
    offset: int = Query(default=0),
    limit: int = Query(default=50, le=200),
    session: AsyncSession = Depends(get_session),
):
    identity = await get_identity(request)
    job_row = (await session.execute(
        text("SELECT id, status FROM scan_jobs WHERE id = CAST(:id AS uuid) AND team_id = CAST(:team_id AS uuid)"),
        {"id": job_id, "team_id": identity["team_id"]},
    )).mappings().first()
    if not job_row:
        raise HTTPException(status_code=404, detail="Job not found")

    where_clauses = ["job_id = CAST(:job_id AS uuid)"]
    params: dict[str, Any] = {"job_id": job_id, "limit": limit, "offset": offset}
    if severity:
        where_clauses.append("severity = :severity")
        params["severity"] = severity
    where = "WHERE " + " AND ".join(where_clauses)
    rows = (await session.execute(
        text(f"SELECT * FROM scan_findings {where} ORDER BY severity, created_at LIMIT :limit OFFSET :offset"),
        params,
    )).mappings().all()
    findings = [dict(r) for r in rows]

    if format == "sarif":
        return _to_sarif(job_id, findings)

    total_row = (await session.execute(
        text(f"SELECT COUNT(*) AS n FROM scan_findings WHERE job_id = CAST(:job_id AS uuid)"),
        {"job_id": job_id},
    )).mappings().first()
    return {"total": total_row["n"], "offset": offset, "findings": findings}


_SARIF_LEVEL = {"critical": "error", "high": "error", "medium": "warning", "low": "note", "info": "none"}


def _to_sarif(job_id: str, findings: list[dict]) -> dict:
    rules = {}
    results = []
    for f in findings:
        rule_id = f"{f['scanner']}/{f['category']}"
        rules[rule_id] = {
            "id": rule_id,
            "name": f["title"],
            "shortDescription": {"text": f["title"]},
            "fullDescription": {"text": f["description"]},
            "defaultConfiguration": {"level": _SARIF_LEVEL.get(f["severity"], "warning")},
        }
        results.append({
            "ruleId": rule_id,
            "level": _SARIF_LEVEL.get(f["severity"], "warning"),
            "message": {"text": f["description"]},
            "properties": {"severity": f["severity"], "scanner": f["scanner"]},
        })
    return {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [{
            "tool": {"driver": {"name": "ai-gw-scanner", "version": "1.0.0", "rules": list(rules.values())}},
            "results": results,
            "properties": {"jobId": job_id},
        }],
    }
```

- [ ] **Step 4: Run the tests**

```bash
cd services/scanner && pytest tests/test_jobs.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add services/scanner/app/routers/jobs.py \
        services/scanner/tests/conftest.py \
        services/scanner/tests/test_jobs.py
git commit -m "feat(scanner): add job submission with quota and guardrail enforcement"
```

---

## Task 5: Scanner Service — Internal Worker Protocol

**Files:**
- Modify: `services/scanner/app/routers/internal.py`

- [ ] **Step 1: Write test for internal endpoints**

Add to `services/scanner/tests/test_jobs.py`:

```python
@pytest.mark.asyncio
async def test_internal_endpoint_rejects_bad_secret(mock_session, mock_redis):
    from app.main import app
    app.state.redis = mock_redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/internal/jobs/some-id/complete",
            json={"status": "completed"},
            headers={"Authorization": "Bearer wrong-secret"},
        )
    assert resp.status_code == 403
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd services/scanner && pytest tests/test_jobs.py::test_internal_endpoint_rejects_bad_secret -v
```

Expected: FAIL — route does not exist yet.

- [ ] **Step 3: Implement internal router**

```python
# services/scanner/app/routers/internal.py
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import require_worker_auth
from app.db import get_session

router = APIRouter(prefix="/internal/jobs", tags=["internal"])


class FindingsBatch(BaseModel):
    findings: list[dict]


class CompletePayload(BaseModel):
    status: str  # completed | failed
    error_message: str | None = None
    partial_results: bool = False


@router.post("/{job_id}/progress")
async def report_progress(
    job_id: str,
    payload: dict,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    require_worker_auth(request)
    await session.execute(
        text("UPDATE scan_jobs SET worker_id = :worker_id WHERE id = CAST(:id AS uuid)"),
        {"id": job_id, "worker_id": payload.get("worker_id")},
    )
    await session.commit()
    return {"ok": True}


@router.post("/{job_id}/findings")
async def bulk_insert_findings(
    job_id: str,
    payload: FindingsBatch,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    require_worker_auth(request)
    for f in payload.findings:
        import json
        evidence = f.get("evidence")
        await session.execute(
            text("""
                INSERT INTO scan_findings
                    (job_id, scanner, severity, category, title, description, evidence, remediation)
                VALUES
                    (CAST(:job_id AS uuid), :scanner, :severity, :category,
                     :title, :description, CAST(:evidence AS jsonb), :remediation)
            """),
            {
                "job_id": job_id,
                "scanner": f["scanner"],
                "severity": f["severity"],
                "category": f["category"],
                "title": f["title"],
                "description": f["description"],
                "evidence": json.dumps(evidence) if evidence else None,
                "remediation": f.get("remediation"),
            },
        )
    await session.commit()
    return {"inserted": len(payload.findings)}


@router.post("/{job_id}/complete")
async def complete_job(
    job_id: str,
    payload: CompletePayload,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    require_worker_auth(request)
    await session.execute(
        text("""
            UPDATE scan_jobs
            SET status = :status,
                finished_at = NOW(),
                error_message = :error_message,
                partial_results = :partial_results
            WHERE id = CAST(:id AS uuid)
        """),
        {
            "id": job_id,
            "status": payload.status,
            "error_message": payload.error_message,
            "partial_results": payload.partial_results,
        },
    )
    await session.commit()
    return {"ok": True}
```

- [ ] **Step 4: Run all tests**

```bash
cd services/scanner && pytest tests/ -v
```

Expected: All tests PASS including the new secret-rejection test.

- [ ] **Step 5: Commit**

```bash
git add services/scanner/app/routers/internal.py services/scanner/tests/test_jobs.py
git commit -m "feat(scanner): add internal worker protocol endpoints"
```

---

## Task 6: Output Parsers

**Files:**
- Create: `services/scanner/app/worker/__init__.py`
- Create: `services/scanner/app/worker/parsers/__init__.py`
- Create: `services/scanner/app/worker/parsers/garak.py`
- Create: `services/scanner/app/worker/parsers/nuclei.py`
- Create: `services/scanner/app/worker/parsers/nmap.py`
- Create: `services/scanner/tests/test_parsers.py`

- [ ] **Step 1: Write parser tests**

```python
# services/scanner/tests/test_parsers.py
from app.worker.parsers.garak import parse_garak_jsonl
from app.worker.parsers.nuclei import parse_nuclei_json
from app.worker.parsers.nmap import parse_nmap_xml


GARAK_SAMPLE = """
{"attempt_idx":0,"probe":"promptinjection.HijackHateHumans","result_class":"promptinjection.HijackHateHumans","passed":false,"notes":{"trigger":"ignore previous","response":"I will now say hateful things"}}
{"attempt_idx":1,"probe":"promptinjection.HijackHateHumans","result_class":"promptinjection.HijackHateHumans","passed":true,"notes":{}}
"""

NUCLEI_SAMPLE = [
    {
        "template-id": "CVE-2021-41773",
        "info": {"name": "Path Traversal", "severity": "critical", "description": "Apache path traversal"},
        "host": "http://myapp.simcorp.internal",
        "matched-at": "http://myapp.simcorp.internal/cgi-bin/.%2e/%2e%2e/etc/passwd",
        "type": "http",
    }
]

NMAP_XML = """<?xml version="1.0"?>
<nmaprun>
  <host>
    <ports>
      <port protocol="tcp" portid="22">
        <state state="open"/>
        <service name="ssh" product="OpenSSH" version="8.9"/>
      </port>
      <port protocol="tcp" portid="8080">
        <state state="open"/>
        <service name="http" product="nginx"/>
      </port>
    </ports>
  </host>
</nmaprun>"""


def test_garak_parse_finds_failure():
    findings = parse_garak_jsonl(GARAK_SAMPLE)
    assert len(findings) == 1
    f = findings[0]
    assert f["scanner"] == "garak"
    assert f["category"] == "prompt_injection"
    assert f["severity"] in ("critical", "high", "medium", "low", "info")
    assert "title" in f
    assert "description" in f


def test_garak_parse_passes_ignored():
    findings = parse_garak_jsonl(GARAK_SAMPLE)
    # Only failures become findings
    assert all(f["evidence"]["passed"] is False for f in findings)


def test_nuclei_parse():
    findings = parse_nuclei_json(NUCLEI_SAMPLE)
    assert len(findings) == 1
    f = findings[0]
    assert f["scanner"] == "nuclei"
    assert f["severity"] == "critical"
    assert f["title"] == "Path Traversal"


def test_nmap_parse_open_ports():
    findings = parse_nmap_xml(NMAP_XML)
    assert len(findings) == 2
    ports = {f["evidence"]["port"] for f in findings}
    assert ports == {22, 8080}
    assert all(f["scanner"] == "nmap" for f in findings)
    assert all(f["category"] == "open_port" for f in findings)


def test_nmap_parse_severity_ssh():
    findings = parse_nmap_xml(NMAP_XML)
    ssh = next(f for f in findings if f["evidence"]["port"] == 22)
    assert ssh["severity"] == "info"  # SSH expected on internal hosts


def test_nuclei_empty():
    assert parse_nuclei_json([]) == []


def test_garak_empty():
    assert parse_garak_jsonl("") == []
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
cd services/scanner && pytest tests/test_parsers.py -v
```

Expected: `ImportError` — parsers not yet created.

- [ ] **Step 3: Implement Garak parser**

```python
# services/scanner/app/worker/parsers/garak.py
import json

_PROBE_TO_CATEGORY = {
    "promptinjection": "prompt_injection",
    "jailbreak": "jailbreak",
    "leakage": "pii_extraction",
    "toxicity": "toxicity",
    "xss": "xss",
    "continuation": "content_policy",
}

_PROBE_TO_SEVERITY = {
    "promptinjection": "high",
    "jailbreak": "high",
    "leakage": "critical",
    "toxicity": "medium",
}


def _probe_category(probe_class: str) -> str:
    prefix = probe_class.split(".")[0].lower() if "." in probe_class else probe_class.lower()
    return _PROBE_TO_CATEGORY.get(prefix, "ai_security")


def _probe_severity(probe_class: str) -> str:
    prefix = probe_class.split(".")[0].lower() if "." in probe_class else probe_class.lower()
    return _PROBE_TO_SEVERITY.get(prefix, "medium")


def parse_garak_jsonl(output: str) -> list[dict]:
    """Parse Garak JSONL output. Returns one finding per failed attempt."""
    findings = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("passed", True):
            continue
        probe_class = record.get("probe", "unknown")
        findings.append({
            "scanner": "garak",
            "severity": _probe_severity(probe_class),
            "category": _probe_category(probe_class),
            "title": f"Garak probe failed: {probe_class}",
            "description": (
                f"The probe '{probe_class}' triggered a failure. "
                f"The model may be susceptible to {_probe_category(probe_class).replace('_', ' ')}."
            ),
            "evidence": {
                "probe": probe_class,
                "passed": False,
                "notes": record.get("notes", {}),
                "attempt_idx": record.get("attempt_idx"),
            },
            "remediation": (
                "Review the model's system prompt and add guardrail rules to block "
                f"{_probe_category(probe_class).replace('_', ' ')} patterns."
            ),
        })
    return findings
```

- [ ] **Step 4: Implement Nuclei parser**

```python
# services/scanner/app/worker/parsers/nuclei.py
_NUCLEI_SEVERITY_MAP = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "info": "info",
    "unknown": "info",
}


def parse_nuclei_json(records: list[dict]) -> list[dict]:
    """Parse Nuclei JSON output (list of finding objects)."""
    findings = []
    for r in records:
        info = r.get("info", {})
        severity = _NUCLEI_SEVERITY_MAP.get(info.get("severity", "").lower(), "info")
        findings.append({
            "scanner": "nuclei",
            "severity": severity,
            "category": "api_vuln",
            "title": info.get("name", r.get("template-id", "Unknown finding")),
            "description": info.get("description", "No description available."),
            "evidence": {
                "template_id": r.get("template-id"),
                "matched_at": r.get("matched-at"),
                "host": r.get("host"),
                "type": r.get("type"),
            },
            "remediation": info.get("remediation") or "Apply the fix described in the CVE or template documentation.",
        })
    return findings
```

- [ ] **Step 5: Implement Nmap parser**

```python
# services/scanner/app/worker/parsers/nmap.py
import xml.etree.ElementTree as ET

# Ports that are expected on internal infrastructure — classified as info, not a finding
_EXPECTED_INTERNAL_PORTS = {22, 80, 443, 8080, 8443, 8000, 8001, 8002, 8003, 8004,
                             8005, 8006, 8007, 8008, 8009, 8010, 8011, 3000, 3001, 3002}

_PORT_SEVERITY = {
    21: "high",    # FTP — plaintext
    23: "high",    # Telnet — plaintext
    25: "medium",  # SMTP
    110: "medium", # POP3
    143: "medium", # IMAP
    3306: "high",  # MySQL exposed
    5432: "high",  # Postgres exposed
    6379: "high",  # Redis exposed
    27017: "high", # MongoDB exposed
}


def parse_nmap_xml(xml_output: str) -> list[dict]:
    """Parse Nmap XML output. Returns one finding per open port."""
    findings = []
    try:
        root = ET.fromstring(xml_output)
    except ET.ParseError:
        return findings

    for host in root.findall("host"):
        ports_elem = host.find("ports")
        if ports_elem is None:
            continue
        for port_elem in ports_elem.findall("port"):
            state = port_elem.find("state")
            if state is None or state.get("state") != "open":
                continue
            port_num = int(port_elem.get("portid", 0))
            service = port_elem.find("service")
            service_name = service.get("name", "unknown") if service is not None else "unknown"
            service_product = service.get("product", "") if service is not None else ""
            service_version = service.get("version", "") if service is not None else ""

            severity = _PORT_SEVERITY.get(port_num, "info" if port_num in _EXPECTED_INTERNAL_PORTS else "low")
            findings.append({
                "scanner": "nmap",
                "severity": severity,
                "category": "open_port",
                "title": f"Open port {port_num}/{port_elem.get('protocol', 'tcp')}: {service_name}",
                "description": (
                    f"Port {port_num} is open and running {service_product} {service_version}".strip()
                    or f"Port {port_num} is open."
                ),
                "evidence": {
                    "port": port_num,
                    "protocol": port_elem.get("protocol", "tcp"),
                    "service": service_name,
                    "product": service_product,
                    "version": service_version,
                },
                "remediation": (
                    "Ensure this port is intentionally exposed. "
                    "If not needed externally, restrict access via firewall rules."
                ) if severity != "info" else "Port appears expected for this service type.",
            })
    return findings
```

- [ ] **Step 6: Create `__init__.py` stubs**

```python
# services/scanner/app/worker/__init__.py
# (empty)
```

```python
# services/scanner/app/worker/parsers/__init__.py
# (empty)
```

- [ ] **Step 7: Run all parser tests**

```bash
cd services/scanner && pytest tests/test_parsers.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add services/scanner/app/worker/ services/scanner/tests/test_parsers.py
git commit -m "feat(scanner): add Garak, Nuclei, and Nmap output parsers"
```

---

## Task 7: Scanner Worker — Docker Runner

**Files:**
- Create: `services/scanner/app/worker/runner.py`
- Create: `services/scanner/docker/Dockerfile.garak`

- [ ] **Step 1: Create the Garak Docker image**

```dockerfile
# services/scanner/docker/Dockerfile.garak
FROM python:3.12-slim
RUN pip install --no-cache-dir garak==0.15.0
ENTRYPOINT ["python", "-m", "garak"]
```

- [ ] **Step 2: Create the worker runner**

```python
# services/scanner/app/worker/runner.py
"""Redis queue worker — polls for jobs and executes scan containers."""
import asyncio
import json
import logging
import os
import socket
import time
import uuid
from typing import Any

import docker
import httpx

from app.config import settings
from app.worker.parsers.garak import parse_garak_jsonl
from app.worker.parsers.nuclei import parse_nuclei_json
from app.worker.parsers.nmap import parse_nmap_xml

log = logging.getLogger(__name__)
WORKER_ID = f"{socket.gethostname()}-{os.getpid()}"

_TIER_NMAP_ARGS = {
    "quick": ["--top-ports", "100", "-T4"],
    "standard": ["--top-ports", "1000", "-T4", "-sV"],
    "deep": ["-p-", "-T4", "-sV", "-sC"],
}
_TIER_NUCLEI_TEMPLATES = {
    "quick": ["http/technologies"],
    "standard": ["http/vulnerabilities", "http/misconfiguration", "http/exposures"],
    "deep": ["http/vulnerabilities", "http/misconfiguration", "http/exposures",
             "http/cves", "http/takeovers", "network"],
}
_TIER_GARAK_PROBES = {
    "quick": ["promptinjection.HijackHateHumans", "promptinjection.HijackKillHumans",
              "leakage.SnapshotData", "jailbreak.Dan", "toxicity.ToxicCommentModel"],
    "standard": ["promptinjection", "jailbreak", "leakage", "xss", "toxicity"],
    "deep": [],  # empty = all probes
}

_docker_client: docker.DockerClient | None = None


def _docker() -> docker.DockerClient:
    global _docker_client
    if _docker_client is None:
        _docker_client = docker.from_env()
    return _docker_client


async def _post_internal(path: str, payload: Any) -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        await client.post(
            f"http://localhost:8011{path}",
            json=payload,
            headers={"Authorization": f"Bearer {settings.scanner_worker_secret}"},
        )


def _run_container(image: str, command: list[str], timeout: int = settings.max_container_timeout_seconds) -> str:
    """Run a Docker container synchronously. Returns combined stdout output."""
    container = _docker().containers.run(
        image,
        command=command,
        detach=True,
        remove=False,
        network="ai-gw_default",
    )
    try:
        container.wait(timeout=timeout)
        output = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
    except Exception as exc:
        log.warning("Container %s timed out or failed: %s", container.id, exc)
        container.kill()
        output = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
    finally:
        container.remove(force=True)
    return output


async def _run_nmap(job_id: str, target_url: str, tier: str) -> None:
    from urllib.parse import urlparse
    host = urlparse(target_url).hostname or target_url
    args = _TIER_NMAP_ARGS.get(tier, _TIER_NMAP_ARGS["quick"])
    command = ["-oX", "-"] + args + [host]
    log.info("Running nmap for job %s: nmap %s", job_id, " ".join(command))
    xml_output = await asyncio.to_thread(_run_container, "instrumentisto/nmap", command)
    findings = parse_nmap_xml(xml_output)
    if findings:
        await _post_internal(f"/internal/jobs/{job_id}/findings", {"findings": findings})


async def _run_nuclei(job_id: str, target_url: str, tier: str) -> None:
    templates = _TIER_NUCLEI_TEMPLATES.get(tier, _TIER_NUCLEI_TEMPLATES["quick"])
    template_args = []
    for t in templates:
        template_args += ["-t", t]
    command = ["-u", target_url, "-json"] + template_args + ["-silent", "-no-color"]
    log.info("Running nuclei for job %s", job_id)
    raw_output = await asyncio.to_thread(
        _run_container, "projectdiscovery/nuclei", command
    )
    records = []
    for line in raw_output.splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    findings = parse_nuclei_json(records)
    if findings:
        await _post_internal(f"/internal/jobs/{job_id}/findings", {"findings": findings})


async def _run_zap(job_id: str, target_url: str, openapi_spec_url: str) -> None:
    """Run ZAP API scan. Only called on deep tier when an OpenAPI spec URL is registered."""
    command = ["zap-api-scan.py", "-t", openapi_spec_url, "-f", "openapi",
               "-J", "/zap/results.json", "-I"]
    log.info("Running ZAP for job %s against spec %s", job_id, openapi_spec_url)
    await asyncio.to_thread(_run_container, "zaproxy/zap-stable", command)
    # ZAP writes JSON to /zap/results.json inside the container; use -J flag output via logs
    # For simplicity parse from container logs (ZAP -J flag outputs to stdout in this mode)
    # In production, mount a shared volume and read the file directly
    # This basic integration records a single informational finding; detailed parsing is v2
    findings = [{
        "scanner": "zap",
        "severity": "info",
        "category": "api_vuln",
        "title": "ZAP API scan completed",
        "description": f"ZAP deep API scan ran against OpenAPI spec at {openapi_spec_url}. Review the SARIF output for detailed findings.",
        "evidence": {"spec_url": openapi_spec_url},
        "remediation": None,
    }]
    await _post_internal(f"/internal/jobs/{job_id}/findings", {"findings": findings})


async def _run_garak(job_id: str, target_url: str, tier: str) -> None:
    probes = _TIER_GARAK_PROBES.get(tier, _TIER_GARAK_PROBES["quick"])
    probe_args = []
    for p in probes:
        probe_args += ["--probe", p]
    command = [
        "--model_type", "rest",
        "--model_name", target_url,
        "--report_prefix", "/tmp/garak_out",
        "--parallel_requests", "1",
    ] + probe_args
    log.info("Running garak for job %s", job_id)
    raw_output = await asyncio.to_thread(
        _run_container, "ai-gateway/garak:latest", command
    )
    findings = parse_garak_jsonl(raw_output)
    if findings:
        await _post_internal(f"/internal/jobs/{job_id}/findings", {"findings": findings})


async def process_job(job_payload: dict) -> None:
    job_id = job_payload["job_id"]
    target_url = job_payload["target_url"]
    scan_types = job_payload.get("scan_types", ["ai", "api", "network"])
    tier = job_payload.get("tier", "quick")

    await _post_internal(f"/internal/jobs/{job_id}/progress", {"worker_id": WORKER_ID})

    tasks = []
    if "network" in scan_types or "api" in scan_types:
        tasks.append(_run_nmap(job_id, target_url, tier))
    if "api" in scan_types:
        tasks.append(_run_nuclei(job_id, target_url, tier))
    if "api" in scan_types and tier == "deep" and job_payload.get("openapi_spec_url"):
        tasks.append(_run_zap(job_id, target_url, job_payload["openapi_spec_url"]))

    partial = False
    try:
        await asyncio.gather(*tasks)
        # Garak after Nmap (sequential — uses open port info conceptually)
        if "ai" in scan_types:
            await _run_garak(job_id, target_url, tier)
        status = "completed"
    except asyncio.TimeoutError:
        partial = True
        status = "completed"
    except Exception as exc:
        log.error("Job %s failed: %s", job_id, exc)
        await _post_internal(f"/internal/jobs/{job_id}/complete", {
            "status": "failed",
            "error_message": str(exc),
            "partial_results": False,
        })
        return

    await _post_internal(f"/internal/jobs/{job_id}/complete", {
        "status": status,
        "error_message": None,
        "partial_results": partial,
    })


async def run_worker(redis) -> None:
    """Block on Redis queue and process jobs."""
    log.info("Scanner worker %s started", WORKER_ID)
    while True:
        try:
            item = await redis.brpop(settings.scan_job_queue_key, timeout=5)
            if item is None:
                continue
            _, raw = item
            payload = json.loads(raw)
            asyncio.create_task(process_job(payload))
        except Exception as exc:
            log.error("Worker error: %s", exc)
            await asyncio.sleep(2)
```

- [ ] **Step 3: Start the worker from main.py lifespan**

Edit `services/scanner/app/main.py`, replace the lifespan function:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = make_redis(settings.redis_url)
    from app.worker.runner import run_worker
    worker_task = asyncio.create_task(run_worker(app.state.redis))
    yield
    worker_task.cancel()
    await app.state.redis.aclose()
```

- [ ] **Step 4: Build the Garak image**

```bash
docker build -f services/scanner/docker/Dockerfile.garak -t ai-gateway/garak:latest .
```

Expected: Image builds and `docker images | grep garak` shows the image.

- [ ] **Step 5: Commit**

```bash
git add services/scanner/app/worker/runner.py \
        services/scanner/app/main.py \
        services/scanner/docker/Dockerfile.garak
git commit -m "feat(scanner): add Docker-based scan worker with Garak/Nuclei/Nmap runners"
```

---

## Task 8: Docker Compose and Nginx

**Files:**
- Modify: `infra/docker-compose.yml`
- Modify: `infra/nginx/default.conf`

- [ ] **Step 1: Add scanner service to docker-compose.yml**

Find the `league:` service block and add the scanner service after it:

```yaml
  scanner:
    build:
      context: ../services/scanner
    ports:
      - "127.0.0.1:8011:8011"
    env_file: ../.env
    environment:
      ENVIRONMENT: development
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    extra_hosts:
      - "host.docker.internal:host-gateway"
    depends_on:
      db-migrate:
        condition: service_completed_successfully
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "python3 -c \"import urllib.request; urllib.request.urlopen('http://localhost:8011/health')\" 2>/dev/null || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 10
```

- [ ] **Step 2: Add nginx location block**

In `infra/nginx/default.conf`, add the following block alongside the other service location blocks (e.g., after the `league` block):

```nginx
    location /scanner/ {
        set $upstream http://scanner:8011;
        rewrite ^/scanner/(.*)$ /$1 break;
        proxy_pass             $upstream;
        proxy_set_header       Host              $host;
        proxy_set_header       X-Real-IP         $remote_addr;
        proxy_set_header       X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header       X-Forwarded-Proto $scheme;
        # Block internal worker endpoints from being called externally
        location ~ ^/scanner/internal/ {
            return 403;
        }
    }
```

- [ ] **Step 3: Start the stack and verify**

```bash
docker compose -f infra/docker-compose.yml up --build scanner
curl http://localhost:8080/scanner/health
```

Expected: `{"status":"ok"}`

Also verify internal routes are blocked:
```bash
curl -I http://localhost:8080/scanner/internal/jobs/test/complete
```
Expected: `HTTP/1.1 403 Forbidden`

- [ ] **Step 4: Commit**

```bash
git add infra/docker-compose.yml infra/nginx/default.conf
git commit -m "feat(scanner): wire scanner service into Docker Compose and nginx"
```

---

## Task 9: Admin Portal — Security Section

**Files:**
- Create: `apps/admin/app/admin/security/page.tsx`
- Create: `apps/admin/app/admin/security/targets/page.tsx`
- Create: `apps/admin/app/admin/security/jobs/page.tsx`
- Create: `apps/admin/app/admin/security/quotas/page.tsx`

- [ ] **Step 1: Create the root page (redirect to targets)**

```tsx
// apps/admin/app/admin/security/page.tsx
import { redirect } from 'next/navigation';

export default function SecurityPage() {
  redirect('/admin/security/targets');
}
```

- [ ] **Step 2: Create the targets approval page**

```tsx
// apps/admin/app/admin/security/targets/page.tsx
'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const ADMIN_API = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

interface ScanTarget {
  id: string;
  team_id: string;
  url: string;
  label: string;
  status: 'pending_approval' | 'approved' | 'revoked';
  allowed_scan_types: string[];
  openapi_spec_url: string | null;
  created_at: string;
  notes: string | null;
}

const ALL_SCAN_TYPES = ['ai', 'api', 'network'];

export default function TargetsPage() {
  const qc = useQueryClient();
  const [selectedTypes, setSelectedTypes] = useState<Record<string, string[]>>({});
  const [filter, setFilter] = useState<'pending_approval' | 'approved' | 'revoked' | ''>('pending_approval');

  const { data: targets = [], isLoading } = useQuery<ScanTarget[]>({
    queryKey: ['admin-scanner-targets', filter],
    queryFn: () =>
      fetch(`${ADMIN_API}/scanner/targets${filter ? `?status=${filter}` : ''}`).then(r => r.json()),
    refetchInterval: 10_000,
  });

  const approve = useMutation({
    mutationFn: ({ id, types }: { id: string; types: string[] }) =>
      fetch(`${ADMIN_API}/scanner/targets/${id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ allowed_scan_types: types }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-scanner-targets'] }),
  });

  const revoke = useMutation({
    mutationFn: (id: string) =>
      fetch(`${ADMIN_API}/scanner/targets/${id}/revoke`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-scanner-targets'] }),
  });

  const getTypes = (id: string, defaults: string[]) =>
    selectedTypes[id] ?? defaults;

  const toggleType = (id: string, defaults: string[], type: string) => {
    const current = getTypes(id, defaults);
    setSelectedTypes(prev => ({
      ...prev,
      [id]: current.includes(type) ? current.filter(t => t !== type) : [...current, type],
    }));
  };

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold mb-4">Scanner — Targets</h1>

      <div className="flex gap-2 mb-4">
        {(['pending_approval', 'approved', 'revoked', ''] as const).map(s => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`px-3 py-1 rounded text-sm ${filter === s ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700'}`}
          >
            {s || 'All'}
          </button>
        ))}
      </div>

      {isLoading && <p className="text-gray-500">Loading…</p>}

      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-left bg-gray-50">
            <th className="p-3 border">Label / URL</th>
            <th className="p-3 border">Team</th>
            <th className="p-3 border">Status</th>
            <th className="p-3 border">Scan Types</th>
            <th className="p-3 border">Actions</th>
          </tr>
        </thead>
        <tbody>
          {targets.map(t => (
            <tr key={t.id} className="border-b hover:bg-gray-50">
              <td className="p-3 border">
                <div className="font-medium">{t.label}</div>
                <div className="text-gray-500 truncate max-w-xs">{t.url}</div>
              </td>
              <td className="p-3 border text-gray-600 font-mono text-xs">{t.team_id}</td>
              <td className="p-3 border">
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                  t.status === 'approved' ? 'bg-green-100 text-green-800' :
                  t.status === 'pending_approval' ? 'bg-yellow-100 text-yellow-800' :
                  'bg-red-100 text-red-800'
                }`}>
                  {t.status}
                </span>
              </td>
              <td className="p-3 border">
                <div className="flex gap-1">
                  {ALL_SCAN_TYPES.map(type => (
                    <label key={type} className="flex items-center gap-1 text-xs">
                      <input
                        type="checkbox"
                        checked={getTypes(t.id, t.allowed_scan_types).includes(type)}
                        onChange={() => toggleType(t.id, t.allowed_scan_types, type)}
                      />
                      {type}
                    </label>
                  ))}
                </div>
              </td>
              <td className="p-3 border">
                <div className="flex gap-2">
                  {t.status !== 'approved' && (
                    <button
                      onClick={() => approve.mutate({ id: t.id, types: getTypes(t.id, t.allowed_scan_types) })}
                      className="px-2 py-1 bg-green-600 text-white rounded text-xs"
                    >
                      Approve
                    </button>
                  )}
                  {t.status === 'approved' && (
                    <button
                      onClick={() => revoke.mutate(t.id)}
                      className="px-2 py-1 bg-red-600 text-white rounded text-xs"
                    >
                      Revoke
                    </button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 3: Create the jobs monitoring page**

```tsx
// apps/admin/app/admin/security/jobs/page.tsx
'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const SCANNER_API = process.env.NEXT_PUBLIC_SCANNER_API ?? 'http://localhost:8011';

interface ScanJob {
  id: string;
  team_id: string;
  target_id: string;
  tier: string;
  status: string;
  trigger: string;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  partial_results: boolean;
}

function duration(job: ScanJob): string {
  if (!job.started_at) return '—';
  const end = job.finished_at ? new Date(job.finished_at) : new Date();
  const secs = Math.floor((end.getTime() - new Date(job.started_at).getTime()) / 1000);
  return secs < 60 ? `${secs}s` : `${Math.floor(secs / 60)}m ${secs % 60}s`;
}

export default function JobsPage() {
  const qc = useQueryClient();

  const { data: jobs = [], isLoading } = useQuery<ScanJob[]>({
    queryKey: ['admin-scanner-jobs'],
    queryFn: () => fetch(`${SCANNER_API}/jobs?limit=50`).then(r => r.json()),
    refetchInterval: 5_000,
  });

  const cancel = useMutation({
    mutationFn: (id: string) => fetch(`${SCANNER_API}/jobs/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-scanner-jobs'] }),
  });

  const STATUS_COLOR: Record<string, string> = {
    queued: 'bg-gray-100 text-gray-700',
    running: 'bg-blue-100 text-blue-700',
    completed: 'bg-green-100 text-green-700',
    failed: 'bg-red-100 text-red-700',
    cancelled: 'bg-gray-200 text-gray-500',
  };

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold mb-4">Scanner — All Jobs</h1>
      {isLoading && <p className="text-gray-500">Loading…</p>}
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-left bg-gray-50">
            <th className="p-3 border">Job ID</th>
            <th className="p-3 border">Team</th>
            <th className="p-3 border">Tier</th>
            <th className="p-3 border">Status</th>
            <th className="p-3 border">Trigger</th>
            <th className="p-3 border">Duration</th>
            <th className="p-3 border">Actions</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map(j => (
            <tr key={j.id} className="border-b hover:bg-gray-50">
              <td className="p-3 border font-mono text-xs">{j.id.slice(0, 8)}…</td>
              <td className="p-3 border font-mono text-xs">{j.team_id.slice(0, 8)}…</td>
              <td className="p-3 border">{j.tier}</td>
              <td className="p-3 border">
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLOR[j.status] ?? 'bg-gray-100'}`}>
                  {j.status}{j.partial_results ? ' (partial)' : ''}
                </span>
              </td>
              <td className="p-3 border text-gray-600">{j.trigger}</td>
              <td className="p-3 border">{duration(j)}</td>
              <td className="p-3 border">
                {['queued', 'running'].includes(j.status) && (
                  <button
                    onClick={() => cancel.mutate(j.id)}
                    className="px-2 py-1 bg-red-600 text-white rounded text-xs"
                  >
                    Cancel
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: Create the quotas management page**

```tsx
// apps/admin/app/admin/security/quotas/page.tsx
'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const ADMIN_API = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

interface TeamQuota {
  id: string;
  name: string;
  scanner_quota: {
    daily_limit: number;
    allow_external_targets: boolean;
    max_tier: 'quick' | 'standard' | 'deep';
  };
}

export default function QuotasPage() {
  const qc = useQueryClient();
  const [killSwitchPending, setKillSwitchPending] = useState(false);

  const { data: teams = [] } = useQuery<TeamQuota[]>({
    queryKey: ['admin-scanner-quotas'],
    queryFn: () => fetch(`${ADMIN_API}/scanner/quotas`).then(r => r.json()),
  });

  const updateQuota = useMutation({
    mutationFn: ({ teamId, patch }: { teamId: string; patch: Partial<TeamQuota['scanner_quota']> }) =>
      fetch(`${ADMIN_API}/scanner/quotas/${teamId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-scanner-quotas'] }),
  });

  const toggleKillSwitch = async (enable: boolean) => {
    setKillSwitchPending(true);
    await fetch(`${ADMIN_API}/scanner/kill-switch?enabled=${enable}`, { method: 'POST' });
    setKillSwitchPending(false);
  };

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold">Scanner — Team Quotas</h1>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-600">Global kill switch:</span>
          <button
            disabled={killSwitchPending}
            onClick={() => toggleKillSwitch(true)}
            className="px-3 py-1 bg-red-600 text-white rounded text-sm disabled:opacity-50"
          >
            Disable scanning
          </button>
          <button
            disabled={killSwitchPending}
            onClick={() => toggleKillSwitch(false)}
            className="px-3 py-1 bg-green-600 text-white rounded text-sm disabled:opacity-50"
          >
            Enable scanning
          </button>
        </div>
      </div>

      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-left bg-gray-50">
            <th className="p-3 border">Team</th>
            <th className="p-3 border">Daily limit</th>
            <th className="p-3 border">Max tier</th>
            <th className="p-3 border">External targets</th>
          </tr>
        </thead>
        <tbody>
          {teams.map(t => (
            <tr key={t.id} className="border-b hover:bg-gray-50">
              <td className="p-3 border font-medium">{t.name}</td>
              <td className="p-3 border">
                <input
                  type="number"
                  min={1}
                  max={50}
                  defaultValue={t.scanner_quota.daily_limit}
                  className="w-16 border rounded px-2 py-1 text-sm"
                  onBlur={e => updateQuota.mutate({
                    teamId: t.id,
                    patch: { daily_limit: parseInt(e.target.value, 10) },
                  })}
                />
              </td>
              <td className="p-3 border">
                <select
                  defaultValue={t.scanner_quota.max_tier}
                  className="border rounded px-2 py-1 text-sm"
                  onChange={e => updateQuota.mutate({
                    teamId: t.id,
                    patch: { max_tier: e.target.value as 'quick' | 'standard' | 'deep' },
                  })}
                >
                  <option value="quick">quick</option>
                  <option value="standard">standard</option>
                  <option value="deep">deep</option>
                </select>
              </td>
              <td className="p-3 border">
                <input
                  type="checkbox"
                  defaultChecked={t.scanner_quota.allow_external_targets}
                  onChange={e => updateQuota.mutate({
                    teamId: t.id,
                    patch: { allow_external_targets: e.target.checked },
                  })}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add apps/admin/app/admin/security/
git commit -m "feat(scanner): add admin portal security section (targets, jobs, quotas)"
```

---

## Task 10: Developer Portal — Security Section

**Files:**
- Create: `apps/portal/app/portal/security/page.tsx`
- Create: `apps/portal/app/portal/security/targets/page.tsx`
- Create: `apps/portal/app/portal/security/scans/page.tsx`
- Create: `apps/portal/app/portal/security/scans/[jobId]/page.tsx`

- [ ] **Step 1: Create the root page**

```tsx
// apps/portal/app/portal/security/page.tsx
import { redirect } from 'next/navigation';

export default function SecurityPage() {
  redirect('/portal/security/scans');
}
```

- [ ] **Step 2: Create the targets registration page**

```tsx
// apps/portal/app/portal/security/targets/page.tsx
'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const ADMIN_API = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

interface ScanTarget {
  id: string;
  url: string;
  label: string;
  status: 'pending_approval' | 'approved' | 'revoked';
  allowed_scan_types: string[];
  openapi_spec_url: string | null;
  created_at: string;
}

export default function TargetsPage() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    url: '', label: '', openapi_spec_url: '',
    scan_types: ['ai', 'api', 'network'],
  });

  // In a real app, team_id and user_id come from the session
  const TEAM_ID = process.env.NEXT_PUBLIC_TEAM_ID ?? '';
  const USER_ID = process.env.NEXT_PUBLIC_USER_ID ?? '';

  const { data: targets = [] } = useQuery<ScanTarget[]>({
    queryKey: ['portal-scanner-targets', TEAM_ID],
    queryFn: () =>
      fetch(`${ADMIN_API}/scanner/targets?team_id=${TEAM_ID}`).then(r => r.json()),
    refetchInterval: 15_000,
  });

  const register = useMutation({
    mutationFn: (body: typeof form & { team_id: string; created_by: string }) =>
      fetch(`${ADMIN_API}/scanner/targets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: body.url,
          label: body.label,
          openapi_spec_url: body.openapi_spec_url || null,
          requested_scan_types: body.scan_types,
          team_id: body.team_id,
          created_by: body.created_by,
        }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portal-scanner-targets'] });
      setShowForm(false);
      setForm({ url: '', label: '', openapi_spec_url: '', scan_types: ['ai', 'api', 'network'] });
    },
  });

  const STATUS_COLOR: Record<string, string> = {
    pending_approval: 'bg-yellow-100 text-yellow-800',
    approved: 'bg-green-100 text-green-800',
    revoked: 'bg-red-100 text-red-800',
  };

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-semibold">Security — Targets</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-4 py-2 bg-blue-600 text-white rounded text-sm"
        >
          + Register target
        </button>
      </div>

      {showForm && (
        <div className="border rounded p-4 mb-4 bg-gray-50">
          <h2 className="font-medium mb-3">Register new target</h2>
          <div className="grid grid-cols-2 gap-3">
            <input
              placeholder="Label (e.g. My AI Service)"
              value={form.label}
              onChange={e => setForm(f => ({ ...f, label: e.target.value }))}
              className="border rounded px-3 py-2 text-sm"
            />
            <input
              placeholder="URL (e.g. https://myapp.simcorp.internal)"
              value={form.url}
              onChange={e => setForm(f => ({ ...f, url: e.target.value }))}
              className="border rounded px-3 py-2 text-sm"
            />
            <input
              placeholder="OpenAPI spec URL (optional — enables deep API scan)"
              value={form.openapi_spec_url}
              onChange={e => setForm(f => ({ ...f, openapi_spec_url: e.target.value }))}
              className="border rounded px-3 py-2 text-sm col-span-2"
            />
            <div className="col-span-2 flex gap-3">
              {['ai', 'api', 'network'].map(type => (
                <label key={type} className="flex items-center gap-1 text-sm">
                  <input
                    type="checkbox"
                    checked={form.scan_types.includes(type)}
                    onChange={e => setForm(f => ({
                      ...f,
                      scan_types: e.target.checked
                        ? [...f.scan_types, type]
                        : f.scan_types.filter(t => t !== type),
                    }))}
                  />
                  {type} scanning
                </label>
              ))}
            </div>
          </div>
          <div className="flex gap-2 mt-3">
            <button
              onClick={() => register.mutate({ ...form, team_id: TEAM_ID, created_by: USER_ID })}
              disabled={!form.url || !form.label}
              className="px-4 py-2 bg-blue-600 text-white rounded text-sm disabled:opacity-50"
            >
              Submit for approval
            </button>
            <button onClick={() => setShowForm(false)} className="px-4 py-2 bg-gray-200 rounded text-sm">
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="grid gap-3">
        {targets.map(t => (
          <div key={t.id} className="border rounded p-4 flex items-start justify-between">
            <div>
              <div className="font-medium">{t.label}</div>
              <div className="text-gray-500 text-sm">{t.url}</div>
              <div className="text-gray-400 text-xs mt-1">
                Types: {t.allowed_scan_types.join(', ')}
              </div>
            </div>
            <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLOR[t.status]}`}>
              {t.status}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create the scans page**

```tsx
// apps/portal/app/portal/security/scans/page.tsx
'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';

const ADMIN_API = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';
const SCANNER_API = process.env.NEXT_PUBLIC_SCANNER_API ?? 'http://localhost:8011';

interface ScanTarget {
  id: string;
  label: string;
  url: string;
  status: string;
  allowed_scan_types: string[];
}
interface ScanJob {
  id: string;
  target_id: string;
  tier: string;
  status: string;
  queued_at: string;
  finished_at: string | null;
  partial_results: boolean;
}

const TEAM_ID = process.env.NEXT_PUBLIC_TEAM_ID ?? '';
const STATUS_COLOR: Record<string, string> = {
  queued: 'bg-gray-100 text-gray-700',
  running: 'bg-blue-100 text-blue-700',
  completed: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
  cancelled: 'bg-gray-200 text-gray-500',
};

export default function ScansPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [selectedTarget, setSelectedTarget] = useState('');
  const [selectedTier, setSelectedTier] = useState('quick');

  const { data: targets = [] } = useQuery<ScanTarget[]>({
    queryKey: ['portal-scanner-targets', TEAM_ID],
    queryFn: () =>
      fetch(`${ADMIN_API}/scanner/targets?team_id=${TEAM_ID}&status=approved`).then(r => r.json()),
  });

  const { data: jobs = [] } = useQuery<ScanJob[]>({
    queryKey: ['portal-scanner-jobs'],
    queryFn: () =>
      fetch(`${SCANNER_API}/jobs`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('api_key') ?? ''}` },
      }).then(r => r.json()),
    refetchInterval: 3_000,
  });

  const submit = useMutation({
    mutationFn: () =>
      fetch(`${SCANNER_API}/jobs`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('api_key') ?? ''}`,
        },
        body: JSON.stringify({ target_id: selectedTarget, tier: selectedTier }),
      }).then(r => r.json()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portal-scanner-jobs'] });
      setShowForm(false);
    },
  });

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-semibold">Security — Scans</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-4 py-2 bg-blue-600 text-white rounded text-sm"
        >
          + Run scan
        </button>
      </div>

      {showForm && (
        <div className="border rounded p-4 mb-4 bg-gray-50">
          <h2 className="font-medium mb-3">New scan</h2>
          <div className="flex gap-3 items-end">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Target</label>
              <select
                value={selectedTarget}
                onChange={e => setSelectedTarget(e.target.value)}
                className="border rounded px-3 py-2 text-sm"
              >
                <option value="">Select target…</option>
                {targets.map(t => (
                  <option key={t.id} value={t.id}>{t.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Tier</label>
              <select
                value={selectedTier}
                onChange={e => setSelectedTier(e.target.value)}
                className="border rounded px-3 py-2 text-sm"
              >
                <option value="quick">Quick (~5 min)</option>
                <option value="standard">Standard (~15 min)</option>
                <option value="deep">Deep (~45 min)</option>
              </select>
            </div>
            <button
              onClick={() => submit.mutate()}
              disabled={!selectedTarget}
              className="px-4 py-2 bg-blue-600 text-white rounded text-sm disabled:opacity-50"
            >
              Start scan
            </button>
            <button onClick={() => setShowForm(false)} className="px-4 py-2 bg-gray-200 rounded text-sm">
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="grid gap-3">
        {jobs.map(j => (
          <div
            key={j.id}
            onClick={() => j.status === 'completed' && router.push(`/portal/security/scans/${j.id}`)}
            className={`border rounded p-4 flex items-center justify-between ${j.status === 'completed' ? 'cursor-pointer hover:bg-gray-50' : ''}`}
          >
            <div>
              <div className="font-mono text-sm text-gray-600">{j.id.slice(0, 8)}…</div>
              <div className="text-xs text-gray-400 mt-0.5">
                {j.tier} · {new Date(j.queued_at).toLocaleString()}
              </div>
            </div>
            <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLOR[j.status] ?? 'bg-gray-100'}`}>
              {j.status}{j.partial_results ? ' (partial)' : ''}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create the results view**

```tsx
// apps/portal/app/portal/security/scans/[jobId]/page.tsx
'use client';

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'next/navigation';

const SCANNER_API = process.env.NEXT_PUBLIC_SCANNER_API ?? 'http://localhost:8011';

interface Finding {
  id: string;
  scanner: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  category: string;
  title: string;
  description: string;
  evidence: Record<string, unknown> | null;
  remediation: string | null;
}

interface ResultsResponse {
  total: number;
  findings: Finding[];
}

const SEVERITY_COLOR: Record<string, string> = {
  critical: 'bg-red-100 text-red-900 border-red-300',
  high: 'bg-orange-100 text-orange-900 border-orange-300',
  medium: 'bg-yellow-100 text-yellow-900 border-yellow-300',
  low: 'bg-blue-100 text-blue-900 border-blue-300',
  info: 'bg-gray-100 text-gray-700 border-gray-200',
};

const SEVERITY_ORDER = ['critical', 'high', 'medium', 'low', 'info'];

export default function ResultsPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const authHeader = { Authorization: `Bearer ${typeof window !== 'undefined' ? localStorage.getItem('api_key') ?? '' : ''}` };

  const { data, isLoading } = useQuery<ResultsResponse>({
    queryKey: ['scanner-results', jobId],
    queryFn: () =>
      fetch(`${SCANNER_API}/jobs/${jobId}/results?limit=200`, { headers: authHeader }).then(r => r.json()),
  });

  const findings = data?.findings ?? [];
  const counts = SEVERITY_ORDER.reduce((acc, sev) => ({
    ...acc,
    [sev]: findings.filter(f => f.severity === sev).length,
  }), {} as Record<string, number>);

  const downloadSarif = () => {
    window.open(`${SCANNER_API}/jobs/${jobId}/results?format=sarif`, '_blank');
  };

  const grouped = SEVERITY_ORDER.map(sev => ({
    severity: sev,
    items: findings.filter(f => f.severity === sev),
  })).filter(g => g.items.length > 0);

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-semibold">Scan Results</h1>
        <button
          onClick={downloadSarif}
          className="px-4 py-2 bg-gray-800 text-white rounded text-sm"
        >
          Download SARIF
        </button>
      </div>

      {isLoading && <p className="text-gray-500">Loading…</p>}

      <div className="flex gap-3 mb-6">
        {SEVERITY_ORDER.map(sev => counts[sev] > 0 && (
          <span key={sev} className={`px-3 py-1 rounded border text-sm font-medium ${SEVERITY_COLOR[sev]}`}>
            {counts[sev]} {sev}
          </span>
        ))}
        {findings.length === 0 && !isLoading && (
          <span className="text-green-700 bg-green-50 px-3 py-1 rounded border border-green-200 text-sm font-medium">
            No findings
          </span>
        )}
      </div>

      {grouped.map(({ severity, items }) => (
        <div key={severity} className="mb-6">
          <h2 className="font-semibold text-sm uppercase tracking-wide text-gray-500 mb-2">
            {severity} ({items.length})
          </h2>
          <div className="grid gap-3">
            {items.map(f => (
              <div key={f.id} className={`border rounded p-4 ${SEVERITY_COLOR[f.severity]}`}>
                <div className="flex items-start justify-between">
                  <div>
                    <div className="font-medium">{f.title}</div>
                    <div className="text-xs opacity-70 mt-0.5">{f.scanner} · {f.category}</div>
                  </div>
                </div>
                <p className="mt-2 text-sm">{f.description}</p>
                {f.remediation && (
                  <p className="mt-2 text-sm opacity-80">
                    <span className="font-medium">Remediation:</span> {f.remediation}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 5: Add NEXT_PUBLIC_SCANNER_API to portal env**

Add to `apps/portal/.env.local` (or `.env.example`):
```
NEXT_PUBLIC_SCANNER_API=http://localhost:8011
```

- [ ] **Step 6: Commit**

```bash
git add apps/portal/app/portal/security/
git commit -m "feat(scanner): add developer portal security section (targets, scans, results)"
```

---

## Task 11: End-to-End Smoke Test

- [ ] **Step 1: Start the full stack**

```bash
docker compose -f infra/docker-compose.yml up --build
```

Wait for all services healthy.

- [ ] **Step 2: Register a target via API**

```bash
curl -s -X POST http://localhost:8080/admin/scanner/targets \
  -H "Content-Type: application/json" \
  -d '{
    "url": "http://host.docker.internal:8011",
    "label": "Scanner self-test",
    "requested_scan_types": ["api", "network"],
    "team_id": "<a valid team uuid from your DB>",
    "created_by": "<a valid user uuid>"
  }' | jq .
```

Expected: `{"id": "...", "status": "pending_approval", ...}`

- [ ] **Step 3: Approve the target**

```bash
TARGET_ID="<id from previous step>"
curl -s -X POST "http://localhost:8080/admin/scanner/targets/${TARGET_ID}/approve" \
  -H "Content-Type: application/json" \
  -d '{"allowed_scan_types": ["api", "network"]}' | jq .
```

Expected: `{"status": "approved"}`

- [ ] **Step 4: Submit a scan job**

```bash
curl -s -X POST http://localhost:8080/scanner/jobs \
  -H "Authorization: Bearer <a valid team API key>" \
  -H "Content-Type: application/json" \
  -d "{\"target_id\": \"${TARGET_ID}\", \"tier\": \"quick\"}" | jq .
```

Expected: `{"job_id": "...", "status": "queued", "estimated_duration_minutes": 5}`

- [ ] **Step 5: Poll until complete**

```bash
JOB_ID="<id from previous step>"
watch -n3 "curl -s http://localhost:8080/scanner/jobs/${JOB_ID} -H 'Authorization: Bearer <key>' | jq .status"
```

Expected: `"queued"` → `"running"` → `"completed"` within ~5 minutes.

- [ ] **Step 6: Fetch results**

```bash
curl -s "http://localhost:8080/scanner/jobs/${JOB_ID}/results" \
  -H "Authorization: Bearer <key>" | jq '{total: .total, severities: [.findings[].severity] | group_by(.) | map({(.[0]): length}) | add}'
```

Expected: JSON with finding counts by severity.

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "feat(scanner): complete security scanner implementation"
```
