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
