"""Tests for the librarian MCP surface — auth gating + tool wiring.

The knowledge base is shared, so MCP auth is access-gating only: a valid sk-*
Bearer is required, but there is no per-caller row scoping. search_knowledge is
mocked so no real DB/embedding backend is needed.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import app.auth as auth
import app.main as main
import pytest


def _tool_call(tool: str, arguments: dict | None = None, req_id: int = 1) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments or {}},
    }


# ── resolve_caller: status mapping (unit) ────────────────────────────────────


class _FakeReq:
    def __init__(self, headers: dict):
        self.headers = headers


@pytest.mark.asyncio
async def test_resolve_caller_missing_bearer_raises_401():
    with pytest.raises(auth.AuthError) as exc:
        await auth.resolve_caller(_FakeReq({}))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_resolve_caller_valid_token_passes():
    with patch.object(auth, "_validate", AsyncMock(return_value=200)):
        # Should not raise.
        await auth.resolve_caller(_FakeReq({"Authorization": "Bearer sk-good"}))


@pytest.mark.asyncio
async def test_resolve_caller_invalid_token_raises_401():
    with patch.object(auth, "_validate", AsyncMock(return_value=401)):
        with pytest.raises(auth.AuthError) as exc:
            await auth.resolve_caller(_FakeReq({"Authorization": "Bearer sk-bad"}))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_resolve_caller_rate_limited_raises_429():
    with patch.object(auth, "_validate", AsyncMock(return_value=429)):
        with pytest.raises(auth.AuthError) as exc:
            await auth.resolve_caller(_FakeReq({"Authorization": "Bearer sk-x"}))
    assert exc.value.status_code == 429


# ── REST tool surface: auth required ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_rest_search_requires_auth(client):
    with patch.object(main, "search_knowledge", AsyncMock()) as sk:
        r = await client.post("/mcp/tools/search", json={"query": "x"})
    assert r.status_code == 401
    sk.assert_not_called()


@pytest.mark.asyncio
async def test_rest_topics_requires_auth(client):
    r = await client.post("/mcp/tools/topics")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_sse_requires_auth(client):
    r = await client.get("/mcp/sse")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_rest_search_with_valid_token(client):
    fake_items = [{"title": "Doc", "content": "hello world", "score": 0.9}]
    with (
        patch.object(main, "resolve_caller", AsyncMock(return_value=None)),
        patch.object(main, "search_knowledge", AsyncMock(return_value=fake_items)) as sk,
    ):
        r = await client.post(
            "/mcp/tools/search",
            json={"query": "hello"},
            headers={"Authorization": "Bearer sk-good"},
        )
    assert r.status_code == 200
    assert r.json()["items"] == fake_items
    sk.assert_awaited_once()


# ── JSON-RPC surface: auth required ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_jsonrpc_requires_auth(client):
    with patch.object(main, "search_knowledge", AsyncMock()) as sk:
        r = await client.post("/mcp", json=_tool_call("search", {"query": "x"}))
    assert r.status_code == 200  # JSON-RPC errors ride a 200 envelope
    body = r.json()
    assert body["error"]["code"] == -32000
    assert body["error"]["message"] == "unauthorized"
    sk.assert_not_called()


@pytest.mark.asyncio
async def test_jsonrpc_search_with_valid_token(client):
    fake_items = [{"title": "Doc", "content": "hi", "score": 0.5}]
    with (
        patch.object(main, "resolve_caller", AsyncMock(return_value=None)),
        patch.object(main, "search_knowledge", AsyncMock(return_value=fake_items)),
    ):
        r = await client.post(
            "/mcp",
            json=_tool_call("search", {"query": "hi"}),
            headers={"Authorization": "Bearer sk-good"},
        )
    assert r.status_code == 200
    body = r.json()
    inner = json.loads(body["result"]["content"][0]["text"])
    assert inner["items"] == fake_items


# ── Discovery stays public (regression guard against over-gating) ────────────


@pytest.mark.asyncio
async def test_manifest_is_public(client):
    r = await client.get("/mcp/manifest")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_tools_list_is_public(client):
    r = await client.get("/mcp/tools")
    assert r.status_code == 200
