"""Tests for the cache service router (GET /v1/models, POST /v1/chat/completions)."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from httpx import Response as HttpxResponse

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

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
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

        with (
            patch("app.exact.get", new=AsyncMock(return_value=None)),
            patch("app.semantic.embed", new=AsyncMock(side_effect=Exception("no embed"))),
        ):
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

        with (
            patch("app.router.get_policy", new=AsyncMock(return_value=opt_out_policy)),
            patch("app.exact.get", new=AsyncMock()) as mock_exact_get,
            patch("app.semantic.get", new=AsyncMock()) as mock_sem_get,
        ):
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

        with (
            patch("app.exact.get", new=AsyncMock(return_value=None)),
            patch("app.semantic.embed", new=AsyncMock(return_value=[0.1, 0.2, 0.3])),
            patch("app.semantic.get", new=AsyncMock(return_value=sem_cached)),
        ):
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

        with (
            patch("app.exact.get", new=AsyncMock(return_value=None)),
            patch("app.semantic.embed", new=AsyncMock(side_effect=Exception("skip"))),
            patch("app.exact.set", new=AsyncMock()),
        ):
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
        with (
            patch("app.exact.get", new=AsyncMock(return_value=None)),
            patch("app.semantic.embed", new=AsyncMock(side_effect=Exception("skip"))),
            patch("app.exact.set", new=mock_exact_set),
        ):
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
# Input guardrails
# ---------------------------------------------------------------------------

_REDACT_RULE = {
    "id": "gr-1",
    "name": "secret-redact",
    "type": "pattern",
    "action": "redact",
    "applies_to": "input",
    "enabled": True,
    "severity": "medium",
    "config": {"patterns": ["sk-secret"], "mask": "[REDACTED]"},
}

import json as _j  # noqa: E402  (used in guardrail helpers below)


class TestInputGuardrails:
    async def test_input_redact_masks_forwarded_body(self, app_and_client):
        """A redact guardrail must mask matching text in messages before forwarding to LiteLLM."""
        app, client = app_and_client

        forwarded_bodies = []
        litellm_url_fragment = "chat/completions"

        async def _post_side_effect(url, **kwargs):
            if "validate" in url:
                return _auth_response_ok()
            if litellm_url_fragment in url:
                forwarded_bodies.append(kwargs.get("json", {}))
                return _litellm_chat_response("ok")
            # observability / guardrail-hits — ignore
            return HttpxResponse(200, json={})

        app.state.http.post = AsyncMock(side_effect=_post_side_effect)

        guardrail_json = _j.dumps([_REDACT_RULE])

        async def _redis_get_side_effect(key):
            if key.startswith("guardrails:"):
                return guardrail_json
            return None

        app.state.redis.get = AsyncMock(side_effect=_redis_get_side_effect)

        secret_body = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "my key is sk-secret please help"}],
        }

        with (
            patch("app.exact.get", new=AsyncMock(return_value=None)),
            patch("app.semantic.embed", new=AsyncMock(side_effect=Exception("skip"))),
            patch("app.exact.set", new=AsyncMock()),
        ):
            resp = await client.post(
                "/v1/chat/completions",
                json=secret_body,
                headers={"Authorization": "Bearer valid"},
            )

        assert resp.status_code == 200
        assert len(forwarded_bodies) == 1
        forwarded_content = forwarded_bodies[0]["messages"][0]["content"]
        assert "sk-secret" not in forwarded_content
        assert "[REDACTED]" in forwarded_content

    async def test_input_block_list_content_is_blocked(self, app_and_client):
        """A block guardrail must trigger when content is a list of parts (multimodal format)."""
        app, client = app_and_client

        _BLOCK_RULE = {
            "id": "gr-block-list",
            "name": "secret-block",
            "type": "pattern",
            "action": "block",
            "applies_to": "input",
            "enabled": True,
            "severity": "high",
            "config": {"patterns": ["sk-secret"]},
        }

        guardrail_json = _j.dumps([_BLOCK_RULE])

        async def _redis_get_side_effect(key):
            if key.startswith("guardrails:"):
                return guardrail_json
            return None

        app.state.redis.get = AsyncMock(side_effect=_redis_get_side_effect)
        app.state.http.post = AsyncMock(return_value=_auth_response_ok())

        list_content_body = {
            "model": "gpt-4",
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "sk-secret here"}],
                }
            ],
        }

        with (
            patch("app.exact.get", new=AsyncMock(return_value=None)),
            patch("app.semantic.embed", new=AsyncMock(side_effect=Exception("skip"))),
        ):
            resp = await client.post(
                "/v1/chat/completions",
                json=list_content_body,
                headers={"Authorization": "Bearer valid"},
            )

        assert resp.status_code == 400
        assert resp.json()["error"] == "blocked_by_guardrail"

    async def test_input_redact_list_content_masks_text_parts(self, app_and_client):
        """A redact guardrail must mask text parts inside list-format message content."""
        app, client = app_and_client

        forwarded_bodies = []

        async def _post_side_effect(url, **kwargs):
            if "validate" in url:
                return _auth_response_ok()
            if "chat/completions" in url:
                forwarded_bodies.append(kwargs.get("json", {}))
                return _litellm_chat_response("ok")
            return HttpxResponse(200, json={})

        app.state.http.post = AsyncMock(side_effect=_post_side_effect)

        guardrail_json = _j.dumps([_REDACT_RULE])

        async def _redis_get_side_effect(key):
            if key.startswith("guardrails:"):
                return guardrail_json
            return None

        app.state.redis.get = AsyncMock(side_effect=_redis_get_side_effect)

        list_content_body = {
            "model": "gpt-4",
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "my key is sk-secret please help"}],
                }
            ],
        }

        with (
            patch("app.exact.get", new=AsyncMock(return_value=None)),
            patch("app.semantic.embed", new=AsyncMock(side_effect=Exception("skip"))),
            patch("app.exact.set", new=AsyncMock()),
        ):
            resp = await client.post(
                "/v1/chat/completions",
                json=list_content_body,
                headers={"Authorization": "Bearer valid"},
            )

        assert resp.status_code == 200
        assert len(forwarded_bodies) == 1
        fwd_parts = forwarded_bodies[0]["messages"][0]["content"]
        assert isinstance(fwd_parts, list)
        assert fwd_parts[0]["type"] == "text"
        assert "sk-secret" not in fwd_parts[0]["text"]
        assert "[REDACTED]" in fwd_parts[0]["text"]


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

        with (
            patch("app.exact.get", new=AsyncMock(return_value=None)),
            patch("app.semantic.embed", new=AsyncMock(return_value=[0.1, 0.2, 0.3])),
            patch("app.semantic.get", new=AsyncMock(return_value=_CACHED_RESPONSE)),
        ):
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


# ---------------------------------------------------------------------------
# Output guardrails
# ---------------------------------------------------------------------------

_OUTPUT_BLOCK_RULE = {
    "id": "gr-out-1",
    "name": "secret-output-block",
    "type": "pattern",
    "action": "block",
    "applies_to": "output",
    "enabled": True,
    "severity": "high",
    "config": {"patterns": ["forbidden-output"]},
}

_OUTPUT_REDACT_RULE = {
    "id": "gr-out-2",
    "name": "secret-output-redact",
    "type": "pattern",
    "action": "redact",
    "applies_to": "output",
    "enabled": True,
    "severity": "medium",
    "config": {"patterns": ["sk-output-secret"], "mask": "[REDACTED]"},
}


class TestOutputGuardrails:
    async def _make_client_with_guardrail(self, app_and_client, rule, litellm_content):
        """Helper: set up redis with one guardrail rule and a litellm response."""
        app, client = app_and_client

        guardrail_json = _j.dumps([rule])

        async def _redis_get_side_effect(key):
            if key.startswith("guardrails:"):
                return guardrail_json
            return None

        app.state.redis.get = AsyncMock(side_effect=_redis_get_side_effect)

        async def _post_side_effect(url, **kwargs):
            if "validate" in url:
                return _auth_response_ok()
            if "chat/completions" in url:
                return _litellm_chat_response(litellm_content)
            return HttpxResponse(200, json={})

        app.state.http.post = AsyncMock(side_effect=_post_side_effect)
        return app, client

    async def test_output_block_withholds_and_skips_cache(self, app_and_client):
        """Output block rule must replace content with withheld notice and skip cache writes."""
        app, client = await self._make_client_with_guardrail(
            app_and_client, _OUTPUT_BLOCK_RULE, "forbidden-output here"
        )

        mock_exact_set = AsyncMock()
        mock_semantic_set = AsyncMock()
        with (
            patch("app.exact.get", new=AsyncMock(return_value=None)),
            patch("app.semantic.embed", new=AsyncMock(side_effect=Exception("skip"))),
            patch("app.exact.set", new=mock_exact_set),
            patch("app.semantic.set", new=mock_semantic_set),
        ):
            resp = await client.post(
                "/v1/chat/completions",
                json=CHAT_BODY,
                headers={"Authorization": "Bearer valid"},
            )

        assert resp.status_code == 200
        body = resp.json()
        content = body["choices"][0]["message"]["content"]
        assert "withheld" in content
        assert "secret-output-block" in content
        mock_exact_set.assert_not_awaited()
        mock_semantic_set.assert_not_awaited()

    async def test_output_redact_masks_completion(self, app_and_client):
        """Output redact rule must mask matching text in the completion content."""
        app, client = await self._make_client_with_guardrail(
            app_and_client, _OUTPUT_REDACT_RULE, "here is your sk-output-secret key"
        )

        with (
            patch("app.exact.get", new=AsyncMock(return_value=None)),
            patch("app.semantic.embed", new=AsyncMock(side_effect=Exception("skip"))),
            patch("app.exact.set", new=AsyncMock()),
        ):
            resp = await client.post(
                "/v1/chat/completions",
                json=CHAT_BODY,
                headers={"Authorization": "Bearer valid"},
            )

        assert resp.status_code == 200
        content = resp.json()["choices"][0]["message"]["content"]
        assert "sk-output-secret" not in content
        assert "[REDACTED]" in content

    async def test_output_tool_call_null_content_ok(self, app_and_client):
        """A completion with null content (tool call) must not crash; return 200."""
        app, client = app_and_client

        guardrail_json = _j.dumps([_OUTPUT_BLOCK_RULE])

        async def _redis_get_side_effect(key):
            if key.startswith("guardrails:"):
                return guardrail_json
            return None

        app.state.redis.get = AsyncMock(side_effect=_redis_get_side_effect)

        async def _post_side_effect(url, **kwargs):
            if "validate" in url:
                return _auth_response_ok()
            if "chat/completions" in url:
                return HttpxResponse(
                    200,
                    json={
                        "id": "chatcmpl-tool",
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [{"id": "tc1", "type": "function"}],
                                }
                            }
                        ],
                        "usage": {"prompt_tokens": 5, "completion_tokens": 3},
                    },
                )
            return HttpxResponse(200, json={})

        app.state.http.post = AsyncMock(side_effect=_post_side_effect)

        with (
            patch("app.exact.get", new=AsyncMock(return_value=None)),
            patch("app.semantic.embed", new=AsyncMock(side_effect=Exception("skip"))),
            patch("app.exact.set", new=AsyncMock()),
        ):
            resp = await client.post(
                "/v1/chat/completions",
                json=CHAT_BODY,
                headers={"Authorization": "Bearer valid"},
            )

        assert resp.status_code == 200
