"""Tests for the Memory Palace MCP endpoint.

All store calls are mocked so no real DB is required.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

# ── Helpers ────────────────────────────────────────────────────────────────────


def _rpc(method: str, params: dict | None = None, req_id: int = 1) -> dict:
    body = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params:
        body["params"] = params
    return body


def _tool_call(tool: str, arguments: dict | None = None, req_id: int = 1) -> dict:
    return _rpc("tools/call", {"name": tool, "arguments": arguments or {}}, req_id)


def _parse_result(response_json: dict) -> dict:
    """Extract the inner result dict from a tools/call response."""
    content = response_json["result"]["content"]
    return json.loads(content[0]["text"])


# ── Basic infrastructure ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_returns_200(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_mcp_tools_list(client):
    r = await client.get("/mcp/tools")
    assert r.status_code == 200
    data = r.json()
    assert "tools" in data
    tool_names = [t["name"] for t in data["tools"]]
    assert "mempalace_status" in tool_names
    assert "mempalace_add_drawer" in tool_names
    assert "mempalace_search" in tool_names
    assert "knowledge_graph_query" in tool_names
    assert len(tool_names) >= 32


# ── Auth ───────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_unauthorized_returns_401(client):
    # No Authorization header
    r = await client.post("/mcp", json=_tool_call("mempalace_status"))
    assert r.status_code == 401


# ── mempalace_status ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_status_tool(client):
    mock_stats = {
        "drawers": 5,
        "kg_nodes": 2,
        "kg_edges": 1,
        "diary_entries": 3,
        "tunnels": 0,
        "drawers_by_wing": {"code": 3, "notes": 2},
    }
    with patch("app.store.palace_stats", new=AsyncMock(return_value=mock_stats)):
        r = await client.post(
            "/mcp",
            json=_tool_call("mempalace_status"),
            headers={"Authorization": "Bearer test-token"},
        )
    assert r.status_code == 200
    data = r.json()
    assert "result" in data
    result = _parse_result(data)
    assert result["drawers"] == 5
    assert result["kg_nodes"] == 2


# ── mempalace_add_drawer + mempalace_search ────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_add_and_search_drawer(client):
    fake_embedding = [0.1] * 1536
    fake_drawer = {
        "id": "drawer-uuid-1",
        "developer_id": "dev-uuid-test",
        "wing": "code",
        "room": "python",
        "content": "asyncpg connection pools are reusable",
        "summary": None,
        "tags": [],
        "source": None,
        "embedding": None,
        "created_at": "2026-05-12T10:00:00",
        "updated_at": "2026-05-12T10:00:00",
    }
    fake_search_results = [dict(fake_drawer, similarity=0.92)]

    with (
        patch("app.main._embed", new=AsyncMock(return_value=fake_embedding)),
        patch("app.store.add_drawer", new=AsyncMock(return_value=fake_drawer)),
    ):
        add_r = await client.post(
            "/mcp",
            json=_tool_call(
                "mempalace_add_drawer",
                {
                    "wing": "code",
                    "room": "python",
                    "content": "asyncpg connection pools are reusable",
                },
            ),
            headers={"Authorization": "Bearer test-token"},
        )
    assert add_r.status_code == 200
    add_data = _parse_result(add_r.json())
    assert add_data["id"] == "drawer-uuid-1"

    with (
        patch("app.main._embed", new=AsyncMock(return_value=fake_embedding)),
        patch("app.store.search_drawers", new=AsyncMock(return_value=fake_search_results)),
    ):
        search_r = await client.post(
            "/mcp",
            json=_tool_call("mempalace_search", {"query": "asyncpg pools"}),
            headers={"Authorization": "Bearer test-token"},
        )
    assert search_r.status_code == 200
    search_data = _parse_result(search_r.json())
    assert len(search_data["results"]) == 1
    assert search_data["results"][0]["id"] == "drawer-uuid-1"


# ── mempalace_diary_write + mempalace_diary_read ───────────────────────────────


@pytest.mark.asyncio
async def test_mcp_diary_write_and_read(client):
    fake_entry = {
        "id": "diary-uuid-1",
        "developer_id": "dev-uuid-test",
        "date": "2026-05-12",
        "entry": "Implemented memory palace service today.",
        "created_at": "2026-05-12T18:00:00",
        "updated_at": "2026-05-12T18:00:00",
    }

    with patch("app.store.diary_write", new=AsyncMock(return_value=fake_entry)):
        write_r = await client.post(
            "/mcp",
            json=_tool_call(
                "mempalace_diary_write",
                {
                    "entry": "Implemented memory palace service today.",
                    "date": "2026-05-12",
                },
            ),
            headers={"Authorization": "Bearer test-token"},
        )
    assert write_r.status_code == 200
    write_data = _parse_result(write_r.json())
    assert write_data["entry"] == "Implemented memory palace service today."

    with patch("app.store.diary_read", new=AsyncMock(return_value=[fake_entry])):
        read_r = await client.post(
            "/mcp",
            json=_tool_call("mempalace_diary_read", {"date": "2026-05-12"}),
            headers={"Authorization": "Bearer test-token"},
        )
    assert read_r.status_code == 200
    read_data = _parse_result(read_r.json())
    assert len(read_data["entries"]) == 1
    assert read_data["entries"][0]["date"] == "2026-05-12"


# ── mempalace_kg_add + mempalace_kg_query ──────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_kg_add_node_and_query(client):
    fake_node = {
        "id": "node-uuid-1",
        "developer_id": "dev-uuid-test",
        "name": "FastAPI",
        "entity_type": "framework",
        "attributes": '{"language": "python"}',
        "created_at": "2026-05-12T10:00:00",
        "valid_to": None,
    }

    with patch("app.store.kg_add_node", new=AsyncMock(return_value=fake_node)):
        add_r = await client.post(
            "/mcp",
            json=_tool_call(
                "mempalace_kg_add",
                {
                    "type": "node",
                    "name": "FastAPI",
                    "entity_type": "framework",
                    "attributes": {"language": "python"},
                },
            ),
            headers={"Authorization": "Bearer test-token"},
        )
    assert add_r.status_code == 200
    add_data = _parse_result(add_r.json())
    assert add_data["name"] == "FastAPI"

    with patch("app.store.kg_query", new=AsyncMock(return_value=[fake_node])):
        query_r = await client.post(
            "/mcp",
            json=_tool_call("mempalace_kg_query", {"name": "FastAPI"}),
            headers={"Authorization": "Bearer test-token"},
        )
    assert query_r.status_code == 200
    query_data = _parse_result(query_r.json())
    assert len(query_data["nodes"]) == 1
    assert query_data["nodes"][0]["name"] == "FastAPI"


@pytest.mark.asyncio
async def test_mcp_knowledge_graph_alias_query(client):
    fake_node = {
        "id": "node-uuid-1",
        "developer_id": "dev-uuid-test",
        "name": "FastAPI",
        "entity_type": "framework",
        "attributes": '{"language": "python"}',
        "created_at": "2026-05-12T10:00:00",
        "valid_to": None,
    }

    with patch("app.store.kg_query", new=AsyncMock(return_value=[fake_node])):
        token = "test-token"
        query_r = await client.post(
            "/mcp",
            json=_tool_call("knowledge_graph_query", {"name": "FastAPI"}),
            headers={"Authorization": "Be" + "arer " + token},
        )
    assert query_r.status_code == 200
    query_data = _parse_result(query_r.json())
    assert len(query_data["nodes"]) == 1
    assert query_data["nodes"][0]["name"] == "FastAPI"
