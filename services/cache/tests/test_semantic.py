"""Tests for app.semantic: _cosine, get, and set."""
import json
import math
from unittest.mock import AsyncMock, call, patch

import pytest

from app.semantic import _cosine, get, set as sem_set


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

class TestSemanticGet:
    async def test_no_keys_returns_none(self):
        redis = AsyncMock()
        redis.keys = AsyncMock(return_value=[])

        result = await get([0.1, 0.2], threshold=0.9, redis=redis)

        assert result is None

    async def test_key_above_threshold_returns_cached_response(self):
        stored_emb = [1.0, 0.0]
        query_emb = [1.0, 0.0]  # identical → cosine = 1.0
        cached_resp = {"choices": [{"message": {"content": "cached"}}]}

        redis = AsyncMock()
        redis.keys = AsyncMock(return_value=["sem:abc:emb"])
        # First get → embedding bytes; second get → response bytes
        redis.get = AsyncMock(
            side_effect=[
                json.dumps(stored_emb),       # "sem:abc:emb"
                json.dumps(cached_resp),       # "sem:abc:resp"
            ]
        )

        result = await get(query_emb, threshold=0.9, redis=redis)

        assert result == cached_resp

    async def test_key_below_threshold_returns_none(self):
        stored_emb = [0.0, 1.0]   # orthogonal to query
        query_emb = [1.0, 0.0]

        redis = AsyncMock()
        redis.keys = AsyncMock(return_value=["sem:abc:emb"])
        redis.get = AsyncMock(return_value=json.dumps(stored_emb))

        result = await get(query_emb, threshold=0.9, redis=redis)

        assert result is None

    async def test_picks_best_match_among_multiple_keys(self):
        query = [1.0, 0.0]
        poor_match = [0.0, 1.0]      # orthogonal → 0.0
        good_match = [0.99, 0.14]    # near-identical → close to 1.0
        best_resp = {"choices": [{"message": {"content": "best"}}]}

        redis = AsyncMock()
        redis.keys = AsyncMock(return_value=["sem:poor:emb", "sem:best:emb"])

        async def _get(key):
            if key == "sem:poor:emb":
                return json.dumps(poor_match)
            if key == "sem:best:emb":
                return json.dumps(good_match)
            if key == "sem:best:resp":
                return json.dumps(best_resp)
            return None

        redis.get = AsyncMock(side_effect=_get)

        result = await get(query, threshold=0.9, redis=redis)

        assert result == best_resp

    async def test_missing_response_key_returns_none(self):
        """If the :emb key matches but :resp is gone (TTL race), return None."""
        stored_emb = [1.0, 0.0]
        query_emb = [1.0, 0.0]

        redis = AsyncMock()
        redis.keys = AsyncMock(return_value=["sem:abc:emb"])

        async def _get(key):
            if key == "sem:abc:emb":
                return json.dumps(stored_emb)
            # :resp key has already expired
            return None

        redis.get = AsyncMock(side_effect=_get)

        result = await get(query_emb, threshold=0.9, redis=redis)

        assert result is None


# ---------------------------------------------------------------------------
# semantic.set — writes two Redis keys with TTL
# ---------------------------------------------------------------------------

class TestSemanticSet:
    async def test_writes_emb_and_resp_keys_with_ttl(self):
        redis = AsyncMock()
        redis.setex = AsyncMock()

        embedding = [0.1, 0.2, 0.3]
        response = {"choices": []}
        ttl = 1800

        await sem_set(embedding, response, ttl, redis)

        assert redis.setex.await_count == 2
        calls = redis.setex.call_args_list

        # Gather the key names from positional args
        keys_written = [c[0][0] for c in calls]
        ttls_written = [c[0][1] for c in calls]

        emb_keys = [k for k in keys_written if ":emb" in k]
        resp_keys = [k for k in keys_written if ":resp" in k]

        assert len(emb_keys) == 1, "Expected exactly one :emb key"
        assert len(resp_keys) == 1, "Expected exactly one :resp key"
        assert all(t == ttl for t in ttls_written), "Both keys must use the supplied TTL"

    async def test_emb_and_resp_share_same_uuid(self):
        redis = AsyncMock()
        redis.setex = AsyncMock()

        await sem_set([1.0, 2.0], {"choices": []}, 600, redis)

        calls = redis.setex.call_args_list
        keys = [c[0][0] for c in calls]
        # Extract the UUID portion: "sem:{uuid}:emb" / "sem:{uuid}:resp"
        prefixed = [k.split(":") for k in keys]
        uuids = {parts[1] for parts in prefixed}
        assert len(uuids) == 1, "Both keys must share the same entry UUID"

    async def test_stored_embedding_is_json_serialisable(self):
        stored_values = {}

        async def _setex(key, ttl, value):
            stored_values[key] = value

        redis = AsyncMock()
        redis.setex = AsyncMock(side_effect=_setex)

        emb = [0.5, 0.6, 0.7]
        await sem_set(emb, {"choices": []}, 60, redis)

        emb_key = next(k for k in stored_values if ":emb" in k)
        assert json.loads(stored_values[emb_key]) == emb
