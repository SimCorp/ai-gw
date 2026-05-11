"""Tests for the POST /events router endpoint."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

_TEST_INTERNAL_KEY = "test-internal-key"


@pytest.fixture
async def client():
    from app.main import app

    # Replace the lifespan-managed bus with a simple mock
    app.state.bus = AsyncMock()
    app.state.bus.publish = AsyncMock()
    app.state.settings = SimpleNamespace(internal_api_key=_TEST_INTERNAL_KEY)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Internal-Key": _TEST_INTERNAL_KEY},
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# POST /events
# ---------------------------------------------------------------------------


async def test_valid_event_returns_202(client):
    response = await client.post(
        "/events",
        json={"team_id": "team-1"},
    )
    assert response.status_code == 202


async def test_event_published_to_bus(client):
    from app.main import app

    app.state.bus.publish.reset_mock()
    await client.post("/events", json={"team_id": "team-1"})
    app.state.bus.publish.assert_called_once()


async def test_minimal_event_only_team_id(client):
    """team_id is the only required field; all others have defaults."""
    response = await client.post("/events", json={"team_id": "minimal-team"})
    assert response.status_code == 202


async def test_event_with_all_fields(client):
    payload = {
        "team_id": "team-full",
        "project_id": "proj-1",
        "key_id": "key-abc",
        "model": "gpt-4o",
        "tokens_input": 512,
        "tokens_output": 256,
        "cost_usd": 0.025,
        "cache_hit": True,
        "latency_ms": 450,
        "error": None,
    }
    response = await client.post("/events", json=payload)
    assert response.status_code == 202


async def test_invalid_body_missing_team_id_returns_422(client):
    """Omitting the required team_id field should yield a 422 Unprocessable Entity."""
    response = await client.post("/events", json={"model": "gpt-4"})
    assert response.status_code == 422


async def test_missing_internal_key_returns_401(client):
    """POST /events without X-Internal-Key must return 401."""
    from app.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as anon:
        response = await anon.post("/events", json={"team_id": "team-1"})
    assert response.status_code == 401


async def test_wrong_internal_key_returns_401(client):
    """POST /events with wrong X-Internal-Key must return 401."""
    from app.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Internal-Key": "wrong-key"},
    ) as bad:
        response = await bad.post("/events", json={"team_id": "team-1"})
    assert response.status_code == 401


async def test_response_body_is_accepted(client):
    response = await client.post("/events", json={"team_id": "team-x"})
    assert response.json() == {"accepted": True}


async def test_published_event_has_correct_team_id(client):
    from app.main import app

    app.state.bus.publish.reset_mock()
    await client.post("/events", json={"team_id": "team-check"})

    call_args = app.state.bus.publish.call_args
    event = call_args.args[0]
    assert event.team_id == "team-check"
