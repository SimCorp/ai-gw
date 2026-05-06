"""Cache behaviour tests.

Cache hits depend on the exact-match key (SHA-256 of the normalised request
body) being stored on the first call.  All three conditions must hold:
  1. The upstream returns 200
  2. The team policy has opt_out=False (default)
  3. The Redis TTL has not expired between calls

To isolate tests from each other we use per-test unique prompts so that
leftover cache entries from a previous run never produce a false HIT.
"""

import uuid

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────


def _payload(prompt: str, stream: bool = False) -> dict:
    return {
        "model": "claude-haiku-4-5",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 5,
        "stream": stream,
    }


def _unique_prompt() -> str:
    """Generate a prompt that will never appear in the cache."""
    return f"Unique cache-busting probe {uuid.uuid4()}"


# ── Cache HIT ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_second_identical_request_is_cache_hit(gateway_client):
    """Two identical non-streaming requests: first MISS, second HIT.

    If the first request fails (upstream hiccup) the test is skipped rather
    than marked as a failure, because cache can only return HIT on a prior 200.
    """
    prompt = f"Cache HIT probe {uuid.uuid4()}"
    payload = _payload(prompt)

    # First request — should be a MISS and must succeed for the HIT test to work
    resp1 = await gateway_client.post("/v1/chat/completions", json=payload)
    if resp1.status_code != 200:
        pytest.skip(
            f"First request returned {resp1.status_code}; "
            "cannot test cache HIT without a prior successful 200."
        )
    assert resp1.headers.get("x-cache", "MISS").upper() == "MISS", (
        "First request to a brand-new prompt must be a cache MISS"
    )

    # Second request — must be served from cache
    resp2 = await gateway_client.post("/v1/chat/completions", json=payload)
    assert resp2.status_code == 200, (
        f"Second request failed with {resp2.status_code}: {resp2.text[:300]}"
    )
    assert resp2.headers.get("x-cache", "").upper() == "HIT", (
        f"Second identical request must return X-Cache: HIT, "
        f"got {resp2.headers.get('x-cache', '(missing)')!r}"
    )


@pytest.mark.asyncio
async def test_cache_hit_response_body_matches(gateway_client):
    """The body returned on a cache HIT should match the original response."""
    prompt = f"Cache body-match probe {uuid.uuid4()}"
    payload = _payload(prompt)

    resp1 = await gateway_client.post("/v1/chat/completions", json=payload)
    if resp1.status_code != 200:
        pytest.skip("First request did not succeed; skipping body-match check.")

    resp2 = await gateway_client.post("/v1/chat/completions", json=payload)
    if resp2.headers.get("x-cache", "").upper() != "HIT":
        pytest.skip("Second request was not a cache HIT; skipping body-match check.")

    # The cached response should have the same choices content
    body1 = resp1.json()
    body2 = resp2.json()
    assert (
        body1["choices"][0]["message"]["content"]
        == body2["choices"][0]["message"]["content"]
    ), "Cache HIT body content differs from the original response"


# ── Cache MISS ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unique_prompt_is_cache_miss(gateway_client):
    """A request with a unique UUID in the prompt must return X-Cache: MISS."""
    resp = await gateway_client.post(
        "/v1/chat/completions", json=_payload(_unique_prompt())
    )
    # We only check the cache header, not the status, to avoid failing on
    # transient upstream errors.
    if resp.status_code != 200:
        pytest.skip(f"Upstream returned {resp.status_code}; skipping cache-header check.")
    assert resp.headers.get("x-cache", "MISS").upper() == "MISS", (
        f"Unique-prompt request must be a cache MISS, "
        f"got {resp.headers.get('x-cache', '(missing)')!r}"
    )


# ── Streaming bypasses cache ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_streaming_request_is_cache_miss(gateway_client):
    """Streaming requests must bypass the cache and return X-Cache: MISS."""
    payload = _payload(_unique_prompt(), stream=True)
    async with gateway_client.stream("POST", "/v1/chat/completions", json=payload) as resp:
        assert resp.status_code == 200, (
            f"Streaming request failed: {resp.status_code}"
        )
        cache_header = resp.headers.get("x-cache", "MISS")
        # Consume the body so the connection is released cleanly
        async for _ in resp.aiter_bytes():
            pass

    assert cache_header.upper() == "MISS", (
        f"Streaming response must not be served from cache, "
        f"got X-Cache: {cache_header!r}"
    )


@pytest.mark.asyncio
async def test_streaming_not_cached_for_next_request(gateway_client):
    """A streaming response must not be stored in the cache.

    Send an identical non-streaming request after the streaming one and
    confirm it is also a MISS (the streaming call stored nothing).
    """
    # Use a prompt that is unique to this test run so prior runs cannot
    # accidentally prime the cache.
    prompt = f"Streaming no-cache probe {uuid.uuid4()}"

    # Streaming request — should not write to cache
    async with gateway_client.stream(
        "POST",
        "/v1/chat/completions",
        json=_payload(prompt, stream=True),
    ) as resp:
        if resp.status_code != 200:
            pytest.skip(f"Upstream returned {resp.status_code} for streaming request.")
        async for _ in resp.aiter_bytes():
            pass

    # Non-streaming follow-up — must still be a MISS
    resp2 = await gateway_client.post("/v1/chat/completions", json=_payload(prompt))
    if resp2.status_code != 200:
        pytest.skip(f"Non-streaming follow-up returned {resp2.status_code}.")
    assert resp2.headers.get("x-cache", "MISS").upper() == "MISS", (
        "Non-streaming request after a streaming call should be a cache MISS "
        "(streaming requests must not populate the cache)"
    )
