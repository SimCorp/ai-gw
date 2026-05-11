"""Integration tests for MCP server registry endpoints.

Tests cover:
  - Summary endpoint baseline
  - Full server CRUD lifecycle: create → list → get → update → delete
  - Ping endpoint (mock / unreachable URL — checks field updates)
  - Tool toggle (enable/disable)
  - Team access: grant → list → revoke
  - 404 handling on missing resources
  - 400 on empty PATCH body
"""

import uuid

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────


def _server_payload(suffix: str | None = None) -> dict:
    uid = suffix or uuid.uuid4().hex[:8]
    return {
        "name": f"test-mcp-{uid}",
        "description": f"Integration test MCP server {uid}",
        "url": f"http://mcp-test-{uid}.internal",
        "auth_type": "none",
        "enabled": True,
    }


# ── Summary ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_summary_returns_200(admin_client):
    """GET /mcp/summary must return 200 with expected keys."""
    resp = await admin_client.get("/mcp/summary")
    assert resp.status_code == 200
    data = resp.json()
    for key in ("server_count", "active_count", "disabled_count", "error_count",
                "pending_count", "total_tools", "enabled_tools", "teams_with_access"):
        assert key in data, f"Summary missing key '{key}'"


@pytest.mark.asyncio
async def test_summary_counts_are_non_negative(admin_client):
    """All summary counts must be >= 0."""
    resp = await admin_client.get("/mcp/summary")
    assert resp.status_code == 200
    for k, v in resp.json().items():
        assert v >= 0, f"Summary field '{k}' is negative: {v}"


# ── Create ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_server_returns_201(admin_client):
    """POST /mcp/servers must return 201 with the new server object."""
    payload = _server_payload()
    resp = await admin_client.post("/mcp/servers", json=payload)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "id" in data
    assert data["name"] == payload["name"]
    assert data["url"] == payload["url"]
    assert data["status"] == "pending"

    await admin_client.delete(f"/mcp/servers/{data['id']}")


