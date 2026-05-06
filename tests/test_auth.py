"""Authentication tests — validate sk- key acceptance and rejection paths.

All requests go through the gateway (cache service on :8002) which calls
the auth service internally.  The client fixtures in conftest.py handle
the base URL and credential injection.
"""

import uuid

import httpx
import pytest

from conftest import GATEWAY_URL

# Minimal chat payload — a real LLM call is NOT needed for auth tests; we only
# care about the HTTP status returned before or during auth validation.
_MINIMAL_PAYLOAD = {
    "model": "claude-haiku-4-5",
    "messages": [{"role": "user", "content": "ping"}],
    "max_tokens": 5,
}


@pytest.mark.asyncio
async def test_valid_key_returns_200(gateway_client):
    """A valid sk- key must be accepted and receive a 200 from the backend."""
    resp = await gateway_client.post("/v1/chat/completions", json=_MINIMAL_PAYLOAD)
    # Accept 200 (OK) or 429 (rate-limited) — both prove auth passed.
    assert resp.status_code in {200, 429}, (
        f"Expected 200 or 429 with a valid key, got {resp.status_code}: {resp.text[:300]}"
    )


@pytest.mark.asyncio
async def test_invalid_key_returns_401():
    """A fabricated sk- key that does not exist in the DB must return 401."""
    async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=15.0) as client:
        resp = await client.post(
            "/v1/chat/completions",
            json=_MINIMAL_PAYLOAD,
            headers={"Authorization": "Bearer sk-this-key-does-not-exist-at-all-xyz"},
        )
    assert resp.status_code == 401, (
        f"Expected 401 for invalid key, got {resp.status_code}: {resp.text[:300]}"
    )


@pytest.mark.asyncio
async def test_missing_authorization_returns_401():
    """A request with no Authorization header must return 401."""
    async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=15.0) as client:
        resp = await client.post("/v1/chat/completions", json=_MINIMAL_PAYLOAD)
    assert resp.status_code == 401, (
        f"Expected 401 for missing header, got {resp.status_code}: {resp.text[:300]}"
    )


@pytest.mark.asyncio
async def test_empty_bearer_returns_401():
    """An 'Authorization: Bearer ' header with no token must return 401."""
    async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=15.0) as client:
        resp = await client.post(
            "/v1/chat/completions",
            json=_MINIMAL_PAYLOAD,
            headers={"Authorization": "Bearer "},
        )
    assert resp.status_code == 401, (
        f"Expected 401 for empty bearer, got {resp.status_code}: {resp.text[:300]}"
    )


@pytest.mark.asyncio
async def test_jwt_format_token_returns_401():
    """A Bearer token that does not start with 'sk-' is treated as a JWT.

    Without a configured OIDC provider the auth service either cannot reach
    the JWKS endpoint (503 from auth) or rejects the token signature (401).
    The cache layer converts any non-200 auth response to 401 at the gateway.
    """
    # A plausible-looking JWT header.payload.signature that isn't actually valid
    fake_jwt = (
        "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6ImZha2Uta2lkIn0"
        ".eyJzdWIiOiJ0ZXN0LXVzZXIiLCJleHAiOjk5OTk5OTk5OTl9"
        ".AAABBBCCC"
    )
    async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=15.0) as client:
        resp = await client.post(
            "/v1/chat/completions",
            json=_MINIMAL_PAYLOAD,
            headers={"Authorization": f"Bearer {fake_jwt}"},
        )
    # Cache layer wraps any auth non-200 as 401
    assert resp.status_code == 401, (
        f"Expected 401 for JWT token without OIDC, got {resp.status_code}: {resp.text[:300]}"
    )


@pytest.mark.asyncio
async def test_revoked_key_returns_401(admin_client, test_team):
    """A key that has been revoked must be rejected with 401.

    We create a dedicated key, verify it works, revoke it, then verify it
    no longer works — all within a single test to keep the state clear.
    """
    # 1. Create a fresh key
    create_resp = await admin_client.post(
        f"/teams/{test_team}/keys",
        json={"name": "revocation-test-key"},
    )
    assert create_resp.status_code == 201
    key_data = create_resp.json()
    raw_key = key_data["key"]
    key_id = key_data["id"]

    # 2. Confirm it works before revocation
    async with httpx.AsyncClient(
        base_url=GATEWAY_URL,
        headers={"Authorization": f"Bearer {raw_key}"},
        timeout=15.0,
    ) as client:
        pre_resp = await client.post("/v1/chat/completions", json=_MINIMAL_PAYLOAD)
    assert pre_resp.status_code in {200, 429}, (
        f"Key should be valid before revocation, got {pre_resp.status_code}"
    )

    # 3. Revoke
    revoke_resp = await admin_client.delete(f"/teams/{test_team}/keys/{key_id}")
    assert revoke_resp.status_code == 204

    # 4. Confirm it no longer works
    async with httpx.AsyncClient(
        base_url=GATEWAY_URL,
        headers={"Authorization": f"Bearer {raw_key}"},
        timeout=15.0,
    ) as client:
        post_resp = await client.post("/v1/chat/completions", json=_MINIMAL_PAYLOAD)
    assert post_resp.status_code == 401, (
        f"Revoked key must return 401, got {post_resp.status_code}: {post_resp.text[:300]}"
    )
