from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.rate_limiter import check_rate_limit
from app.validators.api_key import validate_api_key
from app.validators.jwt import _oidc_identity, _validate_jwks_uri
from fastapi import HTTPException


def _make_pipeline_redis(incr_result: int) -> AsyncMock:
    """Build a mock Redis whose pipeline().execute() returns [incr_result, True]."""
    pipe = AsyncMock()
    pipe.incr = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = AsyncMock(return_value=[incr_result, True])

    @asynccontextmanager
    async def _pipeline(transaction=False):
        yield pipe

    redis = AsyncMock()
    redis.pipeline = _pipeline
    return redis


@pytest.fixture
def mock_db():
    db = AsyncMock()
    return db


async def test_api_key_valid(mock_db):
    key = "sk-test-key-123"
    mock_db.fetchrow = AsyncMock(
        return_value={
            "id": "key-uuid-1",
            "team_id": "team-1",
            "project_id": None,
            "scopes": None,
            "capture_content": False,
        }
    )

    result = await validate_api_key(key, mock_db)

    mock_db.fetchrow.assert_awaited_once()
    assert result["team_id"] == "team-1"
    assert result["capture_content"] is False


async def test_api_key_invalid(mock_db):
    mock_db.fetchrow = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await validate_api_key("sk-bad-key", mock_db)

    assert exc_info.value.status_code == 401


async def test_rate_limit_allows_under_limit():
    await check_rate_limit("team-1", "claude-3-5-sonnet", _make_pipeline_redis(1), rpm_limit=100)


async def test_rate_limit_blocks_over_limit():
    with pytest.raises(HTTPException) as exc_info:
        await check_rate_limit(
            "team-1", "claude-3-5-sonnet", _make_pipeline_redis(101), rpm_limit=100
        )

    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers


def test_jwks_uri_private_resolution_blocked(monkeypatch):
    """Hostname resolving to a private address is rejected regardless of ENVIRONMENT.

    Guards the SSRF gate: the env-based bypass (development/test/ci) was removed,
    so the private-address check must always fire after resolution.
    """
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setattr("app.validators.jwt.socket.gethostbyname", lambda host: "10.0.0.1")

    with pytest.raises(ValueError, match="private address"):
        _validate_jwks_uri("https://internal-idp.example/keys")


def test_jwks_uri_public_resolution_allowed(monkeypatch):
    """Hostname resolving to a public address passes."""
    monkeypatch.setattr("app.validators.jwt.socket.gethostbyname", lambda host: "93.184.216.34")

    _validate_jwks_uri("https://idp.example/keys")  # must not raise


# ---------------------------------------------------------------------------
# OIDC identity — must be per-user, never the tenant-wide `tid`
# ---------------------------------------------------------------------------


def test_oidc_identity_uses_per_user_oid_not_tenant_tid():
    # `tid` is the same for every user in the tenant; using it would collapse
    # all SSO callers into one cache namespace. oid (per-user) must win.
    payload = {"oid": "user-123", "sub": "subj", "tid": "tenant-shared"}
    assert _oidc_identity(payload) == "user-123"


def test_oidc_identity_falls_back_to_sub_when_no_oid():
    assert _oidc_identity({"sub": "subj", "tid": "tenant-shared"}) == "subj"


def test_oidc_identity_never_returns_tenant_id():
    assert _oidc_identity({"tid": "tenant-shared"}) != "tenant-shared"
