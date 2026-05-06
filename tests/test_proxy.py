"""End-to-end proxy tests — exercise the full request path through the gateway.

These tests make real LLM calls.  To keep costs minimal we use
claude-haiku-4-5 with max_tokens=5 on all inference tests.

The /anthropic/v1/messages Anthropic-native endpoint is NOT currently wired
through the cache layer (cache router only exposes /v1/chat/completions).
That test is therefore marked xfail with an explanatory reason so it does not
block CI but documents the intended future behaviour.
"""

import pytest

from conftest import GATEWAY_URL

_HAIKU = "claude-haiku-4-5"
_MINIMAL = {
    "model": _HAIKU,
    "messages": [{"role": "user", "content": "Say: hi"}],
    "max_tokens": 5,
}


# ── OpenAI-compat endpoint ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_completions_200(gateway_client):
    """POST /v1/chat/completions with a valid payload must return 200."""
    resp = await gateway_client.post("/v1/chat/completions", json=_MINIMAL)
    assert resp.status_code == 200, (
        f"Expected 200, got {resp.status_code}: {resp.text[:500]}"
    )


@pytest.mark.asyncio
async def test_chat_completions_response_shape(gateway_client):
    """Response body must conform to the OpenAI chat completion shape."""
    resp = await gateway_client.post("/v1/chat/completions", json=_MINIMAL)
    assert resp.status_code == 200
    body = resp.json()
    # Top-level required fields
    for field in ("id", "object", "model", "choices"):
        assert field in body, f"Response missing field '{field}'"
    assert body["object"] == "chat.completion"
    # At least one choice
    assert len(body["choices"]) >= 1
    choice = body["choices"][0]
    assert "message" in choice
    assert "content" in choice["message"]


@pytest.mark.asyncio
async def test_chat_completions_usage_present(gateway_client):
    """Usage tokens should be present in the response."""
    resp = await gateway_client.post("/v1/chat/completions", json=_MINIMAL)
    assert resp.status_code == 200
    body = resp.json()
    assert "usage" in body, "Response missing 'usage' object"
    for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
        assert field in body["usage"], f"'usage' missing field '{field}'"


@pytest.mark.asyncio
async def test_chat_completions_max_tokens_respected(gateway_client):
    """Response completion should not grossly exceed max_tokens=5."""
    payload = {**_MINIMAL, "max_tokens": 5}
    resp = await gateway_client.post("/v1/chat/completions", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    completion_tokens = body.get("usage", {}).get("completion_tokens", 0)
    # Allow a small overshoot; token counting can differ slightly from words.
    assert completion_tokens <= 20, (
        f"Completion used {completion_tokens} tokens with max_tokens=5"
    )


# ── Anthropic-native endpoint (not yet wired through cache layer) ─────────────


@pytest.mark.xfail(
    strict=False,
    reason=(
        "The Anthropic native /anthropic/v1/messages endpoint is not yet routed "
        "through the cache service (gateway:8002).  The cache router only exposes "
        "POST /v1/chat/completions.  This test documents the intended future "
        "behaviour; it is expected to fail until the passthrough is implemented."
    ),
)
@pytest.mark.asyncio
async def test_anthropic_messages_endpoint(gateway_client):
    """POST /anthropic/v1/messages should return 200 using the Anthropic messages format."""
    payload = {
        "model": _HAIKU,
        "max_tokens": 5,
        "messages": [{"role": "user", "content": "Say: hi"}],
    }
    resp = await gateway_client.post("/anthropic/v1/messages", json=payload)
    assert resp.status_code == 200, (
        f"Expected 200, got {resp.status_code}: {resp.text[:500]}"
    )
    body = resp.json()
    assert "content" in body
    assert isinstance(body["content"], list)


# ── Streaming ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_streaming_returns_200_and_event_stream(gateway_client):
    """POST /v1/chat/completions with stream:true must return 200 and text/event-stream content-type."""
    payload = {**_MINIMAL, "stream": True}
    async with gateway_client.stream("POST", "/v1/chat/completions", json=payload) as resp:
        assert resp.status_code == 200, (
            f"Expected 200 for streaming request, got {resp.status_code}"
        )
        content_type = resp.headers.get("content-type", "")
        assert content_type.startswith("text/event-stream"), (
            f"Expected text/event-stream, got {content_type!r}"
        )
        # Read at least one chunk to confirm data is flowing
        chunks = []
        async for chunk in resp.aiter_bytes():
            chunks.append(chunk)
            if len(chunks) >= 1:
                break
        assert len(chunks) >= 1, "No data received from streaming response"


@pytest.mark.asyncio
async def test_streaming_cache_header_miss(gateway_client):
    """Streaming responses must not be served from cache (X-Cache: MISS)."""
    payload = {**_MINIMAL, "stream": True}
    async with gateway_client.stream("POST", "/v1/chat/completions", json=payload) as resp:
        assert resp.status_code == 200
        # Consume response to completion
        async for _ in resp.aiter_bytes():
            pass
        cache_header = resp.headers.get("x-cache", "MISS")
    assert cache_header.upper() == "MISS", (
        f"Streaming response must bypass cache, got X-Cache: {cache_header!r}"
    )


# ── Error cases ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_model_returns_error(gateway_client):
    """An unrecognised model name must return a 4xx error (LiteLLM 400 or 404)."""
    payload = {
        "model": "does-not-exist-model-xyz-9999",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 5,
    }
    resp = await gateway_client.post("/v1/chat/completions", json=payload)
    assert 400 <= resp.status_code < 500, (
        f"Expected 4xx for unknown model, got {resp.status_code}: {resp.text[:300]}"
    )
