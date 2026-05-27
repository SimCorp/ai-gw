# AI-League Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `league` FastAPI service at port 8010, covering the DB schema, all API endpoints (seasons, challenges, submissions, scoring, leaderboard, store, points, proposals), and docker-compose wiring.

**Architecture:** New `services/league/` FastAPI service using the same async SQLAlchemy + asyncpg + alembic-via-admin pattern as other gateway services. League schema added as migration `0017` in `services/admin/migrations/versions/`. Service authenticates via shared Redis session lookup (same pattern as admin service).

**Tech Stack:** Python 3.12, FastAPI 0.111, SQLAlchemy 2.0 async, asyncpg, alembic (via admin service), httpx (litellm calls), redis[hiredis], pydantic-settings, pytest + pytest-asyncio + pytest-mock

> **Scope note:** This plan covers the backend service only. Portal UIs (admin portal league management, developer portal league section) are separate plans to follow once this service is deployed and tested.

---

## File Map

**New files — `services/league/`:**
- `Dockerfile` — service image
- `pyproject.toml` — dependencies + pytest config
- `app/__init__.py`
- `app/config.py` — pydantic-settings (DATABASE_URL, REDIS_URL, LITELLM_URL, etc.)
- `app/db.py` — async engine + `get_session` dependency + `Base`
- `app/auth.py` — `require_dev_auth`, `require_admin_auth` (Redis session lookup)
- `app/main.py` — FastAPI app, lifespan, CORS, router includes
- `app/scoring.py` — pure scoring functions (quality, robustness, tokens, speed, cost, improvement_rate, creativity, composite)
- `app/models/__init__.py`
- `app/models/season.py` — `Season` ORM model
- `app/models/challenge.py` — `Challenge` ORM model
- `app/models/submission.py` — `Submission` ORM model
- `app/models/score.py` — `Score` ORM model
- `app/models/leaderboard.py` — `LeaderboardEntry` ORM model
- `app/models/store.py` — `StoreItem`, `Purchase` ORM models
- `app/models/points.py` — `PointsLedger` ORM model
- `app/models/proposal.py` — `ChallengeProposal` ORM model
- `app/routers/__init__.py`
- `app/routers/seasons.py` — CRUD for seasons, weight config
- `app/routers/challenges.py` — CRUD for challenges (admin-gated)
- `app/routers/submissions.py` — submit agent, trigger execution + scoring
- `app/routers/leaderboard.py` — per-season rankings
- `app/routers/store.py` — item catalogue + purchase
- `app/routers/points.py` — points balance + ledger
- `app/routers/proposals.py` — community challenge proposals
- `tests/conftest.py` — pytest fixtures (mock Redis, mock litellm, in-memory DB)
- `tests/test_scoring.py` — unit tests for scoring engine
- `tests/test_seasons.py` — router tests for seasons
- `tests/test_challenges.py` — router tests for challenges
- `tests/test_submissions.py` — integration tests for submission pipeline
- `tests/test_leaderboard.py` — leaderboard tests
- `tests/test_store.py` — store + points tests

**New file — DB migration:**
- `services/admin/migrations/versions/0017_league_schema.py`

**Modified files:**
- `infra/docker-compose.yml` — add `league:` service entry
- `.env.example` — add `LEAGUE_*` env vars (if applicable)

---

## Task 1: DB Migration — League Schema

**Files:**
- Create: `services/admin/migrations/versions/0017_league_schema.py`

- [ ] **Step 1: Write the migration**

```python
# services/admin/migrations/versions/0017_league_schema.py
"""League schema — seasons, challenges, submissions, scores, leaderboard, store, points

Revision ID: 0017
Revises: 0016
"""
from alembic import op
from typing import Sequence, Union

revision = "0017"
down_revision = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS league_seasons (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name            TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'upcoming'
                            CHECK (status IN ('upcoming', 'active', 'closed')),
            starts_at       TIMESTAMPTZ NOT NULL,
            ends_at         TIMESTAMPTZ NOT NULL,
            scoring_weights JSONB NOT NULL DEFAULT '{"quality":0.35,"robustness":0.20,"token_efficiency":0.15,"speed":0.10,"cost_efficiency":0.10,"improvement_rate":0.05,"creativity":0.05}',
            season_multiplier NUMERIC(4,2) NOT NULL DEFAULT 1.0,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS league_challenges (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            season_id            UUID NOT NULL REFERENCES league_seasons(id) ON DELETE CASCADE,
            title                TEXT NOT NULL,
            goal                 TEXT NOT NULL,
            training_inputs      JSONB NOT NULL DEFAULT '[]',
            hidden_test_suite    JSONB NOT NULL DEFAULT '[]',
            allowed_models       TEXT[] NOT NULL DEFAULT ARRAY['claude-sonnet-4-6'],
            max_tokens_budget    INT NOT NULL DEFAULT 4096,
            max_league_attempts  INT NOT NULL DEFAULT 3,
            scores_revealed_at   TIMESTAMPTZ,
            status               TEXT NOT NULL DEFAULT 'draft'
                                 CHECK (status IN ('draft', 'active', 'closed')),
            proposed_by          UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_league_challenges_season ON league_challenges(season_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS league_submissions (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            challenge_id     UUID NOT NULL REFERENCES league_challenges(id) ON DELETE CASCADE,
            engineer_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            mode             TEXT NOT NULL CHECK (mode IN ('training', 'league')),
            system_prompt    TEXT NOT NULL,
            tool_config      JSONB NOT NULL DEFAULT '[]',
            attempt_number   INT NOT NULL DEFAULT 1,
            run_results      JSONB,
            prompt_hash      TEXT NOT NULL,
            submitted_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_league_submissions_challenge ON league_submissions(challenge_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_league_submissions_engineer ON league_submissions(engineer_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS league_scores (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            submission_id     UUID NOT NULL REFERENCES league_submissions(id) ON DELETE CASCADE,
            quality           NUMERIC(5,2) NOT NULL DEFAULT 0,
            robustness        NUMERIC(5,2) NOT NULL DEFAULT 0,
            token_efficiency  NUMERIC(5,2) NOT NULL DEFAULT 0,
            speed             NUMERIC(5,2) NOT NULL DEFAULT 0,
            cost_efficiency   NUMERIC(5,2) NOT NULL DEFAULT 0,
            improvement_rate  NUMERIC(5,2) NOT NULL DEFAULT 50,
            creativity        NUMERIC(5,2) NOT NULL DEFAULT 50,
            composite         NUMERIC(7,2) NOT NULL DEFAULT 0
        )
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_league_scores_submission ON league_scores(submission_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS league_leaderboard (
            season_id         UUID NOT NULL REFERENCES league_seasons(id) ON DELETE CASCADE,
            engineer_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            composite_score   NUMERIC(7,2) NOT NULL DEFAULT 0,
            rank              INT,
            points_earned     INT NOT NULL DEFAULT 0,
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (season_id, engineer_id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS league_points_ledger (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            engineer_id   UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            delta         INT NOT NULL,
            reason        TEXT NOT NULL CHECK (reason IN (
                              'league_submission_reward',
                              'training_xp_reward',
                              'store_purchase',
                              'admin_grant',
                              'season_exclusive_grant'
                          )),
            ref_id        UUID,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_league_points_engineer ON league_points_ledger(engineer_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS league_store_items (
            id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name                  TEXT NOT NULL,
            type                  TEXT NOT NULL CHECK (type IN ('badge', 'card_border', 'avatar_frame', 'title')),
            point_cost            INT NOT NULL DEFAULT 0,
            asset_url             TEXT NOT NULL DEFAULT '',
            exclusive_season_id   UUID REFERENCES league_seasons(id) ON DELETE SET NULL,
            exclusive_top_n       INT,
            active                BOOLEAN NOT NULL DEFAULT TRUE,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS league_purchases (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            engineer_id   UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            item_id       UUID NOT NULL REFERENCES league_store_items(id) ON DELETE CASCADE,
            purchased_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (engineer_id, item_id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS league_challenge_proposals (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            proposed_by    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title          TEXT NOT NULL,
            goal           TEXT NOT NULL,
            notes          TEXT NOT NULL DEFAULT '',
            status         TEXT NOT NULL DEFAULT 'proposed'
                           CHECK (status IN ('proposed', 'approved', 'rejected')),
            reviewed_by    UUID REFERENCES users(id) ON DELETE SET NULL,
            reviewer_notes TEXT NOT NULL DEFAULT '',
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade():
    for tbl in [
        "league_challenge_proposals",
        "league_purchases",
        "league_store_items",
        "league_points_ledger",
        "league_leaderboard",
        "league_scores",
        "league_submissions",
        "league_challenges",
        "league_seasons",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
```

- [ ] **Step 2: Verify migration parses cleanly**

```bash
cd /home/bntp/repos/ai-gw
python3 -c "import services.admin.migrations.versions.0017_league_schema" 2>/dev/null || \
  python3 -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('m', 'services/admin/migrations/versions/0017_league_schema.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print('upgrade OK:', bool(m.upgrade))
print('downgrade OK:', bool(m.downgrade))
print('revision:', m.revision)
print('down_revision:', m.down_revision)
"
```
Expected output:
```
upgrade OK: True
downgrade OK: True
revision: 0017
down_revision: 0016
```

- [ ] **Step 3: Commit**

```bash
git add services/admin/migrations/versions/0017_league_schema.py
git commit -m "feat(league): add league schema migration (0017)"
```

---

## Task 2: Service Scaffold

