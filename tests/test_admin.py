"""Admin API tests — team management, API key lifecycle, system health JSON shape.

All endpoints under /teams, /system, etc. require the X-Admin-Token header.
The admin_client fixture injects that automatically.
"""

import uuid

import pytest


# ── System health ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_system_health_shape(admin_client):
    """GET /system/health must return the expected top-level JSON keys."""
    resp = await admin_client.get("/system/health")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    for key in ("overall", "last_updated", "services", "redis", "postgres"):
        assert key in data, f"Response missing key '{key}'"


@pytest.mark.asyncio
async def test_system_health_redis_shape(admin_client):
    """The 'redis' block must have the expected sub-keys."""
    resp = await admin_client.get("/system/health")
    assert resp.status_code == 200
    redis = resp.json()["redis"]
    for key in ("status", "ping_ms", "used_memory_mb", "connected_clients"):
        assert key in redis, f"Redis health block missing key '{key}'"


@pytest.mark.asyncio
async def test_system_health_postgres_shape(admin_client):
    """The 'postgres' block must have the expected sub-keys."""
    resp = await admin_client.get("/system/health")
    assert resp.status_code == 200
    pg = resp.json()["postgres"]
    for key in ("status", "ping_ms", "active_connections"):
        assert key in pg, f"Postgres health block missing key '{key}'"


@pytest.mark.asyncio
async def test_system_health_requires_admin_token():
    """GET /system/health must reject requests without the admin token."""
    import httpx
    from conftest import ADMIN_URL

    async with httpx.AsyncClient(base_url=ADMIN_URL, timeout=10.0) as client:
        resp = await client.get("/system/health")
    assert resp.status_code == 401, (
        f"Expected 401 without admin token, got {resp.status_code}"
    )


# ── Team CRUD ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_team_returns_201(admin_client):
    """POST /teams must return 201 and the created team object."""
    uid = uuid.uuid4().hex[:8]
    resp = await admin_client.post(
        "/teams", json={"name": f"admin-test-{uid}", "slug": f"admin-test-{uid}"}
    )
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "id" in data
    assert data["slug"] == f"admin-test-{uid}"

    # Teardown
    await admin_client.delete(f"/teams/{data['id']}")


@pytest.mark.asyncio
async def test_list_teams_includes_created_team(admin_client, test_team):
    """GET /teams must include the team created by the test_team fixture."""
    resp = await admin_client.get("/teams")
    assert resp.status_code == 200
    ids = [t["id"] for t in resp.json()]
    assert test_team in ids, (
        f"test_team {test_team!r} not found in team list"
    )


@pytest.mark.asyncio
async def test_get_team(admin_client, test_team):
    """GET /teams/{id} must return the team."""
    resp = await admin_client.get(f"/teams/{test_team}")
    assert resp.status_code == 200
    assert resp.json()["id"] == test_team


@pytest.mark.asyncio
async def test_get_nonexistent_team_returns_404(admin_client):
    """GET /teams/{non-existent-id} must return 404."""
    resp = await admin_client.get(f"/teams/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_team_returns_204(admin_client):
    """DELETE /teams/{id} must return 204."""
    uid = uuid.uuid4().hex[:8]
    create = await admin_client.post(
        "/teams", json={"name": f"delete-me-{uid}", "slug": f"delete-me-{uid}"}
    )
    assert create.status_code == 201
    team_id = create.json()["id"]

    delete = await admin_client.delete(f"/teams/{team_id}")
    assert delete.status_code == 204

    # Confirm it's gone
    get = await admin_client.get(f"/teams/{team_id}")
    assert get.status_code == 404


# ── API key lifecycle ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_api_key_returns_sk_prefix(admin_client, test_team):
    """POST /teams/{id}/keys must return a key with sk- prefix."""
    resp = await admin_client.post(
        f"/teams/{test_team}/keys",
        json={"name": "admin-test-key"},
    )
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "key" in data, "Response must contain the raw 'key' field"
    assert data["key"].startswith("sk-"), (
        f"API key must start with 'sk-', got {data['key'][:10]!r}"
    )

    # Teardown
    await admin_client.delete(f"/teams/{test_team}/keys/{data['id']}")


@pytest.mark.asyncio
async def test_create_api_key_shape(admin_client, test_team):
    """POST /teams/{id}/keys response must include id, name, key, created_at."""
    resp = await admin_client.post(
        f"/teams/{test_team}/keys",
        json={"name": "shape-test-key"},
    )
    assert resp.status_code == 201
    data = resp.json()
    for field in ("id", "name", "key", "created_at"):
        assert field in data, f"API key response missing field '{field}'"

    # Teardown
    await admin_client.delete(f"/teams/{test_team}/keys/{data['id']}")


@pytest.mark.asyncio
async def test_list_keys_excludes_revoked(admin_client, test_team):
    """A revoked key must not appear in GET /teams/{id}/keys."""
    # Create a key
    create = await admin_client.post(
        f"/teams/{test_team}/keys",
        json={"name": "revoke-list-test-key"},
    )
    assert create.status_code == 201
    key_id = create.json()["id"]

    # Revoke it
    revoke = await admin_client.delete(f"/teams/{test_team}/keys/{key_id}")
    assert revoke.status_code == 204

    # It must not appear in the list
    list_resp = await admin_client.get(f"/teams/{test_team}/keys")
    assert list_resp.status_code == 200
    ids = [k["id"] for k in list_resp.json()]
    assert key_id not in ids, (
        f"Revoked key {key_id!r} must not appear in active keys list"
    )


@pytest.mark.asyncio
async def test_revoked_key_rejected_by_gateway(admin_client, test_team):
    """An API key revoked via admin API must be rejected at the gateway (401)."""
    import httpx
    from conftest import GATEWAY_URL

    # Create a fresh key
    create = await admin_client.post(
        f"/teams/{test_team}/keys",
        json={"name": "gateway-revoke-test-key"},
    )
    assert create.status_code == 201
    data = create.json()
    raw_key = data["key"]
    key_id = data["id"]

    # Revoke it via admin
    await admin_client.delete(f"/teams/{test_team}/keys/{key_id}")

    # Attempt to use it at the gateway
    async with httpx.AsyncClient(
        base_url=GATEWAY_URL,
        headers={"Authorization": f"Bearer {raw_key}"},
        timeout=15.0,
    ) as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "claude-haiku-4-5",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5,
            },
        )
    assert resp.status_code == 401, (
        f"Revoked key must return 401 at gateway, got {resp.status_code}"
    )
