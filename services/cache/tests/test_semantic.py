"""Tests for app.semantic: get, set, circuit breaker, team isolation.

Uses a real PostgreSQL container (pgvector/pgvector:pg16) so the HNSW index
and cosine-distance operator are exercised against the actual driver.  The
container starts once per module; each test function gets a clean table via
DELETE in the pool fixture.

Run with:
    cd services/cache
    pytest tests/test_semantic.py -v --tb=short
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import asyncpg
import pytest
import pytest_asyncio
from app.semantic import (  # noqa: E402
    _emb_to_str,
    get,
    is_circuit_open,
    record_embedding_failure,
    reset_circuit,
)
from app.semantic import set as sem_set  # noqa: E402
from testcontainers.postgres import PostgresContainer

pytestmark = pytest.mark.asyncio(loop_scope="module")

# ---------------------------------------------------------------------------
# Test table DDL — uses vector(3) for small test embeddings
# ---------------------------------------------------------------------------

_DDL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS cache_entries (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id     TEXT        NOT NULL,
    project_id  TEXT        NOT NULL,
    embedding   vector(3)   NOT NULL,
    response    JSONB       NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cache_entries_embedding
    ON cache_entries USING hnsw (embedding vector_cosine_ops);
"""

TEAM = "team1"
PROJECT = "proj1"

# ---------------------------------------------------------------------------
# Module-scoped container + pool
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def pg_container():
    with PostgresContainer("pgvector/pgvector:pg16") as postgres:
        yield postgres


def _asyncpg_url(container: PostgresContainer) -> str:
    return container.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def pool(pg_container):
    url = _asyncpg_url(pg_container)
    p = await asyncpg.create_pool(url, min_size=1, max_size=3)
    await p.execute(_DDL)
    yield p
    await p.close()


# ---------------------------------------------------------------------------
# Per-test cleanup + open Redis mock
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(loop_scope="module", autouse=True)
async def clean_table(pool):
    yield
    await pool.execute("DELETE FROM cache_entries")


def _open_redis() -> AsyncMock:
    """Return an AsyncMock Redis with the circuit breaker key absent."""
    redis = AsyncMock()
    redis.exists = AsyncMock(return_value=0)
    return redis


def _closed_redis() -> AsyncMock:
    """Return an AsyncMock Redis with the circuit breaker key present (open)."""
    redis = AsyncMock()
    redis.exists = AsyncMock(return_value=1)
    return redis


# ---------------------------------------------------------------------------
# _emb_to_str — pure helper
# ---------------------------------------------------------------------------


def test_emb_to_str_encodes_floats():
    assert _emb_to_str([1.0, 2.0, 3.0]) == "[1.0,2.0,3.0]"


def test_emb_to_str_single_element():
    assert _emb_to_str([0.5]) == "[0.5]"


# ---------------------------------------------------------------------------
# semantic.get — pgvector HNSW lookup
# ---------------------------------------------------------------------------


class TestSemanticGet:
    async def test_empty_table_returns_none_zero_score(self, pool):
        result, score = await get([1.0, 0.0, 0.0], 0.9, pool, _open_redis(), TEAM, PROJECT)
        assert result is None
        assert score == 0.0

    async def test_identical_embedding_returns_response_with_score_one(self, pool):
        resp = {"choices": [{"message": {"content": "hello"}}]}
        redis = _open_redis()
        await sem_set([1.0, 0.0, 0.0], resp, 3600, pool, redis, TEAM, PROJECT)

        result, score = await get([1.0, 0.0, 0.0], 0.9, pool, _open_redis(), TEAM, PROJECT)

        assert result == resp
        assert score >= 0.99

    async def test_below_threshold_returns_none_with_near_miss_score(self, pool):
        resp = {"choices": [{"message": {"content": "x"}}]}
        redis = _open_redis()
        # Store [1,0,0]; query with orthogonal [0,1,0] → cosine similarity ≈ 0
        await sem_set([1.0, 0.0, 0.0], resp, 3600, pool, redis, TEAM, PROJECT)

        result, score = await get([0.0, 1.0, 0.0], 0.9, pool, _open_redis(), TEAM, PROJECT)

        assert result is None
        assert score < 0.9  # near-miss score is low (orthogonal)

    async def test_near_miss_score_is_positive_when_entry_exists(self, pool):
        resp = {"choices": []}
        redis = _open_redis()
        # Store embedding similar but not above threshold
        await sem_set([1.0, 0.0, 0.0], resp, 3600, pool, redis, TEAM, PROJECT)

        # Slightly off angle: not identical but has some similarity
        _, score = await get([0.9, 0.4, 0.0], 0.99, pool, _open_redis(), TEAM, PROJECT)

        assert score > 0  # near-miss score should be non-zero

    async def test_expired_entry_not_returned(self, pool):
        resp = {"choices": [{"message": {"content": "expired"}}]}
        # Bypass the set() TTL jitter by inserting directly with past expires_at
        await pool.execute(
            """
            INSERT INTO cache_entries (team_id, project_id, embedding, response, expires_at)
            VALUES ($1, $2, $3::vector, $4::jsonb, $5)
            """,
            TEAM,
            PROJECT,
            _emb_to_str([1.0, 0.0, 0.0]),
            json.dumps(resp),
            datetime.now(timezone.utc) - timedelta(seconds=1),
        )

        result, score = await get([1.0, 0.0, 0.0], 0.9, pool, _open_redis(), TEAM, PROJECT)

        assert result is None
        assert score == 0.0

    async def test_circuit_open_returns_none_without_db_query(self, pool):
        result, score = await get([1.0, 0.0, 0.0], 0.9, pool, _closed_redis(), TEAM, PROJECT)
        assert result is None
        assert score == 0.0


