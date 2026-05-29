"""Integration tests for organization "area" nodes.

The org-node refactor removed the dedicated /areas endpoints; areas are now
just nodes with type='area' on the unified /nodes surface
(services/admin/app/routers/nodes.py). These tests were rewritten from /areas
to /nodes accordingly.

Tests cover:
  - Full CRUD lifecycle: create → list → get → update → delete
  - 404 on missing resource
  - Node policy get/set (the {explicit, inherited} contract)

Notes on what changed vs the old /areas tests:
  - Area nodes are created *under* the root node (a parent_id is required so the
    node can be deleted afterwards; root nodes are undeletable).
  - The node create response has no caller-supplied slug — slug is derived from
    the name server-side — so we assert slug is present rather than echoing an
    input slug.
  - The old GET /areas/{id} "{area, teams, policy}" envelope has no /nodes
    equivalent; GET /nodes/{id} returns the node fields plus parent/children/
    member_count/spend_mtd. The get test was rewritten to that contract.
  - The old area-policy tests assumed a flat policy row with an `id`. The
    /nodes/{id}/policy contract is GET → {explicit, inherited} and PUT → {ok}.
    Those tests were rewritten to the new contract; the idempotency-by-row-id
    test was dropped (no row id is exposed and policy upsert idempotency is
    covered by test_admin_policies.py).
"""

import uuid

import pytest

from conftest import ADMIN_URL  # noqa: F401 — also used for URL building


# ── Helpers ──────────────────────────────────────────────────────────────────


def _area_payload(parent_id: str, suffix: str | None = None) -> dict:
    uid = suffix or uuid.uuid4().hex[:8]
    return {
        "name": f"area-{uid}",
        "type": "area",
        "parent_id": parent_id,
        "color": "#4A90E2",
    }


# ── Create ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_area_returns_201(admin_client, root_node_id):
    """POST /nodes (type=area) must return 201 and the created node object."""
    payload = _area_payload(root_node_id)
    resp = await admin_client.post("/nodes", json=payload)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "id" in data
    assert data["name"] == payload["name"]
    assert data["type"] == "area"

    # cleanup
    await admin_client.delete(f"/nodes/{data['id']}")


@pytest.mark.asyncio
async def test_create_area_response_shape(admin_client, root_node_id):
    """POST /nodes response must include id, name, slug, type, color, created_at."""
    payload = _area_payload(root_node_id)
    resp = await admin_client.post("/nodes", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    for field in ("id", "name", "slug", "type", "color", "created_at"):
        assert field in data, f"Node response missing field '{field}'"

    # cleanup
    await admin_client.delete(f"/nodes/{data['id']}")


# ── List ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_areas_returns_200(admin_client):
    """GET /nodes?type=area must return 200 with a list."""
    resp = await admin_client.get("/nodes", params={"type": "area"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_areas_includes_created_area(admin_client, root_node_id):
    """An area node just created must appear in GET /nodes?type=area."""
    payload = _area_payload(root_node_id)
    create_resp = await admin_client.post("/nodes", json=payload)
    assert create_resp.status_code == 201
    area_id = create_resp.json()["id"]

    try:
        list_resp = await admin_client.get("/nodes", params={"type": "area"})
        assert list_resp.status_code == 200
        ids = [a["id"] for a in list_resp.json()]
        assert area_id in ids, f"Created area node {area_id!r} not found in list"
    finally:
        await admin_client.delete(f"/nodes/{area_id}")


# ── Get ───────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_area_returns_correct_fields(admin_client, root_node_id):
    """GET /nodes/{id} must return the node with parent/children/member_count."""
    payload = _area_payload(root_node_id)
    create_resp = await admin_client.post("/nodes", json=payload)
    assert create_resp.status_code == 201
    area_id = create_resp.json()["id"]

    try:
        resp = await admin_client.get(f"/nodes/{area_id}")
        assert resp.status_code == 200
        data = resp.json()
        # GET /nodes/{id} returns the node fields plus a nested envelope.
        assert data["id"] == area_id
        assert data["type"] == "area"
        for field in ("parent", "children", "member_count", "spend_mtd"):
            assert field in data, f"Node detail missing field '{field}'"
    finally:
        await admin_client.delete(f"/nodes/{area_id}")


@pytest.mark.asyncio
async def test_get_area_not_found_returns_404(admin_client):
    """GET /nodes/{non-existent-id} must return 404."""
    resp = await admin_client.get(f"/nodes/{uuid.uuid4()}")
    assert resp.status_code == 404


# ── Update ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_area_returns_200(admin_client, root_node_id):
    """PUT /nodes/{id} must return 200 with updated values."""
    payload = _area_payload(root_node_id)
    create_resp = await admin_client.post("/nodes", json=payload)
    assert create_resp.status_code == 201
    area_id = create_resp.json()["id"]

    try:
        uid = uuid.uuid4().hex[:8]
        update_payload = {
            "name": f"updated-area-{uid}",
            "color": "#FF0000",
        }
        resp = await admin_client.put(f"/nodes/{area_id}", json=update_payload)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["name"] == update_payload["name"]
        assert data["color"] == "#FF0000"
    finally:
        await admin_client.delete(f"/nodes/{area_id}")


# ── Delete ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_area_returns_204(admin_client, root_node_id):
    """DELETE /nodes/{id} must return 204."""
    payload = _area_payload(root_node_id)
    create_resp = await admin_client.post("/nodes", json=payload)
    assert create_resp.status_code == 201
    area_id = create_resp.json()["id"]

    delete_resp = await admin_client.delete(f"/nodes/{area_id}")
    assert delete_resp.status_code == 204

    # Confirm it's gone
    get_resp = await admin_client.get(f"/nodes/{area_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_area_twice_returns_404(admin_client, root_node_id):
    """Deleting a node twice — the second DELETE must return 404."""
    payload = _area_payload(root_node_id)
    create_resp = await admin_client.post("/nodes", json=payload)
    assert create_resp.status_code == 201
    area_id = create_resp.json()["id"]

    first = await admin_client.delete(f"/nodes/{area_id}")
    assert first.status_code == 204

    second = await admin_client.delete(f"/nodes/{area_id}")
    assert second.status_code == 404


# ── Node Policy ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_area_policy_returns_200_empty_when_no_policy(admin_client, root_node_id):
    """GET /nodes/{id}/policy must return 200 with the {explicit, inherited}
    envelope (explicit empty) when no policy is set on the node."""
    payload = _area_payload(root_node_id)
    create_resp = await admin_client.post("/nodes", json=payload)
    assert create_resp.status_code == 201
    area_id = create_resp.json()["id"]

    try:
        resp = await admin_client.get(f"/nodes/{area_id}/policy")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert "explicit" in data
        assert "inherited" in data
        # No policy set on this node yet → no explicit fields.
        assert data["explicit"] == {} or data["explicit"] is None
    finally:
        await admin_client.delete(f"/nodes/{area_id}")


@pytest.mark.asyncio
async def test_upsert_area_policy_then_get_reflects_values(admin_client, root_node_id):
    """PUT /nodes/{id}/policy then GET must return the updated values under
    the 'explicit' key."""
    payload = _area_payload(root_node_id)
    create_resp = await admin_client.post("/nodes", json=payload)
    assert create_resp.status_code == 201
    area_id = create_resp.json()["id"]

    try:
        policy_payload = {
            "cache_ttl_seconds": 7200,
            "cache_similarity_threshold": 0.92,
            "cache_opt_out": False,
            "embedding_model": "text-embedding-3-small",
            "rate_limit_rpm": 500,
            "allowed_models": ["claude-haiku-4-5"],
        }
        put_resp = await admin_client.put(f"/nodes/{area_id}/policy", json=policy_payload)
        assert put_resp.status_code == 200, f"Expected 200, got {put_resp.status_code}: {put_resp.text}"
        # PUT returns {"ok": True}
        assert put_resp.json().get("ok") is True

        # GET should reflect the same values under explicit.
        get_resp = await admin_client.get(f"/nodes/{area_id}/policy")
        assert get_resp.status_code == 200
        explicit = get_resp.json()["explicit"]
        assert explicit["cache_ttl_seconds"] == 7200
        assert explicit["rate_limit_rpm"] == 500
    finally:
        await admin_client.delete(f"/nodes/{area_id}")
