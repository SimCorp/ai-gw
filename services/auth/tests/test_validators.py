from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.rate_limiter import check_rate_limit
from app.validators.api_key import validate_api_key
from fastapi import HTTPException


def _make_pipeline_redis(incr_result: int) -> AsyncMock:
    """Build a mock Redis whose pipeline().execute() returns [incr_result, True]."""
    pipe = AsyncMock()
    pipe.incr = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = AsyncMock(return_value=[incr_result, True])

    @asynccontextmanager
    async def _pipeline(transaction=False):
        yield pipe

    redis = AsyncMock()
    redis.pipeline = _pipeline
    return redis


@pytest.fixture
def mock_db():
    db = AsyncMock()
    return db


async def test_api_key_valid(mock_db):
    key = "sk-test-key-123"
    mock_db.fetchrow = AsyncMock(return_value={"id": "key-uuid-1", "team_id": "team-1", "project_id": None})

    result = await validate_api_key(key, mock_db)

    mock_db.fetchrow.assert_awaited_once()
    assert result["team_id"] == "team-1"


async def test_api_key_invalid(mock_db):
    mock_db.fetchrow = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await validate_api_key("sk-bad-key", mock_db)

    assert exc_info.value.status_code == 401


async def test_rate_limit_allows_under_limit():
    await check_rate_limit("team-1", "claude-3-5-sonnet", _make_pipeline_redis(1), rpm_limit=100)


async def test_rate_limit_blocks_over_limit():
    with pytest.raises(HTTPException) as exc_info:
        await check_rate_limit(
            "team-1", "claude-3-5-sonnet", _make_pipeline_redis(101), rpm_limit=100
        )

    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers
