"""Tests for the unified /nodes organization-tree router.

These endpoints authenticate via unified_auth.get_current_user. We use a
node_client fixture that overrides get_current_user with a fake
platform_admin whose role is scoped to the root path "/". Because "/" is a
prefix of every node path, can_access() passes for every permission tier.

require_platform_admin is Depends(get_current_user), so overriding
get_current_user propagates to it automatically.
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def node_client(mock_session):
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


# ---------------------------------------------------------------------------
# Row helpers — complete column set that _node_to_dict reads
# ---------------------------------------------------------------------------


def _node_row(
    node_id=None,
    name="Platform",
    slug="platform",
    type="team",
    parent_id=None,
    path=None,
    color=None,
    description=None,
    location=None,
    monthly_budget_usd=None,
    budget_alert_threshold=None,
):
    nid = node_id or str(uuid.uuid4())
    return {
        "id": nid,
        "name": name,
        "slug": slug,
        "type": type,
        "parent_id": parent_id,
        "path": path or f"/{nid}",
        "color": color,
        "description": description,
        "location": location,
        "monthly_budget_usd": monthly_budget_usd,
        "budget_alert_threshold": budget_alert_threshold,
        "created_at": None,
    }


def _result_mappings_all(rows):
    r = MagicMock()
    r.mappings.return_value.all.return_value = rows
    return r


def _result_mappings_first(row):
    r = MagicMock()
    r.mappings.return_value.first.return_value = row
    return r


def _result_first(value):
    """For .first() (tuple-style) and .scalar() callers."""
    r = MagicMock()
    r.first.return_value = value
    return r


def _result_scalar(value):
    r = MagicMock()
    r.scalar.return_value = value
    return r


def _sequence(*results):
    """Build a mock session whose execute() yields each result in order."""
    sess = AsyncMock()
    sess.execute = AsyncMock(side_effect=list(results))
    sess.commit = AsyncMock()
    return sess


# ===========================================================================
# GET /nodes  (list)
# ===========================================================================


async def test_list_nodes_returns_200(node_client, mock_session):
    rows = [_node_row(name="Area", type="area"), _node_row(name="Team", type="team")]
    mock_session.execute.return_value = _result_mappings_all(rows)

    resp = await node_client.get("/nodes")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 2
    assert body[0]["name"] == "Area"


async def test_list_nodes_empty(node_client, mock_session):
    mock_session.execute.return_value = _result_mappings_all([])
    resp = await node_client.get("/nodes")
    assert resp.status_code == 200
    assert resp.json() == []


# ===========================================================================
# GET /nodes/tree
# ===========================================================================


async def test_get_tree_nests_children(node_client, mock_session):
    root_id = str(uuid.uuid4())
    child_id = str(uuid.uuid4())
    rows = [
        _node_row(node_id=root_id, name="Root", type="area", parent_id=None, path=f"/{root_id}"),
        _node_row(
            node_id=child_id,
            name="Child",
            type="team",
            parent_id=root_id,
            path=f"/{root_id}/{child_id}",
        ),
    ]
    mock_session.execute.return_value = _result_mappings_all(rows)

    resp = await node_client.get("/nodes/tree")
    assert resp.status_code == 200
    tree = resp.json()
    assert len(tree) == 1
    assert tree[0]["name"] == "Root"
    assert len(tree[0]["children"]) == 1
    assert tree[0]["children"][0]["name"] == "Child"


# ===========================================================================
# POST /nodes  (create)
# ===========================================================================


async def test_create_root_node_returns_201(node_client):
    from app.db import get_session
    from app.main import app

    new_row = _node_row(name="New Area", type="area", parent_id=None)
    # create_node (root branch): 1 INSERT, then _get_node_row SELECT.
    sess = _sequence(
        MagicMock(),  # INSERT
        _result_mappings_first(new_row),  # _get_node_row
    )

    async def override():
        yield sess

    app.dependency_overrides[get_session] = override

    resp = await node_client.post("/nodes", json={"name": "New Area", "type": "area"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "New Area"
    assert body["type"] == "area"


async def test_create_child_node_under_parent(node_client):
    from app.db import get_session
    from app.main import app

    parent_id = str(uuid.uuid4())
    parent_path = f"/{parent_id}"
    new_row = _node_row(name="Sub Team", type="team", parent_id=parent_id, path=f"{parent_path}/x")
    # create_node (child branch): SELECT parent path, INSERT, _get_node_row.
    sess = _sequence(
        _result_first((parent_id, parent_path)),  # parent lookup
        MagicMock(),  # INSERT
        _result_mappings_first(new_row),  # _get_node_row
    )

    async def override():
        yield sess

    app.dependency_overrides[get_session] = override

    resp = await node_client.post(
        "/nodes",
        json={"name": "Sub Team", "type": "team", "parent_id": parent_id},
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Sub Team"


# ===========================================================================
# GET /nodes/{id}
# ===========================================================================


async def test_get_node_detail(node_client):
    from app.db import get_session
    from app.main import app

    nid = str(uuid.uuid4())
    row = _node_row(node_id=nid, name="Detail Node", parent_id=None)
    # get_node: _get_node_row, children, member_count, spend_mtd
    # (parent branch skipped because parent_id is None)
    sess = _sequence(
        _result_mappings_first(row),  # _get_node_row
        _result_mappings_all([]),  # children
        _result_scalar(0),  # member_count
        _result_scalar(0),  # spend_mtd
    )

    async def override():
        yield sess

    app.dependency_overrides[get_session] = override

    resp = await node_client.get(f"/nodes/{nid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == nid
    assert body["member_count"] == 0
    assert body["spend_mtd"] == 0.0
    assert body["children"] == []


async def test_get_node_not_found(node_client, mock_session):
    mock_session.execute.return_value = _result_mappings_first(None)
    resp = await node_client.get(f"/nodes/{uuid.uuid4()}")
    assert resp.status_code == 404


# ===========================================================================
# Permissions (role_assignments)
# ===========================================================================


async def test_list_permissions(node_client):
    from app.db import get_session
    from app.main import app

    nid = str(uuid.uuid4())
    node = _node_row(node_id=nid)
    assignment = {
        "id": str(uuid.uuid4()),
        "entra_group_id": "grp-1",
        "entra_group_name": "Engineers",
        "role": "developer",
        "node_id": nid,
        "granted_at": None,
        "granted_by": None,
        "granted_by_email": None,
    }
    sess = _sequence(
        _result_mappings_first(node),  # _get_node_row
        _result_mappings_all([assignment]),  # assignments
    )

    async def override():
        yield sess

    app.dependency_overrides[get_session] = override

    resp = await node_client.get(f"/nodes/{nid}/permissions")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["entra_group_id"] == "grp-1"
    assert body[0]["role"] == "developer"


async def test_add_permission_returns_201(node_client):
    from app.db import get_session
    from app.main import app

    nid = str(uuid.uuid4())
    node = _node_row(node_id=nid)
    sess = _sequence(
        _result_mappings_first(node),  # _get_node_row
        MagicMock(),  # INSERT
    )

    async def override():
        yield sess

    app.dependency_overrides[get_session] = override

    resp = await node_client.post(
        f"/nodes/{nid}/permissions",
        json={"entra_group_id": "grp-9", "entra_group_name": "Ops", "role": "team_admin"},
    )
    assert resp.status_code == 201
    assert resp.json()["ok"] is True


async def test_add_permission_invalid_role_returns_422(node_client):
    from app.db import get_session
    from app.main import app

    nid = str(uuid.uuid4())
    node = _node_row(node_id=nid)
    sess = _sequence(_result_mappings_first(node))  # only _get_node_row reached

    async def override():
        yield sess

    app.dependency_overrides[get_session] = override

    resp = await node_client.post(
        f"/nodes/{nid}/permissions",
        json={"entra_group_id": "grp-9", "role": "wizard"},
    )
    assert resp.status_code == 422


async def test_remove_permission_returns_204(node_client):
    from app.db import get_session
    from app.main import app

    nid = str(uuid.uuid4())
    aid = str(uuid.uuid4())
    node = _node_row(node_id=nid)
    sess = _sequence(
        _result_mappings_first(node),  # _get_node_row
        MagicMock(),  # DELETE
    )

    async def override():
        yield sess

    app.dependency_overrides[get_session] = override

    resp = await node_client.delete(f"/nodes/{nid}/permissions/{aid}")
    assert resp.status_code == 204


# ===========================================================================
# Members
# ===========================================================================


async def test_list_members(node_client):
    from app.db import get_session
    from app.main import app

    nid = str(uuid.uuid4())
    node = _node_row(node_id=nid)
    member = {
        "id": str(uuid.uuid4()),
        "node_id": nid,
        "user_id": str(uuid.uuid4()),
        "role": "developer",
        "created_at": None,
        "email": "dev@simcorp.com",
        "display_name": "Dev User",
    }
    sess = _sequence(
        _result_mappings_first(node),  # _get_node_row
        _result_mappings_all([member]),  # members
    )

    async def override():
        yield sess

    app.dependency_overrides[get_session] = override

    resp = await node_client.get(f"/nodes/{nid}/members")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["email"] == "dev@simcorp.com"


async def test_add_member_returns_201(node_client):
    from app.db import get_session
    from app.main import app

    nid = str(uuid.uuid4())
    node = _node_row(node_id=nid)
    sess = _sequence(
        _result_mappings_first(node),  # _get_node_row
        MagicMock(),  # INSERT
    )

    async def override():
        yield sess

    app.dependency_overrides[get_session] = override

    resp = await node_client.post(
        f"/nodes/{nid}/members",
        json={"user_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 201
    assert resp.json()["ok"] is True


async def test_remove_member_returns_204(node_client):
    from app.db import get_session
    from app.main import app

    nid = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    node = _node_row(node_id=nid)
    sess = _sequence(
        _result_mappings_first(node),  # _get_node_row
        MagicMock(),  # DELETE
    )

    async def override():
        yield sess

    app.dependency_overrides[get_session] = override

    resp = await node_client.delete(f"/nodes/{nid}/members/{uid}")
    assert resp.status_code == 204


# ===========================================================================
# Budget — including Redis write-through
# ===========================================================================


async def test_put_budget_writes_through_to_redis(node_client):
    from app.db import get_session
    from app.main import app

    nid = str(uuid.uuid4())
    # parent_id=None so the parent-budget validation branch is skipped.
    node = _node_row(node_id=nid, parent_id=None)
    final_row = {"monthly_budget_usd": 500.0, "budget_alert_threshold": 0.9}
    # set_budget: _get_node_row, UPDATE, final SELECT (then redis write-through)
    sess = _sequence(
        _result_mappings_first(node),  # _get_node_row
        MagicMock(),  # UPDATE
        _result_mappings_first(final_row),  # final SELECT for write-through
    )

    async def override():
        yield sess

    app.dependency_overrides[get_session] = override

    resp = await node_client.put(
        f"/nodes/{nid}/budget",
        json={"monthly_budget_usd": 500.0, "budget_alert_threshold": 0.9},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # The write-through must set budget_limit:team:{node_id} in Redis.
    redis = app.state.redis
    redis.set.assert_called_once()
    call_args = redis.set.call_args
    assert call_args.args[0] == f"budget_limit:team:{nid}"
    import json

    payload = json.loads(call_args.args[1])
    assert payload["limit"] == 500.0
    assert payload["alert_pct"] == 0.9


async def test_get_budget(node_client):
    from app.db import get_session
    from app.main import app

    nid = str(uuid.uuid4())
    node = _node_row(
        node_id=nid, parent_id=None, monthly_budget_usd=1000.0, budget_alert_threshold=0.75
    )
    # get_budget: _get_node_row, spend_subtree, spend_children
    # (parent branch skipped because parent_id is None)
    sess = _sequence(
        _result_mappings_first(node),  # _get_node_row
        _result_scalar(200.0),  # spend_subtree
        _result_scalar(50.0),  # spend_children
    )

    async def override():
        yield sess

    app.dependency_overrides[get_session] = override

    resp = await node_client.get(f"/nodes/{nid}/budget")
    assert resp.status_code == 200
    body = resp.json()
    assert body["budget_usd"] == 1000.0
    assert body["spend_mtd"] == 200.0
    assert body["spend_own_mtd"] == 150.0
    assert body["spend_children_mtd"] == 50.0
    assert body["pct_used"] == 0.2
    assert body["alert_threshold"] == 0.75
