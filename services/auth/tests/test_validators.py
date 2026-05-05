import hashlib

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, MagicMock, patch

from app.rate_limiter import check_rate_limit
from app.validators.api_key import validate_api_key


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.incr = AsyncMock(return_value=1)
    redis.expire = AsyncMock()
    return redis


@pytest.fixture
def mock_db():
    db = AsyncMock()
    return db


async def test_api_key_valid(mock_db):
    key = "sk-test-key-123"
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    mock_db.fetchrow = AsyncMock(return_value={"team_id": "team-1", "project_id": None})

    result = await validate_api_key(key, mock_db)

    mock_db.fetchrow.assert_awaited_once()
    assert result["team_id"] == "team-1"


async def test_api_key_invalid(mock_db):
    mock_db.fetchrow = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await validate_api_key("sk-bad-key", mock_db)

    assert exc_info.value.status_code == 401


async def test_rate_limit_allows_under_limit(mock_redis):
    mock_redis.incr = AsyncMock(return_value=1)
    await check_rate_limit("team-1", "claude-3-5-sonnet", mock_redis, rpm_limit=100)


async def test_rate_limit_blocks_over_limit(mock_redis):
    mock_redis.incr = AsyncMock(return_value=101)

    with pytest.raises(HTTPException) as exc_info:
        await check_rate_limit("team-1", "claude-3-5-sonnet", mock_redis, rpm_limit=100)

    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers
