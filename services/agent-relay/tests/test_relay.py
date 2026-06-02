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
