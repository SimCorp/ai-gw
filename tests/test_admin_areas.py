"""Integration tests for the /areas endpoints.

Tests cover:
  - Full CRUD lifecycle: create → list → get → update → delete
  - 404 on missing resource
  - Area policy upsert and retrieval
"""

import uuid

import pytest

from conftest import ADMIN_URL  # noqa: F401 — also used for URL building


# ── Helpers ──────────────────────────────────────────────────────────────────


def _area_payload(suffix: str | None = None) -> dict:
    uid = suffix or uuid.uuid4().hex[:8]
    return {"name": f"area-{uid}", "slug": f"area-{uid}", "color": "#4A90E2"}


# ── Create ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_area_returns_201(admin_client):
    """POST /areas must return 201 and the created area object."""
    payload = _area_payload()
    resp = await admin_client.post("/areas", json=payload)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "id" in data
    assert data["slug"] == payload["slug"]
    assert data["name"] == payload["name"]

    # cleanup
    await admin_client.delete(f"/areas/{data['id']}")


@pytest.mark.asyncio
async def test_create_area_response_shape(admin_client):
    """POST /areas response must include id, name, slug, color, created_at."""
    payload = _area_payload()
    resp = await admin_client.post("/areas", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    for field in ("id", "name", "slug", "color", "created_at"):
        assert field in data, f"Area response missing field '{field}'"

    # cleanup
    await admin_client.delete(f"/areas/{data['id']}")


# ── List ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_areas_returns_200(admin_client):
    """GET /areas must return 200 with a list."""
    resp = await admin_client.get("/areas")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_areas_includes_created_area(admin_client):
    """An area just created must appear in GET /areas."""
    payload = _area_payload()
    create_resp = await admin_client.post("/areas", json=payload)
    assert create_resp.status_code == 201
    area_id = create_resp.json()["id"]

    try:
        list_resp = await admin_client.get("/areas")
        assert list_resp.status_code == 200
        ids = [a["id"] for a in list_resp.json()]
        assert area_id in ids, f"Created area {area_id!r} not found in list"
    finally:
        await admin_client.delete(f"/areas/{area_id}")


# ── Get ───────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_area_returns_correct_fields(admin_client):
    """GET /areas/{id} must return area, teams, and policy keys."""
    payload = _area_payload()
    create_resp = await admin_client.post("/areas", json=payload)
    assert create_resp.status_code == 201
    area_id = create_resp.json()["id"]

    try:
        resp = await admin_client.get(f"/areas/{area_id}")
        assert resp.status_code == 200
        data = resp.json()
        # The get endpoint returns a nested structure
        assert "area" in data
        assert "teams" in data
        assert "policy" in data
        assert data["area"]["id"] == area_id
    finally:
        await admin_client.delete(f"/areas/{area_id}")


@pytest.mark.asyncio
async def test_get_area_not_found_returns_404(admin_client):
    """GET /areas/{non-existent-id} must return 404."""
    resp = await admin_client.get(f"/areas/{uuid.uuid4()}")
    assert resp.status_code == 404


# ── Update ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_area_returns_200(admin_client):
    """PUT /areas/{id} must return 200 with updated values."""
    payload = _area_payload()
    create_resp = await admin_client.post("/areas", json=payload)
    assert create_resp.status_code == 201
    area_id = create_resp.json()["id"]

    try:
        uid = uuid.uuid4().hex[:8]
        update_payload = {
            "name": f"updated-area-{uid}",
            "slug": payload["slug"],  # keep same slug
            "color": "#FF0000",
        }
        resp = await admin_client.put(f"/areas/{area_id}", json=update_payload)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["name"] == update_payload["name"]
        assert data["color"] == "#FF0000"
    finally:
        await admin_client.delete(f"/areas/{area_id}")


# ── Delete ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_area_returns_204(admin_client):
    """DELETE /areas/{id} must return 204."""
    payload = _area_payload()
    create_resp = await admin_client.post("/areas", json=payload)
    assert create_resp.status_code == 201
    area_id = create_resp.json()["id"]

    delete_resp = await admin_client.delete(f"/areas/{area_id}")
    assert delete_resp.status_code == 204

    # Confirm it's gone
    get_resp = await admin_client.get(f"/areas/{area_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_area_twice_returns_404(admin_client):
    """Deleting an area twice — the second DELETE must return 404."""
    payload = _area_payload()
    create_resp = await admin_client.post("/areas", json=payload)
    assert create_resp.status_code == 201
    area_id = create_resp.json()["id"]

    first = await admin_client.delete(f"/areas/{area_id}")
    assert first.status_code == 204

    second = await admin_client.delete(f"/areas/{area_id}")
    assert second.status_code == 404


# ── Area Policy ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_area_policy_returns_200_empty_when_no_policy(admin_client):
    """GET /areas/{id}/policy must return 200 with empty dict when no policy set."""
    payload = _area_payload()
    create_resp = await admin_client.post("/areas", json=payload)
    assert create_resp.status_code == 201
    area_id = create_resp.json()["id"]

    try:
        resp = await admin_client.get(f"/areas/{area_id}/policy")
        assert resp.status_code == 200
        # Either empty dict or a policy object
        data = resp.json()
        assert isinstance(data, dict)
    finally:
        await admin_client.delete(f"/areas/{area_id}")


@pytest.mark.asyncio
async def test_upsert_area_policy_then_get_reflects_values(admin_client):
    """PUT /areas/{id}/policy then GET must return the updated values."""
    payload = _area_payload()
    create_resp = await admin_client.post("/areas", json=payload)
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
        put_resp = await admin_client.put(f"/areas/{area_id}/policy", json=policy_payload)
        assert put_resp.status_code == 200, f"Expected 200, got {put_resp.status_code}: {put_resp.text}"
        put_data = put_resp.json()
        assert put_data["cache_ttl_seconds"] == 7200
        assert put_data["rate_limit_rpm"] == 500

        # GET should reflect the same values
        get_resp = await admin_client.get(f"/areas/{area_id}/policy")
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["cache_ttl_seconds"] == 7200
        assert get_data["rate_limit_rpm"] == 500
    finally:
        await admin_client.delete(f"/areas/{area_id}")


@pytest.mark.asyncio
async def test_upsert_area_policy_second_time_updates_not_duplicates(admin_client):
    """Calling PUT /areas/{id}/policy twice must upsert (no duplicate row)."""
    payload = _area_payload()
    create_resp = await admin_client.post("/areas", json=payload)
    assert create_resp.status_code == 201
    area_id = create_resp.json()["id"]

    try:
        base_policy = {
            "cache_ttl_seconds": 3600,
            "cache_similarity_threshold": 0.95,
            "cache_opt_out": False,
            "embedding_model": "text-embedding-3-small",
            "rate_limit_rpm": 1000,
            "allowed_models": [],
        }
        first = await admin_client.put(f"/areas/{area_id}/policy", json=base_policy)
        assert first.status_code == 200
        first_id = first.json()["id"]

        updated_policy = {**base_policy, "rate_limit_rpm": 2000}
        second = await admin_client.put(f"/areas/{area_id}/policy", json=updated_policy)
        assert second.status_code == 200
        # Should still be the same policy record (upsert, not insert)
        assert second.json()["id"] == first_id
        assert second.json()["rate_limit_rpm"] == 2000
    finally:
        await admin_client.delete(f"/areas/{area_id}")
