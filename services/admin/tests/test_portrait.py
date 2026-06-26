"""Tests for usage portrait generation."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Pure unit tests for _build_scene
# ---------------------------------------------------------------------------


def test_build_scene_opus_foggy_tools():
    from app.routers.portrait import _build_scene

    stats = {
        "top_model": "claude-opus-4-7",
        "cache_hit_pct": 0.25,  # below 0.5 → fog
        "tool_ratio": 0.5,  # above 0.3 → gears
        "peak_hour": 2,  # 0-6 → moonlit
        "request_count": 120,  # ≥100 → dense forest
    }
    prompt, scene_data = _build_scene(stats)

    assert "owl" in prompt
    assert "fog" in prompt
    assert "gear" in prompt
    assert "moonlit" in prompt
    assert "dense" in prompt
    assert len(scene_data) == 5
    for key in ("creature", "atmosphere", "machinery", "time", "scale"):
        assert key in scene_data
        assert "name" in scene_data[key]
        assert "reason" in scene_data[key]


def test_build_scene_sonnet_clear_no_tools():
    from app.routers.portrait import _build_scene

    stats = {
        "top_model": "claude-sonnet-4-6",
        "cache_hit_pct": 0.72,  # ≥ 0.5 → clear morning light
        "tool_ratio": 0.0,  # < 0.3 → no machinery
        "peak_hour": 10,  # 7-11 → dawn
        "request_count": 15,  # < 20 → single tree
    }
    prompt, scene_data = _build_scene(stats)

    assert "songbird" in prompt
    assert "morning" in prompt
    assert "gear" not in prompt
    assert "dawn" in prompt
    assert "single ancient tree" in prompt


def test_build_scene_unknown_model_uses_default():
    from app.routers.portrait import _build_scene

    stats = {
        "top_model": "some-unknown-model",
        "cache_hit_pct": 0.5,
        "tool_ratio": 0.0,
        "peak_hour": 14,
        "request_count": 50,
    }
    prompt, scene_data = _build_scene(stats)
    assert "heron" in prompt


# ---------------------------------------------------------------------------
# Endpoint: 404 when developer has no cost_records
# ---------------------------------------------------------------------------


@pytest.fixture
async def portrait_client_no_data():
    from app.db import get_session
    from app.main import app
    from app.routers.dev_auth import _get_current_developer

    dev_id = str(uuid.uuid4())

    async def fake_developer():
        return {"user_id": dev_id, "email": "dev@example.com", "developer_id": dev_id}

    fake_session = AsyncMock()
    # portrait cache miss: first execute (cache lookup) returns no row
    # usage stats query: second execute returns a row with request_count = 0
    no_row = MagicMock()
    no_row.mappings.return_value.first.return_value = None

    zero_stats = MagicMock()
    zero_stats.mappings.return_value.first.return_value = {
        "top_model": None,
        "cache_hit_pct": None,
        "tool_ratio": None,
        "peak_hour": None,
        "request_count": 0,
    }

    fake_session.execute = AsyncMock(side_effect=[no_row, zero_stats])

    async def override_session():
        yield fake_session

    app.dependency_overrides[_get_current_developer] = fake_developer
    app.dependency_overrides[get_session] = override_session
    app.state.redis = AsyncMock()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_portrait_me_returns_404_when_no_usage(portrait_client_no_data):
    resp = await portrait_client_no_data.get("/portrait/me")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "No usage data available for portrait"
