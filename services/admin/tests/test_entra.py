"""Tests for the Entra group → role mapping router (/settings/entra).

Backed by role_assignments after the org-node refactor. The router depends on
require_platform_admin (= Depends(get_current_user)); we override
get_current_user with a platform_admin fake so the dependency passes.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

FAKE_ADMIN = {
    "user_id": str(uuid.uuid4()),
    "email": "admin@simcorp.com",
    "display_name": "Admin",
    "roles": [{"role": "platform_admin", "node_path": "/"}],
}


@pytest.fixture
async def entra_client(mock_session):
    from app.auth import require_admin_auth
    from app.db import get_session
    from app.main import app
    from app.routers.unified_auth import get_current_user

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_admin_auth] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: FAKE_ADMIN
    app.state.redis = AsyncMock()

    from httpx import ASGITransport, AsyncClient
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c

    app.dependency_overrides.clear()


def _result_mappings_all(rows):
    r = MagicMock()
    r.mappings.return_value.all.return_value = rows
    return r


def _result_mappings_first(row):
    r = MagicMock()
    r.mappings.return_value.first.return_value = row
    return r


def _result_mappings_one(row):
    r = MagicMock()
    r.mappings.return_value.one.return_value = row
    return r


def _result_fetchone(value):
    r = MagicMock()
    r.fetchone.return_value = value
    return r


def _sequence(*results):
    sess = AsyncMock()
    sess.execute = AsyncMock(side_effect=list(results))
    sess.commit = AsyncMock()
    return sess


def _override_session(app, sess):
    from app.db import get_session

    async def override():
        yield sess
    app.dependency_overrides[get_session] = override


# ===========================================================================
# GET — list mappings
# ===========================================================================

async def test_list_mappings_maps_root_to_global(entra_client, mock_session):
    # The list query already applies the root→'global' CASE in SQL; we just
    # verify the row passes through unchanged.
    rows = [
        {
            "id": str(uuid.uuid4()),
            "entra_group_id": "grp-1",
            "entra_group_name": "Platform Admins",
            "role": "platform_admin",
            "scope_id": str(uuid.uuid4()),
            "created_at": None,
            "scope_type": "global",
            "scope_name": None,
            "created_by_email": None,
        },
        {
            "id": str(uuid.uuid4()),
            "entra_group_id": "grp-2",
            "entra_group_name": "Team Devs",
            "role": "developer",
            "scope_id": str(uuid.uuid4()),
            "created_at": None,
            "scope_type": "team",
            "scope_name": "Core Team",
            "created_by_email": None,
        },
    ]
    mock_session.execute.return_value = _result_mappings_all(rows)

    resp = await entra_client.get("/settings/entra")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["scope_type"] == "global"
    assert body[1]["scope_type"] == "team"
    assert body[1]["scope_name"] == "Core Team"


# ===========================================================================
# POST — create mapping
# ===========================================================================

async def test_create_global_mapping_resolves_root_node(entra_client):
    from app.main import app

    root_id = str(uuid.uuid4())
    new_id = str(uuid.uuid4())
    inserted = {
        "id": new_id,
        "entra_group_id": "grp-glob",
        "entra_group_name": "Admins",
        "role": "platform_admin",
        "scope_id": root_id,
        "created_at": None,
    }
    # create_mapping (global): _root_node_id SELECT, then INSERT...RETURNING
    sess = _sequence(
        _result_mappings_first({"id": root_id}),  # _root_node_id
        _result_mappings_one(inserted),           # INSERT RETURNING
    )
    _override_session(app, sess)

    resp = await entra_client.post("/settings/entra", json={
        "entra_group_id": "grp-glob",
        "entra_group_name": "Admins",
        "role": "platform_admin",
        "scope_type": "global",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["entra_group_id"] == "grp-glob"
    assert body["scope_id"] == root_id


async def test_create_team_scoped_mapping(entra_client):
    from app.main import app

    team_node = str(uuid.uuid4())
    new_id = str(uuid.uuid4())
    inserted = {
        "id": new_id,
        "entra_group_id": "grp-team",
        "entra_group_name": "Team",
        "role": "developer",
        "scope_id": team_node,
        "created_at": None,
    }
    # scope_type='team' with scope_id → no root lookup, just INSERT.
    sess = _sequence(_result_mappings_one(inserted))
    _override_session(app, sess)

    resp = await entra_client.post("/settings/entra", json={
        "entra_group_id": "grp-team",
        "entra_group_name": "Team",
        "role": "developer",
        "scope_type": "team",
        "scope_id": team_node,
    })
    assert resp.status_code == 201
    assert resp.json()["scope_id"] == team_node


async def test_create_invalid_role_returns_422(entra_client, mock_session):
    # Validation runs before any DB access.
    resp = await entra_client.post("/settings/entra", json={
        "entra_group_id": "grp-x",
        "role": "supreme_leader",
        "scope_type": "global",
    })
    assert resp.status_code == 422


async def test_create_area_scope_without_scope_id_returns_422(entra_client, mock_session):
    resp = await entra_client.post("/settings/entra", json={
        "entra_group_id": "grp-y",
        "role": "area_owner",
        "scope_type": "area",
        # scope_id omitted → must 422
    })
    assert resp.status_code == 422


# ===========================================================================
# DELETE
# ===========================================================================

async def test_delete_mapping_returns_204(entra_client):
    from app.main import app

    mapping_id = str(uuid.uuid4())
    sess = _sequence(_result_fetchone((mapping_id,)))  # DELETE...RETURNING found
    _override_session(app, sess)

    resp = await entra_client.delete(f"/settings/entra/{mapping_id}")
    assert resp.status_code == 204


async def test_delete_mapping_not_found_returns_404(entra_client):
    from app.main import app

    mapping_id = str(uuid.uuid4())
    sess = _sequence(_result_fetchone(None))  # DELETE found nothing
    _override_session(app, sess)

    resp = await entra_client.delete(f"/settings/entra/{mapping_id}")
    assert resp.status_code == 404