@pytest.mark.asyncio
async def test_create_server_response_shape(admin_client):
    """POST /mcp/servers response must include all expected fields."""
    payload = _server_payload()
    resp = await admin_client.post("/mcp/servers", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    for field in ("id", "name", "url", "auth_type", "status", "enabled", "created_at"):
        assert field in data, f"Server response missing field '{field}'"

    await admin_client.delete(f"/mcp/servers/{data['id']}")


@pytest.mark.asyncio
async def test_create_server_bearer_auth(admin_client):
    """POST /mcp/servers with bearer auth stores auth_type correctly."""
    uid = uuid.uuid4().hex[:8]
    payload = {
        "name": f"test-mcp-bearer-{uid}",
        "url": f"http://mcp-bearer-{uid}.internal",
        "auth_type": "bearer",
        "auth_secret": "my-bearer-token",
    }
    resp = await admin_client.post("/mcp/servers", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["auth_type"] == "bearer"

    await admin_client.delete(f"/mcp/servers/{data['id']}")


# ── List ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_servers_returns_200(admin_client):
    """GET /mcp/servers must return 200 with a list."""
    resp = await admin_client.get("/mcp/servers")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_servers_includes_created(admin_client):
    """A server just created must appear in GET /mcp/servers."""
    payload = _server_payload()
    create_resp = await admin_client.post("/mcp/servers", json=payload)
    assert create_resp.status_code == 201
    server_id = create_resp.json()["id"]

    list_resp = await admin_client.get("/mcp/servers")
    assert list_resp.status_code == 200
    ids = [s["id"] for s in list_resp.json()]
    assert server_id in ids

    await admin_client.delete(f"/mcp/servers/{server_id}")


# ── Get ───────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_server_returns_200(admin_client):
    """GET /mcp/servers/{id} must return server, tools, and access lists."""
    payload = _server_payload()
    create_resp = await admin_client.post("/mcp/servers", json=payload)
    server_id = create_resp.json()["id"]

    resp = await admin_client.get(f"/mcp/servers/{server_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "server" in data
    assert "tools" in data
    assert "access" in data
    assert data["server"]["id"] == server_id

    await admin_client.delete(f"/mcp/servers/{server_id}")


@pytest.mark.asyncio
async def test_get_server_404_on_missing(admin_client):
    """GET /mcp/servers/{non-existent} must return 404."""
    fake_id = str(uuid.uuid4())
    resp = await admin_client.get(f"/mcp/servers/{fake_id}")
    assert resp.status_code == 404


# ── Update ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_server_name(admin_client):
    """PUT /mcp/servers/{id} must update specified fields."""
    payload = _server_payload()
    create_resp = await admin_client.post("/mcp/servers", json=payload)
    server_id = create_resp.json()["id"]
    new_name = f"updated-{uuid.uuid4().hex[:8]}"

    resp = await admin_client.put(f"/mcp/servers/{server_id}", json={"name": new_name})
    assert resp.status_code == 200
    assert resp.json()["name"] == new_name

    await admin_client.delete(f"/mcp/servers/{server_id}")


@pytest.mark.asyncio
async def test_update_server_disable(admin_client):
    """PUT /mcp/servers/{id} with enabled=false must disable the server."""
    payload = _server_payload()
    create_resp = await admin_client.post("/mcp/servers", json=payload)
    server_id = create_resp.json()["id"]

    resp = await admin_client.put(f"/mcp/servers/{server_id}", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    await admin_client.delete(f"/mcp/servers/{server_id}")


@pytest.mark.asyncio
async def test_update_server_404_on_missing(admin_client):
    """PUT /mcp/servers/{non-existent} must return 404."""
    fake_id = str(uuid.uuid4())
    resp = await admin_client.put(f"/mcp/servers/{fake_id}", json={"name": "whatever"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_server_400_on_empty_body(admin_client):
    """PUT /mcp/servers/{id} with no fields must return 400."""
    payload = _server_payload()
    create_resp = await admin_client.post("/mcp/servers", json=payload)
    server_id = create_resp.json()["id"]

    resp = await admin_client.put(f"/mcp/servers/{server_id}", json={})
    assert resp.status_code == 400

    await admin_client.delete(f"/mcp/servers/{server_id}")


# ── Delete ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_server_returns_204(admin_client):
    """DELETE /mcp/servers/{id} must return 204."""
    payload = _server_payload()
    create_resp = await admin_client.post("/mcp/servers", json=payload)
    server_id = create_resp.json()["id"]

    resp = await admin_client.delete(f"/mcp/servers/{server_id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_server_removes_from_list(admin_client):
    """After DELETE, server must not appear in GET /mcp/servers."""
    payload = _server_payload()
    create_resp = await admin_client.post("/mcp/servers", json=payload)
    server_id = create_resp.json()["id"]

    await admin_client.delete(f"/mcp/servers/{server_id}")

    list_resp = await admin_client.get("/mcp/servers")
    ids = [s["id"] for s in list_resp.json()]
    assert server_id not in ids


@pytest.mark.asyncio
async def test_delete_server_404_on_missing(admin_client):
    """DELETE /mcp/servers/{non-existent} must return 404."""
    fake_id = str(uuid.uuid4())
    resp = await admin_client.delete(f"/mcp/servers/{fake_id}")
    assert resp.status_code == 404


# ── Ping ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ping_unreachable_sets_error_status(admin_client):
    """POST /mcp/servers/{id}/ping against an unreachable URL sets status=error."""
    payload = _server_payload()
    create_resp = await admin_client.post("/mcp/servers", json=payload)
    server_id = create_resp.json()["id"]

    resp = await admin_client.post(f"/mcp/servers/{server_id}/ping")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"

    # Verify DB was updated
    get_resp = await admin_client.get(f"/mcp/servers/{server_id}")
    assert get_resp.json()["server"]["status"] == "error"

    await admin_client.delete(f"/mcp/servers/{server_id}")


@pytest.mark.asyncio
async def test_ping_response_shape(admin_client):
    """POST /mcp/servers/{id}/ping must return status, tool_count, latency_ms, tools."""
    payload = _server_payload()
    create_resp = await admin_client.post("/mcp/servers", json=payload)
    server_id = create_resp.json()["id"]

    resp = await admin_client.post(f"/mcp/servers/{server_id}/ping")
    assert resp.status_code == 200
    data = resp.json()
    for field in ("status", "tool_count", "latency_ms", "tools"):
        assert field in data, f"Ping response missing '{field}'"

    await admin_client.delete(f"/mcp/servers/{server_id}")


@pytest.mark.asyncio
async def test_ping_404_on_missing_server(admin_client):
    """POST /mcp/servers/{non-existent}/ping must return 404."""
    fake_id = str(uuid.uuid4())
    resp = await admin_client.post(f"/mcp/servers/{fake_id}/ping")
    assert resp.status_code == 404


# ── Tools ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_tools_empty_on_new_server(admin_client):
    """GET /mcp/servers/{id}/tools returns [] for a fresh server."""
    payload = _server_payload()
    create_resp = await admin_client.post("/mcp/servers", json=payload)
    server_id = create_resp.json()["id"]

    resp = await admin_client.get(f"/mcp/servers/{server_id}/tools")
    assert resp.status_code == 200
    assert resp.json() == []

    await admin_client.delete(f"/mcp/servers/{server_id}")


@pytest.mark.asyncio
async def test_list_tools_404_on_missing_server(admin_client):
    """GET /mcp/servers/{non-existent}/tools must return 404."""
    fake_id = str(uuid.uuid4())
    resp = await admin_client.get(f"/mcp/servers/{fake_id}/tools")
    assert resp.status_code == 404


# ── Access control ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_grant_access_returns_201(admin_client, test_team):
    """POST /mcp/servers/{id}/access must grant team access and return 201."""
    payload = _server_payload()
    create_resp = await admin_client.post("/mcp/servers", json=payload)
    server_id = create_resp.json()["id"]

    resp = await admin_client.post(
        f"/mcp/servers/{server_id}/access",
        json={"team_id": test_team},
    )
    assert resp.status_code == 201

    await admin_client.delete(f"/mcp/servers/{server_id}")


@pytest.mark.asyncio
async def test_grant_access_idempotent(admin_client, test_team):
    """Granting the same team access twice must not fail (ON CONFLICT DO NOTHING)."""
    payload = _server_payload()
    create_resp = await admin_client.post("/mcp/servers", json=payload)
    server_id = create_resp.json()["id"]

    await admin_client.post(
        f"/mcp/servers/{server_id}/access",
        json={"team_id": test_team},
    )
    resp = await admin_client.post(
        f"/mcp/servers/{server_id}/access",
        json={"team_id": test_team},
    )
    assert resp.status_code in (200, 201)

    await admin_client.delete(f"/mcp/servers/{server_id}")


@pytest.mark.asyncio
async def test_list_access_includes_granted_team(admin_client, test_team):
    """GET /mcp/servers/{id}/access must include a team after access is granted."""
    payload = _server_payload()
    create_resp = await admin_client.post("/mcp/servers", json=payload)
    server_id = create_resp.json()["id"]

    await admin_client.post(
        f"/mcp/servers/{server_id}/access",
        json={"team_id": test_team},
    )

    resp = await admin_client.get(f"/mcp/servers/{server_id}/access")
    assert resp.status_code == 200
    team_ids = [a["team_id"] for a in resp.json()]
    assert test_team in team_ids

    await admin_client.delete(f"/mcp/servers/{server_id}")


@pytest.mark.asyncio
async def test_revoke_access_returns_204(admin_client, test_team):
    """DELETE /mcp/servers/{id}/access/{team_id} must return 204."""
    payload = _server_payload()
    create_resp = await admin_client.post("/mcp/servers", json=payload)
    server_id = create_resp.json()["id"]

    await admin_client.post(
        f"/mcp/servers/{server_id}/access",
        json={"team_id": test_team},
    )

    resp = await admin_client.delete(f"/mcp/servers/{server_id}/access/{test_team}")
    assert resp.status_code == 204

    await admin_client.delete(f"/mcp/servers/{server_id}")


@pytest.mark.asyncio
async def test_revoke_access_removes_from_list(admin_client, test_team):
    """After revoke, team must not appear in access list."""
    payload = _server_payload()
    create_resp = await admin_client.post("/mcp/servers", json=payload)
    server_id = create_resp.json()["id"]

    await admin_client.post(
        f"/mcp/servers/{server_id}/access",
        json={"team_id": test_team},
    )
    await admin_client.delete(f"/mcp/servers/{server_id}/access/{test_team}")

    resp = await admin_client.get(f"/mcp/servers/{server_id}/access")
    team_ids = [a["team_id"] for a in resp.json()]
    assert test_team not in team_ids

    await admin_client.delete(f"/mcp/servers/{server_id}")


@pytest.mark.asyncio
async def test_revoke_access_404_when_not_granted(admin_client, test_team):
    """DELETE /mcp/servers/{id}/access/{team_id} when not granted must return 404."""
    payload = _server_payload()
    create_resp = await admin_client.post("/mcp/servers", json=payload)
    server_id = create_resp.json()["id"]

    resp = await admin_client.delete(f"/mcp/servers/{server_id}/access/{test_team}")
    assert resp.status_code == 404

    await admin_client.delete(f"/mcp/servers/{server_id}")


@pytest.mark.asyncio
async def test_grant_access_404_on_missing_server(admin_client, test_team):
    """POST /mcp/servers/{non-existent}/access must return 404."""
    fake_id = str(uuid.uuid4())
    resp = await admin_client.post(
        f"/mcp/servers/{fake_id}/access",
        json={"team_id": test_team},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_grant_access_404_on_missing_team(admin_client):
    """POST /mcp/servers/{id}/access with non-existent team must return 404."""
    payload = _server_payload()
    create_resp = await admin_client.post("/mcp/servers", json=payload)
    server_id = create_resp.json()["id"]

    resp = await admin_client.post(
        f"/mcp/servers/{server_id}/access",
        json={"team_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404

    await admin_client.delete(f"/mcp/servers/{server_id}")


# ── Summary delta ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_summary_server_count_increases_on_create(admin_client):
    """server_count in summary must go up by 1 after creating a server."""
    before = (await admin_client.get("/mcp/summary")).json()["server_count"]

    payload = _server_payload()
    create_resp = await admin_client.post("/mcp/servers", json=payload)
    server_id = create_resp.json()["id"]

    after = (await admin_client.get("/mcp/summary")).json()["server_count"]
    assert after == before + 1

    await admin_client.delete(f"/mcp/servers/{server_id}")
