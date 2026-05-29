"""Tests for DID-style identity signing (services/admin/app/identity_signing.py).

All tests use mock Redis so no real Redis instance is required.
"""
from __future__ import annotations

import time

import jwt
import pytest
from app.identity_signing import (
    get_or_create_signing_key,
    issue_identity_token,
    verify_identity_token,
)

# ---------------------------------------------------------------------------
# Shared fixture: a minimal stateful fake Redis
# ---------------------------------------------------------------------------


class FakeRedis:
    """Tiny in-memory Redis fake that supports get/setex."""

    def __init__(self):
        self._store: dict[str, bytes] = {}

    async def get(self, key: str):
        return self._store.get(key)

    async def setex(self, key: str, ttl: int, value):
        if isinstance(value, str):
            value = value.encode()
        self._store[key] = value

    async def delete(self, *keys: str):
        for k in keys:
            self._store.pop(k, None)


@pytest.fixture
def fake_redis():
    return FakeRedis()


# ---------------------------------------------------------------------------
# test_issue_and_verify_token — round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_issue_and_verify_token(fake_redis):
    """Issuing a token and verifying it with the public key should succeed."""
    token = await issue_identity_token(
        redis=fake_redis,
        slug="my-agent",
        name="My Agent",
        team_id="team-abc",
        capabilities=["search", "summarise"],
        ttl_seconds=3600,
    )

    assert isinstance(token, str)
    assert token.count(".") == 2  # three parts: header.payload.signature

    # Retrieve the public key from the same fake redis
    private_key, kid = await get_or_create_signing_key(fake_redis)
    pub_key = private_key.public_key()

    claims = verify_identity_token(token, pub_key)

    assert claims["sub"] == "my-agent"
    assert claims["name"] == "My Agent"
    assert claims["team_id"] == "team-abc"
    assert claims["capabilities"] == ["search", "summarise"]
    assert claims["iss"] == "ai-gateway"
    assert claims["exp"] > claims["iat"]


# ---------------------------------------------------------------------------
# test_expired_token_rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_token_rejected(fake_redis):
    """A token issued with ttl_seconds=0 (or already expired) must be rejected."""
    # Issue with a very short TTL; then backdate it by re-encoding with a past exp
    private_key, kid = await get_or_create_signing_key(fake_redis)

    now = int(time.time())
    payload = {
        "iss": "ai-gateway",
        "sub": "old-agent",
        "name": "Old Agent",
        "iat": now - 120,
        "exp": now - 60,   # already expired 60 s ago
        "capabilities": [],
    }
    expired_token = jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": kid})

    pub_key = private_key.public_key()
    with pytest.raises(jwt.ExpiredSignatureError):
        verify_identity_token(expired_token, pub_key)


# ---------------------------------------------------------------------------
# test_jwks_endpoint_returns_public_key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jwks_endpoint_returns_public_key(fake_redis):
    """GET /identity/jwks must return a JWK Set with at least one RSA key."""
    import os
    os.environ.setdefault("DEV_BYPASS_AUTH", "true")
    os.environ.setdefault("ENVIRONMENT", "development")

    from app.main import app
    from httpx import ASGITransport, AsyncClient

    # Wire up the fake redis so the endpoint can find the signing key
    app.state.redis = fake_redis
    # Pre-populate a key so get_or_create_signing_key has something to return
    await get_or_create_signing_key(fake_redis)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/identity/jwks")

    assert response.status_code == 200
    body = response.json()
    assert "keys" in body
    assert len(body["keys"]) == 1

    jwk = body["keys"][0]
    assert jwk["kty"] == "RSA"
    assert jwk["alg"] == "RS256"
    assert "n" in jwk
    assert "e" in jwk
    assert "kid" in jwk


# ---------------------------------------------------------------------------
# test_tampered_token_rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tampered_token_rejected(fake_redis):
    """A token whose signature has been altered must raise InvalidSignatureError."""
    token = await issue_identity_token(
        redis=fake_redis,
        slug="legit-agent",
        name="Legit Agent",
        team_id=None,
        capabilities=["read"],
        ttl_seconds=3600,
    )

    # Flip a character in the signature segment (the FIRST part).
    # The last base64url char only encodes a few trailing bits, so flipping it
    # can decode to identical signature bytes — that made this test flaky in CI.
    # The first char always maps to real bits, so the bytes always change.
    header, payload, sig = token.split(".")
    bad_sig = ("A" if sig[0] != "A" else "B") + sig[1:]
    tampered_token = f"{header}.{payload}.{bad_sig}"

    private_key, _ = await get_or_create_signing_key(fake_redis)
    pub_key = private_key.public_key()

    with pytest.raises(jwt.InvalidSignatureError):
        verify_identity_token(tampered_token, pub_key)
