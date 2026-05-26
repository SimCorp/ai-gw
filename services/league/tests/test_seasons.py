# services/league/tests/test_seasons.py
import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

os.environ.setdefault("DEV_BYPASS_AUTH", "true")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.main import app
from app.db import get_session


def _make_session_override(mock_session):
    async def _override():
        yield mock_session
    return _override


def _mock_redis():
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    r.aclose = AsyncMock()
    return r


def _mock_season_row():
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "Q2 2026",
        "status": "upcoming",
        "starts_at": "2026-04-01T00:00:00+00:00",
        "ends_at": "2026-06-30T23:59:59+00:00",
        "scoring_weights": {
            "quality": 0.35, "robustness": 0.20,
            "token_efficiency": 0.15, "speed": 0.10,
            "cost_efficiency": 0.10, "improvement_rate": 0.05,
            "creativity": 0.05,
        },
        "season_multiplier": "1.00",
        "created_at": "2026-05-01T00:00:00+00:00",
    }


def test_list_seasons_returns_empty_when_no_seasons():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    app.dependency_overrides[get_session] = _make_session_override(mock_session)
    try:
        with patch("app.main.aioredis.from_url", return_value=_mock_redis()):
            with TestClient(app) as client:
                resp = client.get("/seasons")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert resp.status_code == 200
    assert resp.json() == []


def test_create_season_returns_201():
    mock_session = AsyncMock()
    row = _mock_season_row()
    mock_result = MagicMock()
    mock_result.mappings.return_value.one.return_value = row
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    app.dependency_overrides[get_session] = _make_session_override(mock_session)
    try:
        payload = {
            "name": "Q2 2026",
            "starts_at": "2026-04-01T00:00:00Z",
            "ends_at": "2026-06-30T23:59:59Z",
        }
        with patch("app.main.aioredis.from_url", return_value=_mock_redis()):
            with TestClient(app) as client:
                resp = client.post("/seasons", json=payload, headers={"X-Admin-Token": ""})
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert resp.status_code == 201
    assert resp.json()["name"] == "Q2 2026"


def test_update_weights_rejected_when_season_active():
    mock_session = AsyncMock()
    active_row = {**_mock_season_row(), "status": "active"}
    mock_result = MagicMock()
    mock_result.mappings.return_value.one_or_none.return_value = active_row
    mock_session.execute = AsyncMock(return_value=mock_result)

    app.dependency_overrides[get_session] = _make_session_override(mock_session)
    try:
        with patch("app.main.aioredis.from_url", return_value=_mock_redis()):
            with TestClient(app) as client:
                resp = client.patch(
                    "/seasons/11111111-1111-1111-1111-111111111111/weights",
                    json={
                        "quality": 0.35, "robustness": 0.20,
                        "token_efficiency": 0.15, "speed": 0.10,
                        "cost_efficiency": 0.10, "improvement_rate": 0.05,
                        "creativity": 0.05,
                    },
                    headers={"X-Admin-Token": ""},
                )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert resp.status_code == 409


def test_update_weights_rejected_when_weights_dont_sum_to_1():
    mock_session = AsyncMock()
    upcoming_row = _mock_season_row()
    mock_result = MagicMock()
    mock_result.mappings.return_value.one_or_none.return_value = upcoming_row
    mock_session.execute = AsyncMock(return_value=mock_result)

    app.dependency_overrides[get_session] = _make_session_override(mock_session)
    try:
        with patch("app.main.aioredis.from_url", return_value=_mock_redis()):
            with TestClient(app) as client:
                # All weights sum to 0.80, clearly not 1.0
                resp = client.patch(
                    "/seasons/11111111-1111-1111-1111-111111111111/weights",
                    json={
                        "quality": 0.30,
                        "robustness": 0.15,
                        "token_efficiency": 0.10,
                        "speed": 0.10,
                        "cost_efficiency": 0.10,
                        "improvement_rate": 0.03,
                        "creativity": 0.02,
                    },  # sum = 0.80, fails validation
                    headers={"X-Admin-Token": ""},
                )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert resp.status_code == 422
