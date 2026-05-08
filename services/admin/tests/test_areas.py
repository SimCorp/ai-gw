"""Tests for /areas endpoints."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _area_list_row(area_id=None):
    """Row returned by list_areas (includes team_count and has_policy)."""
    _id = area_id or uuid.uuid4()
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "id": _id,
        "name": "Engineering",
        "slug": "engineering",
        "description": "Software teams",
        "color": "#0A7BD7",
        "created_at": None,
        "team_count": 2,
        "has_policy": False,
    }[k]
    return row


def _mappings_all(rows):
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    return result


def _mappings_one_or_none(row):
    result = MagicMock()
    result.mappings.return_value.one_or_none.return_value = row
    return result


def _mappings_one(row):
    result = MagicMock()
    result.mappings.return_value.one.return_value = row
    return result


def _area_detail_row(area_id):
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "id": area_id,
        "name": "Engineering",
        "slug": "engineering",
        "description": "Software teams",
        "color": "#0A7BD7",
        "created_at": None,
    }[k]
    return row


def _teams_list_result(rows):
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    return result


def _policy_row(area_id):
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "id": uuid.uuid4(),
        "area_id": area_id,
        "cache_ttl_seconds": 3600,
        "cache_similarity_threshold": 0.95,
        "cache_opt_out": False,
        "embedding_model": "text-embedding-3-small",
        "rate_limit_rpm": 1000,
        "allowed_models": [],
        "updated_at": None,
    }[k]
    return row


def _area_policy_upsert_row(area_id):
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "id": uuid.uuid4(),
        "area_id": area_id,
        "cache_ttl_seconds": 3600,
        "cache_similarity_threshold": 0.95,
        "cache_opt_out": False,
        "embedding_model": "text-embedding-3-small",
        "rate_limit_rpm": 1000,
        "allowed_models": [],
        "updated_at": None,
    }[k]
    return row


# ---------------------------------------------------------------------------
# GET /areas
# ---------------------------------------------------------------------------

async def test_list_areas_returns_200(client, mock_session):
    mock_session.execute.return_value = _mappings_all([_area_list_row()])

    resp = await client.get("/areas")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["name"] == "Engineering"


# ---------------------------------------------------------------------------
# POST /areas
# ---------------------------------------------------------------------------

async def test_create_area_returns_201(client, mock_session):
    area_id = uuid.uuid4()
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "id": area_id,
        "name": "Finance",
        "slug": "finance",
        "description": None,
        "color": None,
        "created_at": None,
    }[k]
    mock_session.execute.return_value = _mappings_one(row)

    resp = await client.post("/areas", json={"name": "Finance", "slug": "finance"})

    assert resp.status_code == 201
    body = resp.json()
    assert body["slug"] == "finance"


# ---------------------------------------------------------------------------
# GET /areas/{id}
# ---------------------------------------------------------------------------

async def test_get_area_found(client, mock_session):
    area_id = uuid.uuid4()
    area_row = _area_detail_row(area_id)
    no_policy = _mappings_one_or_none(None)

    mock_session.execute.side_effect = [
        _mappings_one_or_none(area_row),   # area lookup
        _mappings_all([]),                  # teams list
        no_policy,                          # policy lookup
    ]

    resp = await client.get(f"/areas/{area_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert "area" in body
    assert "teams" in body
    assert "policy" in body
    assert body["area"]["slug"] == "engineering"


async def test_get_area_not_found(client, mock_session):
    area_id = uuid.uuid4()
    mock_session.execute.return_value = _mappings_one_or_none(None)

    resp = await client.get(f"/areas/{area_id}")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /areas/{id}
# ---------------------------------------------------------------------------

async def test_update_area_found(client, mock_session):
    area_id = uuid.uuid4()
    row = _area_detail_row(area_id)
    mock_session.execute.return_value = _mappings_one_or_none(row)

    resp = await client.put(
        f"/areas/{area_id}",
        json={"name": "Engineering Updated", "slug": "engineering-updated"},
    )

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# DELETE /areas/{id}
# ---------------------------------------------------------------------------

async def test_delete_area_found(client, mock_session):
    area_id = uuid.uuid4()
    # delete_area uses result.fetchone() — not mappings()
    delete_result = MagicMock()
    delete_result.fetchone.return_value = (area_id,)
    mock_session.execute.return_value = delete_result

    resp = await client.delete(f"/areas/{area_id}")

    assert resp.status_code == 204


async def test_delete_area_not_found(client, mock_session):
    area_id = uuid.uuid4()
    delete_result = MagicMock()
    delete_result.fetchone.return_value = None
    mock_session.execute.return_value = delete_result

    resp = await client.delete(f"/areas/{area_id}")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /areas/{id}/policy
# ---------------------------------------------------------------------------

async def test_get_area_policy_returns_200(client, mock_session):
    area_id = uuid.uuid4()

    # First execute: area existence check using .one_or_none() directly on result
    area_exists_result = MagicMock()
    area_exists_result.one_or_none.return_value = (area_id,)

    # Second execute: policy lookup using .mappings().one_or_none()
    policy_row = _policy_row(area_id)
    policy_result = _mappings_one_or_none(policy_row)

    mock_session.execute.side_effect = [area_exists_result, policy_result]

    resp = await client.get(f"/areas/{area_id}/policy")

    assert resp.status_code == 200
    body = resp.json()
    assert "cache_ttl_seconds" in body


async def test_get_area_policy_no_policy_returns_empty_dict(client, mock_session):
    area_id = uuid.uuid4()

    area_exists_result = MagicMock()
    area_exists_result.one_or_none.return_value = (area_id,)

    no_policy_result = _mappings_one_or_none(None)

    mock_session.execute.side_effect = [area_exists_result, no_policy_result]

    resp = await client.get(f"/areas/{area_id}/policy")

    assert resp.status_code == 200
    assert resp.json() == {}


# ---------------------------------------------------------------------------
# PUT /areas/{id}/policy
# ---------------------------------------------------------------------------

async def test_upsert_area_policy_returns_200(client, mock_session):
    area_id = uuid.uuid4()

    # First execute: area existence check
    area_exists_result = MagicMock()
    area_exists_result.one_or_none.return_value = (area_id,)

    # Second execute: the INSERT ... ON CONFLICT upsert returning the row
    upsert_row = _area_policy_upsert_row(area_id)
    upsert_result = _mappings_one(upsert_row)

    mock_session.execute.side_effect = [area_exists_result, upsert_result]

    resp = await client.put(
        f"/areas/{area_id}/policy",
        json={
            "cache_ttl_seconds": 3600,
            "cache_similarity_threshold": 0.95,
            "cache_opt_out": False,
            "embedding_model": "text-embedding-3-small",
            "rate_limit_rpm": 1000,
            "allowed_models": [],
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["area_id"] == str(area_id)
    assert body["cache_ttl_seconds"] == 3600

    # Verify redis.hset was called with the area policy key
    from app.main import app as fastapi_app
    redis = fastapi_app.state.redis
    redis.hset.assert_called_once()
    key_used = redis.hset.call_args[0][0]
    assert str(area_id) in key_used
