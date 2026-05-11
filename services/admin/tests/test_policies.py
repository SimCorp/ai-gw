"""Tests for /teams/{id}/policy and /policies endpoints."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_policy_orm(team_id):
    p = MagicMock()
    p.id = uuid.uuid4()
    p.team_id = team_id
    p.project_id = None
    p.cache_ttl_seconds = 3600
    p.cache_similarity_threshold = 0.95
    p.cache_opt_out = False
    p.embedding_model = "text-embedding-3-small"
    p.rate_limit_rpm = 1000
    p.allowed_models = []
    p.updated_at = None
    return p


def _scalars_first(obj):
    result = MagicMock()
    result.scalars.return_value.first.return_value = obj
    return result


def _scalar_one(obj):
    result = MagicMock()
    result.scalar_one.return_value = obj
    return result


def _mappings_all(rows):
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    return result


# ---------------------------------------------------------------------------
# GET /teams/{id}/policy
# ---------------------------------------------------------------------------

async def test_get_policy_found(client, mock_session):
    team_id = uuid.uuid4()
    policy = _make_policy_orm(team_id)
    mock_session.execute.return_value = _scalars_first(policy)

    resp = await client.get(f"/teams/{team_id}/policy")

    assert resp.status_code == 200


async def test_get_policy_not_found_returns_empty_dict(client, mock_session):
    team_id = uuid.uuid4()
    mock_session.execute.return_value = _scalars_first(None)

    resp = await client.get(f"/teams/{team_id}/policy")

    assert resp.status_code == 200
    assert resp.json() == {}


# ---------------------------------------------------------------------------
# PUT /teams/{id}/policy
# ---------------------------------------------------------------------------

async def test_upsert_policy_calls_redis_hset(client, mock_session):
    team_id = uuid.uuid4()
    policy = _make_policy_orm(team_id)
    mock_session.execute.return_value = _scalar_one(policy)

    resp = await client.put(
        f"/teams/{team_id}/policy",
        json={
            "cache_ttl_seconds": 1800,
            "cache_similarity_threshold": 0.9,
            "cache_opt_out": False,
            "embedding_model": "text-embedding-3-small",
            "rate_limit_rpm": 500,
            "allowed_models": [],
        },
    )

    assert resp.status_code == 200
    from app.main import app as fastapi_app
    redis = fastapi_app.state.redis
    redis.hset.assert_called_once()
    call_args = redis.hset.call_args
    # key should be policy:{team_id}
    assert str(team_id) in call_args[0][0]


async def test_upsert_policy_with_project_id_includes_project_in_key(client, mock_session):
    team_id = uuid.uuid4()
    project_id = uuid.uuid4()
    policy = _make_policy_orm(team_id)
    policy.project_id = project_id
    mock_session.execute.return_value = _scalar_one(policy)

    resp = await client.put(
        f"/teams/{team_id}/policy",
        json={
            "project_id": str(project_id),
            "cache_ttl_seconds": 3600,
            "cache_similarity_threshold": 0.95,
            "cache_opt_out": False,
            "embedding_model": "text-embedding-3-small",
            "rate_limit_rpm": 1000,
            "allowed_models": [],
        },
    )

    assert resp.status_code == 200
    from app.main import app as fastapi_app
    redis = fastapi_app.state.redis
    redis.hset.assert_called()
    key_used = redis.hset.call_args[0][0]
    assert str(project_id) in key_used


# ---------------------------------------------------------------------------
# GET /policies
# ---------------------------------------------------------------------------

async def test_list_all_policies_returns_200(client, mock_session):
    team_id = uuid.uuid4()
    policy_id = uuid.uuid4()

    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "team_id": team_id,
        "team_name": "Engineering",
        "team_slug": "engineering",
        "policy_id": policy_id,
        "cache_ttl_seconds": 3600,
        "cache_similarity_threshold": 0.95,
        "cache_opt_out": False,
        "embedding_model": "text-embedding-3-small",
        "rate_limit_rpm": 1000,
        "allowed_models": [],
        "updated_at": None,
    }[k]

    mock_session.execute.return_value = _mappings_all([row])

    resp = await client.get("/policies")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["team_name"] == "Engineering"
    assert body[0]["policy"] is not None
