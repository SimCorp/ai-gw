"""Admin API tests — org-node (team) management, API key lifecycle, system
health JSON shape.

The org-node refactor replaced /teams with the unified /nodes surface
(services/admin/app/routers/nodes.py); a "team" is a node with type='team'.
The team CRUD tests below were rewritten from /teams to /nodes. The API-key
tests still use /teams/{id}/keys — that router is intact and its node_id FK now
points at organization_nodes, so a node id works in place of the old team id.

All endpoints require the X-Admin-Token header, which the admin_client fixture
injects automatically.
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
    """GET /system/health must reject requests without the admin token.

    Skipped when the running server has auth bypassed (DEV_BYPASS_AUTH=true).
    Detects bypass by probing the endpoint without a token first.
    """
    import httpx
    from conftest import ADMIN_URL

    async with httpx.AsyncClient(base_url=ADMIN_URL, timeout=10.0) as client:
        probe = await client.get("/system/health")

    if probe.status_code == 200:
        pytest.skip("Server has auth bypassed (DEV_BYPASS_AUTH=true) — skipping token enforcement test")

    assert probe.status_code == 401, (
        f"Expected 401 without admin token, got {probe.status_code}"
    )


# ── Team (org node) CRUD ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_team_returns_201(admin_client, root_node_id):
    """POST /nodes (type=team) must return 201 and the created node object."""
    uid = uuid.uuid4().hex[:8]
    resp = await admin_client.post(
        "/nodes",
        json={"name": f"admin-test-{uid}", "type": "team", "parent_id": root_node_id},
    )
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "id" in data
    # slug is derived from the name server-side (no caller-supplied slug field).
    assert data["slug"] == f"admin-test-{uid}"
    assert data["type"] == "team"

    # Teardown
    await admin_client.delete(f"/nodes/{data['id']}")


@pytest.mark.asyncio
async def test_list_teams_includes_created_team(admin_client, test_team):
    """GET /nodes?type=team must include the node created by the test_team fixture."""
    resp = await admin_client.get("/nodes", params={"type": "team"})
    assert resp.status_code == 200
    ids = [t["id"] for t in resp.json()]
    assert test_team in ids, (
        f"test_team node {test_team!r} not found in node list"
    )


@pytest.mark.asyncio
async def test_get_team(admin_client, test_team):
    """GET /nodes/{id} must return the node."""
    resp = await admin_client.get(f"/nodes/{test_team}")
    assert resp.status_code == 200
    assert resp.json()["id"] == test_team


@pytest.mark.asyncio
async def test_get_nonexistent_team_returns_404(admin_client):
    """GET /nodes/{non-existent-id} must return 404."""
    resp = await admin_client.get(f"/nodes/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_team_returns_204(admin_client, root_node_id):
    """DELETE /nodes/{id} must return 204."""
    uid = uuid.uuid4().hex[:8]
    create = await admin_client.post(
        "/nodes",
        json={"name": f"delete-me-{uid}", "type": "team", "parent_id": root_node_id},
    )
    assert create.status_code == 201
    team_id = create.json()["id"]

    delete = await admin_client.delete(f"/nodes/{team_id}")
    assert delete.status_code == 204

    # Confirm it's gone
    get = await admin_client.get(f"/nodes/{team_id}")
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