**Files:**
- Create: `services/league/Dockerfile`
- Create: `services/league/pyproject.toml`
- Create: `services/league/app/__init__.py`
- Create: `services/league/app/config.py`
- Create: `services/league/app/db.py`
- Create: `services/league/app/auth.py`
- Create: `services/league/app/main.py`

- [ ] **Step 1: Write Dockerfile**

```dockerfile
# services/league/Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .
COPY app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
```

- [ ] **Step 2: Write pyproject.toml**

```toml
# services/league/pyproject.toml
[project]
name = "ai-gateway-league"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi~=0.111",
    "uvicorn[standard]>=0.30",
    "pydantic-settings>=2.4",
    "sqlalchemy[asyncio]~=2.0",
    "asyncpg>=0.29",
    "httpx>=0.27",
    "redis[hiredis]>=5.0",
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

- [ ] **Step 3: Write `app/config.py`**

```python
# services/league/app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://aigateway:aigateway@localhost:5432/aigateway"
    redis_url: str = "redis://localhost:6379/0"
    dev_bypass_auth: bool = False
    admin_token: str = ""
    litellm_url: str = "http://litellm:8003"
    litellm_master_key: str = "sk-litellm-local-dev"
    cors_origins: list[str] = ["http://localhost:3001", "http://localhost:3002"]
    training_rate_limit_per_hour: int = 10


settings = Settings()
```

- [ ] **Step 4: Write `app/db.py`**

```python
# services/league/app/db.py
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

- [ ] **Step 5: Write `app/auth.py`**

```python
# services/league/app/auth.py
import json
import secrets

from fastapi import Depends, Header, HTTPException, Request

from app.config import settings


async def require_dev_auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict:
    """Validate developer session from shared Redis."""
    if settings.dev_bypass_auth:
        return {"user_id": "00000000-0000-0000-0000-000000000001", "email": "dev@simcorp.com"}

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization required")

    token = authorization.removeprefix("Bearer ").strip()
    redis = request.app.state.redis
    raw = await redis.get(f"session:{token}")
    if not raw:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    data = json.loads(raw)
    return {"user_id": data["user_id"], "email": data.get("email", "")}


async def require_admin_auth(
    request: Request,
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
) -> dict:
    """Validate admin token: static X-Admin-Token or session with admin role."""
    if settings.dev_bypass_auth:
        return {"user_id": "00000000-0000-0000-0000-000000000001", "role": "platform_admin"}

    if x_admin_token and settings.admin_token:
        if secrets.compare_digest(x_admin_token, settings.admin_token):
            return {"user_id": "token", "role": "platform_admin"}

    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        redis = request.app.state.redis
        raw = await redis.get(f"session:{token}")
        if raw:
            data = json.loads(raw)
            roles = [r["role"] for r in data.get("roles", [])]
            if any(r in roles for r in ("platform_admin", "area_owner", "team_admin")):
                return {"user_id": data["user_id"], "role": "platform_admin"}

    raise HTTPException(status_code=403, detail="Admin access required")
```

- [ ] **Step 6: Write `app/main.py`**

```python
# services/league/app/main.py
import os
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.db import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    yield
    await app.state.redis.aclose()


_is_dev = os.getenv("ENVIRONMENT", "production") in ("development", "test", "ci")

app = FastAPI(
    title="AI Gateway — League Service",
    lifespan=lifespan,
    docs_url="/docs" if _is_dev else None,
    redoc_url="/redoc" if _is_dev else None,
    openapi_url="/openapi.json" if _is_dev else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Admin-Token"],
    allow_credentials=True,
)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}


@app.get("/ready", tags=["health"])
async def ready():
    errors: dict[str, str] = {}
    try:
        await app.state.redis.ping()
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
```

- [ ] **Step 7: Verify the app imports cleanly**

```bash
cd /home/bntp/repos/ai-gw/services/league
pip install -e ".[dev]"
DEV_BYPASS_AUTH=true ENVIRONMENT=development python3 -c "from app.main import app; print('OK')"
```
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add services/league/
git commit -m "feat(league): scaffold league service (config, db, auth, main)"
```

---

## Task 3: ORM Models

**Files:**
- Create: `services/league/app/models/__init__.py`
- Create: `services/league/app/models/season.py`
- Create: `services/league/app/models/challenge.py`
- Create: `services/league/app/models/submission.py`
- Create: `services/league/app/models/score.py`
- Create: `services/league/app/models/leaderboard.py`
- Create: `services/league/app/models/store.py`
- Create: `services/league/app/models/points.py`
- Create: `services/league/app/models/proposal.py`

- [ ] **Step 1: Write `models/__init__.py`** (empty)

```python
# services/league/app/models/__init__.py
```

- [ ] **Step 2: Write `models/season.py`**

```python
# services/league/app/models/season.py
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Season(Base):
    __tablename__ = "league_seasons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'upcoming'"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scoring_weights: Mapped[dict] = mapped_column(JSONB, nullable=False)
    season_multiplier: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, server_default=text("1.0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
```

- [ ] **Step 3: Write `models/challenge.py`**

```python
# services/league/app/models/challenge.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Challenge(Base):
    __tablename__ = "league_challenges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    season_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("league_seasons.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    training_inputs: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    hidden_test_suite: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    allowed_models: Mapped[list] = mapped_column(ARRAY(Text), nullable=False)
    max_tokens_budget: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("4096"))
    max_league_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    scores_revealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))
    proposed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
```

- [ ] **Step 4: Write `models/submission.py`**

```python
# services/league/app/models/submission.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Submission(Base):
    __tablename__ = "league_submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    challenge_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("league_challenges.id", ondelete="CASCADE"), nullable=False)
    engineer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    tool_config: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    run_results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    prompt_hash: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
```

- [ ] **Step 5: Write `models/score.py`**

```python
# services/league/app/models/score.py
import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Score(Base):
    __tablename__ = "league_scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("league_submissions.id", ondelete="CASCADE"), nullable=False, unique=True)
    quality: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("0"))
    robustness: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("0"))
    token_efficiency: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("0"))
    speed: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("0"))
    cost_efficiency: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("0"))
    improvement_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("50"))
    creativity: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("50"))
    composite: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False, server_default=text("0"))
```

- [ ] **Step 6: Write `models/leaderboard.py`**

```python
# services/league/app/models/leaderboard.py
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class LeaderboardEntry(Base):
    __tablename__ = "league_leaderboard"

    season_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("league_seasons.id", ondelete="CASCADE"), primary_key=True)
    engineer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    composite_score: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False, server_default=text("0"))
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    points_earned: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
```

- [ ] **Step 7: Write `models/store.py`**

```python
# services/league/app/models/store.py
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class StoreItem(Base):
    __tablename__ = "league_store_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    point_cost: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    asset_url: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    exclusive_season_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("league_seasons.id", ondelete="SET NULL"), nullable=True)
    exclusive_top_n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))


class Purchase(Base):
    __tablename__ = "league_purchases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    engineer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("league_store_items.id", ondelete="CASCADE"), nullable=False)
    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
```

- [ ] **Step 8: Write `models/points.py`**

```python
# services/league/app/models/points.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PointsLedger(Base):
    __tablename__ = "league_points_ledger"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    engineer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
```

- [ ] **Step 9: Write `models/proposal.py`**

```python
# services/league/app/models/proposal.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ChallengeProposal(Base):
    __tablename__ = "league_challenge_proposals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    proposed_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'proposed'"))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewer_notes: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
```

- [ ] **Step 10: Verify all models import cleanly**

```bash
cd /home/bntp/repos/ai-gw/services/league
DEV_BYPASS_AUTH=true python3 -c "
from app.models.season import Season
from app.models.challenge import Challenge
from app.models.submission import Submission
from app.models.score import Score
from app.models.leaderboard import LeaderboardEntry
from app.models.store import StoreItem, Purchase
from app.models.points import PointsLedger
from app.models.proposal import ChallengeProposal
print('All models OK')
"
```
Expected: `All models OK`

- [ ] **Step 11: Commit**

```bash
git add services/league/app/models/
git commit -m "feat(league): add ORM models for all league tables"
```

---

## Task 4: Scoring Engine (TDD)

**Files:**
- Create: `services/league/app/scoring.py`
- Create: `services/league/tests/conftest.py`
- Create: `services/league/tests/__init__.py`
- Create: `services/league/tests/test_scoring.py`

- [ ] **Step 1: Write failing tests first**

```python
# services/league/tests/test_scoring.py
import pytest
from app.scoring import (
    score_quality_exact,
    score_efficiency,
    score_robustness,
    score_improvement_rate,
    compute_composite,
    DEFAULT_WEIGHTS,
)


# quality: exact match
def test_quality_exact_all_correct():
    results = [
        {"expected": "A", "actual": "A"},
        {"expected": "B", "actual": "B"},
    ]
    assert score_quality_exact(results) == pytest.approx(100.0)


def test_quality_exact_half_correct():
    results = [
        {"expected": "A", "actual": "A"},
        {"expected": "B", "actual": "C"},
    ]
    assert score_quality_exact(results) == pytest.approx(50.0)


def test_quality_exact_empty():
    assert score_quality_exact([]) == pytest.approx(0.0)


# efficiency (token, speed, cost all use same formula)
def test_efficiency_at_median():
    # using exactly the median should score 50
    assert score_efficiency(actual=100, median=100) == pytest.approx(50.0)


def test_efficiency_half_median():
    # using half the median should score 100 (capped)
    assert score_efficiency(actual=50, median=100) == pytest.approx(100.0)


