# services/league/tests/test_challenges.py
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.auth import require_dev_auth
from app.db import get_session
from app.main import app


def _make_session_override(mock_session):
    async def _override():
        yield mock_session

    return _override


async def _fake_dev_auth():
    return {"user_id": "00000000-0000-0000-0000-000000000001", "email": "dev@simcorp.com"}


def _mock_redis():
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    r.aclose = AsyncMock()
    return r


def _mock_challenge():
    return {
        "id": "22222222-2222-2222-2222-222222222222",
        "season_id": "11111111-1111-1111-1111-111111111111",
        "title": "Intent Classifier",
        "goal": "Classify customer intent",
        "training_inputs": [],
        "allowed_models": ["claude-sonnet-4-6"],
        "max_tokens_budget": 4096,
        "max_league_attempts": 3,
        "scores_revealed_at": None,
        "status": "draft",
        "proposed_by": None,
        "created_at": "2026-05-01T00:00:00+00:00",
    }


def test_list_challenges_for_season():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [_mock_challenge()]
    mock_session.execute = AsyncMock(return_value=mock_result)

    app.dependency_overrides[get_session] = _make_session_override(mock_session)
    app.dependency_overrides[require_dev_auth] = _fake_dev_auth
    try:
        with patch("app.main.aioredis.from_url", return_value=_mock_redis()):
            with TestClient(app) as client:
                resp = client.get("/seasons/11111111-1111-1111-1111-111111111111/challenges")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["title"] == "Intent Classifier"


def test_challenge_detail_hides_hidden_test_suite():
    """hidden_test_suite must never appear in non-admin challenge detail."""
    ch = {**_mock_challenge(), "hidden_test_suite": [{"input": "secret", "expected": "X"}]}
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.one_or_none.return_value = ch
    mock_session.execute = AsyncMock(return_value=mock_result)

    app.dependency_overrides[get_session] = _make_session_override(mock_session)
    app.dependency_overrides[require_dev_auth] = _fake_dev_auth
    try:
        with patch("app.main.aioredis.from_url", return_value=_mock_redis()):
            with TestClient(app) as client:
                resp = client.get("/challenges/22222222-2222-2222-2222-222222222222")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert "hidden_test_suite" not in resp.json()
    assert "secret" not in str(resp.json())


def test_create_challenge_requires_admin():
    """With no admin credentials, creating a challenge should require admin."""
    mock_session = AsyncMock()
    app.dependency_overrides[get_session] = _make_session_override(mock_session)
    try:
        with patch("app.main.aioredis.from_url", return_value=_mock_redis()):
            with TestClient(app) as client:
                resp = client.post(
                    "/seasons/11111111-1111-1111-1111-111111111111/challenges",
                    json={"title": "Test", "goal": "Classify"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 403
