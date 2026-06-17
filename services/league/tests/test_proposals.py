# services/league/tests/test_proposals.py
from unittest.mock import AsyncMock, MagicMock, patch

from app.auth import require_admin_auth, require_dev_auth
from app.db import get_session
from app.main import app

_USER_ID = "00000000-0000-0000-0000-000000000001"
_PROPOSAL_ID = "44444444-4444-4444-4444-444444444444"


def _make_session_override(mock_session):
    async def _override():
        yield mock_session

    return _override


async def _fake_dev_auth():
    return {"user_id": _USER_ID, "email": "dev@simcorp.com"}


async def _fake_admin_auth():
    return {"user_id": _USER_ID, "role": "platform_admin"}


def _mock_redis():
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    r.aclose = AsyncMock()
    return r


def test_create_proposal_returns_201():
    mock_session = AsyncMock()
    insert_result = MagicMock()
    insert_result.scalar.return_value = _PROPOSAL_ID
    mock_session.execute = AsyncMock(return_value=insert_result)
    mock_session.commit = AsyncMock()

    app.dependency_overrides[get_session] = _make_session_override(mock_session)
    app.dependency_overrides[require_dev_auth] = _fake_dev_auth
    try:
        with patch("app.main.aioredis.from_url", return_value=_mock_redis()):
            from fastapi.testclient import TestClient

            with TestClient(app) as client:
                resp = client.post(
                    "/proposals",
                    json={
                        "title": "Trade note summarizer",
                        "goal": "Summarize trade notes",
                        "notes": "Would be useful for FI team",
                    },
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == _PROPOSAL_ID
    assert body["status"] == "proposed"


def test_list_proposals_requires_admin():
    """Without admin auth the endpoint should return 403."""
    mock_session = AsyncMock()
    app.dependency_overrides[get_session] = _make_session_override(mock_session)
    try:
        with patch("app.main.aioredis.from_url", return_value=_mock_redis()):
            from fastapi.testclient import TestClient

            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/proposals")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code in (401, 403)


def test_review_proposal_approve():
    mock_session = AsyncMock()
    update_result = MagicMock()
    update_result.mappings.return_value.one_or_none.return_value = {
        "id": _PROPOSAL_ID,
        "status": "approved",
    }
    mock_session.execute = AsyncMock(return_value=update_result)
    mock_session.commit = AsyncMock()

    app.dependency_overrides[get_session] = _make_session_override(mock_session)
    app.dependency_overrides[require_admin_auth] = _fake_admin_auth
    try:
        with patch("app.main.aioredis.from_url", return_value=_mock_redis()):
            from fastapi.testclient import TestClient

            with TestClient(app) as client:
                resp = client.patch(
                    f"/proposals/{_PROPOSAL_ID}/review",
                    json={"status": "approved", "reviewer_notes": "Great idea"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


def test_review_proposal_invalid_status():
    mock_session = AsyncMock()
    app.dependency_overrides[get_session] = _make_session_override(mock_session)
    app.dependency_overrides[require_admin_auth] = _fake_admin_auth
    try:
        with patch("app.main.aioredis.from_url", return_value=_mock_redis()):
            from fastapi.testclient import TestClient

            with TestClient(app) as client:
                resp = client.patch(
                    f"/proposals/{_PROPOSAL_ID}/review",
                    json={"status": "pending"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 422


def test_review_proposal_not_found():
    mock_session = AsyncMock()
    update_result = MagicMock()
    update_result.mappings.return_value.one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=update_result)
    mock_session.commit = AsyncMock()

    app.dependency_overrides[get_session] = _make_session_override(mock_session)
    app.dependency_overrides[require_admin_auth] = _fake_admin_auth
    try:
        with patch("app.main.aioredis.from_url", return_value=_mock_redis()):
            from fastapi.testclient import TestClient

            with TestClient(app) as client:
                resp = client.patch(
                    f"/proposals/{_PROPOSAL_ID}/review",
                    json={"status": "rejected", "reviewer_notes": "Not relevant"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404