def test_efficiency_double_median():
    # using double the median should score 25
    assert score_efficiency(actual=200, median=100) == pytest.approx(25.0)


def test_efficiency_zero_actual():
    # zero actual is treated as 1 to avoid division by zero
    assert score_efficiency(actual=0, median=100) == pytest.approx(100.0)


def test_efficiency_zero_median():
    # zero median falls back to 50 (neutral)
    assert score_efficiency(actual=100, median=0) == pytest.approx(50.0)


# robustness
def test_robustness_all_pass():
    assert score_robustness(passed=10, total=10) == pytest.approx(100.0)


def test_robustness_none_pass():
    assert score_robustness(passed=0, total=10) == pytest.approx(0.0)


def test_robustness_zero_total():
    assert score_robustness(passed=0, total=0) == pytest.approx(0.0)


# improvement rate
def test_improvement_rate_first_submission():
    # no prior best → neutral score of 50
    assert score_improvement_rate(current=700.0, prior_best=None) == pytest.approx(50.0)


def test_improvement_rate_50pct_improvement():
    # 50% improvement from prior best → score 100 (cap)
    assert score_improvement_rate(current=900.0, prior_best=600.0) == pytest.approx(100.0)


def test_improvement_rate_no_improvement():
    # same score as prior best → score 50 (neutral)
    assert score_improvement_rate(current=600.0, prior_best=600.0) == pytest.approx(50.0)


def test_improvement_rate_regression():
    # worse than prior best → score 0 (floor)
    assert score_improvement_rate(current=300.0, prior_best=600.0) == pytest.approx(0.0)


# composite
def test_composite_all_100():
    scores = {
        "quality": 100.0,
        "robustness": 100.0,
        "token_efficiency": 100.0,
        "speed": 100.0,
        "cost_efficiency": 100.0,
        "improvement_rate": 100.0,
        "creativity": 100.0,
    }
    # weights sum to 1.0 → composite = 100 * 1000 / 100 = 1000
    assert compute_composite(scores, DEFAULT_WEIGHTS) == pytest.approx(1000.0)


def test_composite_all_zero():
    scores = {k: 0.0 for k in DEFAULT_WEIGHTS}
    assert compute_composite(scores, DEFAULT_WEIGHTS) == pytest.approx(0.0)


def test_composite_weights_must_sum_to_1():
    bad_weights = {k: 0.5 for k in DEFAULT_WEIGHTS}  # sums to 3.5
    with pytest.raises(ValueError, match="weights must sum to 1.0"):
        compute_composite({k: 50.0 for k in DEFAULT_WEIGHTS}, bad_weights)
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /home/bntp/repos/ai-gw/services/league
pytest tests/test_scoring.py -v 2>&1 | head -20
```
Expected: `ImportError: cannot import name 'score_quality_exact' from 'app.scoring'` (or similar "not found" errors)

- [ ] **Step 3: Write `app/scoring.py` to make tests pass**

```python
# services/league/app/scoring.py

DEFAULT_WEIGHTS = {
    "quality": 0.35,
    "robustness": 0.20,
    "token_efficiency": 0.15,
    "speed": 0.10,
    "cost_efficiency": 0.10,
    "improvement_rate": 0.05,
    "creativity": 0.05,
}


def score_quality_exact(results: list[dict]) -> float:
    """Score quality by exact string match. results = [{expected, actual}, ...]"""
    if not results:
        return 0.0
    passed = sum(1 for r in results if str(r.get("actual", "")).strip() == str(r.get("expected", "")).strip())
    return passed * 100.0 / len(results)


def score_efficiency(actual: float, median: float) -> float:
    """Score efficiency: using less than median is better. Returns 0–100.
    
    Formula: (median / actual) * 50, capped at 100, floored at 0.
    median=0 returns neutral 50. actual=0 treated as 1.
    """
    if median == 0:
        return 50.0
    actual = max(actual, 1)
    return min(100.0, max(0.0, (median / actual) * 50.0))


def score_robustness(passed: int, total: int) -> float:
    """Score robustness as % of edge-case test variants passed."""
    if total == 0:
        return 0.0
    return passed * 100.0 / total


def score_improvement_rate(current: float, prior_best: float | None) -> float:
    """Score improvement vs personal season best.
    
    Returns 50 (neutral) if no prior best (first submission).
    Improvement of >=50% → 100. No change → 50. Regression → 0.
    """
    if prior_best is None or prior_best == 0:
        return 50.0
    delta = (current - prior_best) / prior_best  # e.g. 0.5 = 50% improvement
    delta = max(-1.0, min(0.5, delta))  # clamp [-100%, +50%]
    # Map [-1, 0.5] → [0, 100]
    return (delta + 1.0) / 1.5 * 100.0


def compute_composite(scores: dict[str, float], weights: dict[str, float]) -> float:
    """Compute weighted composite score 0–1000.
    
    Raises ValueError if weights don't sum to 1.0 (±0.01 tolerance).
    """
    weight_sum = sum(weights.values())
    if abs(weight_sum - 1.0) > 0.01:
        raise ValueError(f"weights must sum to 1.0, got {weight_sum:.4f}")
    raw = sum(scores.get(dim, 0.0) * w for dim, w in weights.items())
    return round(raw * 10.0, 2)  # scale 0–100 weighted avg → 0–1000
```

- [ ] **Step 4: Run tests — verify all pass**

```bash
cd /home/bntp/repos/ai-gw/services/league
pytest tests/test_scoring.py -v
```
Expected: all tests PASSED

- [ ] **Step 5: Commit**

```bash
git add services/league/app/scoring.py services/league/tests/
git commit -m "feat(league): scoring engine with full unit test coverage"
```

---

## Task 5: Season Router

**Files:**
- Create: `services/league/app/routers/__init__.py`
- Create: `services/league/app/routers/seasons.py`
- Modify: `services/league/app/main.py` (add router include)
- Create: `services/league/tests/test_seasons.py`

- [ ] **Step 1: Write failing tests**

```python
# services/league/tests/test_seasons.py
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


def _make_app():
    import os
    os.environ.setdefault("DEV_BYPASS_AUTH", "true")
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    from app.main import app
    return app


def _mock_season_row():
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "Q2 2026",
        "status": "upcoming",
        "starts_at": "2026-04-01T00:00:00+00:00",
        "ends_at": "2026-06-30T23:59:59+00:00",
        "scoring_weights": {
            "quality": 0.35, "robustness": 0.20,
            "token_efficiency": 0.15, "speed": 0.10,
            "cost_efficiency": 0.10, "improvement_rate": 0.05,
            "creativity": 0.05,
        },
        "season_multiplier": "1.00",
        "created_at": "2026-05-01T00:00:00+00:00",
    }


def test_list_seasons_returns_empty_when_no_seasons():
    app = _make_app()
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch("app.routers.seasons.get_session", return_value=mock_session):
        with TestClient(app) as client:
            resp = client.get("/seasons")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_season_returns_201():
    app = _make_app()
    mock_session = AsyncMock()
    row = _mock_season_row()
    mock_result = MagicMock()
    mock_result.mappings.return_value.one.return_value = row
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    payload = {
        "name": "Q2 2026",
        "starts_at": "2026-04-01T00:00:00Z",
        "ends_at": "2026-06-30T23:59:59Z",
    }
    with patch("app.routers.seasons.get_session", return_value=mock_session):
        with TestClient(app) as client:
            resp = client.post("/seasons", json=payload, headers={"X-Admin-Token": ""})
    assert resp.status_code == 201
    assert resp.json()["name"] == "Q2 2026"


def test_update_weights_rejected_when_season_active():
    app = _make_app()
    mock_session = AsyncMock()
    active_row = {**_mock_season_row(), "status": "active"}
    mock_result = MagicMock()
    mock_result.mappings.return_value.one_or_none.return_value = active_row
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch("app.routers.seasons.get_session", return_value=mock_session):
        with TestClient(app) as client:
            resp = client.patch(
                "/seasons/11111111-1111-1111-1111-111111111111/weights",
                json={"quality": 0.5, "robustness": 0.5},
                headers={"X-Admin-Token": ""},
            )
    assert resp.status_code == 409


def test_update_weights_rejected_when_weights_dont_sum_to_1():
    app = _make_app()
    mock_session = AsyncMock()
    upcoming_row = _mock_season_row()
    mock_result = MagicMock()
    mock_result.mappings.return_value.one_or_none.return_value = upcoming_row
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch("app.routers.seasons.get_session", return_value=mock_session):
        with TestClient(app) as client:
            resp = client.patch(
                "/seasons/11111111-1111-1111-1111-111111111111/weights",
                json={"quality": 0.9},  # doesn't sum to 1
                headers={"X-Admin-Token": ""},
            )
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests — verify they fail with ImportError**

```bash
cd /home/bntp/repos/ai-gw/services/league
pytest tests/test_seasons.py -v 2>&1 | head -10
```
Expected: module not found errors

- [ ] **Step 3: Write `app/routers/seasons.py`**

