"""Behavioral tests for the agent-relay service."""

import json
from unittest.mock import AsyncMock


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_invoke_round_trip(client):
    from app import main

    token = "tok-roundtrip"

    async def fake_send(raw):
        # invoke() has already registered _pending[invocation_id] by now.
        msg = json.loads(raw)
        inv_id = msg["invocation_id"]
        main._pending[inv_id].set_result(
            {"invocation_id": inv_id, "outputs": {"answer": 42}, "exit_code": 0}
        )

    ws = AsyncMock()
    ws.send_text = AsyncMock(side_effect=fake_send)
    main._connections[token] = ws
    main._slug_to_token["agent-x"] = token

    resp = await client.post("/invoke/agent-x", json={"inputs": {"q": "hi"}, "env": {}})

    assert resp.status_code == 200
    assert resp.json() == {"outputs": {"answer": 42}, "exit_code": 0}
    # The payload sent to the agent carried a generated invocation_id + inputs.
    sent = json.loads(ws.send_text.call_args[0][0])
    assert sent["inputs"] == {"q": "hi"}
    assert "invocation_id" in sent


async def test_invoke_not_connected_returns_503(client):
    resp = await client.post("/invoke/nobody", json={"inputs": {}, "env": {}})
    assert resp.status_code == 503
    assert "not connected" in resp.json()["detail"]


async def test_invoke_timeout_returns_504(client, monkeypatch):
    from app import main

    token = "tok-timeout"
    ws = AsyncMock()
    ws.send_text = AsyncMock()  # never resolves the pending future
    main._connections[token] = ws
    main._slug_to_token["slow-agent"] = token

    # Shrink the hard-coded 300s wait so the test is fast. invoke() reads the
    # literal 300.0; patch asyncio.wait_for to use a tiny timeout instead.
    real_wait_for = main.asyncio.wait_for

    async def fast_wait_for(awaitable, timeout):
        return await real_wait_for(awaitable, timeout=0.05)

    monkeypatch.setattr(main.asyncio, "wait_for", fast_wait_for)

    resp = await client.post("/invoke/slow-agent", json={"inputs": {}, "env": {}})
    assert resp.status_code == 504
    assert "timed out" in resp.json()["detail"]
    # The pending future must be cleaned up after timeout.
    assert main._pending == {}


async def test_invoke_requires_relay_secret_when_configured(client, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "_settings", config.Settings(relay_secret="s3cret"))

    # Missing header → 401, even before connection lookup.
    resp = await client.post("/invoke/anything", json={"inputs": {}, "env": {}})
    assert resp.status_code == 401


async def test_register_returns_token_and_populates_state(client):
    from app import main

    main._redis = AsyncMock()  # capture the Redis write

    resp = await client.post(
        "/register", json={"slug": "agent-a", "name": "Agent A", "capabilities": ["x"]}
    )
    assert resp.status_code == 200
    body = resp.json()
    token = body["relay_token"]
    assert body["slug"] == "agent-a"
    assert main._registered_agents[token]["slug"] == "agent-a"
    assert main._slug_to_token["agent-a"] == token
    main._redis.set.assert_awaited_once()
    key, value = main._redis.set.call_args[0]
    assert key == "relay:agent:agent-a:token"
    assert value == token


async def test_register_enforces_relay_secret_when_configured(client, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "_settings", config.Settings(relay_secret="s3cret"))

    bad = await client.post("/register", json={"slug": "a", "name": "A"})
    assert bad.status_code == 401

    ok = await client.post(
        "/register",
        json={"slug": "a", "name": "A"},
        headers={"X-Relay-Secret": "s3cret"},
    )
    assert ok.status_code == 200


async def test_list_agents_only_returns_connected(client):
    from app import main

    # One registered+connected, one registered but not connected.
    main._registered_agents["t1"] = {
        "slug": "online-agent",
        "name": "Online",
        "capabilities": [],
        "connected_at": "2026-06-02T00:00:00+00:00",
    }
    main._connections["t1"] = AsyncMock()
    main._registered_agents["t2"] = {
        "slug": "offline-agent",
        "name": "Offline",
        "capabilities": [],
    }

    resp = await client.get("/agents")
    assert resp.status_code == 200
    agents = resp.json()
    slugs = {a["slug"] for a in agents}
    assert slugs == {"online-agent"}
    # relay_token must never be exposed.
    assert all("relay_token" not in a for a in agents)


def test_ws_unknown_token_is_rejected():
    import pytest
    from app.main import app
    from starlette.testclient import TestClient

    with TestClient(app) as tc:
        with pytest.raises(Exception):
            # Server closes with code 4004 before accepting; the context
            # manager surfaces the rejection as an exception on enter.
            with tc.websocket_connect("/connect/does-not-exist"):
                pass


def test_ws_connect_then_disconnect_cleans_up_state():
    from app import main
    from app.main import app
    from starlette.testclient import TestClient

    token = "tok-ws"
    main._registered_agents[token] = {
        "slug": "ws-agent",
        "name": "WS",
        "capabilities": [],
    }
    main._slug_to_token["ws-agent"] = token

    with TestClient(app) as tc:
        with tc.websocket_connect(f"/connect/{token}"):
            # While connected, the agent shows up in /agents.
            listed = tc.get("/agents").json()
            assert any(a["slug"] == "ws-agent" for a in listed)
        # After the WS context exits (disconnect), state is cleaned up.
        assert token not in main._connections
        assert main._slug_to_token.get("ws-agent") is None


async def test_invoke_does_not_consult_redis(client):
    """invoke() is single-instance: an unknown slug 503s without a Redis lookup."""
    from app import main

    main._redis = AsyncMock()
    main._redis.get = AsyncMock(return_value="some-token-from-another-instance")

    resp = await client.post("/invoke/elsewhere", json={"inputs": {}, "env": {}})

    assert resp.status_code == 503
    main._redis.get.assert_not_called()
