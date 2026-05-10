"""Tests for the cache service router (GET /v1/models, POST /v1/chat/completions)."""
import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport, Response as HttpxResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth_response_ok(team_id="team-1", project_id=None, key_id="key-abc"):
    """Return a mock httpx.Response that looks like a 200 auth validation."""
    return HttpxResponse(
        200,
        json={"team_id": team_id, "project_id": project_id, "key_id": key_id},
    )


def _auth_response_401():
    return HttpxResponse(401, json={"error": "Unauthorized"})


def _auth_response_429():
    return HttpxResponse(429, json={"error": "rate limit exceeded"})


def _litellm_models_response():
    return HttpxResponse(200, json={"object": "list", "data": []})


def _litellm_chat_response(content="Hello!"):
    return HttpxResponse(
        200,
        json={
            "id": "chatcmpl-test",
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        },
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def app_and_client():
    """Yield (app, client) so tests can mutate app.state.http after the fixture runs."""
    from app.main import app

    mock_redis = AsyncMock()
    mock_redis.hgetall = AsyncMock(return_value={})
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.keys = AsyncMock(return_value=[])

    mock_http = AsyncMock()

    app.state.redis = mock_redis
    app.state.http = mock_http

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield app, c


# ---------------------------------------------------------------------------
# GET /v1/models
# ---------------------------------------------------------------------------

class TestListModels:
    async def test_auth_returns_none_gives_401(self, app_and_client):
        app, client = app_and_client
        app.state.http.post = AsyncMock(return_value=_auth_response_401())

        resp = await client.get("/v1/models", headers={"Authorization": "Bearer bad-token"})

        assert resp.status_code == 401

    async def test_auth_returns_429_forwarded(self, app_and_client):
        app, client = app_and_client
        app.state.http.post = AsyncMock(return_value=_auth_response_429())

        resp = await client.get("/v1/models", headers={"Authorization": "Bearer any-token"})

        assert resp.status_code == 429

    async def test_auth_success_proxies_to_litellm(self, app_and_client):
        app, client = app_and_client
        app.state.http.post = AsyncMock(return_value=_auth_response_ok())
        app.state.http.get = AsyncMock(return_value=_litellm_models_response())

        resp = await client.get("/v1/models", headers={"Authorization": "Bearer valid-token"})

        assert resp.status_code == 200
        app.state.http.get.assert_awaited_once()
        # Make sure the forwarded request targeted the /v1/models path
        call_url = str(app.state.http.get.call_args[0][0])
        assert "/v1/models" in call_url


# ---------------------------------------------------------------------------
# POST /v1/chat/completions
# ---------------------------------------------------------------------------

CHAT_BODY = {"model": "gpt-4", "messages": [{"role": "user", "content": "ping"}]}


class TestChatCompletions:
    async def test_missing_auth_gives_401(self, app_and_client):
        # No Authorization header at all; auth service would get an empty token.
        app, client = app_and_client
        app.state.http.post = AsyncMock(return_value=_auth_response_401())

        resp = await client.post("/v1/chat/completions", json=CHAT_BODY)

        assert resp.status_code == 401

    async def test_auth_429_forwarded(self, app_and_client):
        app, client = app_and_client
        app.state.http.post = AsyncMock(return_value=_auth_response_429())

        resp = await client.post(
            "/v1/chat/completions",
            json=CHAT_BODY,
            headers={"Authorization": "Bearer limited"},
        )

        assert resp.status_code == 429

    async def test_exact_cache_hit_returns_hit_header(self, app_and_client):
        """When exact.get returns a cached response the router must return X-Cache: HIT."""
        app, client = app_and_client
        cached_body = {"choices": [{"message": {"content": "cached!"}}]}
        app.state.http.post = AsyncMock(return_value=_auth_response_ok())

        with patch("app.exact.get", new=AsyncMock(return_value=cached_body)):
            resp = await client.post(
                "/v1/chat/completions",
                json=CHAT_BODY,
                headers={"Authorization": "Bearer valid"},
            )

        assert resp.status_code == 200
        assert resp.headers.get("x-cache", "").upper() == "HIT"
        assert resp.json() == cached_body

    async def test_cache_miss_calls_litellm_returns_miss_header(self, app_and_client):
        """On a full cache miss the router forwards to LiteLLM and returns X-Cache: MISS."""
        app, client = app_and_client
        litellm_resp = _litellm_chat_response("world")

        async def _post_side_effect(url, **kwargs):
            if "validate" in url:
                return _auth_response_ok()
            return litellm_resp

        app.state.http.post = AsyncMock(side_effect=_post_side_effect)

        with patch("app.exact.get", new=AsyncMock(return_value=None)), \
             patch("app.semantic.embed", new=AsyncMock(side_effect=Exception("no embed"))):
            resp = await client.post(
                "/v1/chat/completions",
                json=CHAT_BODY,
                headers={"Authorization": "Bearer valid"},
            )

        assert resp.status_code == 200
        assert resp.headers.get("x-cache", "").upper() == "MISS"

    async def test_opt_out_skips_cache_and_calls_litellm(self, app_and_client):
        """When policy.opt_out=True the cache lookup must be skipped entirely."""
        app, client = app_and_client
        from app.policy import CachePolicy

        opt_out_policy = CachePolicy(
            ttl_seconds=3600,
            similarity_threshold=0.95,
            opt_out=True,
            embedding_model="text-embedding-3-small",
        )

        async def _post_side_effect(url, **kwargs):
            if "validate" in url:
                return _auth_response_ok()
            return _litellm_chat_response("direct")

        app.state.http.post = AsyncMock(side_effect=_post_side_effect)

        with patch("app.router.get_policy", new=AsyncMock(return_value=opt_out_policy)), \
             patch("app.exact.get", new=AsyncMock()) as mock_exact_get, \
             patch("app.semantic.get", new=AsyncMock()) as mock_sem_get:
            resp = await client.post(
                "/v1/chat/completions",
                json=CHAT_BODY,
                headers={"Authorization": "Bearer valid"},
            )

        assert resp.status_code == 200
        # Neither exact nor semantic lookup should have been called
        mock_exact_get.assert_not_awaited()
        mock_sem_get.assert_not_awaited()

    async def test_semantic_cache_hit_returns_hit_header(self, app_and_client):
        """Semantic cache hit must return X-Cache: HIT without calling LiteLLM."""
        app, client = app_and_client
        sem_cached = {"choices": [{"message": {"content": "semantic hit"}}]}

        async def _post_side_effect(url, **kwargs):
            if "validate" in url:
                return _auth_response_ok()
            # If LiteLLM is ever called the test should fail loudly.
            raise AssertionError("LiteLLM should NOT have been called on semantic hit")

        app.state.http.post = AsyncMock(side_effect=_post_side_effect)

        with patch("app.exact.get", new=AsyncMock(return_value=None)), \
             patch("app.semantic.embed", new=AsyncMock(return_value=[0.1, 0.2, 0.3])), \
             patch("app.semantic.get", new=AsyncMock(return_value=sem_cached)):
            resp = await client.post(
                "/v1/chat/completions",
                json=CHAT_BODY,
                headers={"Authorization": "Bearer valid"},
            )

        assert resp.status_code == 200
        assert resp.headers.get("x-cache", "").upper() == "HIT"
        assert resp.json() == sem_cached

    async def test_cache_miss_emits_observability_event(self, app_and_client):
        """After a LiteLLM call the router must fire a POST to the observability service."""
        app, client = app_and_client
        obs_calls = []

        async def _post_side_effect(url, **kwargs):
            if "validate" in url:
                return _auth_response_ok()
            if "/events" in url:
                obs_calls.append(url)
                return HttpxResponse(200, json={})
            return _litellm_chat_response("hi")

        app.state.http.post = AsyncMock(side_effect=_post_side_effect)

        with patch("app.exact.get", new=AsyncMock(return_value=None)), \
             patch("app.semantic.embed", new=AsyncMock(side_effect=Exception("skip"))), \
             patch("app.exact.set", new=AsyncMock()):
            resp = await client.post(
                "/v1/chat/completions",
                json=CHAT_BODY,
                headers={"Authorization": "Bearer valid"},
            )

        assert resp.status_code == 200
        # asyncio.create_task schedules the event call; drain pending tasks.
        import asyncio
        await asyncio.sleep(0)
        assert any("/events" in url for url in obs_calls), (
            "Expected an observability event POST after cache miss"
        )

    async def test_response_stored_in_exact_cache_after_miss(self, app_and_client):
        """On a successful LiteLLM response the result must be persisted via exact.set."""
        app, client = app_and_client

        async def _post_side_effect(url, **kwargs):
            if "validate" in url:
                return _auth_response_ok()
            return _litellm_chat_response("stored!")

        app.state.http.post = AsyncMock(side_effect=_post_side_effect)

        mock_exact_set = AsyncMock()
        with patch("app.exact.get", new=AsyncMock(return_value=None)), \
             patch("app.semantic.embed", new=AsyncMock(side_effect=Exception("skip"))), \
             patch("app.exact.set", new=mock_exact_set):
            resp = await client.post(
                "/v1/chat/completions",
                json=CHAT_BODY,
                headers={"Authorization": "Bearer valid"},
            )

        assert resp.status_code == 200
        mock_exact_set.assert_awaited_once()
        # Verify the stored body is the LiteLLM response (second positional arg)
        stored_body = mock_exact_set.call_args[0][1]
        assert stored_body["choices"][0]["message"]["content"] == "stored!"


# ---------------------------------------------------------------------------
# Streaming cache hits (stream: true)
# ---------------------------------------------------------------------------

STREAM_BODY = {"model": "gpt-4", "messages": [{"role": "user", "content": "ping"}], "stream": True}

_CACHED_RESPONSE = {
    "id": "chatcmpl-cached",
    "model": "gpt-4",
    "choices": [{"message": {"role": "assistant", "content": "cached!"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 3},
}


class TestStreamingCacheHits:
    async def test_exact_hit_stream_returns_sse_content_type(self, app_and_client):
        """stream:true + exact cache hit → text/event-stream response."""
        app, client = app_and_client
        app.state.http.post = AsyncMock(return_value=_auth_response_ok())

        with patch("app.exact.get", new=AsyncMock(return_value=_CACHED_RESPONSE)):
            resp = await client.post(
                "/v1/chat/completions",
                json=STREAM_BODY,
                headers={"Authorization": "Bearer valid"},
            )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        assert resp.headers.get("x-cache", "").upper() == "HIT"

    async def test_exact_hit_stream_body_contains_sse_chunks(self, app_and_client):
        """stream:true + exact cache hit → body is valid SSE with data: lines."""
        app, client = app_and_client
        app.state.http.post = AsyncMock(return_value=_auth_response_ok())

        with patch("app.exact.get", new=AsyncMock(return_value=_CACHED_RESPONSE)):
            resp = await client.post(
                "/v1/chat/completions",
                json=STREAM_BODY,
                headers={"Authorization": "Bearer valid"},
            )

        body = resp.text
        assert "data: " in body
        assert "data: [DONE]" in body
        # At least one chunk must carry the cached content
        import json as _j
        content_found = any(
            _j.loads(line[6:]).get("choices", [{}])[0].get("delta", {}).get("content") == "cached!"
            for line in body.splitlines()
            if line.startswith("data: ") and line != "data: [DONE]"
        )
        assert content_found

    async def test_exact_hit_stream_x_cache_stage_exact(self, app_and_client):
        """Exact SSE hit must carry X-Cache-Stage: exact."""
        app, client = app_and_client
        app.state.http.post = AsyncMock(return_value=_auth_response_ok())

        with patch("app.exact.get", new=AsyncMock(return_value=_CACHED_RESPONSE)):
            resp = await client.post(
                "/v1/chat/completions",
                json=STREAM_BODY,
                headers={"Authorization": "Bearer valid"},
            )

        assert resp.headers.get("x-cache-stage", "").lower() == "exact"

    async def test_semantic_hit_stream_returns_sse(self, app_and_client):
        """stream:true + semantic cache hit → text/event-stream, X-Cache: HIT."""
        app, client = app_and_client

        async def _post_side_effect(url, **kwargs):
            if "validate" in url:
                return _auth_response_ok()
            raise AssertionError("LiteLLM must not be called on semantic hit")

        app.state.http.post = AsyncMock(side_effect=_post_side_effect)

        with patch("app.exact.get", new=AsyncMock(return_value=None)), \
             patch("app.semantic.embed", new=AsyncMock(return_value=[0.1, 0.2, 0.3])), \
             patch("app.semantic.get", new=AsyncMock(return_value=_CACHED_RESPONSE)):
            resp = await client.post(
                "/v1/chat/completions",
                json=STREAM_BODY,
                headers={"Authorization": "Bearer valid"},
            )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        assert resp.headers.get("x-cache", "").upper() == "HIT"
        assert resp.headers.get("x-cache-stage", "").lower() == "semantic"
        assert "data: [DONE]" in resp.text

    async def test_nonstreaming_exact_hit_returns_json(self, app_and_client):
        """Without stream:true an exact hit must still return plain JSON."""
        app, client = app_and_client
        app.state.http.post = AsyncMock(return_value=_auth_response_ok())

        with patch("app.exact.get", new=AsyncMock(return_value=_CACHED_RESPONSE)):
            resp = await client.post(
                "/v1/chat/completions",
                json=CHAT_BODY,
                headers={"Authorization": "Bearer valid"},
            )

        assert resp.status_code == 200
        assert "application/json" in resp.headers.get("content-type", "")
        assert resp.json()["id"] == "chatcmpl-cached"
