"""Integration tests for guardrail management endpoints.

Tests cover:
  - Full CRUD lifecycle: create → list → patch → delete
  - Summary stats
  - Recent hits list
  - 404 on missing guardrail
  - 400 on empty PATCH body
"""

import uuid

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────


def _guardrail_payload(suffix: str | None = None) -> dict:
    uid = suffix or uuid.uuid4().hex[:8]
    return {
        "name": f"test-guardrail-{uid}",
        "description": f"Integration test guardrail {uid}",
        "type": "keyword",
        "applies_to": "input",
        "action": "block",
        "severity": "high",
        "priority": 100,
        "config": {"keywords": ["test-keyword"]},
    }


# ── Create ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_guardrail_returns_201(admin_client):
    """POST /guardrails must return 201 and a guardrail object."""
    payload = _guardrail_payload()
    resp = await admin_client.post("/guardrails", json=payload)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "id" in data
    assert data["name"] == payload["name"]
    assert data["type"] == "keyword"

    # Cleanup
    await admin_client.delete(f"/guardrails/{data['id']}")


@pytest.mark.asyncio
async def test_create_guardrail_response_shape(admin_client):
    """POST /guardrails response must include all expected fields."""
    payload = _guardrail_payload()
    resp = await admin_client.post("/guardrails", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    for field in ("id", "name", "type", "applies_to", "action", "severity",
                  "priority", "enabled", "created_at"):
        assert field in data, f"Guardrail response missing field '{field}'"

    # Cleanup
    await admin_client.delete(f"/guardrails/{data['id']}")


# ── List ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_guardrails_returns_200(admin_client):
    """GET /guardrails must return 200 with a list."""
    resp = await admin_client.get("/guardrails")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_guardrails_includes_created(admin_client):
    """A guardrail just created must appear in GET /guardrails."""
    payload = _guardrail_payload()
    create_resp = await admin_client.post("/guardrails", json=payload)
    assert create_resp.status_code == 201
    guardrail_id = create_resp.json()["id"]

    try:
        list_resp = await admin_client.get("/guardrails")
        assert list_resp.status_code == 200
        ids = [g["id"] for g in list_resp.json()]
        assert str(guardrail_id) in [str(i) for i in ids], (
            f"Created guardrail {guardrail_id!r} not found in list"
        )
    finally:
        await admin_client.delete(f"/guardrails/{guardrail_id}")


# ── Summary ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_guardrails_summary_returns_200(admin_client):
    """GET /guardrails/summary must return 200."""
    resp = await admin_client.get("/guardrails/summary")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_guardrails_summary_has_expected_keys(admin_client):
    """GET /guardrails/summary must include active_count and hits_24h."""
    resp = await admin_client.get("/guardrails/summary")
    assert resp.status_code == 200
    data = resp.json()
    for field in ("active_count", "hits_24h"):
        assert field in data, f"Guardrail summary missing field '{field}'"


# ── Recent hits ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_guardrails_hits_returns_200(admin_client):
    """GET /guardrails/hits must return 200 with a list."""
    resp = await admin_client.get("/guardrails/hits")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── Patch ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_guardrail_enable_disable_returns_200(admin_client):
    """PATCH /guardrails/{id} with enabled field must return 200."""
    payload = _guardrail_payload()
    create_resp = await admin_client.post("/guardrails", json=payload)
    assert create_resp.status_code == 201
    guardrail_id = create_resp.json()["id"]
    original_enabled = create_resp.json().get("enabled", True)

    try:
        # Toggle enabled
        patch_resp = await admin_client.patch(
            f"/guardrails/{guardrail_id}",
            json={"enabled": not original_enabled},
        )
        assert patch_resp.status_code == 200, (
            f"Expected 200, got {patch_resp.status_code}: {patch_resp.text}"
        )
        assert patch_resp.json()["enabled"] == (not original_enabled)
    finally:
        await admin_client.delete(f"/guardrails/{guardrail_id}")


@pytest.mark.asyncio
async def test_patch_guardrail_update_description_returns_200(admin_client):
    """PATCH /guardrails/{id} with description update must return 200."""
    payload = _guardrail_payload()
    create_resp = await admin_client.post("/guardrails", json=payload)
    assert create_resp.status_code == 201
    guardrail_id = create_resp.json()["id"]

    try:
        patch_resp = await admin_client.patch(
            f"/guardrails/{guardrail_id}",
            json={"description": "Updated description via integration test"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["description"] == "Updated description via integration test"
    finally:
        await admin_client.delete(f"/guardrails/{guardrail_id}")


@pytest.mark.asyncio
async def test_patch_guardrail_no_fields_returns_400(admin_client):
    """PATCH /guardrails/{id} with empty body must return 400."""
    payload = _guardrail_payload()
    create_resp = await admin_client.post("/guardrails", json=payload)
    assert create_resp.status_code == 201
    guardrail_id = create_resp.json()["id"]

    try:
        patch_resp = await admin_client.patch(f"/guardrails/{guardrail_id}", json={})
        assert patch_resp.status_code == 400, (
            f"Expected 400 for empty patch, got {patch_resp.status_code}: {patch_resp.text}"
        )
    finally:
        await admin_client.delete(f"/guardrails/{guardrail_id}")


# ── Delete ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_guardrail_returns_204(admin_client):
    """DELETE /guardrails/{id} must return 204."""
    payload = _guardrail_payload()
    create_resp = await admin_client.post("/guardrails", json=payload)
    assert create_resp.status_code == 201
    guardrail_id = create_resp.json()["id"]

    delete_resp = await admin_client.delete(f"/guardrails/{guardrail_id}")
    assert delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_guardrail_twice_returns_404(admin_client):
    """Deleting a guardrail twice — the second DELETE must return 404."""
    payload = _guardrail_payload()
    create_resp = await admin_client.post("/guardrails", json=payload)
    assert create_resp.status_code == 201
    guardrail_id = create_resp.json()["id"]

    first = await admin_client.delete(f"/guardrails/{guardrail_id}")
    assert first.status_code == 204

    second = await admin_client.delete(f"/guardrails/{guardrail_id}")
    assert second.status_code == 404


@pytest.mark.asyncio
async def test_patch_nonexistent_guardrail_returns_404(admin_client):
    """PATCH /guardrails/{non-existent-id} must return 404."""
    resp = await admin_client.patch(
        f"/guardrails/{uuid.uuid4()}",
        json={"enabled": False},
    )
    assert resp.status_code == 404
