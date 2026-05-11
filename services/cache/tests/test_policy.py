"""Tests for app.policy.get_policy."""
from unittest.mock import AsyncMock

import pytest

from app.config import settings as _defaults
from app.policy import CachePolicy, get_policy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _redis_with(data: dict) -> AsyncMock:
    """Return a Redis mock whose hgetall always yields `data`."""
    redis = AsyncMock()
    redis.hgetall = AsyncMock(return_value=data)
    return redis


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetPolicy:
    async def test_redis_has_policy_for_team_returns_correct_values(self):
        redis = _redis_with({
            "ttl_seconds": "7200",
            "similarity_threshold": "0.85",
            "opt_out": "false",
            "embedding_model": "text-embedding-ada-002",
        })

        policy = await get_policy("team-42", None, redis)

        assert isinstance(policy, CachePolicy)
        assert policy.ttl_seconds == 7200
        assert policy.similarity_threshold == pytest.approx(0.85)
        assert policy.opt_out is False
        assert policy.embedding_model == "text-embedding-ada-002"

    async def test_redis_empty_returns_defaults(self):
        redis = _redis_with({})

        policy = await get_policy("team-42", None, redis)

        assert policy.ttl_seconds == _defaults.default_ttl_seconds
        assert policy.similarity_threshold == pytest.approx(_defaults.default_similarity_threshold)
        assert policy.opt_out is False
        assert policy.embedding_model == _defaults.embedding_model

    async def test_opt_out_true_string_sets_opt_out_true(self):
        redis = _redis_with({"opt_out": "true"})

        policy = await get_policy("team-99", None, redis)

        assert policy.opt_out is True

    async def test_opt_out_false_string_sets_opt_out_false(self):
        redis = _redis_with({"opt_out": "false"})

        policy = await get_policy("team-99", None, redis)

        assert policy.opt_out is False

    async def test_opt_out_mixed_case_true_handled(self):
        """The implementation lower-cases before comparison, so 'True' must work."""
        redis = _redis_with({"opt_out": "True"})

        policy = await get_policy("team-1", None, redis)

        assert policy.opt_out is True

    async def test_project_id_uses_team_project_key(self):
        redis = _redis_with({})

        await get_policy("team-7", "proj-abc", redis)

        redis.hgetall.assert_awaited_once_with("policy:team-7:proj-abc")

    async def test_no_project_id_uses_team_key(self):
        redis = _redis_with({})

        await get_policy("team-7", None, redis)

        redis.hgetall.assert_awaited_once_with("policy:team-7")

    async def test_partial_redis_data_falls_back_to_defaults_for_missing_fields(self):
        """Only ttl_seconds provided; remaining fields fall back to defaults."""
        redis = _redis_with({"ttl_seconds": "120"})

        policy = await get_policy("team-1", None, redis)

        assert policy.ttl_seconds == 120
        assert policy.similarity_threshold == pytest.approx(_defaults.default_similarity_threshold)
        assert policy.opt_out is False
        assert policy.embedding_model == _defaults.embedding_model

    async def test_returns_cache_policy_dataclass_instance(self):
        redis = _redis_with({})

        policy = await get_policy("any-team", None, redis)

        assert isinstance(policy, CachePolicy)

    async def test_conversation_turn_limit_default_is_3(self):
        redis = _redis_with({})

        policy = await get_policy("team-1", None, redis)

        assert policy.conversation_turn_limit == 3

    async def test_conversation_turn_limit_parsed_from_redis(self):
        redis = _redis_with({"conversation_turn_limit": "5"})

        policy = await get_policy("team-1", None, redis)

        assert policy.conversation_turn_limit == 5
        assert isinstance(policy.conversation_turn_limit, int)

    async def test_budget_hard_cap_default_is_zero(self):
        redis = _redis_with({})

        policy = await get_policy("team-1", None, redis)

        assert policy.budget_hard_cap == 0.0

    async def test_budget_hard_cap_parsed_as_float(self):
        redis = _redis_with({"budget_hard_cap": "75.50"})

        policy = await get_policy("team-1", None, redis)

        assert policy.budget_hard_cap == pytest.approx(75.50)
        assert isinstance(policy.budget_hard_cap, float)

    async def test_embedding_circuit_open_default_false(self):
        redis = _redis_with({})

        policy = await get_policy("team-1", None, redis)

        assert policy.embedding_circuit_open is False

    async def test_embedding_circuit_open_true_string(self):
        redis = _redis_with({"embedding_circuit_open": "true"})

        policy = await get_policy("team-1", None, redis)

        assert policy.embedding_circuit_open is True

    async def test_embedding_circuit_open_false_string(self):
        redis = _redis_with({"embedding_circuit_open": "False"})

        policy = await get_policy("team-1", None, redis)

        assert policy.embedding_circuit_open is False
