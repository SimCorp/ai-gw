# services/league/tests/test_store.py
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

os.environ.setdefault("DEV_BYPASS_AUTH", "true")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.main import app
from app.db import get_session

_USER_ID = "00000000-0000-0000-0000-000000000001"
_ITEM_ID = "33333333-3333-3333-3333-333333333333"


def _make_session_override(mock_session):
    async def _override():
        yield mock_session
    return _override


def _mock_redis():
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    r.aclose = AsyncMock()
    return r


def test_balance_returns_sum_of_ledger():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = 1840
    mock_session.execute = AsyncMock(return_value=mock_result)

    app.dependency_overrides[get_session] = _make_session_override(mock_session)
    try:
        with patch("app.main.aioredis.from_url", return_value=_mock_redis()):
            with TestClient(app) as client:
                resp = client.get("/store/balance")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert resp.status_code == 200
    assert resp.json()["balance"] == 1840


def test_purchase_deducts_points_and_creates_purchase():
    mock_session = AsyncMock()

    item_row = {
        "id": _ITEM_ID, "point_cost": 800, "active": True,
        "exclusive_season_id": None, "exclusive_top_n": None,
    }
    balance_result = MagicMock()
    balance_result.scalar.return_value = 1840
    item_result = MagicMock()
    item_result.mappings.return_value.one_or_none.return_value = item_row
    already_owned_result = MagicMock()
    already_owned_result.scalar.return_value = 0

    mock_session.execute = AsyncMock(side_effect=[
        item_result,
        balance_result,
        already_owned_result,
        AsyncMock(),  # insert purchase
        AsyncMock(),  # insert ledger debit
    ])
    mock_session.commit = AsyncMock()

    app.dependency_overrides[get_session] = _make_session_override(mock_session)
    try:
        with patch("app.main.aioredis.from_url", return_value=_mock_redis()):
            with TestClient(app) as client:
                resp = client.post(f"/store/purchase/{_ITEM_ID}")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert resp.status_code == 200
    assert resp.json()["new_balance"] == 1040  # 1840 - 800


def test_purchase_exclusive_item_rejected():
    mock_session = AsyncMock()
    item_row = {
        "id": _ITEM_ID, "point_cost": 0, "active": True,
        "exclusive_season_id": "11111111-1111-1111-1111-111111111111",
        "exclusive_top_n": 3,
    }
    mock_result = MagicMock()
    mock_result.mappings.return_value.one_or_none.return_value = item_row
    mock_session.execute = AsyncMock(return_value=mock_result)

    app.dependency_overrides[get_session] = _make_session_override(mock_session)
    try:
        with patch("app.main.aioredis.from_url", return_value=_mock_redis()):
            with TestClient(app) as client:
                resp = client.post(f"/store/purchase/{_ITEM_ID}")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert resp.status_code == 403
    assert "exclusive" in resp.json()["detail"].lower()


def test_purchase_fails_on_insufficient_points():
    mock_session = AsyncMock()
    item_row = {
        "id": _ITEM_ID, "point_cost": 2000, "active": True,
        "exclusive_season_id": None, "exclusive_top_n": None,
    }
    item_result = MagicMock()
    item_result.mappings.return_value.one_or_none.return_value = item_row
    balance_result = MagicMock()
    balance_result.scalar.return_value = 500  # not enough

    mock_session.execute = AsyncMock(side_effect=[item_result, balance_result])

    app.dependency_overrides[get_session] = _make_session_override(mock_session)
    try:
        with patch("app.main.aioredis.from_url", return_value=_mock_redis()):
            with TestClient(app) as client:
                resp = client.post(f"/store/purchase/{_ITEM_ID}")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert resp.status_code == 402
    assert "insufficient" in resp.json()["detail"].lower()
