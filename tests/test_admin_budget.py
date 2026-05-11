"""Integration tests for budget management endpoints.

Tests cover:
  - Team budget: get (default null), set, clear
  - Org budget: get, set
  - Combined budget status dashboard
  - Key budget: get, set
"""

import uuid

import pytest


# ── Team budget ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_team_budget_returns_200(admin_client, test_team):
    """GET /teams/{id}/budget must return 200."""
    resp = await admin_client.get(f"/teams/{test_team}/budget")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_get_team_budget_unlimited_by_default(admin_client, test_team):
    """A new team's budget must be null (unlimited) by default."""
    resp = await admin_client.get(f"/teams/{test_team}/budget")
    assert resp.status_code == 200
    data = resp.json()
    assert data["monthly_budget_usd"] is None, (
        f"New team should have null budget, got {data['monthly_budget_usd']!r}"
    )
    assert data["team_id"] == test_team


@pytest.mark.asyncio
async def test_set_team_budget_returns_200(admin_client, test_team):
    """PUT /teams/{id}/budget must return 200."""
    resp = await admin_client.put(
        f"/teams/{test_team}/budget",
        json={"monthly_budget_usd": 500.0, "budget_alert_pct": 0.8, "budget_action": "alert"},
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_set_team_budget_get_reflects_new_limit(admin_client, test_team):
    """After PUT /teams/{id}/budget, GET must reflect the new limit."""
    await admin_client.put(
        f"/teams/{test_team}/budget",
        json={"monthly_budget_usd": 750.0, "budget_alert_pct": 0.85, "budget_action": "block"},
    )
    get_resp = await admin_client.get(f"/teams/{test_team}/budget")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["monthly_budget_usd"] == 750.0
    assert data["budget_action"] == "block"


@pytest.mark.asyncio
async def test_set_team_budget_null_removes_limit(admin_client, test_team):
    """PUT /teams/{id}/budget with null must remove the limit (unlimited)."""
    # First set a limit
    await admin_client.put(
        f"/teams/{test_team}/budget",
        json={"monthly_budget_usd": 100.0, "budget_alert_pct": 0.8, "budget_action": "alert"},
    )
    # Then clear it
    resp = await admin_client.put(
        f"/teams/{test_team}/budget",
        json={"monthly_budget_usd": None, "budget_alert_pct": 0.8, "budget_action": "alert"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["monthly_budget_usd"] is None


@pytest.mark.asyncio
async def test_get_team_budget_response_shape(admin_client, test_team):
    """GET /teams/{id}/budget must include expected keys."""
    resp = await admin_client.get(f"/teams/{test_team}/budget")
    assert resp.status_code == 200
    data = resp.json()
    for field in ("team_id", "monthly_budget_usd", "budget_alert_pct", "budget_action",
                  "current_spend_usd", "budget_remaining_usd", "pct_used"):
        assert field in data, f"Team budget response missing field '{field}'"


# ── Org budget ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_org_budget_returns_200(admin_client):
    """GET /org/budget must return 200."""
    resp = await admin_client.get("/org/budget")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_get_org_budget_response_shape(admin_client):
    """GET /org/budget must include expected keys."""
    resp = await admin_client.get("/org/budget")
    assert resp.status_code == 200
    data = resp.json()
    for field in ("monthly_budget_usd", "budget_alert_pct", "budget_action",
                  "current_spend_usd", "budget_remaining_usd", "pct_used"):
        assert field in data, f"Org budget response missing field '{field}'"


@pytest.mark.asyncio
async def test_set_org_budget_returns_200(admin_client):
    """PUT /org/budget must return 200."""
    resp = await admin_client.put(
        "/org/budget",
        json={"monthly_budget_usd": 50000.0, "budget_alert_pct": 0.9, "budget_action": "alert"},
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


# ── Budget status ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_budget_status_returns_200(admin_client):
    """GET /budget/status must return 200."""
    resp = await admin_client.get("/budget/status")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_budget_status_has_org_and_teams_keys(admin_client):
    """GET /budget/status must include org, teams, team_count keys."""
    resp = await admin_client.get("/budget/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "org" in data, "budget/status response missing 'org' key"
    assert "teams" in data, "budget/status response missing 'teams' key"
    assert "team_count" in data, "budget/status response missing 'team_count' key"
    assert isinstance(data["teams"], list)


@pytest.mark.asyncio
async def test_budget_status_org_shape(admin_client):
    """The 'org' block in /budget/status must have expected keys."""
    resp = await admin_client.get("/budget/status")
    assert resp.status_code == 200
    org = resp.json()["org"]
    for field in ("monthly_budget_usd", "budget_alert_pct", "budget_action",
                  "current_spend_usd", "budget_remaining_usd", "pct_used"):
        assert field in org, f"Org budget status missing field '{field}'"


# ── Key budget ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_key_budget_returns_200(admin_client, test_team):
    """GET /keys/{key_id}/budget must return 200 with null limit for a new key."""
    # Create a fresh key inline to get the ID
    create_resp = await admin_client.post(
        f"/teams/{test_team}/keys",
        json={"name": "budget-test-key"},
    )
    assert create_resp.status_code == 201
    key_data = create_resp.json()
    key_id = key_data["id"]

    try:
        resp = await admin_client.get(f"/keys/{key_id}/budget")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["key_id"] == key_id
        assert data["monthly_budget_usd"] is None
    finally:
        await admin_client.delete(f"/teams/{test_team}/keys/{key_id}")


@pytest.mark.asyncio
async def test_set_key_budget_returns_200(admin_client, test_team):
    """PUT /keys/{key_id}/budget must return 200."""
    create_resp = await admin_client.post(
        f"/teams/{test_team}/keys",
        json={"name": "budget-set-test-key"},
    )
    assert create_resp.status_code == 201
    key_id = create_resp.json()["id"]

    try:
        resp = await admin_client.put(
            f"/keys/{key_id}/budget",
            json={"monthly_budget_usd": 50.0},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["monthly_budget_usd"] == 50.0
    finally:
        await admin_client.delete(f"/teams/{test_team}/keys/{key_id}")


@pytest.mark.asyncio
async def test_get_key_budget_reflects_set_limit(admin_client, test_team):
    """After PUT /keys/{key_id}/budget, GET must reflect the new limit."""
    create_resp = await admin_client.post(
        f"/teams/{test_team}/keys",
        json={"name": "budget-reflect-test-key"},
    )
    assert create_resp.status_code == 201
    key_id = create_resp.json()["id"]

    try:
        await admin_client.put(
            f"/keys/{key_id}/budget",
            json={"monthly_budget_usd": 123.45},
        )
        get_resp = await admin_client.get(f"/keys/{key_id}/budget")
        assert get_resp.status_code == 200
        assert get_resp.json()["monthly_budget_usd"] == 123.45
    finally:
        await admin_client.delete(f"/teams/{test_team}/keys/{key_id}")


@pytest.mark.asyncio
async def test_get_key_budget_response_shape(admin_client, test_team):
    """GET /keys/{key_id}/budget must include expected keys."""
    create_resp = await admin_client.post(
        f"/teams/{test_team}/keys",
        json={"name": "budget-shape-test-key"},
    )
    assert create_resp.status_code == 201
    key_id = create_resp.json()["id"]

    try:
        resp = await admin_client.get(f"/keys/{key_id}/budget")
        assert resp.status_code == 200
        data = resp.json()
        for field in ("key_id", "monthly_budget_usd", "current_spend_usd",
                      "budget_remaining_usd", "pct_used"):
            assert field in data, f"Key budget response missing field '{field}'"
    finally:
        await admin_client.delete(f"/teams/{test_team}/keys/{key_id}")