```python
# services/league/app/routers/seasons.py
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_auth
from app.db import get_session
from app.scoring import DEFAULT_WEIGHTS

router = APIRouter(prefix="/seasons", tags=["seasons"])

_WEIGHT_KEYS = set(DEFAULT_WEIGHTS.keys())


class SeasonCreate(BaseModel):
    name: str
    starts_at: datetime
    ends_at: datetime
    scoring_weights: dict[str, float] = DEFAULT_WEIGHTS
    season_multiplier: float = 1.0

    @model_validator(mode="after")
    def check_weights(self):
        if abs(sum(self.scoring_weights.values()) - 1.0) > 0.01:
            raise ValueError("scoring_weights must sum to 1.0")
        if set(self.scoring_weights.keys()) != _WEIGHT_KEYS:
            raise ValueError(f"scoring_weights must contain exactly: {_WEIGHT_KEYS}")
        return self


class WeightsUpdate(BaseModel):
    quality: float = DEFAULT_WEIGHTS["quality"]
    robustness: float = DEFAULT_WEIGHTS["robustness"]
    token_efficiency: float = DEFAULT_WEIGHTS["token_efficiency"]
    speed: float = DEFAULT_WEIGHTS["speed"]
    cost_efficiency: float = DEFAULT_WEIGHTS["cost_efficiency"]
    improvement_rate: float = DEFAULT_WEIGHTS["improvement_rate"]
    creativity: float = DEFAULT_WEIGHTS["creativity"]

    @model_validator(mode="after")
    def check_sum(self):
        total = (self.quality + self.robustness + self.token_efficiency +
                 self.speed + self.cost_efficiency + self.improvement_rate + self.creativity)
        if abs(total - 1.0) > 0.01:
            raise ValueError("weights must sum to 1.0")
        return self


def _season_to_dict(row: Any) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "status": row["status"],
        "starts_at": row["starts_at"].isoformat() if hasattr(row["starts_at"], "isoformat") else row["starts_at"],
        "ends_at": row["ends_at"].isoformat() if hasattr(row["ends_at"], "isoformat") else row["ends_at"],
        "scoring_weights": row["scoring_weights"],
        "season_multiplier": float(row["season_multiplier"]),
        "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else row["created_at"],
    }


@router.get("")
async def list_seasons(session: AsyncSession = Depends(get_session)):
    result = await session.execute(text(
        "SELECT * FROM league_seasons ORDER BY starts_at DESC"
    ))
    return [_season_to_dict(row) for row in result.mappings().all()]


@router.post("", status_code=201)
async def create_season(
    body: SeasonCreate,
    session: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin_auth),
):
    import json
    result = await session.execute(text("""
        INSERT INTO league_seasons (name, status, starts_at, ends_at, scoring_weights, season_multiplier)
        VALUES (:name, 'upcoming', :starts_at, :ends_at, CAST(:weights AS jsonb), :multiplier)
        RETURNING *
    """), {
        "name": body.name,
        "starts_at": body.starts_at,
        "ends_at": body.ends_at,
        "weights": json.dumps(body.scoring_weights),
        "multiplier": body.season_multiplier,
    })
    await session.commit()
    return _season_to_dict(result.mappings().one())


@router.patch("/{season_id}/weights")
async def update_weights(
    season_id: UUID,
    body: WeightsUpdate,
    session: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin_auth),
):
    import json
    row = (await session.execute(
        text("SELECT * FROM league_seasons WHERE id = :id"),
        {"id": str(season_id)},
    )).mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Season not found")
    if row["status"] != "upcoming":
        raise HTTPException(status_code=409, detail="Cannot change weights once season is active or closed")
    weights = {
        "quality": body.quality, "robustness": body.robustness,
        "token_efficiency": body.token_efficiency, "speed": body.speed,
        "cost_efficiency": body.cost_efficiency, "improvement_rate": body.improvement_rate,
        "creativity": body.creativity,
    }
    await session.execute(text("""
        UPDATE league_seasons SET scoring_weights = CAST(:w AS jsonb) WHERE id = :id
    """), {"w": json.dumps(weights), "id": str(season_id)})
    await session.commit()
    return {"id": str(season_id), "scoring_weights": weights}


@router.patch("/{season_id}/status")
async def update_status(
    season_id: UUID,
    body: dict,
    session: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin_auth),
):
    new_status = body.get("status")
    if new_status not in ("upcoming", "active", "closed"):
        raise HTTPException(status_code=422, detail="status must be upcoming, active, or closed")
    await session.execute(text(
        "UPDATE league_seasons SET status = :s WHERE id = :id"
    ), {"s": new_status, "id": str(season_id)})
    await session.commit()
    return {"id": str(season_id), "status": new_status}
```

- [ ] **Step 4: Add router to `app/main.py`**

Add to the imports and router includes section:
```python
# In app/main.py — add after existing imports:
from app.routers import seasons as seasons_router

# Add after the existing @app.get("/ready") handler:
app.include_router(seasons_router.router)
```

- [ ] **Step 5: Run tests — verify all pass**

```bash
cd /home/bntp/repos/ai-gw/services/league
pytest tests/test_seasons.py -v
```
Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add services/league/app/routers/ services/league/app/main.py services/league/tests/test_seasons.py
git commit -m "feat(league): season router with CRUD and weight management"
```

---

## Task 6: Challenge Router

**Files:**
- Create: `services/league/app/routers/challenges.py`
- Create: `services/league/tests/test_challenges.py`
- Modify: `services/league/app/main.py`

- [ ] **Step 1: Write failing tests**

```python
# services/league/tests/test_challenges.py
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

os.environ.setdefault("DEV_BYPASS_AUTH", "true")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.main import app


def _mock_challenge():
    return {
        "id": "22222222-2222-2222-2222-222222222222",
        "season_id": "11111111-1111-1111-1111-111111111111",
        "title": "Intent Classifier",
        "goal": "Classify customer intent",
        "training_inputs": [],
        "allowed_models": ["claude-sonnet-4-6"],
        "max_tokens_budget": 4096,
        "max_league_attempts": 3,
        "scores_revealed_at": None,
        "status": "draft",
        "proposed_by": None,
        "created_at": "2026-05-01T00:00:00+00:00",
    }


def test_list_challenges_for_season():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [_mock_challenge()]
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch("app.routers.challenges.get_session", return_value=mock_session):
        with TestClient(app) as client:
            resp = client.get("/seasons/11111111-1111-1111-1111-111111111111/challenges")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["title"] == "Intent Classifier"


def test_challenge_detail_hides_hidden_test_suite():
    """hidden_test_suite must never appear in non-admin challenge detail."""
    ch = {**_mock_challenge(), "hidden_test_suite": [{"input": "secret", "expected": "X"}]}
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.one_or_none.return_value = ch
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch("app.routers.challenges.get_session", return_value=mock_session):
        with TestClient(app) as client:
            resp = client.get("/challenges/22222222-2222-2222-2222-222222222222")
    assert resp.status_code == 200
    assert "hidden_test_suite" not in resp.json()
    assert "secret" not in str(resp.json())


def test_create_challenge_requires_admin():
    """Without DEV_BYPASS_AUTH, creating a challenge should require admin."""
    import importlib
    os.environ["DEV_BYPASS_AUTH"] = "false"
    # Re-import config with bypass off
    import app.config as cfg_mod
    cfg_mod.settings.dev_bypass_auth = False

    mock_session = AsyncMock()
    with patch("app.routers.challenges.get_session", return_value=mock_session):
        with TestClient(app) as client:
            resp = client.post(
                "/seasons/11111111-1111-1111-1111-111111111111/challenges",
                json={"title": "Test", "goal": "Classify"},
            )
    assert resp.status_code == 403
    # Restore
    os.environ["DEV_BYPASS_AUTH"] = "true"
    cfg_mod.settings.dev_bypass_auth = True
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /home/bntp/repos/ai-gw/services/league
pytest tests/test_challenges.py -v 2>&1 | head -10
```
Expected: router not found errors

- [ ] **Step 3: Write `app/routers/challenges.py`**

```python
# services/league/app/routers/challenges.py
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_auth, require_dev_auth
from app.db import get_session

router = APIRouter(tags=["challenges"])

_PUBLIC_COLS = "id, season_id, title, goal, training_inputs, allowed_models, max_tokens_budget, max_league_attempts, scores_revealed_at, status, proposed_by, created_at"


class ChallengeCreate(BaseModel):
    title: str
    goal: str
    training_inputs: list[dict] = []
    hidden_test_suite: list[dict] = []
    allowed_models: list[str] = ["claude-sonnet-4-6"]
    max_tokens_budget: int = 4096
    max_league_attempts: int = 3


def _challenge_to_dict(row, include_hidden: bool = False) -> dict:
    d = {
        "id": str(row["id"]),
        "season_id": str(row["season_id"]),
        "title": row["title"],
        "goal": row["goal"],
        "training_inputs": row["training_inputs"],
        "allowed_models": list(row["allowed_models"]),
        "max_tokens_budget": row["max_tokens_budget"],
        "max_league_attempts": row["max_league_attempts"],
        "scores_revealed_at": row["scores_revealed_at"].isoformat() if row["scores_revealed_at"] else None,
        "status": row["status"],
        "proposed_by": str(row["proposed_by"]) if row["proposed_by"] else None,
        "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else row["created_at"],
    }
    if include_hidden:
        d["hidden_test_suite"] = row.get("hidden_test_suite", [])
    return d


@router.get("/seasons/{season_id}/challenges")
async def list_challenges(
    season_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user=Depends(require_dev_auth),
):
    result = await session.execute(text(f"""
        SELECT {_PUBLIC_COLS} FROM league_challenges
        WHERE season_id = :season_id
        ORDER BY created_at
    """), {"season_id": str(season_id)})
    return [_challenge_to_dict(row) for row in result.mappings().all()]


@router.get("/challenges/{challenge_id}")
async def get_challenge(
    challenge_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user=Depends(require_dev_auth),
):
    row = (await session.execute(text(f"""
        SELECT {_PUBLIC_COLS} FROM league_challenges WHERE id = :id
    """), {"id": str(challenge_id)})).mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return _challenge_to_dict(row, include_hidden=False)


