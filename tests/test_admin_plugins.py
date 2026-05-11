"""Integration tests for plugin registry endpoints."""

import uuid

import pytest


def _plugin_payload(suffix: str | None = None) -> dict:
    uid = suffix or uuid.uuid4().hex[:8]
    return {
        "name": f"test-plugin-{uid}",
        "slug": f"test-plugin-{uid}",
        "description": f"Integration test plugin {uid}",
        "version": "1.0.0",
        "author": "test",
        "category": "tool",
        "scopes": ["compute"],
        "enabled": True,
    }


# ── Summary ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_summary_returns_200(admin_client):
    resp = await admin_client.get("/plugins/summary")
    assert resp.status_code == 200
    data = resp.json()
    for key in ("total", "enabled", "disabled", "per_category", "total_overrides"):
        assert key in data


@pytest.mark.asyncio
async def test_summary_seeded_plugins_present(admin_client):
    resp = await admin_client.get("/plugins/summary")
    assert resp.json()["total"] >= 9


# ── Create ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_plugin_returns_201(admin_client):
    payload = _plugin_payload()
    resp = await admin_client.post("/plugins", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == payload["name"]
    assert data["slug"] == payload["slug"]
    assert data["category"] == "tool"
    await admin_client.delete(f"/plugins/{data['id']}")


@pytest.mark.asyncio
async def test_create_plugin_response_shape(admin_client):
    payload = _plugin_payload()
    resp = await admin_client.post("/plugins", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    for field in ("id", "name", "slug", "version", "author", "category", "enabled", "created_at"):
        assert field in data, f"Missing field '{field}'"
    await admin_client.delete(f"/plugins/{data['id']}")


@pytest.mark.asyncio
async def test_create_plugin_stores_scopes(admin_client):
    payload = _plugin_payload()
    payload["scopes"] = ["internet", "compute"]
    resp = await admin_client.post("/plugins", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert set(data["scopes"]) == {"internet", "compute"}
    await admin_client.delete(f"/plugins/{data['id']}")


# ── List ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_plugins_returns_200(admin_client):
    resp = await admin_client.get("/plugins")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_plugins_includes_seeded(admin_client):
    resp = await admin_client.get("/plugins")
    slugs = [p["slug"] for p in resp.json()]
    assert "web-search" in slugs
    assert "code-interpreter" in slugs


@pytest.mark.asyncio
async def test_list_plugins_includes_created(admin_client):
    payload = _plugin_payload()
    create_resp = await admin_client.post("/plugins", json=payload)
    plugin_id = create_resp.json()["id"]

    list_resp = await admin_client.get("/plugins")
    ids = [p["id"] for p in list_resp.json()]
    assert plugin_id in ids

    await admin_client.delete(f"/plugins/{plugin_id}")


# ── Get ───────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_plugin_returns_plugin_and_overrides(admin_client):
    payload = _plugin_payload()
    create_resp = await admin_client.post("/plugins", json=payload)
    plugin_id = create_resp.json()["id"]

    resp = await admin_client.get(f"/plugins/{plugin_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "plugin" in data
    assert "team_overrides" in data
    assert data["plugin"]["id"] == plugin_id

    await admin_client.delete(f"/plugins/{plugin_id}")


@pytest.mark.asyncio
async def test_get_plugin_404_on_missing(admin_client):
    resp = await admin_client.get(f"/plugins/{uuid.uuid4()}")
    assert resp.status_code == 404


# ── Update ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_plugin_name(admin_client):
    payload = _plugin_payload()
    create_resp = await admin_client.post("/plugins", json=payload)
    plugin_id = create_resp.json()["id"]

    new_name = f"updated-{uuid.uuid4().hex[:8]}"
    resp = await admin_client.put(f"/plugins/{plugin_id}", json={"name": new_name})
    assert resp.status_code == 200
    assert resp.json()["name"] == new_name

    await admin_client.delete(f"/plugins/{plugin_id}")


@pytest.mark.asyncio
async def test_update_plugin_disable(admin_client):
    payload = _plugin_payload()
    create_resp = await admin_client.post("/plugins", json=payload)
    plugin_id = create_resp.json()["id"]

    resp = await admin_client.put(f"/plugins/{plugin_id}", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    await admin_client.delete(f"/plugins/{plugin_id}")


@pytest.mark.asyncio
async def test_update_plugin_scopes(admin_client):
    payload = _plugin_payload()
    create_resp = await admin_client.post("/plugins", json=payload)
    plugin_id = create_resp.json()["id"]

    resp = await admin_client.put(f"/plugins/{plugin_id}", json={"scopes": ["internet", "files"]})
    assert resp.status_code == 200
    assert set(resp.json()["scopes"]) == {"internet", "files"}

    await admin_client.delete(f"/plugins/{plugin_id}")


@pytest.mark.asyncio
async def test_update_plugin_400_on_empty(admin_client):
    payload = _plugin_payload()
    create_resp = await admin_client.post("/plugins", json=payload)
    plugin_id = create_resp.json()["id"]

    resp = await admin_client.put(f"/plugins/{plugin_id}", json={})
    assert resp.status_code == 400

    await admin_client.delete(f"/plugins/{plugin_id}")


@pytest.mark.asyncio
async def test_update_plugin_404_on_missing(admin_client):
    resp = await admin_client.put(f"/plugins/{uuid.uuid4()}", json={"name": "x"})
    assert resp.status_code == 404


# ── Delete ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_plugin_returns_204(admin_client):
    payload = _plugin_payload()
    create_resp = await admin_client.post("/plugins", json=payload)
    plugin_id = create_resp.json()["id"]

    resp = await admin_client.delete(f"/plugins/{plugin_id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_plugin_404_on_missing(admin_client):
    resp = await admin_client.delete(f"/plugins/{uuid.uuid4()}")
    assert resp.status_code == 404


# ── Team overrides ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_team_override_returns_201(admin_client, test_team):
    payload = _plugin_payload()
    create_resp = await admin_client.post("/plugins", json=payload)
    plugin_id = create_resp.json()["id"]

    resp = await admin_client.post(
        f"/plugins/{plugin_id}/teams",
        json={"team_id": test_team, "enabled": True},
    )
    assert resp.status_code == 201

    await admin_client.delete(f"/plugins/{plugin_id}")


@pytest.mark.asyncio
async def test_set_team_override_upsert(admin_client, test_team):
    payload = _plugin_payload()
    create_resp = await admin_client.post("/plugins", json=payload)
    plugin_id = create_resp.json()["id"]

    await admin_client.post(
        f"/plugins/{plugin_id}/teams",
        json={"team_id": test_team, "enabled": True},
    )
    resp = await admin_client.post(
        f"/plugins/{plugin_id}/teams",
        json={"team_id": test_team, "enabled": False},
    )
    assert resp.status_code in (200, 201)
    assert resp.json()["enabled"] is False

    await admin_client.delete(f"/plugins/{plugin_id}")


@pytest.mark.asyncio
async def test_list_team_overrides_includes_added(admin_client, test_team):
    payload = _plugin_payload()
    create_resp = await admin_client.post("/plugins", json=payload)
    plugin_id = create_resp.json()["id"]

    await admin_client.post(
        f"/plugins/{plugin_id}/teams",
        json={"team_id": test_team, "enabled": True},
    )

    resp = await admin_client.get(f"/plugins/{plugin_id}/teams")
    assert resp.status_code == 200
    team_ids = [o["team_id"] for o in resp.json()]
    assert test_team in team_ids

    await admin_client.delete(f"/plugins/{plugin_id}")


@pytest.mark.asyncio
async def test_delete_team_override_returns_204(admin_client, test_team):
    payload = _plugin_payload()
    create_resp = await admin_client.post("/plugins", json=payload)
    plugin_id = create_resp.json()["id"]

    await admin_client.post(
        f"/plugins/{plugin_id}/teams",
        json={"team_id": test_team, "enabled": True},
    )

    resp = await admin_client.delete(f"/plugins/{plugin_id}/teams/{test_team}")
    assert resp.status_code == 204

    await admin_client.delete(f"/plugins/{plugin_id}")


@pytest.mark.asyncio
async def test_delete_team_override_404_when_missing(admin_client, test_team):
    payload = _plugin_payload()
    create_resp = await admin_client.post("/plugins", json=payload)
    plugin_id = create_resp.json()["id"]

    resp = await admin_client.delete(f"/plugins/{plugin_id}/teams/{test_team}")
    assert resp.status_code == 404

    await admin_client.delete(f"/plugins/{plugin_id}")


@pytest.mark.asyncio
async def test_set_override_404_on_missing_plugin(admin_client, test_team):
    resp = await admin_client.post(
        f"/plugins/{uuid.uuid4()}/teams",
        json={"team_id": test_team, "enabled": True},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_set_override_404_on_missing_team(admin_client):
    payload = _plugin_payload()
    create_resp = await admin_client.post("/plugins", json=payload)
    plugin_id = create_resp.json()["id"]

    resp = await admin_client.post(
        f"/plugins/{plugin_id}/teams",
        json={"team_id": str(uuid.uuid4()), "enabled": True},
    )
    assert resp.status_code == 404

    await admin_client.delete(f"/plugins/{plugin_id}")


# ── Summary delta ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_summary_total_increases_on_create(admin_client):
    before = (await admin_client.get("/plugins/summary")).json()["total"]

    payload = _plugin_payload()
    create_resp = await admin_client.post("/plugins", json=payload)
    plugin_id = create_resp.json()["id"]

    after = (await admin_client.get("/plugins/summary")).json()["total"]
    assert after == before + 1

    await admin_client.delete(f"/plugins/{plugin_id}")


@pytest.mark.asyncio
async def test_summary_overrides_count_increases(admin_client, test_team):
    payload = _plugin_payload()
    create_resp = await admin_client.post("/plugins", json=payload)
    plugin_id = create_resp.json()["id"]

    before = (await admin_client.get("/plugins/summary")).json()["total_overrides"]

    await admin_client.post(
        f"/plugins/{plugin_id}/teams",
        json={"team_id": test_team, "enabled": True},
    )

    after = (await admin_client.get("/plugins/summary")).json()["total_overrides"]
    assert after == before + 1

    await admin_client.delete(f"/plugins/{plugin_id}")
