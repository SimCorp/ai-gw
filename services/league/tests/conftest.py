# services/league/tests/conftest.py
"""Ensure the league service's app module is importable when pytest collects
from the repo root (multiple services share the 'app' package name)."""

import sys
from pathlib import Path

_SERVICE_ROOT = str(Path(__file__).parents[1])
for _k in list(sys.modules.keys()):
    if _k == "app" or _k.startswith("app."):
        del sys.modules[_k]
sys.path.insert(0, _SERVICE_ROOT)

from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

# ── in-memory SQLite async engine for tests ──────────────────────────────────
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default asyncio policy."""
    import asyncio

    return asyncio.DefaultEventLoopPolicy()


_CREATE_TABLES_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS league_seasons (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'upcoming',
    starts_at TEXT NOT NULL,
    ends_at TEXT NOT NULL,
    scoring_weights TEXT,
    season_multiplier REAL NOT NULL DEFAULT 1.0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS league_challenges (
    id TEXT PRIMARY KEY,
    season_id TEXT NOT NULL REFERENCES league_seasons(id),
    title TEXT NOT NULL,
    goal TEXT NOT NULL,
    training_inputs TEXT NOT NULL DEFAULT '[]',
    hidden_test_suite TEXT NOT NULL DEFAULT '[]',
    allowed_models TEXT NOT NULL DEFAULT '["claude-sonnet-4-6"]',
    max_tokens_budget INTEGER NOT NULL DEFAULT 4096,
    max_league_attempts INTEGER NOT NULL DEFAULT 3,
    scores_revealed_at TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    proposed_by TEXT REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS league_submissions (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    challenge_id TEXT NOT NULL REFERENCES league_challenges(id),
    engineer_id TEXT NOT NULL REFERENCES users(id),
    mode TEXT NOT NULL,
    system_prompt TEXT NOT NULL,
    tool_config TEXT NOT NULL DEFAULT '[]',
    attempt_number INTEGER NOT NULL DEFAULT 1,
    run_results TEXT,
    prompt_hash TEXT NOT NULL,
    submitted_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS league_scores (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    submission_id TEXT NOT NULL UNIQUE REFERENCES league_submissions(id),
    quality REAL NOT NULL DEFAULT 0,
    robustness REAL NOT NULL DEFAULT 0,
    token_efficiency REAL NOT NULL DEFAULT 0,
    speed REAL NOT NULL DEFAULT 0,
    cost_efficiency REAL NOT NULL DEFAULT 0,
    improvement_rate REAL NOT NULL DEFAULT 50,
    creativity REAL NOT NULL DEFAULT 50,
    composite REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS league_leaderboard (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    season_id TEXT NOT NULL,
    engineer_id TEXT NOT NULL,
    composite_score REAL NOT NULL DEFAULT 0,
    points_earned INTEGER NOT NULL DEFAULT 0,
    rank INTEGER,
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(season_id, engineer_id)
);
CREATE TABLE IF NOT EXISTS league_points_ledger (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    engineer_id TEXT NOT NULL,
    delta INTEGER NOT NULL,
    reason TEXT NOT NULL,
    ref_id TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS league_store_items (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name TEXT NOT NULL,
    description TEXT,
    cost INTEGER NOT NULL DEFAULT 0,
    category TEXT NOT NULL DEFAULT 'cosmetic',
    metadata TEXT NOT NULL DEFAULT '{}',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS league_purchases (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    engineer_id TEXT NOT NULL,
    item_id TEXT NOT NULL REFERENCES league_store_items(id),
    cost_paid INTEGER NOT NULL DEFAULT 0,
    equipped INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS league_proposals (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    season_id TEXT NOT NULL REFERENCES league_seasons(id),
    proposed_by TEXT NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    goal TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT DEFAULT (datetime('now'))
);
"""

_DROP_TABLES_DDL = [
    "DROP TABLE IF EXISTS league_proposals",
    "DROP TABLE IF EXISTS league_purchases",
    "DROP TABLE IF EXISTS league_store_items",
    "DROP TABLE IF EXISTS league_points_ledger",
    "DROP TABLE IF EXISTS league_leaderboard",
    "DROP TABLE IF EXISTS league_scores",
    "DROP TABLE IF EXISTS league_submissions",
    "DROP TABLE IF EXISTS league_challenges",
    "DROP TABLE IF EXISTS league_seasons",
    "DROP TABLE IF EXISTS users",
]


@pytest.fixture
async def db_engine():
    from sqlalchemy import text

    engine = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        for stmt in _CREATE_TABLES_DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await conn.execute(text(stmt))
    yield engine
    async with engine.begin() as conn:
        for stmt in _DROP_TABLES_DDL:
            await conn.execute(text(stmt))
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.incr = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.ping = AsyncMock(return_value=True)
    return redis


@pytest.fixture
def mock_litellm():
    """Mock httpx client for litellm calls."""
    client = AsyncMock()
    client.post = AsyncMock(
        return_value=MagicMock(
            status_code=200,
            json=lambda: {
                "choices": [{"message": {"content": "mocked response"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            },
        )
    )
    return client


@pytest.fixture
async def app_client(mock_redis, db_session):
    """FastAPI test client with mocked Redis and db session injected."""
    from app.db import get_session
    from app.main import app

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    with patch("app.main.aioredis.from_url", return_value=mock_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client

    app.dependency_overrides.clear()