@router.post("/seasons/{season_id}/challenges", status_code=201)
async def create_challenge(
    season_id: UUID,
    body: ChallengeCreate,
    session: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin_auth),
):
    result = await session.execute(text("""
        INSERT INTO league_challenges
          (season_id, title, goal, training_inputs, hidden_test_suite,
           allowed_models, max_tokens_budget, max_league_attempts)
        VALUES
          (:season_id, :title, :goal,
           CAST(:training_inputs AS jsonb), CAST(:hidden_test_suite AS jsonb),
           :allowed_models, :max_tokens_budget, :max_league_attempts)
        RETURNING *
    """), {
        "season_id": str(season_id),
        "title": body.title,
        "goal": body.goal,
        "training_inputs": json.dumps(body.training_inputs),
        "hidden_test_suite": json.dumps(body.hidden_test_suite),
        "allowed_models": body.allowed_models,
        "max_tokens_budget": body.max_tokens_budget,
        "max_league_attempts": body.max_league_attempts,
    })
    await session.commit()
    row = result.mappings().one()
    return _challenge_to_dict(row, include_hidden=True)  # admin sees full detail


@router.patch("/challenges/{challenge_id}/status")
async def update_challenge_status(
    challenge_id: UUID,
    body: dict,
    session: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin_auth),
):
    new_status = body.get("status")
    if new_status not in ("draft", "active", "closed"):
        raise HTTPException(status_code=422, detail="status must be draft, active, or closed")
    await session.execute(text(
        "UPDATE league_challenges SET status = :s, scores_revealed_at = CASE WHEN :s = 'closed' THEN NOW() ELSE scores_revealed_at END WHERE id = :id"
    ), {"s": new_status, "id": str(challenge_id)})

    if new_status == "closed":
        # Recompute leaderboard ranks for the season this challenge belongs to
        await session.execute(text("""
            WITH ranked AS (
                SELECT season_id, engineer_id,
                       RANK() OVER (PARTITION BY season_id ORDER BY composite_score DESC) AS new_rank
                FROM league_leaderboard
                WHERE season_id = (SELECT season_id FROM league_challenges WHERE id = :cid)
            )
            UPDATE league_leaderboard lb
            SET rank = ranked.new_rank
            FROM ranked
            WHERE lb.season_id = ranked.season_id AND lb.engineer_id = ranked.engineer_id
        """), {"cid": str(challenge_id)})

    await session.commit()
    return {"id": str(challenge_id), "status": new_status}
```

- [ ] **Step 4: Add router to `app/main.py`**

```python
# Add import:
from app.routers import challenges as challenges_router
# Add include:
app.include_router(challenges_router.router)
```

- [ ] **Step 5: Run tests — verify all pass**

```bash
cd /home/bntp/repos/ai-gw/services/league
pytest tests/test_challenges.py -v
```
Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add services/league/app/routers/challenges.py services/league/tests/test_challenges.py services/league/app/main.py
git commit -m "feat(league): challenge router — CRUD with hidden_test_suite guard"
```

---

## Task 7: Submission Execution Pipeline (TDD)

This is the core task. The submission router validates auth, enforces attempt limits, calls litellm for each test case, runs the scoring engine, writes results to DB, and updates the leaderboard entry.

**Files:**
- Create: `services/league/app/routers/submissions.py`
- Create: `services/league/tests/test_submissions.py`
- Modify: `services/league/app/main.py`

- [ ] **Step 1: Write failing tests**

```python
# services/league/tests/test_submissions.py
import hashlib
import json
import os
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from fastapi.testclient import TestClient

os.environ.setdefault("DEV_BYPASS_AUTH", "true")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.main import app

_CHALLENGE_ID = "22222222-2222-2222-2222-222222222222"
_SEASON_ID = "11111111-1111-1111-1111-111111111111"
_USER_ID = "00000000-0000-0000-0000-000000000001"


def _mock_active_challenge():
    return {
        "id": _CHALLENGE_ID,
        "season_id": _SEASON_ID,
        "status": "active",
        "max_league_attempts": 3,
        "max_tokens_budget": 4096,
        "allowed_models": ["claude-sonnet-4-6"],
        "hidden_test_suite": [
            {"input": "My order is late", "expected": "delivery_issue", "weight": 1.0},
            {"input": "I want a refund", "expected": "refund_request", "weight": 1.0},
        ],
        "training_inputs": [
            {"input": "Test input", "expected": "test_output"},
        ],
        "scoring_weights": {
            "quality": 0.35, "robustness": 0.20, "token_efficiency": 0.15,
            "speed": 0.10, "cost_efficiency": 0.10, "improvement_rate": 0.05, "creativity": 0.05,
        },
        "season_multiplier": 1.0,
    }


def _mock_litellm_response(output: str, tokens: int = 100, latency_ms: float = 200.0):
    return {
        "choices": [{"message": {"content": output}}],
        "usage": {"total_tokens": tokens},
        "_latency_ms": latency_ms,
    }


def test_training_submission_returns_scores_immediately():
    challenge = _mock_active_challenge()
    mock_session = AsyncMock()

    # Mock: get challenge, get prior submission count (0), no prior best
    results_seq = [
        MagicMock(**{"mappings.return_value.one_or_none.return_value": challenge}),  # get challenge
        MagicMock(**{"scalar.return_value": 0}),  # attempt count = 0
        MagicMock(**{"mappings.return_value.one_or_none.return_value": None}),  # no prior best
    ]
    mock_session.execute = AsyncMock(side_effect=results_seq + [AsyncMock()] * 10)
    mock_session.commit = AsyncMock()

    litellm_responses = [
        _mock_litellm_response("delivery_issue"),
        _mock_litellm_response("refund_request"),
    ]

    with patch("app.routers.submissions.get_session", return_value=mock_session), \
         patch("app.routers.submissions._call_litellm", new_callable=AsyncMock,
               side_effect=litellm_responses):
        with TestClient(app) as client:
            resp = client.post(f"/challenges/{_CHALLENGE_ID}/submit", json={
                "mode": "training",
                "system_prompt": "You are a classifier. Output only the category.",
                "tool_config": [],
            })

    assert resp.status_code == 200
    body = resp.json()
    assert "scores" in body
    assert body["scores"]["quality"] == pytest.approx(100.0)


def test_league_submission_hides_scores_until_deadline():
    challenge = _mock_active_challenge()
    mock_session = AsyncMock()

    results_seq = [
        MagicMock(**{"mappings.return_value.one_or_none.return_value": challenge}),
        MagicMock(**{"scalar.return_value": 0}),
        MagicMock(**{"mappings.return_value.one_or_none.return_value": None}),
    ]
    mock_session.execute = AsyncMock(side_effect=results_seq + [AsyncMock()] * 10)
    mock_session.commit = AsyncMock()

    litellm_responses = [
        _mock_litellm_response("delivery_issue"),
        _mock_litellm_response("refund_request"),
    ]

    with patch("app.routers.submissions.get_session", return_value=mock_session), \
         patch("app.routers.submissions._call_litellm", new_callable=AsyncMock,
               side_effect=litellm_responses):
        with TestClient(app) as client:
            resp = client.post(f"/challenges/{_CHALLENGE_ID}/submit", json={
                "mode": "league",
                "system_prompt": "Classify intent.",
                "tool_config": [],
            })

    assert resp.status_code == 200
    body = resp.json()
    # League mode: scores stored but NOT returned
    assert "scores" not in body
    assert body["message"] == "Submission received. Scores will be revealed when the challenge closes."


def test_league_submission_blocks_over_limit():
    challenge = _mock_active_challenge()
    mock_session = AsyncMock()

    results_seq = [
        MagicMock(**{"mappings.return_value.one_or_none.return_value": challenge}),
        MagicMock(**{"scalar.return_value": 3}),  # already at limit (3)
    ]
    mock_session.execute = AsyncMock(side_effect=results_seq)

    with patch("app.routers.submissions.get_session", return_value=mock_session):
        with TestClient(app) as client:
            resp = client.post(f"/challenges/{_CHALLENGE_ID}/submit", json={
                "mode": "league",
                "system_prompt": "Classify intent.",
                "tool_config": [],
            })

    assert resp.status_code == 429
    assert "attempt limit" in resp.json()["detail"].lower()


def test_submission_on_inactive_challenge_rejected():
    draft_challenge = {**_mock_active_challenge(), "status": "draft"}
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(
        **{"mappings.return_value.one_or_none.return_value": draft_challenge}
    ))

    with patch("app.routers.submissions.get_session", return_value=mock_session):
        with TestClient(app) as client:
            resp = client.post(f"/challenges/{_CHALLENGE_ID}/submit", json={
                "mode": "training",
                "system_prompt": "test",
                "tool_config": [],
            })

    assert resp.status_code == 409
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /home/bntp/repos/ai-gw/services/league
pytest tests/test_submissions.py -v 2>&1 | head -15
```
Expected: router not found errors

- [ ] **Step 3: Write `app/routers/submissions.py`**