# ---------------------------------------------------------------------------
# Team / project namespace isolation
# ---------------------------------------------------------------------------


class TestTeamNamespace:
    async def test_different_teams_do_not_share_entries(self, pool):
        resp_a = {"choices": [{"message": {"content": "team A"}}]}
        redis = _open_redis()
        await sem_set([1.0, 0.0, 0.0], resp_a, 3600, pool, redis, "teamA", "proj1")

        # teamB has no entries — should not see teamA's response
        result, _ = await get([1.0, 0.0, 0.0], 0.9, pool, _open_redis(), "teamB", "proj1")
        assert result is None

    async def test_different_projects_do_not_share_entries(self, pool):
        resp_p1 = {"choices": [{"message": {"content": "project 1"}}]}
        redis = _open_redis()
        await sem_set([1.0, 0.0, 0.0], resp_p1, 3600, pool, redis, TEAM, "proj1")

        result, _ = await get([1.0, 0.0, 0.0], 0.9, pool, _open_redis(), TEAM, "proj2")
        assert result is None


# ---------------------------------------------------------------------------
# semantic.set — TTL jitter
# ---------------------------------------------------------------------------


class TestSemanticSet:
    async def test_ttl_jitter_within_ten_percent(self, pool):
        base_ttl = 1000
        redis = _open_redis()
        await sem_set([1.0, 0.0, 0.0], {"choices": []}, base_ttl, pool, redis, TEAM, PROJECT)

        row = await pool.fetchrow(
            "SELECT expires_at FROM cache_entries WHERE team_id = $1 AND project_id = $2",
            TEAM,
            PROJECT,
        )
        assert row is not None
        now = datetime.now(timezone.utc)
        actual_ttl = (row["expires_at"] - now).total_seconds()
        assert base_ttl * 0.9 - 2 <= actual_ttl <= base_ttl * 1.1 + 2

    async def test_circuit_open_skips_insert(self, pool):
        await sem_set([1.0, 0.0, 0.0], {"choices": []}, 60, pool, _closed_redis(), TEAM, PROJECT)

        count = await pool.fetchval(
            "SELECT COUNT(*) FROM cache_entries WHERE team_id = $1 AND project_id = $2",
            TEAM,
            PROJECT,
        )
        assert count == 0

    async def test_tool_call_response_round_trips(self, pool):
        tool_resp = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_123",
                                "type": "function",
                                "function": {"name": "get_weather", "arguments": '{"city":"NYC"}'},
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }
        redis = _open_redis()
        await sem_set([1.0, 0.0, 0.0], tool_resp, 3600, pool, redis, TEAM, PROJECT)

        result, score = await get([1.0, 0.0, 0.0], 0.9, pool, _open_redis(), TEAM, PROJECT)

        assert result is not None
        tc = result["choices"][0]["message"]["tool_calls"][0]
        assert tc["function"]["name"] == "get_weather"
        assert score >= 0.99


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    async def test_record_failure_increments_counter(self):
        from app import semantic

        before = semantic._circuit_failures
        semantic._circuit_failures = 0
        redis = AsyncMock()
        redis.set = AsyncMock()
        record_embedding_failure(redis)
        assert semantic._circuit_failures == 1
        semantic._circuit_failures = before  # restore

    async def test_is_circuit_open_true_when_key_exists(self):
        redis = _closed_redis()
        assert await is_circuit_open(redis) is True

    async def test_is_circuit_open_false_when_key_absent(self):
        redis = _open_redis()
        assert await is_circuit_open(redis) is False

    async def test_reset_circuit_clears_counter(self):
        from app import semantic

        semantic._circuit_failures = 10
        redis = AsyncMock()
        redis.delete = AsyncMock()
        await reset_circuit(redis)
        assert semantic._circuit_failures == 0
