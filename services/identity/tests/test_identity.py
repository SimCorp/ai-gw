"""Behavioral tests for the identity service (real Postgres via testcontainers)."""

# Matches the service token configured by the autouse _configure_service_token fixture.
AUTH = {"X-Service-Token": "testtoken"}


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_resolve_ranks_exact_then_capability_then_partial_and_dedups(client, insert_agent):
    # "search" is an exact slug, a capability of another agent, and a partial
    # match of a third — verifies ordering and that no slug appears twice.
    await insert_agent("search", name="Search Bot")  # exact slug
    await insert_agent("indexer", capabilities=["search"])  # capability tag
    await insert_agent("search-helper", name="Helper")  # partial ILIKE
    await insert_agent("unrelated", name="Nothing")  # must not appear

    resp = await client.get("/resolve/search")
    assert resp.status_code == 200
    slugs = [a["slug"] for a in resp.json()]

    # Exact first, then capability, then partial. No duplicates, no 'unrelated'.
    assert slugs == ["search", "indexer", "search-helper"]


async def test_resolve_returns_empty_list_for_no_match(client):
    resp = await client.get("/resolve/ghost")
    assert resp.status_code == 200
    assert resp.json() == []


import uuid


async def test_list_agents_filters(client, insert_agent):
    team_a = uuid.uuid4()
    await insert_agent("a1", category="research", capabilities=["web"], managed=True)
    await insert_agent("a2", category="ops", capabilities=["web", "shell"], managed=False)
    await insert_agent("a3", category="research", capabilities=["shell"], managed=True)

    # Seed one with a team_id via direct SQL (insert_agent has no team param).
    async with client.pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO agent_identities (slug, name, capabilities, team_id) "
            "VALUES ($1, $1, $2, $3)",
            "a4",
            [],
            team_a,
        )

    # capability filter (ANY)
    by_cap = await client.get("/agents", params={"capability": "shell"})
    assert {a["slug"] for a in by_cap.json()} == {"a2", "a3"}

    # category filter
    by_cat = await client.get("/agents", params={"category": "research"})
    assert {a["slug"] for a in by_cat.json()} == {"a1", "a3"}

    # managed filter
    by_managed = await client.get("/agents", params={"managed": "true"})
    assert {a["slug"] for a in by_managed.json()} == {"a1", "a3"}

    # team_id filter
    by_team = await client.get("/agents", params={"team_id": str(team_a)})
    assert {a["slug"] for a in by_team.json()} == {"a4"}

    # no filter → all four
    all_agents = await client.get("/agents")
    assert {a["slug"] for a in all_agents.json()} == {"a1", "a2", "a3", "a4"}


from unittest.mock import AsyncMock


async def test_get_agent_404_and_found(client, insert_agent):
    missing = await client.get("/agents/nope")
    assert missing.status_code == 404

    await insert_agent("found", name="Found", capabilities=["x"])
    ok = await client.get("/agents/found")
    assert ok.status_code == 200
    body = ok.json()
    assert body["slug"] == "found"
    assert body["online"] is False  # redis.exists mocked to 0


async def test_get_agent_online_flag_reflects_redis(client, insert_agent):
    await insert_agent("live", name="Live")
    client.redis.exists = AsyncMock(return_value=1)
    resp = await client.get("/agents/live")
    assert resp.json()["online"] is True


async def test_endpoint_lookup(client, insert_agent):
    await insert_agent("worker", endpoint="http://workflow-worker:8000/invoke/worker", managed=True)
    resp = await client.get("/agents/worker/endpoint")
    assert resp.status_code == 200
    body = resp.json()
    assert body["endpoint"] == "http://workflow-worker:8000/invoke/worker"
    assert body["online"] is False
    assert "agent_id" in body

    assert (await client.get("/agents/ghost/endpoint")).status_code == 404


async def test_identity_summary(client, insert_agent):
    await insert_agent("verified-agent", capabilities=["a", "b"], token_verified=True)
    resp = await client.get("/agents/verified-agent/identity")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "slug": "verified-agent",
        "token_verified": True,
        "capabilities": ["a", "b"],
        "online": False,
    }

    assert (await client.get("/agents/ghost/identity")).status_code == 404


async def test_heartbeat_404_for_unknown_slug(client):
    resp = await client.post("/agents/ghost/heartbeat")
    assert resp.status_code == 404