```python
# services/league/app/routers/submissions.py
import hashlib
import json
import time
import uuid
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_dev_auth
from app.config import settings
from app.db import get_session
from app.scoring import (
    DEFAULT_WEIGHTS,
    compute_composite,
    score_efficiency,
    score_improvement_rate,
    score_quality_exact,
    score_robustness,
)

router = APIRouter(tags=["submissions"])


class SubmissionCreate(BaseModel):
    mode: str  # "training" or "league"
    system_prompt: str
    tool_config: list[dict] = []


async def _call_litellm(system_prompt: str, user_input: str, model: str, max_tokens: int) -> dict:
    """Call litellm and return {output, tokens, latency_ms}."""
    start = time.monotonic()
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{settings.litellm_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            json={
                "model": model,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input},
                ],
            },
        )
        resp.raise_for_status()
    data = resp.json()
    latency_ms = (time.monotonic() - start) * 1000
    return {
        "output": data["choices"][0]["message"]["content"],
        "tokens": data.get("usage", {}).get("total_tokens", 0),
        "latency_ms": latency_ms,
        "cost_usd": data.get("usage", {}).get("cost", 0.0),
    }


async def _run_test_suite(
    system_prompt: str,
    test_cases: list[dict],
    model: str,
    max_tokens: int,
) -> list[dict]:
    """Run system_prompt against each test case. Returns per-case results."""
    results = []
    for case in test_cases:
        try:
            run = await _call_litellm(system_prompt, case["input"], model, max_tokens)
            results.append({
                "input": case["input"],
                "expected": case["expected"],
                "actual": run["output"].strip(),
                "tokens": run["tokens"],
                "latency_ms": run["latency_ms"],
                "cost_usd": run.get("cost_usd", 0.0),
                "weight": case.get("weight", 1.0),
            })
        except Exception as exc:
            results.append({
                "input": case["input"],
                "expected": case["expected"],
                "actual": "",
                "tokens": 0,
                "latency_ms": 0,
                "cost_usd": 0.0,
                "weight": case.get("weight", 1.0),
                "error": str(exc),
            })
    return results


def _compute_scores(
    run_results: list[dict],
    prior_composite: float | None,
    season_weights: dict,
) -> dict[str, float]:
    total_tokens = sum(r["tokens"] for r in run_results)
    total_cost = sum(r["cost_usd"] for r in run_results)
    avg_latency = sum(r["latency_ms"] for r in run_results) / max(len(run_results), 1)

    quality = score_quality_exact(run_results)
    robustness = score_robustness(
        passed=sum(1 for r in run_results if r.get("actual", "").strip() == r.get("expected", "").strip()),
        total=len(run_results),
    )
    token_efficiency = score_efficiency(actual=total_tokens, median=500)  # median seeded at 500; recalculated at scale
    speed = score_efficiency(actual=avg_latency, median=300.0)
    cost_efficiency = score_efficiency(actual=total_cost * 10000, median=5.0)  # scale $ to comparable units

    weights = season_weights or DEFAULT_WEIGHTS
    partial_scores = {
        "quality": quality,
        "robustness": robustness,
        "token_efficiency": token_efficiency,
        "speed": speed,
        "cost_efficiency": cost_efficiency,
        "improvement_rate": 50.0,  # placeholder; updated after composite is known
        "creativity": 50.0,  # placeholder; updated at challenge close
    }
    composite = compute_composite(partial_scores, weights)
    partial_scores["improvement_rate"] = score_improvement_rate(composite, prior_composite)
    # Recompute composite with real improvement_rate
    composite = compute_composite(partial_scores, weights)
    return {**partial_scores, "composite": composite}


@router.post("/challenges/{challenge_id}/submit")
async def submit(
    challenge_id: UUID,
    body: SubmissionCreate,
    session: AsyncSession = Depends(get_session),
    user=Depends(require_dev_auth),
):
    if body.mode not in ("training", "league"):
        raise HTTPException(status_code=422, detail="mode must be 'training' or 'league'")

    # 1. Load challenge + season weights
    row = (await session.execute(text("""
        SELECT c.*, s.scoring_weights, s.season_multiplier
        FROM league_challenges c
        JOIN league_seasons s ON s.id = c.season_id
        WHERE c.id = :id
    """), {"id": str(challenge_id)})).mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Challenge not found")
    if row["status"] != "active":
        raise HTTPException(status_code=409, detail="Challenge is not active")

    # 2. Enforce league attempt limit
    if body.mode == "league":
        attempt_count = (await session.execute(text("""
            SELECT COUNT(*) FROM league_submissions
            WHERE challenge_id = :cid AND engineer_id = :uid AND mode = 'league'
        """), {"cid": str(challenge_id), "uid": user["user_id"]})).scalar()
        if attempt_count >= row["max_league_attempts"]:
            raise HTTPException(status_code=429, detail=f"League attempt limit of {row['max_league_attempts']} reached")

    # 3. Get prior personal best composite for improvement_rate
    prior_row = (await session.execute(text("""
        SELECT MAX(sc.composite) AS best
        FROM league_submissions sub
        JOIN league_scores sc ON sc.submission_id = sub.id
        WHERE sub.challenge_id = :cid AND sub.engineer_id = :uid
    """), {"cid": str(challenge_id), "uid": user["user_id"]})).mappings().one_or_none()
    prior_best = float(prior_row["best"]) if prior_row and prior_row["best"] is not None else None

    # 4. Determine test cases and next attempt number
    test_cases = row["hidden_test_suite"] if body.mode == "league" else row["training_inputs"]
    attempt_num = (await session.execute(text("""
        SELECT COALESCE(MAX(attempt_number), 0) + 1
        FROM league_submissions
        WHERE challenge_id = :cid AND engineer_id = :uid AND mode = :mode
    """), {"cid": str(challenge_id), "uid": user["user_id"], "mode": body.mode})).scalar()

    # 5. Execute agent against test cases
    model = row["allowed_models"][0]
    run_results = await _run_test_suite(body.system_prompt, test_cases, model, row["max_tokens_budget"])

    # 6. Compute scores
    season_weights = row["scoring_weights"] or DEFAULT_WEIGHTS
    scores = _compute_scores(run_results, prior_best, season_weights)

    # 7. Store submission
    prompt_hash = hashlib.sha256(body.system_prompt.encode()).hexdigest()
    sub_result = await session.execute(text("""
        INSERT INTO league_submissions
          (challenge_id, engineer_id, mode, system_prompt, tool_config, attempt_number, run_results, prompt_hash)
        VALUES
          (:cid, :uid, :mode, :prompt, CAST(:tools AS jsonb), :attempt, CAST(:results AS jsonb), :hash)
        RETURNING id
    """), {
        "cid": str(challenge_id),
        "uid": user["user_id"],
        "mode": body.mode,
        "prompt": body.system_prompt,
        "tools": json.dumps(body.tool_config),
        "attempt": attempt_num,
        "results": json.dumps(run_results),
        "hash": prompt_hash,
    })
    submission_id = sub_result.scalar()

    # 8. Store scores
    await session.execute(text("""
        INSERT INTO league_scores
          (submission_id, quality, robustness, token_efficiency, speed,
           cost_efficiency, improvement_rate, creativity, composite)
        VALUES
          (:sid, :quality, :robustness, :token_efficiency, :speed,
           :cost_efficiency, :improvement_rate, :creativity, :composite)
    """), {"sid": str(submission_id), **{k: round(v, 2) for k, v in scores.items()}})

    # 9. Update leaderboard if this is best league composite
    if body.mode == "league":
        season_id = str(row["season_id"])
        multiplier = float(row["season_multiplier"])
        pts = int(scores["composite"] * multiplier)
        await session.execute(text("""
            INSERT INTO league_leaderboard (season_id, engineer_id, composite_score, points_earned, updated_at)
            VALUES (:sid, :uid, :score, :pts, NOW())
            ON CONFLICT (season_id, engineer_id) DO UPDATE
              SET composite_score = GREATEST(league_leaderboard.composite_score, EXCLUDED.composite_score),
                  points_earned = GREATEST(league_leaderboard.points_earned, EXCLUDED.points_earned),
                  updated_at = NOW()
        """), {"sid": season_id, "uid": user["user_id"], "score": round(scores["composite"], 2), "pts": pts})

        # Award points only if this is a new personal best
        if prior_best is None or scores["composite"] > prior_best:
            delta = pts - (int(prior_best * multiplier) if prior_best else 0)
            if delta > 0:
                await session.execute(text("""
                    INSERT INTO league_points_ledger (engineer_id, delta, reason, ref_id)
                    VALUES (:uid, :delta, 'league_submission_reward', :ref)
                """), {"uid": user["user_id"], "delta": delta, "ref": str(submission_id)})

    # 10. Award flat XP for training mode
    if body.mode == "training":
        await session.execute(text("""
            INSERT INTO league_points_ledger (engineer_id, delta, reason, ref_id)
            VALUES (:uid, 50, 'training_xp_reward', :ref)
        """), {"uid": user["user_id"], "ref": str(submission_id)})

    await session.commit()

    # 11. Return result — training: show scores; league: hide scores
    if body.mode == "training":
        return {"submission_id": str(submission_id), "scores": scores, "run_results": run_results}
    else:
        return {
            "submission_id": str(submission_id),
            "message": "Submission received. Scores will be revealed when the challenge closes.",
        }
```

- [ ] **Step 4: Add router to `app/main.py`**

```python
from app.routers import submissions as submissions_router
app.include_router(submissions_router.router)
```

- [ ] **Step 5: Run tests — verify all pass**

```bash
cd /home/bntp/repos/ai-gw/services/league
pytest tests/test_submissions.py -v
```
Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add services/league/app/routers/submissions.py services/league/tests/test_submissions.py services/league/app/main.py
git commit -m "feat(league): submission execution pipeline with scoring integration"
```

---

## Task 8: Leaderboard Router

**Files:**
- Create: `services/league/app/routers/leaderboard.py`
- Create: `services/league/tests/test_leaderboard.py`
- Modify: `services/league/app/main.py`

- [ ] **Step 1: Write failing tests**

```python
# services/league/tests/test_leaderboard.py
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

os.environ.setdefault("DEV_BYPASS_AUTH", "true")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.main import app

_SEASON_ID = "11111111-1111-1111-1111-111111111111"


def test_leaderboard_returns_ranked_entries():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        {
            "engineer_id": "aaaa0000-0000-0000-0000-000000000001",
            "email": "anna@simcorp.com",
            "display_name": "Anna K.",
            "team_name": "Equities",
            "area_name": "Engineering",
            "composite_score": "980.00",
            "rank": 1,
            "points_earned": 980,
            "updated_at": "2026-05-10T12:00:00+00:00",
        }
    ]
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch("app.routers.leaderboard.get_session", return_value=mock_session):
        with TestClient(app) as client:
            resp = client.get(f"/seasons/{_SEASON_ID}/leaderboard")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["rank"] == 1
    assert data[0]["display_name"] == "Anna K."


def test_my_rank_returns_engineer_position():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.one_or_none.return_value = {
        "composite_score": "620.00",
        "rank": 42,
        "points_earned": 620,
    }
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch("app.routers.leaderboard.get_session", return_value=mock_session):
        with TestClient(app) as client:
            resp = client.get(f"/seasons/{_SEASON_ID}/leaderboard/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["rank"] == 42
    assert body["composite_score"] == pytest.approx(620.0)
```

- [ ] **Step 2: Write `app/routers/leaderboard.py`**

```python
# services/league/app/routers/leaderboard.py
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_dev_auth
from app.db import get_session

router = APIRouter(tags=["leaderboard"])


@router.get("/seasons/{season_id}/leaderboard")
async def get_leaderboard(
    season_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user=Depends(require_dev_auth),
):
    result = await session.execute(text("""
        SELECT
            lb.engineer_id,
            u.email,
            u.display_name,
            t.name AS team_name,
            a.name AS area_name,
            lb.composite_score,
            lb.rank,
            lb.points_earned,
            lb.updated_at
        FROM league_leaderboard lb
        JOIN users u ON u.id = lb.engineer_id
        LEFT JOIN developers d ON d.user_id = u.id
        LEFT JOIN teams t ON t.id = d.team_id
        LEFT JOIN areas a ON a.id = t.area_id
        WHERE lb.season_id = :sid
        ORDER BY lb.composite_score DESC
    """), {"sid": str(season_id)})
    rows = result.mappings().all()
    return [
        {
            "engineer_id": str(r["engineer_id"]),
            "email": r["email"],
            "display_name": r["display_name"],
            "team_name": r["team_name"],
            "area_name": r["area_name"],
            "composite_score": float(r["composite_score"]),
            "rank": r["rank"],
            "points_earned": r["points_earned"],
            "updated_at": r["updated_at"].isoformat() if hasattr(r["updated_at"], "isoformat") else r["updated_at"],
        }
        for r in rows
    ]


@router.get("/seasons/{season_id}/leaderboard/me")
async def my_rank(
    season_id: UUID,
    session: AsyncSession = Depends(get_session),
    user=Depends(require_dev_auth),
):
    row = (await session.execute(text("""
        SELECT composite_score, rank, points_earned
        FROM league_leaderboard
        WHERE season_id = :sid AND engineer_id = :uid
    """), {"sid": str(season_id), "uid": user["user_id"]})).mappings().one_or_none()
    if not row:
        return {"rank": None, "composite_score": 0.0, "points_earned": 0}
    return {
        "rank": row["rank"],
        "composite_score": float(row["composite_score"]),
        "points_earned": row["points_earned"],
    }
```

- [ ] **Step 3: Add router + run tests**

```python
# Add to app/main.py:
from app.routers import leaderboard as leaderboard_router
app.include_router(leaderboard_router.router)
```

```bash
cd /home/bntp/repos/ai-gw/services/league
pytest tests/test_leaderboard.py -v
```
Expected: all PASSED

- [ ] **Step 4: Commit**

```bash
git add services/league/app/routers/leaderboard.py services/league/tests/test_leaderboard.py services/league/app/main.py
git commit -m "feat(league): leaderboard router with per-season rankings"
```

---

## Task 9: Store & Points Router

**Files:**
- Create: `services/league/app/routers/store.py`
- Create: `services/league/tests/test_store.py`
- Modify: `services/league/app/main.py`

- [ ] **Step 1: Write failing tests**

```python
# services/league/tests/test_store.py
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

os.environ.setdefault("DEV_BYPASS_AUTH", "true")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.main import app

_USER_ID = "00000000-0000-0000-0000-000000000001"
_ITEM_ID = "33333333-3333-3333-3333-333333333333"


def test_balance_returns_sum_of_ledger():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = 1840
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch("app.routers.store.get_session", return_value=mock_session):
        with TestClient(app) as client:
            resp = client.get("/store/balance")
    assert resp.status_code == 200
    assert resp.json()["balance"] == 1840


def test_purchase_deducts_points_and_creates_purchase():
    mock_session = AsyncMock()

    item_row = {
        "id": _ITEM_ID, "point_cost": 800, "active": True,
        "exclusive_season_id": None, "exclusive_top_n": None,
    }
    balance_result = MagicMock()
    balance_result.scalar.return_value = 1840
    item_result = MagicMock()
    item_result.mappings.return_value.one_or_none.return_value = item_row
    already_owned_result = MagicMock()
    already_owned_result.scalar.return_value = 0

    mock_session.execute = AsyncMock(side_effect=[
        item_result,
        balance_result,
        already_owned_result,
        AsyncMock(),  # insert purchase
        AsyncMock(),  # insert ledger debit
    ])
    mock_session.commit = AsyncMock()

    with patch("app.routers.store.get_session", return_value=mock_session):
        with TestClient(app) as client:
            resp = client.post(f"/store/purchase/{_ITEM_ID}")
    assert resp.status_code == 200
    assert resp.json()["new_balance"] == 1040  # 1840 - 800


def test_purchase_exclusive_item_rejected():
    mock_session = AsyncMock()
    item_row = {
        "id": _ITEM_ID, "point_cost": 0, "active": True,
        "exclusive_season_id": "11111111-1111-1111-1111-111111111111",
        "exclusive_top_n": 3,
    }
    mock_result = MagicMock()
    mock_result.mappings.return_value.one_or_none.return_value = item_row
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch("app.routers.store.get_session", return_value=mock_session):
        with TestClient(app) as client:
            resp = client.post(f"/store/purchase/{_ITEM_ID}")
    assert resp.status_code == 403
    assert "exclusive" in resp.json()["detail"].lower()


def test_purchase_fails_on_insufficient_points():
    mock_session = AsyncMock()
    item_row = {
        "id": _ITEM_ID, "point_cost": 2000, "active": True,
        "exclusive_season_id": None, "exclusive_top_n": None,
    }
    item_result = MagicMock()
    item_result.mappings.return_value.one_or_none.return_value = item_row
    balance_result = MagicMock()
    balance_result.scalar.return_value = 500  # not enough

    mock_session.execute = AsyncMock(side_effect=[item_result, balance_result])

    with patch("app.routers.store.get_session", return_value=mock_session):
        with TestClient(app) as client:
            resp = client.post(f"/store/purchase/{_ITEM_ID}")
    assert resp.status_code == 402
    assert "insufficient" in resp.json()["detail"].lower()
```

- [ ] **Step 2: Write `app/routers/store.py`**

```python
# services/league/app/routers/store.py
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_auth, require_dev_auth
from app.db import get_session

router = APIRouter(prefix="/store", tags=["store"])


@router.get("/balance")
async def get_balance(
    session: AsyncSession = Depends(get_session),
    user=Depends(require_dev_auth),
):
    balance = (await session.execute(text(
        "SELECT COALESCE(SUM(delta), 0) FROM league_points_ledger WHERE engineer_id = :uid"
    ), {"uid": user["user_id"]})).scalar()
    return {"balance": int(balance)}


@router.get("/items")
async def list_items(session: AsyncSession = Depends(get_session), _user=Depends(require_dev_auth)):
    result = await session.execute(text(
        "SELECT id, name, type, point_cost, asset_url, exclusive_season_id, exclusive_top_n FROM league_store_items WHERE active = TRUE ORDER BY point_cost"
    ))
    return [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "type": r["type"],
            "point_cost": r["point_cost"],
            "asset_url": r["asset_url"],
            "exclusive_season_id": str(r["exclusive_season_id"]) if r["exclusive_season_id"] else None,
            "exclusive_top_n": r["exclusive_top_n"],
        }
        for r in result.mappings().all()
    ]


