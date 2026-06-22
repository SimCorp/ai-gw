"""MCP surface: public discovery, REST tools, JSON-RPC dispatch, auth boundary."""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient


async def test_discovery_is_public(client):
    # These endpoints never gate on auth (admin ping_server / clients discover them).
    for path in ("/mcp/manifest", "/mcp/tools", "/mcp"):
        resp = await client.get(path)
        assert resp.status_code == 200
    names = {t["name"] for t in (await client.get("/mcp/tools")).json()}
    assert {"graph_query", "graph_path", "graph_explain", "graph_stats", "list_repos"} <= names


async def test_rest_tool_list_repos(client):
    await client.post("/repos", json={"name": "ims"})
    resp = await client.post("/mcp/tools/list_repos", json={})
    assert resp.status_code == 200
    # Not 'ready' until a build succeeds → list is empty.
    assert resp.json()["repos"] == []


async def test_rest_tool_unknown_404(client):
    assert (await client.post("/mcp/tools/nope", json={})).status_code == 404


async def test_jsonrpc_tools_list(client):
    resp = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert resp.status_code == 200
    tools = resp.json()["result"]["tools"]
    assert any(t["name"] == "graph_query" for t in tools)
    assert all("inputSchema" in t for t in tools)


async def test_jsonrpc_tools_call_graph_query(client, monkeypatch):
    from app import query

    async def _fake_query(repo, question, *, budget=2000, dfs=False):
        return "result-text"

    monkeypatch.setattr(query, "query", _fake_query)
    resp = await client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "graph_query", "arguments": {"repo": "ims", "question": "x"}},
        },
    )
    assert resp.status_code == 200
    text = resp.json()["result"]["content"][0]["text"]
    assert "result-text" in text


async def test_jsonrpc_unknown_tool(client):
    resp = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "nope"}},
    )
    assert resp.json()["error"]["code"] == -32601


@pytest_asyncio.fixture
async def noauth_client(pool, monkeypatch):
    """A client whose auth boundary is live (auth /validate stubbed to 401)."""
    from app import auth, main

    monkeypatch.setattr(main, "_pool", pool)

    async def _deny(_token):
        return 401

    monkeypatch.setattr(auth, "_validate", _deny)
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as c:
        yield c


async def test_repos_requires_auth(noauth_client):
    assert (await noauth_client.get("/repos")).status_code == 401
    assert (await noauth_client.post("/repos", json={"name": "ims"})).status_code == 401


async def test_query_requires_auth(noauth_client):
    assert (await noauth_client.get("/query", params={"repo": "ims", "q": "x"})).status_code == 401


async def test_discovery_public_even_without_auth(noauth_client):
    # Discovery stays open so admin's registry can ping it.
    assert (await noauth_client.get("/mcp/manifest")).status_code == 200
