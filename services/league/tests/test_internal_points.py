"""Tests for the internal points grant API used by other services (admin)."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DEV_BYPASS_AUTH", "true")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ["ADMIN_TOKEN"] = "test-admin-token"

# Reimport settings + app fresh with ADMIN_TOKEN set
from app.config import settings  # noqa: E402

settings.admin_token = "test-admin-token"

from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402


def _make_session_override(mock_session):
    async def _override():
        yield mock_session

    return _override


def _mock_redis():
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    r.aclose = AsyncMock()
    return r


@pytest.fixture
def mock_session():
    s = AsyncMock()
    result = MagicMock()
    s.execute = AsyncMock(return_value=result)
    s.commit = AsyncMock()
    return s


@pytest.fixture
def client(mock_session):
    app.dependency_overrides[get_session] = _make_session_override(mock_session)
    try:
        with patch("app.main.aioredis.from_url", return_value=_mock_redis()):
            with TestClient(app) as c:
                yield c
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_grant_writes_ledger_row(client, mock_session):
    resp = client.post(
        "/league/internal/points/grant",
        headers={"X-Admin-Token": "test-admin-token"},
        json={
            "engineer_id": "00000000-0000-0000-0000-000000000001",
            "delta": 50,
            "reason": "champion_content",
            "ref_id": "11111111-1111-1111-1111-111111111111",
        },
    )
    assert resp.status_code == 201, resp.text
    assert mock_session.execute.await_count >= 1
    # Verify the request body values flowed into the INSERT params
    call_args = mock_session.execute.await_args
    params = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("parameters", {})
    assert params["delta"] == 50
    assert params["reason"] == "champion_content"
    assert params["engineer_id"] == "00000000-0000-0000-0000-000000000001"
    assert params["ref_id"] == "11111111-1111-1111-1111-111111111111"
    mock_session.commit.assert_awaited()


def test_grant_rejects_non_champion_reason(client):
    resp = client.post(
        "/league/internal/points/grant",
        headers={"X-Admin-Token": "test-admin-token"},
        json={
            "engineer_id": "00000000-0000-0000-0000-000000000001",
            "delta": 50,
            "reason": "random_reason",
        },
    )
    assert resp.status_code == 400


def test_grant_requires_admin_token(client):
    resp = client.post(
        "/league/internal/points/grant",
        json={
            "engineer_id": "00000000-0000-0000-0000-000000000001",
            "delta": 50,
            "reason": "champion_content",
        },
    )
    assert resp.status_code == 401
