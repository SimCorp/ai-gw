import json
from unittest.mock import AsyncMock

import pytest
from app import exact


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    return redis


async def test_exact_cache_hit(mock_redis):
    prompt = {"messages": [{"role": "user", "content": "hello"}]}
    response = {"choices": [{"message": {"content": "hi"}}]}
    mock_redis.get = AsyncMock(return_value=json.dumps(response))

    result = await exact.get(prompt, mock_redis)
    assert result == response


async def test_exact_cache_miss(mock_redis):
    mock_redis.get = AsyncMock(return_value=None)

    result = await exact.get({"messages": []}, mock_redis)
    assert result is None


async def test_exact_cache_set(mock_redis):
    mock_redis.setex = AsyncMock()
    prompt = {"messages": [{"role": "user", "content": "hello"}]}
    response = {"choices": []}

    await exact.set(prompt, response, ttl=3600, redis=mock_redis)
    mock_redis.setex.assert_awaited_once()


async def test_redis_failure_is_treated_as_miss(mock_redis):
    mock_redis.get = AsyncMock(side_effect=Exception("Redis down"))

    # exact.get raises — caller should catch and treat as miss (tested at router level)
    with pytest.raises(Exception, match="Redis down"):
        await exact.get({"messages": []}, mock_redis)
