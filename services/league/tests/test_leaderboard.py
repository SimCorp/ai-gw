# services/league/tests/test_leaderboard.py
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

os.environ.setdefault("DEV_BYPASS_AUTH", "true")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.main import app
from app.db import get_session

_SEASON_ID = "11111111-1111-1111-1111-111111111111"


def _make_session_override(mock_session):
    async def _override():
        yield mock_session
    return _override


def _mock_redis():
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    r.aclose = AsyncMock()
    return r


def test_leaderboard_returns_ranked_entries():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        {
            "engineer_id": "aaaa0000-0000-0000-0000-000000000001",
            "email": "anna@simcorp.com",
            "display_name": "Anna K.",
            "team_name": "Equities",
            "area_name": "Engineering",
            "composite_score": "980.00",
            "rank": 1,
            "points_earned": 980,
            "updated_at": "2026-05-10T12:00:00+00:00",
        }
    ]
    mock_session.execute = AsyncMock(return_value=mock_result)

    app.dependency_overrides[get_session] = _make_session_override(mock_session)
    try:
        with patch("app.main.aioredis.from_url", return_value=_mock_redis()):
            with TestClient(app) as client:
                resp = client.get(f"/seasons/{_SEASON_ID}/leaderboard")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["rank"] == 1
    assert data[0]["display_name"] == "Anna K."


def test_my_rank_returns_engineer_position():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.one_or_none.return_value = {
        "composite_score": "620.00",
        "rank": 42,
        "points_earned": 620,
    }
    mock_session.execute = AsyncMock(return_value=mock_result)

    app.dependency_overrides[get_session] = _make_session_override(mock_session)
    try:
        with patch("app.main.aioredis.from_url", return_value=_mock_redis()):
            with TestClient(app) as client:
                resp = client.get(f"/seasons/{_SEASON_ID}/leaderboard/me")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["rank"] == 42
    assert body["composite_score"] == pytest.approx(620.0)
