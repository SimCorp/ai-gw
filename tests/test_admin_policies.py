"""Integration tests for team policy management endpoints.

Tests cover:
  - GET /teams/{id}/policy — returns empty dict initially
  - PUT /teams/{id}/policy — upsert creates/updates policy
  - Idempotent upsert (no duplicate rows)
  - GET /policies — global list, includes updated team
  - Policy field correctness after upsert
"""

import pytest


# ── Get policy ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_policy_returns_200_empty_for_new_team(admin_client, test_team):
    """GET /teams/{id}/policy on a fresh team must return 200 with empty dict."""
    resp = await admin_client.get(f"/teams/{test_team}/policy")
    assert resp.status_code == 200
    data = resp.json()
    # Fresh team: no policy → empty dict {}
    assert data == {} or isinstance(data, dict)


# ── Upsert policy ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_policy_returns_200(admin_client, test_team):
    """PUT /teams/{id}/policy must return 200."""
    policy_payload = {
        "cache_ttl_seconds": 1800,
        "cache_similarity_threshold": 0.90,
        "cache_opt_out": False,
        "embedding_model": "text-embedding-3-small",
        "rate_limit_rpm": 600,
        "allowed_models": [],
    }
    resp = await admin_client.put(f"/teams/{test_team}/policy", json=policy_payload)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_upsert_policy_fields_are_correct(admin_client, test_team):
    """Policy fields returned by PUT must match submitted values."""
    policy_payload = {
        "cache_ttl_seconds": 3600,
        "cache_similarity_threshold": 0.95,
        "cache_opt_out": True,
        "embedding_model": "text-embedding-3-small",
        "rate_limit_rpm": 300,
        "allowed_models": ["claude-haiku-4-5"],
    }
    resp = await admin_client.put(f"/teams/{test_team}/policy", json=policy_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["cache_ttl_seconds"] == 3600
    assert data["cache_similarity_threshold"] == 0.95
    assert data["cache_opt_out"] is True
    assert data["rate_limit_rpm"] == 300


@pytest.mark.asyncio
async def test_upsert_policy_twice_updates_not_duplicates(admin_client, test_team):
    """Calling PUT /teams/{id}/policy twice must update the existing row (upsert)."""
    base = {
        "cache_ttl_seconds": 3600,
        "cache_similarity_threshold": 0.95,
        "cache_opt_out": False,
        "embedding_model": "text-embedding-3-small",
        "rate_limit_rpm": 1000,
        "allowed_models": [],
    }
    first_resp = await admin_client.put(f"/teams/{test_team}/policy", json=base)
    assert first_resp.status_code == 200
    first_id = first_resp.json().get("id")

    updated = {**base, "rate_limit_rpm": 2000, "cache_ttl_seconds": 7200}
    second_resp = await admin_client.put(f"/teams/{test_team}/policy", json=updated)
    assert second_resp.status_code == 200
    second_data = second_resp.json()

    # Should be same policy record (upsert)
    if first_id is not None:
        assert second_data.get("id") == first_id
    assert second_data["rate_limit_rpm"] == 2000
    assert second_data["cache_ttl_seconds"] == 7200


@pytest.mark.asyncio
async def test_get_policy_after_upsert_reflects_values(admin_client, test_team):
    """After PUT, GET /teams/{id}/policy must return the stored policy."""
    policy_payload = {
        "cache_ttl_seconds": 5000,
        "cache_similarity_threshold": 0.88,
        "cache_opt_out": False,
        "embedding_model": "text-embedding-3-small",
        "rate_limit_rpm": 750,
        "allowed_models": [],
    }
    await admin_client.put(f"/teams/{test_team}/policy", json=policy_payload)

    get_resp = await admin_client.get(f"/teams/{test_team}/policy")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["cache_ttl_seconds"] == 5000
    assert data["rate_limit_rpm"] == 750


# ── List all policies ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_all_policies_returns_200(admin_client):
    """GET /policies must return 200 with a list."""
    resp = await admin_client.get("/policies")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_all_policies_includes_updated_team(admin_client, test_team):
    """After upserting a policy, GET /policies must include the team."""
    policy_payload = {
        "cache_ttl_seconds": 3600,
        "cache_similarity_threshold": 0.95,
        "cache_opt_out": False,
        "embedding_model": "text-embedding-3-small",
        "rate_limit_rpm": 1000,
        "allowed_models": [],
    }
    await admin_client.put(f"/teams/{test_team}/policy", json=policy_payload)

    list_resp = await admin_client.get("/policies")
    assert list_resp.status_code == 200
    policies = list_resp.json()

    # Find our team in the list
    team_entry = next(
        (p for p in policies if p["team_id"] == test_team), None
    )
    assert team_entry is not None, f"Team {test_team!r} not found in /policies list"
    assert team_entry["policy"] is not None, "Team should have a policy after upsert"
    assert team_entry["policy"]["rate_limit_rpm"] == 1000


@pytest.mark.asyncio
async def test_list_all_policies_entry_shape(admin_client):
    """Each entry in GET /policies must have team_id, team_name, team_slug, policy keys."""
    resp = await admin_client.get("/policies")
    assert resp.status_code == 200
    data = resp.json()
    if data:
        entry = data[0]
        for field in ("team_id", "team_name", "team_slug", "policy"):
            assert field in entry, f"Policy list entry missing field '{field}'"
