import json
from unittest.mock import AsyncMock

import pytest
from app import exact

TEAM = "team1"
PROJECT = "proj1"


@pytest.fixture
def mock_redis():
    return AsyncMock()


async def test_exact_cache_hit(mock_redis):
    prompt = {"messages": [{"role": "user", "content": "hello"}]}
    response = {"choices": [{"message": {"content": "hi"}}]}
    mock_redis.get = AsyncMock(return_value=json.dumps(response))

    result = await exact.get(prompt, mock_redis, team_id=TEAM, project_id=PROJECT)
    assert result == response


async def test_exact_cache_miss(mock_redis):
    mock_redis.get = AsyncMock(return_value=None)

    result = await exact.get({"messages": []}, mock_redis, team_id=TEAM, project_id=PROJECT)
    assert result is None


async def test_exact_cache_set(mock_redis):
    mock_redis.setex = AsyncMock()
    prompt = {"messages": [{"role": "user", "content": "hello"}]}
    response = {"choices": []}

    await exact.set(prompt, response, ttl=3600, redis=mock_redis, team_id=TEAM, project_id=PROJECT)
    mock_redis.setex.assert_awaited_once()


async def test_redis_failure_is_treated_as_miss(mock_redis):
    mock_redis.get = AsyncMock(side_effect=Exception("Redis down"))

    with pytest.raises(Exception, match="Redis down"):
        await exact.get({"messages": []}, mock_redis, team_id=TEAM, project_id=PROJECT)


async def test_key_includes_team_and_project_namespace(mock_redis):
    mock_redis.setex = AsyncMock()
    prompt = {"messages": [{"role": "user", "content": "hello"}]}

    await exact.set(prompt, {}, ttl=60, redis=mock_redis, team_id=TEAM, project_id=PROJECT)

    key_used = mock_redis.setex.call_args[0][0]
    assert key_used.startswith(f"exact:{TEAM}:{PROJECT}:")


async def test_different_teams_produce_different_keys(mock_redis):
    mock_redis.setex = AsyncMock()
    prompt = {"messages": [{"role": "user", "content": "same prompt"}]}

    await exact.set(prompt, {}, ttl=60, redis=mock_redis, team_id="teamA", project_id="proj1")
    key_a = mock_redis.setex.call_args[0][0]

    mock_redis.setex.reset_mock()

    await exact.set(prompt, {}, ttl=60, redis=mock_redis, team_id="teamB", project_id="proj1")
    key_b = mock_redis.setex.call_args[0][0]

    assert key_a != key_b
    assert "teamA" in key_a
    assert "teamB" in key_b