@router.post("/purchase/{item_id}")
async def purchase_item(
    item_id: UUID,
    session: AsyncSession = Depends(get_session),
    user=Depends(require_dev_auth),
):
    item = (await session.execute(text(
        "SELECT id, point_cost, active, exclusive_season_id, exclusive_top_n FROM league_store_items WHERE id = :id"
    ), {"id": str(item_id)})).mappings().one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if not item["active"]:
        raise HTTPException(status_code=410, detail="Item no longer available")
    if item["exclusive_season_id"] is not None:
        raise HTTPException(status_code=403, detail="This is an exclusive item and cannot be purchased")

    balance = (await session.execute(text(
        "SELECT COALESCE(SUM(delta), 0) FROM league_points_ledger WHERE engineer_id = :uid"
    ), {"uid": user["user_id"]})).scalar()
    if int(balance) < item["point_cost"]:
        raise HTTPException(status_code=402, detail="Insufficient points balance")

    already_owned = (await session.execute(text(
        "SELECT COUNT(*) FROM league_purchases WHERE engineer_id = :uid AND item_id = :iid"
    ), {"uid": user["user_id"], "iid": str(item_id)})).scalar()
    if already_owned:
        raise HTTPException(status_code=409, detail="Item already owned")

    await session.execute(text(
        "INSERT INTO league_purchases (engineer_id, item_id) VALUES (:uid, :iid)"
    ), {"uid": user["user_id"], "iid": str(item_id)})
    await session.execute(text("""
        INSERT INTO league_points_ledger (engineer_id, delta, reason, ref_id)
        VALUES (:uid, :delta, 'store_purchase', :ref)
    """), {"uid": user["user_id"], "delta": -item["point_cost"], "ref": str(item_id)})
    await session.commit()

    new_balance = int(balance) - item["point_cost"]
    return {"item_id": str(item_id), "new_balance": new_balance}


@router.get("/owned")
async def my_items(session: AsyncSession = Depends(get_session), user=Depends(require_dev_auth)):
    result = await session.execute(text("""
        SELECT si.id, si.name, si.type, si.asset_url, p.purchased_at
        FROM league_purchases p
        JOIN league_store_items si ON si.id = p.item_id
        WHERE p.engineer_id = :uid
        ORDER BY p.purchased_at DESC
    """), {"uid": user["user_id"]})
    return [
        {"id": str(r["id"]), "name": r["name"], "type": r["type"],
         "asset_url": r["asset_url"], "purchased_at": r["purchased_at"].isoformat()}
        for r in result.mappings().all()
    ]
```

- [ ] **Step 3: Add router + run tests**

```python
# Add to app/main.py:
from app.routers import store as store_router
app.include_router(store_router.router)
```

```bash
cd /home/bntp/repos/ai-gw/services/league
pytest tests/test_store.py -v
```
Expected: all PASSED

- [ ] **Step 4: Commit**

```bash
git add services/league/app/routers/store.py services/league/tests/test_store.py services/league/app/main.py
git commit -m "feat(league): store router — item catalogue, purchase, points balance"
```

---

## Task 10: Challenge Proposals Router

**Files:**
- Create: `services/league/app/routers/proposals.py`
- Modify: `services/league/app/main.py`

- [ ] **Step 1: Write `app/routers/proposals.py`**

```python
# services/league/app/routers/proposals.py
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_auth, require_dev_auth
from app.db import get_session

router = APIRouter(prefix="/proposals", tags=["proposals"])


class ProposalCreate(BaseModel):
    title: str
    goal: str
    notes: str = ""


class ProposalReview(BaseModel):
    status: str  # "approved" or "rejected"
    reviewer_notes: str = ""


@router.get("")
async def list_proposals(
    session: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin_auth),
):
    result = await session.execute(text("""
        SELECT p.*, u.display_name AS proposer_name
        FROM league_challenge_proposals p
        JOIN users u ON u.id = p.proposed_by
        ORDER BY p.created_at DESC
    """))
    return [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "goal": r["goal"],
            "notes": r["notes"],
            "status": r["status"],
            "proposer_name": r["proposer_name"],
            "proposed_by": str(r["proposed_by"]),
            "reviewed_by": str(r["reviewed_by"]) if r["reviewed_by"] else None,
            "reviewer_notes": r["reviewer_notes"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in result.mappings().all()
    ]


@router.post("", status_code=201)
async def create_proposal(
    body: ProposalCreate,
    session: AsyncSession = Depends(get_session),
    user=Depends(require_dev_auth),
):
    result = await session.execute(text("""
        INSERT INTO league_challenge_proposals (proposed_by, title, goal, notes)
        VALUES (:uid, :title, :goal, :notes)
        RETURNING id
    """), {"uid": user["user_id"], "title": body.title, "goal": body.goal, "notes": body.notes})
    await session.commit()
    return {"id": str(result.scalar()), "status": "proposed"}


@router.patch("/{proposal_id}/review")
async def review_proposal(
    proposal_id: UUID,
    body: ProposalReview,
    session: AsyncSession = Depends(get_session),
    admin=Depends(require_admin_auth),
):
    if body.status not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="status must be 'approved' or 'rejected'")
    result = await session.execute(text("""
        UPDATE league_challenge_proposals
        SET status = :status, reviewed_by = :reviewer, reviewer_notes = :notes
        WHERE id = :id
        RETURNING id, status
    """), {
        "status": body.status,
        "reviewer": admin["user_id"],
        "notes": body.reviewer_notes,
        "id": str(proposal_id),
    })
    await session.commit()
    row = result.mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return {"id": str(row["id"]), "status": row["status"]}
```

- [ ] **Step 2: Add router + verify service starts**

```python
# Add to app/main.py:
from app.routers import proposals as proposals_router
app.include_router(proposals_router.router)
```

```bash
cd /home/bntp/repos/ai-gw/services/league
DEV_BYPASS_AUTH=true ENVIRONMENT=development python3 -c "from app.main import app; print([r.path for r in app.routes])"
```
Expected: list of all routes including `/proposals`, `/store/...`, `/seasons`, etc.

- [ ] **Step 3: Run full test suite**

```bash
cd /home/bntp/repos/ai-gw/services/league
pytest tests/ -v --tb=short
```
Expected: all PASSED across all test files

- [ ] **Step 4: Commit**

```bash
git add services/league/app/routers/proposals.py services/league/app/main.py
git commit -m "feat(league): proposals router — community challenge submissions with admin review"
```

---

## Task 11: Docker-Compose Wiring

**Files:**
- Modify: `infra/docker-compose.yml`

- [ ] **Step 1: Add `league:` service to docker-compose.yml**

Find the block immediately after the `admin:` service definition and add:

```yaml
  league:
    build:
      context: ../services/league
    ports:
      - "127.0.0.1:8010:8010"
    env_file: ../.env
    environment:
      ENVIRONMENT: development
      DATABASE_URL: "postgresql+asyncpg://aigateway:aigateway@postgres:5432/aigateway"
      REDIS_URL: "redis://redis:6379/0"
      LITELLM_URL: "http://litellm:8003"
      DEV_BYPASS_AUTH: "false"
    depends_on:
      db-migrate:
        condition: service_completed_successfully
      redis:
        condition: service_healthy
      litellm:
        condition: service_started
    healthcheck:
      test: ["CMD-SHELL", "python3 -c \"import urllib.request; urllib.request.urlopen('http://localhost:8010/health')\" 2>/dev/null || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 15s
    restart: unless-stopped
```

- [ ] **Step 2: Verify compose file parses**

```bash
cd /home/bntp/repos/ai-gw
docker compose -f infra/docker-compose.yml config --quiet && echo "compose OK"
```
Expected: `compose OK` (no parse errors)

- [ ] **Step 3: Build the league service image**

```bash
cd /home/bntp/repos/ai-gw
docker compose -f infra/docker-compose.yml build league
```
Expected: Build completes without errors

- [ ] **Step 4: Run smoke test (requires full stack)**

```bash
cd /home/bntp/repos/ai-gw
docker compose -f infra/docker-compose.yml up -d postgres redis db-migrate league
sleep 15
curl -s http://localhost:8010/health
curl -s http://localhost:8010/ready
```
Expected: `{"status":"ok"}` and `{"status":"ready"}`

- [ ] **Step 5: Commit**

```bash
git add infra/docker-compose.yml
git commit -m "feat(league): wire league service into docker-compose (port 8010)"
```

---

## Task 12: Final Integration — Full Test Suite & Push

- [ ] **Step 1: Run all league service tests**

```bash
cd /home/bntp/repos/ai-gw/services/league
pytest tests/ -v --tb=short
```
Expected: all PASSED

- [ ] **Step 2: Run existing admin service tests (regression check)**

```bash
cd /home/bntp/repos/ai-gw
pytest services/admin/ services/auth/ -v --tb=short -q
```
Expected: all PASSED (no regressions)

- [ ] **Step 3: Run ruff linting on league service**

```bash
cd /home/bntp/repos/ai-gw
ruff check services/league/
ruff format services/league/ --check
```
Expected: no errors (fix any that appear before committing)

- [ ] **Step 4: Push branch**

```bash
git push origin feature/ai-league
```

---

## Known Limitations (out of scope for this plan)

- **Creativity score** is seeded at 50 (neutral) for all submissions. Full creativity scoring (embedding-distance from the submission centroid) requires calling the litellm embeddings endpoint in batch after the challenge closes. This is a future enhancement — add a `POST /challenges/{id}/score-creativity` admin endpoint in a follow-up task.
- **Median normalisation** for token efficiency, speed, and cost uses hardcoded seed values (500 tokens, 300ms, scaled cost). At scale, these should be computed from real submission medians per challenge. Add a background job to update medians after each challenge closes.
- **LLM-as-judge quality scoring** for open-ended challenges is not implemented; only exact match is. Add a `judgment_mode` field to challenges (`exact` or `llm_judge`) and implement the LLM-judge path as a follow-on task.

## What Comes Next (separate plans)

Once this plan is complete and merged:

- **Plan 2:** Admin portal league management UI (season control, challenge builder, community proposals queue, store editor) — pages in `apps/admin/`
- **Plan 3:** Developer portal league section (active challenges, submission flow, leaderboard, store + profile) — pages in `apps/portal/`
