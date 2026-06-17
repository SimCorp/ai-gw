# services/league/tests/test_submissions.py
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import app.routers.submissions as _subs_mod
from app.auth import require_dev_auth
from app.db import get_session
from app.main import app

_CHALLENGE_ID = "22222222-2222-2222-2222-222222222222"
_SEASON_ID = "11111111-1111-1111-1111-111111111111"
_USER_ID = "00000000-0000-0000-0000-000000000001"


def _make_session_override(mock_session):
    async def _override():
        yield mock_session

    return _override


async def _fake_dev_auth():
    return {"user_id": _USER_ID, "email": "dev@simcorp.com"}


def _mock_redis():
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    r.aclose = AsyncMock()
    return r


def _mock_active_challenge():
    return {
        "id": _CHALLENGE_ID,
        "season_id": _SEASON_ID,
        "status": "active",
        "max_league_attempts": 3,
        "max_tokens_budget": 4096,
        "allowed_models": ["claude-sonnet-4-6"],
        "hidden_test_suite": [
            {"input": "My order is late", "expected": "delivery_issue", "weight": 1.0},
            {"input": "I want a refund", "expected": "refund_request", "weight": 1.0},
        ],
        "training_inputs": [
            {"input": "Test input", "expected": "test_output"},
        ],
        "scoring_weights": {
            "quality": 0.35,
            "robustness": 0.20,
            "token_efficiency": 0.15,
            "speed": 0.10,
            "cost_efficiency": 0.10,
            "improvement_rate": 0.05,
            "creativity": 0.05,
        },
        "season_multiplier": 1.0,
    }


def _mock_litellm_response(output: str, tokens: int = 100, latency_ms: float = 200.0):
    return {
        "choices": [{"message": {"content": output}}],
        "usage": {"total_tokens": tokens},
        "_latency_ms": latency_ms,
    }


def test_training_submission_returns_scores_immediately():
    challenge = _mock_active_challenge()
    mock_session = AsyncMock()

    # Sequence: challenge lookup, prior best (one_or_none), attempt_num (scalar), INSERT sub (scalar), INSERT score, INSERT xp
    challenge_result = MagicMock()
    challenge_result.mappings.return_value.one_or_none.return_value = challenge

    attempt_count_result = MagicMock()
    attempt_count_result.scalar.return_value = 0

    prior_best_result = MagicMock()
    prior_best_result.mappings.return_value.one_or_none.return_value = None

    attempt_num_result = MagicMock()
    attempt_num_result.scalar.return_value = 1

    sub_id_result = MagicMock()
    sub_id_result.scalar.return_value = str(uuid.uuid4())

    mock_session.execute = AsyncMock(
        side_effect=[
            challenge_result,
            prior_best_result,
            attempt_num_result,
            sub_id_result,
            AsyncMock(),  # INSERT score
            AsyncMock(),  # INSERT xp
        ]
    )
    mock_session.commit = AsyncMock()

    litellm_responses = [
        {"output": "test_output", "tokens": 100, "latency_ms": 200.0, "cost_usd": 0.001},
    ]

    app.dependency_overrides[get_session] = _make_session_override(mock_session)
    app.dependency_overrides[require_dev_auth] = _fake_dev_auth
    try:
        with patch("app.main.aioredis.from_url", return_value=_mock_redis()), patch.object(_subs_mod, "_call_litellm", new_callable=AsyncMock, side_effect=litellm_responses):
            with TestClient(app) as client:
                resp = client.post(
                    f"/challenges/{_CHALLENGE_ID}/submit",
                    json={
                        "mode": "training",
                        "system_prompt": "You are a classifier. Output only the category.",
                        "tool_config": [],
                    },
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert "scores" in body
    assert body["scores"]["quality"] == pytest.approx(100.0)


def test_league_submission_hides_scores_until_deadline():
    challenge = _mock_active_challenge()
    mock_session = AsyncMock()

    challenge_result = MagicMock()
    challenge_result.mappings.return_value.one_or_none.return_value = challenge

    attempt_count_result = MagicMock()
    attempt_count_result.scalar.return_value = 0

    prior_best_result = MagicMock()
    prior_best_result.mappings.return_value.one_or_none.return_value = None

    attempt_num_result = MagicMock()
    attempt_num_result.scalar.return_value = 1

    sub_id_result = MagicMock()
    sub_id_result.scalar.return_value = str(uuid.uuid4())

    mock_session.execute = AsyncMock(
        side_effect=[
            challenge_result,
            attempt_count_result,
            prior_best_result,
            attempt_num_result,
            sub_id_result,
            AsyncMock(),  # INSERT score
            AsyncMock(),  # INSERT leaderboard upsert
            AsyncMock(),  # INSERT points_ledger (delta > 0 since prior_best is None)
        ]
    )
    mock_session.commit = AsyncMock()

    litellm_responses = [
        {"output": "delivery_issue", "tokens": 100, "latency_ms": 200.0, "cost_usd": 0.001},
        {"output": "refund_request", "tokens": 100, "latency_ms": 200.0, "cost_usd": 0.001},
    ]

    app.dependency_overrides[get_session] = _make_session_override(mock_session)
    app.dependency_overrides[require_dev_auth] = _fake_dev_auth
    try:
        with patch("app.main.aioredis.from_url", return_value=_mock_redis()), patch("app.routers.submissions._call_litellm", new_callable=AsyncMock, side_effect=litellm_responses):
            with TestClient(app) as client:
                resp = client.post(
                    f"/challenges/{_CHALLENGE_ID}/submit",
                    json={
                        "mode": "league",
                        "system_prompt": "Classify intent.",
                        "tool_config": [],
                    },
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert "scores" not in body
    assert body["message"] == "Submission received. Scores will be revealed when the challenge closes."


def test_league_submission_blocks_over_limit():
    challenge = _mock_active_challenge()
    mock_session = AsyncMock()

    challenge_result = MagicMock()
    challenge_result.mappings.return_value.one_or_none.return_value = challenge

    attempt_count_result = MagicMock()
    attempt_count_result.scalar.return_value = 3  # already at limit

    mock_session.execute = AsyncMock(
        side_effect=[
            challenge_result,
            attempt_count_result,
        ]
    )

    app.dependency_overrides[get_session] = _make_session_override(mock_session)
    app.dependency_overrides[require_dev_auth] = _fake_dev_auth
    try:
        with patch("app.main.aioredis.from_url", return_value=_mock_redis()):
            with TestClient(app) as client:
                resp = client.post(
                    f"/challenges/{_CHALLENGE_ID}/submit",
                    json={
                        "mode": "league",
                        "system_prompt": "Classify intent.",
                        "tool_config": [],
                    },
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 429
    assert "attempt limit" in resp.json()["detail"].lower()


def test_submission_on_inactive_challenge_rejected():
    draft_challenge = {**_mock_active_challenge(), "status": "draft"}
    mock_session = AsyncMock()

    challenge_result = MagicMock()
    challenge_result.mappings.return_value.one_or_none.return_value = draft_challenge
    mock_session.execute = AsyncMock(return_value=challenge_result)

    app.dependency_overrides[get_session] = _make_session_override(mock_session)
    app.dependency_overrides[require_dev_auth] = _fake_dev_auth
    try:
        with patch("app.main.aioredis.from_url", return_value=_mock_redis()):
            with TestClient(app) as client:
                resp = client.post(
                    f"/challenges/{_CHALLENGE_ID}/submit",
                    json={
                        "mode": "training",
                        "system_prompt": "test",
                        "tool_config": [],
                    },
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 409
