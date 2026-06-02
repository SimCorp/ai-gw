"""
Tests for app.router: check_budget() unit tests and POST /validate endpoint tests.

These tests do NOT require a running Redis or Postgres instance.  All external
dependencies are replaced with AsyncMock / MagicMock objects.

Patch targets:
  - app.router.validate_api_key  (imported into router at module level)
  - app.router.validate_jwt
  - app.router.check_rate_limit
  - app.router.check_budget      (only for endpoint tests that want to bypass budget logic)
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_TEAM_ID = "team-abc"
_KEY_ID = "key-xyz"
_PROJECT_ID = "proj-1"
_MONTH = "2026-05"  # hard-coded; tests that care about the month key use side_effect


def _api_key_identity() -> dict:
    return {"team_id": _TEAM_ID, "project_id": _PROJECT_ID, "key_id": _KEY_ID}


def _jwt_identity() -> dict:
    # JWT auth does not set key_id
    return {"team_id": _TEAM_ID, "project_id": _PROJECT_ID}


def _mock_redis() -> AsyncMock:
    """Return a bare AsyncMock that behaves as a Redis client (all methods async)."""
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.hget = AsyncMock(return_value=None)
    return r


# ---------------------------------------------------------------------------
# Fixture: async HTTP client that bypasses lifespan and injects mock state
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():
    from app.main import app

    app.state.redis = _mock_redis()
    app.state.db = AsyncMock()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# check_budget unit tests
# ---------------------------------------------------------------------------


async def test_check_budget_no_key_budget_set():
    """Key budget key absent → allowed."""
    from app.router import check_budget

    redis = _mock_redis()
    redis.get = AsyncMock(return_value=None)  # all gets return None

    allowed, reason = await check_budget(_TEAM_ID, _KEY_ID, redis)

    assert allowed is True
    assert reason == ""


async def test_check_budget_key_spend_below_limit():
    """Key budget set, spend is 4.99, limit 5.00 → allowed."""
    from app.router import check_budget

    redis = _mock_redis()

    def _get(key):
        if key == f"budget_limit:key:{_KEY_ID}":
            return AsyncMock(return_value=json.dumps({"limit": 5.0}))()
        if key.startswith("budget:key:"):
            return AsyncMock(return_value="4.99")()
        return AsyncMock(return_value=None)()

    redis.get = _get

    allowed, reason = await check_budget(_TEAM_ID, _KEY_ID, redis)

    assert allowed is True
    assert reason == ""


async def test_check_budget_key_spend_at_limit():
    """Key budget set, spend equals limit exactly → blocked; reason mentions dollar amount."""
    from app.router import check_budget

    redis = _mock_redis()

    def _get(key):
        if key == f"budget_limit:key:{_KEY_ID}":
            return AsyncMock(return_value=json.dumps({"limit": 10.0}))()
        return AsyncMock(return_value="10.0")()

    redis.get = _get

    allowed, reason = await check_budget(_TEAM_ID, _KEY_ID, redis)

    assert allowed is False
    assert "10" in reason  # dollar amount present in message
    assert "exhausted" in reason.lower()


async def test_check_budget_team_block_at_limit():
    """Team budget set with action='block', spend >= limit → blocked."""
    from app.router import check_budget

    redis = _mock_redis()

    def _get(key):
        if key == f"budget_limit:key:{_KEY_ID}":
            return AsyncMock(return_value=None)()
        if key == f"budget_limit:team:{_TEAM_ID}":
            return AsyncMock(return_value=json.dumps({"limit": 50.0, "action": "block"}))()
        # team spend key
        return AsyncMock(return_value="50.0")()

    redis.get = _get

    allowed, reason = await check_budget(_TEAM_ID, _KEY_ID, redis)

    assert allowed is False
    assert "exhausted" in reason.lower()


async def test_check_budget_team_alert_at_limit():
    """Team budget set with action='alert', spend >= limit → allowed (alert only, no block)."""
    from app.router import check_budget

    redis = _mock_redis()

    def _get(key):
        if key == f"budget_limit:key:{_KEY_ID}":
            return AsyncMock(return_value=None)()
        if key == f"budget_limit:team:{_TEAM_ID}":
            return AsyncMock(return_value=json.dumps({"limit": 50.0, "action": "alert"}))()
        if key.startswith("budget:team:"):
            return AsyncMock(return_value="50.0")()
        return AsyncMock(return_value=None)()

    redis.get = _get

    allowed, reason = await check_budget(_TEAM_ID, _KEY_ID, redis)

    assert allowed is True
    assert reason == ""


async def test_check_budget_org_block_at_limit():
    """Org budget set with action='block', spend >= limit → blocked."""
    from app.router import check_budget

    redis = _mock_redis()

    def _get(key):
        if key == "budget_limit:org":
            return AsyncMock(return_value=json.dumps({"limit": 1000.0, "action": "block"}))()
        if key.startswith("budget:org:"):
            return AsyncMock(return_value="1000.0")()
        return AsyncMock(return_value=None)()

    redis.get = _get

    allowed, reason = await check_budget(_TEAM_ID, _KEY_ID, redis)

    assert allowed is False
    assert "organisation" in reason.lower() or "exhausted" in reason.lower()


async def test_check_budget_org_alert_at_limit():
    """Org budget set with action='alert', spend >= limit → allowed."""
    from app.router import check_budget

    redis = _mock_redis()

    def _get(key):
        if key == "budget_limit:org":
            return AsyncMock(return_value=json.dumps({"limit": 1000.0, "action": "alert"}))()
        if key.startswith("budget:org:"):
            return AsyncMock(return_value="1000.0")()
        return AsyncMock(return_value=None)()

    redis.get = _get

    allowed, reason = await check_budget(_TEAM_ID, _KEY_ID, redis)

    assert allowed is True
    assert reason == ""


async def test_check_budget_redis_exception_fail_open(monkeypatch):
    """Redis raises ConnectionError → fail-open by default (BUDGET_REDIS_FAILOPEN=true)."""

    from app.router import check_budget

    monkeypatch.setenv("BUDGET_REDIS_FAILOPEN", "true")

    redis = _mock_redis()
    redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))

    allowed, reason = await check_budget(_TEAM_ID, _KEY_ID, redis)
    assert allowed is True
    assert reason == ""


async def test_check_budget_redis_exception_fail_closed(monkeypatch):
    """Redis raises ConnectionError → fail-closed when BUDGET_REDIS_FAILOPEN=false."""
    from app.router import check_budget
    from fastapi import HTTPException

    monkeypatch.setenv("BUDGET_REDIS_FAILOPEN", "false")

    redis = _mock_redis()
    redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))

    with pytest.raises(HTTPException) as exc_info:
        await check_budget(_TEAM_ID, _KEY_ID, redis)
    assert exc_info.value.status_code == 503


async def test_check_budget_key_id_none_skips_key_check():
    """key_id=None → key check is skipped; team check is still evaluated."""
    from app.router import check_budget

    redis = _mock_redis()
    key_budget_get = AsyncMock()

    def _get(key):
        if key.startswith("budget_limit:key:"):
            return key_budget_get()
        if key == f"budget_limit:team:{_TEAM_ID}":
            return AsyncMock(return_value=json.dumps({"limit": 20.0, "action": "block"}))()
        # team spend key
        return AsyncMock(return_value="20.0")()

    redis.get = _get

    allowed, reason = await check_budget(_TEAM_ID, None, redis)

    # key-level Redis key must never have been touched
    key_budget_get.assert_not_awaited()
    # team budget blocked
    assert allowed is False


# ---------------------------------------------------------------------------
# POST /validate endpoint tests
# ---------------------------------------------------------------------------


async def test_validate_empty_token(client):
    """Empty token (bare 'Bearer ' prefix) → 401."""
    resp = await client.post("/validate", json={"token": "Bearer ", "model": ""})

    assert resp.status_code == 401


async def test_validate_empty_literal_token(client):
    """Empty string token → 401."""
    resp = await client.post("/validate", json={"token": "", "model": ""})

    assert resp.status_code == 401


async def test_validate_sk_key_returns_200(client):
    """Valid sk-* API key → 200 with team_id and key_id."""
    identity = _api_key_identity()

    with (
        patch("app.router.validate_api_key", new=AsyncMock(return_value=identity)),
        patch("app.router.check_rate_limit", new=AsyncMock()),
        patch("app.router.check_budget", new=AsyncMock(return_value=(True, ""))),
    ):
        resp = await client.post("/validate", json={"token": f"sk-{_KEY_ID}", "model": ""})

    assert resp.status_code == 200
    body = resp.json()
    assert body["team_id"] == _TEAM_ID
    assert body["key_id"] == _KEY_ID


async def test_validate_jwt_returns_200(client):
    """Valid JWT (non-sk token) → 200 with team_id; key_id absent / null."""
    identity = _jwt_identity()

    with (
        patch("app.router.validate_jwt", new=AsyncMock(return_value=identity)),
        patch("app.router.check_rate_limit", new=AsyncMock()),
        patch("app.router.check_budget", new=AsyncMock(return_value=(True, ""))),
    ):
        resp = await client.post("/validate", json={"token": "eyJhbGci.fake.jwt", "model": ""})

    assert resp.status_code == 200
    body = resp.json()
    assert body["team_id"] == _TEAM_ID
    # key_id is optional; ensure it is not a non-None value from a JWT auth
    assert body.get("key_id") is None


async def test_validate_invalid_api_key_returns_401(client):
    """validate_api_key raises HTTPException(401) → endpoint propagates 401."""
    with patch(
        "app.router.validate_api_key",
        new=AsyncMock(side_effect=HTTPException(status_code=401, detail="Invalid key")),
    ):
        resp = await client.post("/validate", json={"token": "sk-bad-key", "model": ""})

    assert resp.status_code == 401


async def test_validate_rate_limit_exceeded_returns_429(client):
    """check_rate_limit raises HTTPException(429) → 429 with standard FastAPI detail shape."""
    identity = _api_key_identity()

    with (
        patch("app.router.validate_api_key", new=AsyncMock(return_value=identity)),
        patch(
            "app.router.check_rate_limit",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": "60"},
                )
            ),
        ),
    ):
        resp = await client.post("/validate", json={"token": f"sk-{_KEY_ID}", "model": ""})

    assert resp.status_code == 429
    # Rate-limit response must NOT carry the budget_exhausted error shape
    body = resp.json()
    assert body.get("error") != "budget_exhausted"


async def test_validate_key_budget_exhausted_returns_429(client):
    """Key-level budget exhausted → 429 JSON with error='budget_exhausted'."""
    identity = _api_key_identity()

    with (
        patch("app.router.validate_api_key", new=AsyncMock(return_value=identity)),
        patch("app.router.check_rate_limit", new=AsyncMock()),
        patch(
            "app.router.check_budget",
            new=AsyncMock(return_value=(False, "API key monthly budget of $10 exhausted")),
        ),
    ):
        resp = await client.post("/validate", json={"token": f"sk-{_KEY_ID}", "model": ""})

    assert resp.status_code == 429
    body = resp.json()
    assert body["error"] == "budget_exhausted"
    assert "message" in body


async def test_validate_team_budget_block_returns_429(client):
    """Team budget (action=block) exhausted → 429 with error='budget_exhausted'."""
    identity = _api_key_identity()

    with (
        patch("app.router.validate_api_key", new=AsyncMock(return_value=identity)),
        patch("app.router.check_rate_limit", new=AsyncMock()),
        patch(
            "app.router.check_budget",
            new=AsyncMock(return_value=(False, "Team monthly budget of $500 exhausted")),
        ),
    ):
        resp = await client.post("/validate", json={"token": f"sk-{_KEY_ID}", "model": ""})

    assert resp.status_code == 429
    body = resp.json()
    assert body["error"] == "budget_exhausted"


async def test_validate_team_budget_alert_returns_200(client):
    """Team budget alert (action=alert) → check_budget returns (True, '') → 200."""
    identity = _api_key_identity()

    with (
        patch("app.router.validate_api_key", new=AsyncMock(return_value=identity)),
        patch("app.router.check_rate_limit", new=AsyncMock()),
        patch("app.router.check_budget", new=AsyncMock(return_value=(True, ""))),
    ):
        resp = await client.post("/validate", json={"token": f"sk-{_KEY_ID}", "model": ""})

    assert resp.status_code == 200
    assert resp.json()["team_id"] == _TEAM_ID


async def test_validate_redis_policy_failure_uses_default_rpm(client):
    """Redis hget raises on policy fetch → default RPM used; request still succeeds."""
    from app.config import settings
    from app.main import app as _app

    identity = _api_key_identity()
    captured_rpm: list[int] = []

    async def _rate_limit_capture(team_id, model, redis, rpm_limit):
        captured_rpm.append(rpm_limit)

    # Re-configure the mock redis that was injected by the fixture
    _app.state.redis.hget = AsyncMock(side_effect=ConnectionError("Redis down"))
    # get() is still needed by check_budget; keep it returning None (no budgets set)
    _app.state.redis.get = AsyncMock(return_value=None)

    with (
        patch("app.router.validate_api_key", new=AsyncMock(return_value=identity)),
        patch("app.router.check_rate_limit", new=AsyncMock(side_effect=_rate_limit_capture)),
        patch("app.router.check_budget", new=AsyncMock(return_value=(True, ""))),
    ):
        resp = await client.post("/validate", json={"token": f"sk-{_KEY_ID}", "model": ""})

    assert resp.status_code == 200
    assert captured_rpm == [settings.rate_limit_default_rpm]
