"""Tests for memory service handler logic not covered by test_mcp.py.

Targets nontrivial control flow: BFS traversal, graph adjacency, conditional
re-embedding, not-found error contracts, component count, and protocol errors.

All store calls are mocked; no real DB required.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest


# ── Helpers (mirror test_mcp.py) ──────────────────────────────────────────────


def _rpc(method: str, params: dict | None = None, req_id: int = 1) -> dict:
    body = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params:
        body["params"] = params
    return body


def _tool_call(tool: str, arguments: dict | None = None, req_id: int = 1) -> dict:
    return _rpc("tools/call", {"name": tool, "arguments": arguments or {}}, req_id)


def _parse_result(response_json: dict) -> dict:
    content = response_json["result"]["content"]
    return json.loads(content[0]["text"])


_AUTH = {"Authorization": "Bearer test-token"}

_FAKE_DRAWER = {
    "id": "drawer-abc",
    "developer_id": "dev-uuid-test",
    "wing": "code",
    "room": "python",
    "content": "original text",
    "summary": None,
    "tags": [],
    "source": None,
    "embedding": None,
    "created_at": "2026-01-01T00:00:00",
    "updated_at": "2026-01-01T00:00:00",
}


# ── update_drawer: selective re-embedding ─────────────────────────────────────


@pytest.mark.asyncio
async def test_update_drawer_no_content_change_skips_embed(client):
    """Updating a non-content field must NOT call _embed."""
    updated = dict(_FAKE_DRAWER, room="rust")

    with (
        patch("app.store.update_drawer", new=AsyncMock(return_value=updated)),
        patch("app.main._embed", new=AsyncMock()) as mock_embed,
    ):
        r = await client.post(
            "/mcp",
            json=_tool_call("mempalace_update_drawer", {"id": "drawer-abc", "room": "rust"}),
            headers=_AUTH,
        )

    assert r.status_code == 200
    data = _parse_result(r.json())
    assert data["room"] == "rust"
    mock_embed.assert_not_called()


@pytest.mark.asyncio
async def test_update_drawer_content_change_re_embeds(client):
    """Updating the content field MUST call _embed and pass the new embedding."""
    fake_embed = [0.5] * 1536
    updated = dict(_FAKE_DRAWER, content="new content", embedding=fake_embed)

    with (
        patch("app.main._embed", new=AsyncMock(return_value=fake_embed)) as mock_embed,
        patch("app.store.update_drawer", new=AsyncMock(return_value=updated)),
    ):
        r = await client.post(
            "/mcp",
            json=_tool_call(
                "mempalace_update_drawer",
                {"id": "drawer-abc", "content": "new content"},
            ),
            headers=_AUTH,
        )

    assert r.status_code == 200
    data = _parse_result(r.json())
    assert data["content"] == "new content"
    mock_embed.assert_called_once_with("new content")


# ── get_drawer: not-found error contract ─────────────────────────────────────


@pytest.mark.asyncio
async def test_get_drawer_not_found_returns_error_in_result(client):
    """A missing drawer returns HTTP 200 with an error in the result — not a 404."""
    with patch("app.store.get_drawer", new=AsyncMock(return_value=None)):
        r = await client.post(
            "/mcp",
            json=_tool_call("mempalace_get_drawer", {"id": "nonexistent-id"}),
            headers=_AUTH,
        )

    assert r.status_code == 200
    data = _parse_result(r.json())
    assert "error" in data
    assert "not found" in data["error"].lower()


# ── follow_tunnels: BFS traversal ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_follow_tunnels_bfs_depth_1(client):
    """BFS from wing_a at depth 1 reaches wing_b directly."""

    async def _fake_find_tunnels(pool, dev, wing):
        if wing == "wing_a":
            return [{"from_wing": "wing_a", "to_wing": "wing_b", "label": "connects"}]
        return []

    with patch("app.store.find_tunnels", new=_fake_find_tunnels):
        r = await client.post(
            "/mcp",
            json=_tool_call("mempalace_follow_tunnels", {"from_wing": "wing_a", "depth": 1}),
            headers=_AUTH,
        )

    assert r.status_code == 200
    data = _parse_result(r.json())
    wings = [item["wing"] for item in data["reachable"]]
    assert "wing_b" in wings
    assert data["reachable"][0]["depth"] == 1


@pytest.mark.asyncio
async def test_follow_tunnels_does_not_revisit_wings(client):
    """A graph with a cycle (a→b, b→a) must not loop indefinitely."""

    async def _fake_find_tunnels(pool, dev, wing):
        tunnels = {
            "alpha": [{"from_wing": "alpha", "to_wing": "beta", "label": "link"}],
            "beta": [{"from_wing": "alpha", "to_wing": "beta", "label": "link"}],
        }
        return tunnels.get(wing, [])

    with patch("app.store.find_tunnels", new=_fake_find_tunnels):
        r = await client.post(
            "/mcp",
            json=_tool_call("mempalace_follow_tunnels", {"from_wing": "alpha", "depth": 5}),
            headers=_AUTH,
        )

    assert r.status_code == 200
    data = _parse_result(r.json())
    # beta should appear exactly once
    reachable_wings = [item["wing"] for item in data["reachable"]]
    assert reachable_wings.count("beta") == 1


# ── traverse: adjacency graph ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_traverse_builds_adjacency_graph(client):
    """Traversal from start_wing returns the full adjacency graph."""

    async def _fake_find_tunnels(pool, dev, wing):
        data = {
            "x": [{"from_wing": "x", "to_wing": "y", "label": "edge"}],
            "y": [{"from_wing": "y", "to_wing": "z", "label": "edge"}],
            "z": [],
        }
        return data.get(wing, [])

    with patch("app.store.find_tunnels", new=_fake_find_tunnels):
        r = await client.post(
            "/mcp",
            json=_tool_call("mempalace_traverse", {"start_wing": "x", "depth": 5}),
            headers=_AUTH,
        )

    assert r.status_code == 200
    data = _parse_result(r.json())
    graph = data["graph"]
    assert "y" in graph["x"]
    assert "z" in graph["y"]
    assert set(data["visited"]) == {"x", "y", "z"}


# ── graph_stats: component count heuristic ────────────────────────────────────


@pytest.mark.asyncio
async def test_graph_stats_zero_nodes_zero_components(client):
    with patch("app.store.kg_stats", new=AsyncMock(return_value={"total_nodes": 0, "total_edges": 0})):
        r = await client.post("/mcp", json=_tool_call("mempalace_graph_stats"), headers=_AUTH)

    assert r.status_code == 200
    data = _parse_result(r.json())
    assert data["nodes"] == 0
    assert data["edges"] == 0
    assert data["components"] == 0


@pytest.mark.asyncio
async def test_graph_stats_nonzero_nodes_one_component(client):
    with patch("app.store.kg_stats", new=AsyncMock(return_value={"total_nodes": 5, "total_edges": 3})):
        r = await client.post("/mcp", json=_tool_call("mempalace_graph_stats"), headers=_AUTH)

    assert r.status_code == 200
    data = _parse_result(r.json())
    assert data["nodes"] == 5
    assert data["edges"] == 3
    assert data["components"] == 1


# ── JSON-RPC protocol: unknown method ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_method_returns_json_rpc_error(client):
    """An unknown method returns -32601 Method Not Found, not an HTTP error."""
    r = await client.post(
        "/mcp",
        json=_rpc("totally_unknown_method"),
        headers=_AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] == -32601
