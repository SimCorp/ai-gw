"""Tests for app.semantic: _cosine, get, and set."""
import json
import math
from unittest.mock import AsyncMock, call, patch

import pytest

from app.semantic import (
    _cosine,
    get,
    set as sem_set,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEAM = "team1"
PROJECT = "proj1"


# ---------------------------------------------------------------------------
# _cosine — pure function, no I/O
# ---------------------------------------------------------------------------

class TestCosine:
    def test_identical_vectors_return_one(self):
        v = [1.0, 2.0, 3.0]
        score = _cosine(v, v)
        assert math.isclose(score, 1.0, abs_tol=1e-9)

    def test_orthogonal_vectors_return_zero(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert math.isclose(_cosine(a, b), 0.0, abs_tol=1e-9)

    def test_zero_vector_returns_zero_no_division_error(self):
        zero = [0.0, 0.0, 0.0]
        v = [1.0, 2.0, 3.0]
        # Neither direction should raise; both must return 0.0
        assert _cosine(zero, v) == 0.0
        assert _cosine(v, zero) == 0.0
        assert _cosine(zero, zero) == 0.0

    def test_opposite_vectors_return_minus_one(self):
        v = [1.0, 0.0]
        neg = [-1.0, 0.0]
        assert math.isclose(_cosine(v, neg), -1.0, abs_tol=1e-9)

    def test_similarity_between_zero_and_one_for_non_orthogonal(self):
        a = [1.0, 1.0]
        b = [1.0, 0.0]
        score = _cosine(a, b)
        assert 0.0 < score < 1.0


# ---------------------------------------------------------------------------
# semantic.get — scans Redis keys, returns best match or None
# ---------------------------------------------------------------------------

def _open_redis() -> AsyncMock:
    """Return an AsyncMock Redis with the circuit breaker key absent (circuit closed)."""
    redis = AsyncMock()
    redis.exists = AsyncMock(return_value=0)
    return redis


class TestSemanticGet:
    def setup_method(self):
        pass  # circuit state lives in Redis; individual tests mock redis.exists=0

    async def test_no_keys_returns_none(self):
        redis = _open_redis()
        redis.keys = AsyncMock(return_value=[])

        result = await get([0.1, 0.2], threshold=0.9, redis=redis, team_id=TEAM, project_id=PROJECT)

        assert result is None

    async def test_key_above_threshold_returns_cached_response(self):
        stored_emb = [1.0, 0.0]
        query_emb = [1.0, 0.0]  # identical → cosine = 1.0
        cached_resp = {"choices": [{"message": {"content": "cached"}}]}

        redis = _open_redis()
        redis.keys = AsyncMock(return_value=[f"sem:{TEAM}:{PROJECT}:abc:emb"])
        # First get → embedding bytes; second get → response bytes
        redis.get = AsyncMock(
            side_effect=[
                json.dumps(stored_emb),       # "sem:team1:proj1:abc:emb"
                json.dumps(cached_resp),       # "sem:team1:proj1:abc:resp"
            ]
        )

        result = await get(query_emb, threshold=0.9, redis=redis, team_id=TEAM, project_id=PROJECT)

        assert result == cached_resp

    async def test_key_below_threshold_returns_none(self):
        stored_emb = [0.0, 1.0]   # orthogonal to query
        query_emb = [1.0, 0.0]

        redis = _open_redis()
        redis.keys = AsyncMock(return_value=[f"sem:{TEAM}:{PROJECT}:abc:emb"])
        redis.get = AsyncMock(return_value=json.dumps(stored_emb))

        result = await get(query_emb, threshold=0.9, redis=redis, team_id=TEAM, project_id=PROJECT)

        assert result is None

    async def test_picks_best_match_among_multiple_keys(self):
        query = [1.0, 0.0]
        poor_match = [0.0, 1.0]      # orthogonal → 0.0
        good_match = [0.99, 0.14]    # near-identical → close to 1.0
        best_resp = {"choices": [{"message": {"content": "best"}}]}

        redis = _open_redis()
        redis.keys = AsyncMock(return_value=[
            f"sem:{TEAM}:{PROJECT}:poor:emb",
            f"sem:{TEAM}:{PROJECT}:best:emb",
        ])

        async def _get(key):
            if key == f"sem:{TEAM}:{PROJECT}:poor:emb":
                return json.dumps(poor_match)
            if key == f"sem:{TEAM}:{PROJECT}:best:emb":
                return json.dumps(good_match)
            if key == f"sem:{TEAM}:{PROJECT}:best:resp":
                return json.dumps(best_resp)
            return None

        redis.get = AsyncMock(side_effect=_get)

        result = await get(query, threshold=0.9, redis=redis, team_id=TEAM, project_id=PROJECT)

        assert result == best_resp

    async def test_missing_response_key_returns_none(self):
        """If the :emb key matches but :resp is gone (TTL race), return None."""
        stored_emb = [1.0, 0.0]
        query_emb = [1.0, 0.0]

        redis = _open_redis()
        redis.keys = AsyncMock(return_value=[f"sem:{TEAM}:{PROJECT}:abc:emb"])

        async def _get(key):
            if key == f"sem:{TEAM}:{PROJECT}:abc:emb":
                return json.dumps(stored_emb)
            # :resp key has already expired
            return None

        redis.get = AsyncMock(side_effect=_get)

        result = await get(query_emb, threshold=0.9, redis=redis, team_id=TEAM, project_id=PROJECT)

        assert result is None


# ---------------------------------------------------------------------------
# semantic.set — writes two Redis keys with TTL
# ---------------------------------------------------------------------------

class TestSemanticSet:
    async def test_writes_emb_and_resp_keys_with_ttl(self):
        redis = _open_redis()
        redis.setex = AsyncMock()

        embedding = [0.1, 0.2, 0.3]
        response = {"choices": []}
        base_ttl = 1800

        await sem_set(embedding, response, base_ttl, redis, team_id=TEAM, project_id=PROJECT)

        assert redis.setex.await_count == 2
        calls = redis.setex.call_args_list

        # Gather the key names from positional args
        keys_written = [c[0][0] for c in calls]
        ttls_written = [c[0][1] for c in calls]

        emb_keys = [k for k in keys_written if ":emb" in k]
        resp_keys = [k for k in keys_written if ":resp" in k]

        assert len(emb_keys) == 1, "Expected exactly one :emb key"
        assert len(resp_keys) == 1, "Expected exactly one :resp key"

        # With jitter, TTL may vary ±10%; just check it's in reasonable range
        for t in ttls_written:
            assert base_ttl * 0.9 - 1 <= t <= base_ttl * 1.1 + 1, (
                f"TTL {t} out of ±10% range for base {base_ttl}"
            )

    async def test_emb_and_resp_share_same_uuid(self):
        redis = _open_redis()
        redis.setex = AsyncMock()

        await sem_set([1.0, 2.0], {"choices": []}, 600, redis, team_id=TEAM, project_id=PROJECT)

        calls = redis.setex.call_args_list
        keys = [c[0][0] for c in calls]
        # Extract the UUID portion: "sem:{team}:{project}:{uuid}:emb" / "sem:{team}:{project}:{uuid}:resp"
        # Split: ["sem", team, project, uuid, suffix]
        uuids = {k.split(":")[3] for k in keys}
        assert len(uuids) == 1, "Both keys must share the same entry UUID"

    async def test_stored_embedding_is_json_serialisable(self):
        stored_values = {}

        async def _setex(key, ttl, value):
            stored_values[key] = value

        redis = _open_redis()
        redis.setex = AsyncMock(side_effect=_setex)

        emb = [0.5, 0.6, 0.7]
        await sem_set(emb, {"choices": []}, 60, redis, team_id=TEAM, project_id=PROJECT)

        emb_key = next(k for k in stored_values if ":emb" in k)
        assert json.loads(stored_values[emb_key]) == emb


# ---------------------------------------------------------------------------
# Team namespace isolation
# ---------------------------------------------------------------------------

class TestTeamNamespace:
    async def test_different_teams_use_different_key_prefix(self):
        """Two teams scanning Redis must use different key patterns."""
        scanned_patterns = []

        async def _keys(pattern):
            scanned_patterns.append(pattern)
            return []

        redis = _open_redis()
        redis.keys = AsyncMock(side_effect=_keys)

        await get([1.0, 0.0], threshold=0.9, redis=redis, team_id="teamA", project_id="proj1")
        await get([1.0, 0.0], threshold=0.9, redis=redis, team_id="teamB", project_id="proj1")

        assert len(scanned_patterns) == 2
        assert scanned_patterns[0] != scanned_patterns[1]
        assert "teamA" in scanned_patterns[0]
        assert "teamB" in scanned_patterns[1]


# ---------------------------------------------------------------------------
# TTL jitter
# ---------------------------------------------------------------------------

class TestTTLJitter:
    async def test_ttl_jitter_applied(self):
        """TTL passed to setex must be within ±10% of the base TTL."""
        base_ttl = 100
        redis = _open_redis()
        redis.setex = AsyncMock()

        await sem_set([0.1, 0.2], {"choices": []}, base_ttl, redis, team_id=TEAM, project_id=PROJECT)

        calls = redis.setex.call_args_list
        ttls_used = [c[0][1] for c in calls]

        for t in ttls_used:
            assert base_ttl * 0.9 <= t <= base_ttl * 1.1, (
                f"TTL {t} is outside ±10% range of base TTL {base_ttl}"
            )


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    async def test_circuit_breaker_skips_get_when_open(self):
        """When circuit key exists in Redis, get() returns None without scanning keys."""
        redis = AsyncMock()
        redis.exists = AsyncMock(return_value=1)  # circuit open
        redis.keys = AsyncMock()

        result = await get([1.0, 0.0], threshold=0.9, redis=redis, team_id=TEAM, project_id=PROJECT)

        assert result is None
        redis.keys.assert_not_called()

    async def test_circuit_breaker_skips_set_when_open(self):
        """When circuit key exists in Redis, set() does not call redis.setex."""
        redis = AsyncMock()
        redis.exists = AsyncMock(return_value=1)  # circuit open
        redis.setex = AsyncMock()

        await sem_set([0.1], {"choices": []}, 60, redis, team_id=TEAM, project_id=PROJECT)

        redis.setex.assert_not_called()

    async def test_circuit_closed_enables_operations(self):
        """When circuit key is absent in Redis, set() proceeds normally."""
        redis = _open_redis()
        redis.setex = AsyncMock()

        await sem_set([0.1, 0.2], {"choices": []}, 60, redis, team_id=TEAM, project_id=PROJECT)

        assert redis.setex.await_count == 2

    async def test_circuit_closed_allows_get(self):
        """When circuit key is absent, get() scans Redis for matches."""
        redis = _open_redis()
        redis.keys = AsyncMock(return_value=[])

        result = await get([1.0, 0.0], threshold=0.9, redis=redis, team_id=TEAM, project_id=PROJECT)

        assert result is None
        redis.keys.assert_called_once()
