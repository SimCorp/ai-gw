"""Tests for the MCPServer JSON-RPC 2.0 handler (services/admin/app/mcp_protocol.py).

All tests run without a real HTTP server — MCPServer.handle() is called directly.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.mcp_protocol import MCPServer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_request() -> MagicMock:
    """Return a minimal stand-in for a FastAPI Request object."""
    return MagicMock()


async def _echo_handler(arguments: dict, request) -> dict:
    """Simple handler that echoes its arguments."""
    return {"echo": arguments}


async def _raising_handler(arguments: dict, request) -> dict:
    raise RuntimeError("tool boom")


def _build_server() -> MCPServer:
    server = MCPServer(name="test-server", version="0.1.0", description="Unit test MCP server")
    server.add_tool(
        name="echo",
        description="Echo arguments back",
        input_schema={
            "type": "object",
            "properties": {"msg": {"type": "string"}},
            "required": ["msg"],
        },
        handler=_echo_handler,
    )
    return server


# ---------------------------------------------------------------------------
# initialize
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_initialize_returns_protocol_version():
    server = _build_server()
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
    }
    response = await server.handle(body, _fake_request())
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    result = response["result"]
    assert result["protocolVersion"] == MCPServer.MCP_PROTOCOL_VERSION
    assert result["serverInfo"]["name"] == "test-server"
    assert result["serverInfo"]["version"] == "0.1.0"
    assert "tools" in result["capabilities"]


# ---------------------------------------------------------------------------
# tools/list
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tools_list_returns_registered_tools():
    server = _build_server()
    body = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    response = await server.handle(body, _fake_request())
    assert response["id"] == 2
    tools = response["result"]["tools"]
    assert isinstance(tools, list)
    assert len(tools) == 1
    assert tools[0]["name"] == "echo"
    assert "inputSchema" in tools[0]


# ---------------------------------------------------------------------------
# tools/call — success
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tools_call_dispatches_to_handler():
    server = _build_server()
    body = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "echo", "arguments": {"msg": "hello"}},
    }
    response = await server.handle(body, _fake_request())
    assert response["id"] == 3
    content = response["result"]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    payload = json.loads(content[0]["text"])
    assert payload == {"echo": {"msg": "hello"}}


# ---------------------------------------------------------------------------
# tools/call — unknown tool
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tools_call_unknown_tool_returns_error():
    server = _build_server()
    body = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "does_not_exist", "arguments": {}},
    }
    response = await server.handle(body, _fake_request())
    assert "error" in response
    assert response["error"]["code"] == -32601


# ---------------------------------------------------------------------------
# tools/call — handler raises
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tools_call_handler_exception_returns_internal_error():
    server = MCPServer(name="s", version="1", description="d")
    server.add_tool(
        name="boom",
        description="explodes",
        input_schema={"type": "object"},
        handler=_raising_handler,
    )
    body = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {"name": "boom", "arguments": {}},
    }
    response = await server.handle(body, _fake_request())
    assert "error" in response
    assert response["error"]["code"] == -32603


# ---------------------------------------------------------------------------
# Unknown method
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_method_returns_error():
    server = _build_server()
    body = {"jsonrpc": "2.0", "id": 6, "method": "nonexistent/method", "params": {}}
    response = await server.handle(body, _fake_request())
    assert "error" in response
    assert response["error"]["code"] == -32601
    assert "nonexistent/method" in response["error"]["message"]


# ---------------------------------------------------------------------------
# Notifications (no id field) — must return HTTP 204 response, not a dict
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notification_returns_no_response():
    server = _build_server()
    # notifications/initialized is always a notification
    body = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    response = await server.handle(body, _fake_request())
    # Should be a Response object (HTTP 204), not a plain dict
    assert hasattr(response, "status_code"), (
        "Expected a Response object for notifications, got a dict"
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_notification_initialize_returns_no_response():
    """An initialize *without* an id field is a notification — no reply."""
    server = _build_server()
    body = {"jsonrpc": "2.0", "method": "initialize", "params": {}}
    response = await server.handle(body, _fake_request())
    assert hasattr(response, "status_code")
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_unknown_notification_returns_no_response():
    server = _build_server()
    body = {"jsonrpc": "2.0", "method": "some/unknown/notification"}
    response = await server.handle(body, _fake_request())
    assert hasattr(response, "status_code")
    assert response.status_code == 204


# ---------------------------------------------------------------------------
# ping
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ping_returns_empty_result():
    server = _build_server()
    body = {"jsonrpc": "2.0", "id": 7, "method": "ping", "params": {}}
    response = await server.handle(body, _fake_request())
    assert response["id"] == 7
    assert response["result"] == {}


# ---------------------------------------------------------------------------
# Multiple tools registration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tools_list_reflects_all_registered_tools():
    server = MCPServer(name="multi", version="1.0", description="test")

    async def noop(args, req):
        return {}

    server.add_tool("alpha", "first", {"type": "object"}, noop)
    server.add_tool("beta", "second", {"type": "object"}, noop)
    server.add_tool("gamma", "third", {"type": "object"}, noop)

    body = {"jsonrpc": "2.0", "id": 8, "method": "tools/list", "params": {}}
    response = await server.handle(body, _fake_request())
    names = [t["name"] for t in response["result"]["tools"]]
    assert names == ["alpha", "beta", "gamma"]
