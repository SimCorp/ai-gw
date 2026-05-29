"""Integration tests for miscellaneous admin endpoints.

Tests cover:
  - Model registry: list and update (enable/disable)
  - Cost reports: team, model group_by with valid period values
  - Audit log: list, limit, action filtering
  - Dashboard stats
"""

import pytest


# ── Model registry ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_models_returns_200(admin_client):
    """GET /models must return 200 with a list."""
    resp = await admin_client.get("/models")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_models_response_shape(admin_client):
    """Each model entry must include expected fields if models are seeded."""
    resp = await admin_client.get("/models")
    assert resp.status_code == 200
    models = resp.json()
    if models:
        model = models[0]
        for field in ("model_id", "name", "provider", "enabled"):
            assert field in model, f"Model registry entry missing field '{field}'"


@pytest.mark.asyncio
async def test_patch_model_enable_disable(admin_client):
    """PATCH /models/{model_id} enable/disable toggle must return 200."""
    # Get models and pick the first one
    list_resp = await admin_client.get("/models")
    assert list_resp.status_code == 200
    models = list_resp.json()

    if not models:
        pytest.skip("No models seeded — cannot test enable/disable toggle")

    model = models[0]
    model_id = model["model_id"]
    original_enabled = model["enabled"]

    # Toggle
    patch_resp = await admin_client.patch(
        f"/models/{model_id}",
        json={"enabled": not original_enabled},
    )
    assert patch_resp.status_code == 200, (
        f"Expected 200, got {patch_resp.status_code}: {patch_resp.text}"
    )
    assert patch_resp.json()["enabled"] == (not original_enabled)

    # Restore to original state
    await admin_client.patch(f"/models/{model_id}", json={"enabled": original_enabled})


# ── Cost reports ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cost_report_group_by_team_returns_200(admin_client):
    """GET /reports/cost?group_by=team&period=30d must return 200 with a list."""
    resp = await admin_client.get("/reports/cost", params={"group_by": "team", "period": "30d"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_cost_report_group_by_model_returns_200(admin_client):
    """GET /reports/cost?group_by=model&period=7d must return 200 with a list."""
    resp = await admin_client.get("/reports/cost", params={"group_by": "model", "period": "7d"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_cost_report_group_by_area_returns_200(admin_client):
    """GET /reports/cost?group_by=area&period=mtd must return 200 with a list."""
    resp = await admin_client.get("/reports/cost", params={"group_by": "area", "period": "mtd"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_cost_report_default_params_returns_200(admin_client):
    """GET /reports/cost without params must use defaults and return 200."""
    resp = await admin_client.get("/reports/cost")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_cost_report_team_entry_shape(admin_client):
    """team group_by entries must include team_id, team_name, request_count, total_cost_usd."""
    resp = await admin_client.get("/reports/cost", params={"group_by": "team", "period": "all"})
    assert resp.status_code == 200
    data = resp.json()
    if data:
        entry = data[0]
        for field in ("team_id", "team_name", "request_count", "total_cost_usd"):
            assert field in entry, f"Cost report team entry missing field '{field}'"


# ── Audit log ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_audit_returns_200(admin_client):
    """GET /audit must return 200 with a list."""
    resp = await admin_client.get("/audit")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_audit_limit_param_respected(admin_client):
    """GET /audit?limit=5 must return at most 5 entries."""
    resp = await admin_client.get("/audit", params={"limit": 5})
    assert resp.status_code == 200
    assert len(resp.json()) <= 5


@pytest.mark.asyncio
async def test_audit_has_create_team_entry(admin_client, test_team):
    """After creating a team (via test_team fixture), audit must have a create_team entry.

    The test_team fixture creates a team which triggers an audit record.
    We query with resource_type=team and check action.
    """
    # test_team fixture creates an org node (type='team'), which emits a
    # 'create_node' audit entry (resource_type='node') in the org-node model.
    resp = await admin_client.get("/audit", params={"resource_type": "node", "limit": 50})
    assert resp.status_code == 200
    entries = resp.json()
    actions = [e.get("action", "") for e in entries]
    assert any("create_node" in action for action in actions), (
        f"Expected a 'create_node' audit entry, found actions: {actions[:10]}"
    )


@pytest.mark.asyncio
async def test_audit_entry_shape(admin_client):
    """Audit log entries must include expected fields."""
    resp = await admin_client.get("/audit", params={"limit": 1})
    assert resp.status_code == 200
    entries = resp.json()
    if entries:
        entry = entries[0]
        for field in ("id", "action", "timestamp"):
            assert field in entry, f"Audit entry missing field '{field}'"


# ── Dashboard stats ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dashboard_stats_returns_200(admin_client):
    """GET /dashboard/stats must return 200."""
    resp = await admin_client.get("/dashboard/stats")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_dashboard_stats_returns_list(admin_client):
    """GET /dashboard/stats must return a list (may be empty if no cost records)."""
    resp = await admin_client.get("/dashboard/stats")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_dashboard_stats_entry_shape(admin_client):
    """If stats entries exist, they must include team_name and request_count."""
    resp = await admin_client.get("/dashboard/stats")
    assert resp.status_code == 200
    data = resp.json()
    if data:
        entry = data[0]
        for field in ("team_name", "request_count"):
            assert field in entry, f"Dashboard stats entry missing field '{field}'"