async def test_heartbeat_sets_redis_key_and_updates_last_seen(client, insert_agent):
    await insert_agent("beater", name="Beater")
    resp = await client.post("/agents/beater/heartbeat")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "ttl": 60}
    client.redis.setex.assert_awaited_once()
    key, ttl, val = client.redis.setex.call_args[0]
    assert key == "identity:online:beater"
    assert ttl == 60


async def test_heartbeat_fails_open_when_no_stored_relay_token(client, insert_agent):
    await insert_agent("open-agent")
    client.redis.get = AsyncMock(return_value=None)  # no relay token registered
    resp = await client.post("/agents/open-agent/heartbeat")
    assert resp.status_code == 200


async def test_heartbeat_rejects_wrong_relay_token(client, insert_agent):
    await insert_agent("guarded")
    client.redis.get = AsyncMock(return_value="correct-token")
    bad = await client.post("/agents/guarded/heartbeat", headers={"X-Relay-Token": "wrong"})
    assert bad.status_code == 401
    good = await client.post(
        "/agents/guarded/heartbeat", headers={"X-Relay-Token": "correct-token"}
    )
    assert good.status_code == 200
    # The gate must read the slug-scoped relay-token key, not some other key.
    client.redis.get.assert_awaited_with("relay:agent:guarded:token")


async def test_register_inserts_then_upserts(client):
    first = await client.post(
        "/agents/register",
        json={"slug": "reg", "name": "Reg One", "capabilities": ["a"]},
        headers=AUTH,
    )
    assert first.status_code == 201
    assert first.json()["name"] == "Reg One"
    assert first.json()["token_verified"] is False

    # Same slug → ON CONFLICT updates in place (no duplicate, new name).
    second = await client.post(
        "/agents/register",
        json={"slug": "reg", "name": "Reg Two", "capabilities": ["a", "b"]},
        headers=AUTH,
    )
    assert second.status_code == 201
    assert second.json()["name"] == "Reg Two"
    assert second.json()["capabilities"] == ["a", "b"]

    listed = await client.get("/agents")
    assert sum(1 for a in listed.json() if a["slug"] == "reg") == 1


async def test_register_verifies_identity_token(client, monkeypatch):
    from app import main

    async def fake_verify(token, admin_url):
        return token == "good-token"

    monkeypatch.setattr(main, "_verify_identity_token", fake_verify)

    verified = await client.post(
        "/agents/register",
        json={"slug": "v", "name": "V", "identity_token": "good-token"},
        headers=AUTH,
    )
    assert verified.json()["token_verified"] is True

    unverified = await client.post(
        "/agents/register",
        json={"slug": "u", "name": "U", "identity_token": "bad-token"},
        headers=AUTH,
    )
    assert unverified.json()["token_verified"] is False


async def test_register_enforces_service_token_when_configured(client, monkeypatch):
    from app import main

    monkeypatch.setattr(main.settings, "identity_service_token", "svc-secret")

    bad = await client.post("/agents/register", json={"slug": "s", "name": "S"})
    assert bad.status_code == 401

    ok = await client.post(
        "/agents/register",
        json={"slug": "s", "name": "S"},
        headers={"X-Service-Token": "svc-secret"},
    )
    assert ok.status_code == 201


async def test_deregister(client, insert_agent):
    await insert_agent("byebye")
    resp = await client.delete("/agents/byebye", headers=AUTH)
    assert resp.status_code == 204
    client.redis.delete.assert_awaited_with("identity:online:byebye")
    assert (await client.get("/agents/byebye")).status_code == 404

    # 404 when already gone.
    assert (await client.delete("/agents/byebye", headers=AUTH)).status_code == 404


async def test_register_fails_closed_when_token_unset(client, monkeypatch):
    """With no service token configured, register is 503 (not open)."""
    from app import main

    monkeypatch.setattr(main.settings, "identity_service_token", "")
    resp = await client.post("/agents/register", json={"slug": "x", "name": "X"})
    assert resp.status_code == 503


async def test_deregister_enforces_service_token_when_configured(client, insert_agent, monkeypatch):
    from app import main

    await insert_agent("protected")
    monkeypatch.setattr(main.settings, "identity_service_token", "svc-secret")
    assert (await client.delete("/agents/protected")).status_code == 401


async def test_capabilities_distinct_sorted(client, insert_agent):
    await insert_agent("c1", capabilities=["web", "shell"])
    await insert_agent("c2", capabilities=["web", "vision"])
    resp = await client.get("/capabilities")
    assert resp.status_code == 200
    assert resp.json() == {"capabilities": ["shell", "vision", "web"]}
