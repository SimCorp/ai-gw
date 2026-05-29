"""Tests for node membership endpoints (rewritten for the org-node refactor).

The old /teams/{id}/members router was removed in migration 0025. Membership is
now managed via /nodes/{id}/members in app/routers/nodes.py:
    GET    /nodes/{id}/members
    POST   /nodes/{id}/members            {"user_id": ...}
    DELETE /nodes/{id}/members/{user_id}

These endpoints authenticate via unified_auth.get_current_user (which does NOT
honour DEV_BYPASS_AUTH), so we override it with a platform_admin fake scoped to
root "/" — a prefix of every node path — so can_access() passes.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

FAKE_USER = {
    "user_id": str(uuid.uuid4()),
    "email": "admin@simcorp.com",
    "display_name": "Admin",
    "roles": [{"role": "platform_admin", "node_path": "/"}],
}


@pytest.fixture
async def member_client(mock_session):
    from app.auth import require_admin_auth
    from app.db import get_session
    from app.main import app
    from app.routers.unified_auth import get_current_user

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_admin_auth] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    app.state.redis = AsyncMock()

    from httpx import ASGITransport, AsyncClient
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Row / result helpers
# ---------------------------------------------------------------------------

def _node_row(node_id):
    return {
        "id": node_id,
        "name": "Team",
        "slug": "team",
        "type": "team",
        "parent_id": None,
        "path": f"/{node_id}",
        "color": None,
        "description": None,
        "location": None,
        "monthly_budget_usd": None,
        "budget_alert_threshold": None,
        "created_at": None,
    }


def _member_row(node_id, user_id=None, role="developer",
                email="dev@simcorp.com", display_name="Dev User"):
    return {
        "id": str(uuid.uuid4()),
        "node_id": node_id,
        "user_id": user_id or str(uuid.uuid4()),
        "role": role,
        "created_at": None,
        "email": email,
        "display_name": display_name,
    }


def _result_mappings_first(row):
    r = MagicMock()
    r.mappings.return_value.first.return_value = row
    return r


def _result_mappings_all(rows):
    r = MagicMock()
    r.mappings.return_value.all.return_value = rows
    return r


def _sequence(*results):
    sess = AsyncMock()
    sess.execute = AsyncMock(side_effect=list(results))
    sess.commit = AsyncMock()
    return sess


def _override(app, sess):
    from app.db import get_session

    async def override():
        yield sess
    app.dependency_overrides[get_session] = override


# ===========================================================================
# GET /nodes/{id}/members
# ===========================================================================

async def test_list_members_returns_200(member_client):
    from app.main import app

    nid = str(uuid.uuid4())
    sess = _sequence(
        _result_mappings_first(_node_row(nid)),                  # _get_node_row
        _result_mappings_all([_member_row(nid), _member_row(nid)]),  # members
    )
    _override(app, sess)

    resp = await member_client.get(f"/nodes/{nid}/members")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 2
    assert body[0]["email"] == "dev@simcorp.com"
    assert body[0]["node_id"] == nid


async def test_list_members_empty(member_client):
    from app.main import app

    nid = str(uuid.uuid4())
    sess = _sequence(
        _result_mappings_first(_node_row(nid)),  # _get_node_row
        _result_mappings_all([]),                # members
    )
    _override(app, sess)

    resp = await member_client.get(f"/nodes/{nid}/members")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_members_node_not_found_returns_404(member_client):
    from app.main import app

    nid = str(uuid.uuid4())
    sess = _sequence(_result_mappings_first(None))  # node missing
    _override(app, sess)

    resp = await member_client.get(f"/nodes/{nid}/members")
    assert resp.status_code == 404


# ===========================================================================
# POST /nodes/{id}/members
# ===========================================================================

async def test_add_member_returns_201(member_client):
    from app.main import app

    nid = str(uuid.uuid4())
    sess = _sequence(
        _result_mappings_first(_node_row(nid)),  # _get_node_row
        MagicMock(),                             # INSERT
    )
    _override(app, sess)

    resp = await member_client.post(
        f"/nodes/{nid}/members",
        json={"user_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 201
    assert resp.json()["ok"] is True


async def test_add_member_missing_user_id_returns_422(member_client):
    from app.main import app

    nid = str(uuid.uuid4())
    # Body validation fails before any DB access, but _get_node_row would be the
    # first call — pydantic rejects the empty body first, so no execute needed.
    sess = _sequence()
    _override(app, sess)

    resp = await member_client.post(f"/nodes/{nid}/members", json={})
    assert resp.status_code == 422


async def test_add_member_node_not_found_returns_404(member_client):
    from app.main import app

    nid = str(uuid.uuid4())
    sess = _sequence(_result_mappings_first(None))  # node missing
    _override(app, sess)

    resp = await member_client.post(
        f"/nodes/{nid}/members",
        json={"user_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


# ===========================================================================
# DELETE /nodes/{id}/members/{user_id}
# ===========================================================================

async def test_remove_member_returns_204(member_client):
    from app.main import app

    nid = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    sess = _sequence(
        _result_mappings_first(_node_row(nid)),  # _get_node_row
        MagicMock(),                             # DELETE
    )
    _override(app, sess)

    resp = await member_client.delete(f"/nodes/{nid}/members/{uid}")
    assert resp.status_code == 204


async def test_remove_member_node_not_found_returns_404(member_client):
    from app.main import app

    nid = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    sess = _sequence(_result_mappings_first(None))  # node missing
    _override(app, sess)

    resp = await member_client.delete(f"/nodes/{nid}/members/{uid}")
    assert resp.status_code == 404
