"""Tests for the local-groups CRUD router (added 2026-06-22).

Local groups bundle local-account users so admins can assign them roles on org
nodes. Endpoints authenticate via unified_auth.get_current_user and gate on
can_access; we override get_current_user with a fake platform_admin scoped to "/"
(a prefix of every path) and supply a sequenced mock session.
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
async def lg_client(mock_session):
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

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


def _mappings_all(rows):
    r = MagicMock()
    r.mappings.return_value.all.return_value = rows
    return r


def _first(value):
    r = MagicMock()
    r.first.return_value = value
    return r


def _sequence(*results):
    sess = AsyncMock()
    sess.execute = AsyncMock(side_effect=list(results))
    sess.commit = AsyncMock()
    return sess


def _use(sess):
    from app.db import get_session
    from app.main import app

    async def override():
        yield sess

    app.dependency_overrides[get_session] = override


async def test_list_groups_returns_rows(lg_client):
    row = {"id": "lcl-1", "name": "Platform", "created_at": None, "member_count": 3}
    _use(_sequence(_mappings_all([row])))

    resp = await lg_client.get("/admin/local-groups")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["id"] == "lcl-1"
    assert body[0]["member_count"] == 3


async def test_create_group_returns_201_with_prefixed_id(lg_client):
    _use(_sequence(MagicMock()))  # INSERT

    resp = await lg_client.post("/admin/local-groups", json={"name": "Ops"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Ops"
    assert body["id"].startswith("lcl-")


async def test_delete_group_returns_204(lg_client):
    _use(_sequence(MagicMock(), MagicMock()))  # delete role_assignments, delete group

    resp = await lg_client.delete("/admin/local-groups/lcl-1")
    assert resp.status_code == 204


async def test_list_members_returns_users(lg_client):
    member = {
        "id": uuid.uuid4(),
        "email": "dev@simcorp.com",
        "display_name": "Dev",
        "group_id": "lcl-1",
    }
    _use(_sequence(_mappings_all([member])))

    resp = await lg_client.get("/admin/local-groups/lcl-1/members")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["email"] == "dev@simcorp.com"


async def test_add_member_returns_201(lg_client):
    _use(_sequence(_first(("lcl-1",)), MagicMock()))  # group exists, then INSERT

    resp = await lg_client.post(
        "/admin/local-groups/lcl-1/members", json={"user_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 201
    assert resp.json()["ok"] is True


async def test_add_member_unknown_group_returns_404(lg_client):
    _use(_sequence(_first(None)))  # group does not exist

    resp = await lg_client.post(
        "/admin/local-groups/nope/members", json={"user_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 404


async def test_remove_member_returns_204(lg_client):
    _use(_sequence(MagicMock()))  # DELETE

    resp = await lg_client.delete(f"/admin/local-groups/lcl-1/members/{uuid.uuid4()}")
    assert resp.status_code == 204
