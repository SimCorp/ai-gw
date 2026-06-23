"""Reusable JSON-RPC 2.0 handler for MCP (Model Context Protocol).

Usage::

    server = MCPServer(name="my-mcp", version="1.0", description="...")
    server.add_tool(name, description, input_schema, handler_fn)

    @router.post("/mcp")
    async def mcp_endpoint(body: dict, request: Request):
        return await server.handle(body, request)

Spec: https://spec.modelcontextprotocol.io  (JSON-RPC 2.0, version 2024-11-05)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

from fastapi import Request
from fastapi.responses import Response, StreamingResponse

_log = logging.getLogger(__name__)


class MCPServer:
    """JSON-RPC 2.0 handler for MCP protocol."""

    MCP_PROTOCOL_VERSION = "2024-11-05"

    def __init__(self, name: str, version: str, description: str) -> None:
        self.name = name
        self.version = version
        self.description = description
        # Ordered list of tool definitions (name, description, inputSchema)
        self._tools: list[dict[str, Any]] = []
        # Map tool name -> async handler callable
        self._handlers: dict[str, Callable[..., Awaitable[Any]]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def add_tool(
        self,
        name: str,
        description: str,
        input_schema: dict,
        handler: Callable[..., Awaitable[Any]],
    ) -> None:
        """Register a tool and its async handler.

        The handler receives ``(arguments: dict, request: Request)`` and should
        return a JSON-serialisable value.
        """
        self._tools.append(
            {
                "name": name,
                "description": description,
                "inputSchema": input_schema,
            }
        )
        self._handlers[name] = handler

    # ------------------------------------------------------------------
    # Internal JSON-RPC helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ok(request_id: Any, result: Any) -> dict:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

    # ------------------------------------------------------------------
    # Method handlers
    # ------------------------------------------------------------------

    def _handle_initialize(self, params: dict, request_id: Any) -> dict:
        return self._ok(
            request_id,
            {
                "protocolVersion": self.MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": self.name, "version": self.version},
            },
        )

    def _handle_tools_list(self, params: dict, request_id: Any) -> dict:
        return self._ok(request_id, {"tools": self._tools})

    async def _handle_tools_call(self, params: dict, request_id: Any, request: Request) -> dict:
        tool_name = params.get("name", "")
        arguments = params.get("arguments") or {}

        handler = self._handlers.get(tool_name)
        if handler is None:
            return self._error(
                request_id,
                -32601,
                f"Tool not found: {tool_name}",
            )

        try:
            result = await handler(arguments, request)
        except Exception as exc:
            _log.exception("Tool %s raised an exception: %s", tool_name, exc)
            return self._error(request_id, -32603, "Tool execution error")

        return self._ok(
            request_id,
            {"content": [{"type": "text", "text": json.dumps(result)}]},
        )

    def _handle_ping(self, params: dict, request_id: Any) -> dict:
        return self._ok(request_id, {})

    # ------------------------------------------------------------------
    # Main dispatch
    # ------------------------------------------------------------------

    async def handle(self, body: dict, request: Request) -> Any:
        """Dispatch a JSON-RPC 2.0 request.

        Returns a response dict, or a FastAPI ``Response`` (HTTP 204) for
        notifications (requests without an ``id``).
        """
        method: str = body.get("method", "")
        params: dict = body.get("params") or {}
        request_id = body.get("id")  # None for notifications

        # Notifications have no ``id``; spec says server MUST NOT reply.
        is_notification = "id" not in body

        if method == "initialize":
            if is_notification:
                return Response(status_code=204)
            return self._handle_initialize(params, request_id)

        if method == "notifications/initialized":
            # Always a notification — no response
            return Response(status_code=204)

        if method == "tools/list":
            if is_notification:
                return Response(status_code=204)
            return self._handle_tools_list(params, request_id)

        if method == "tools/call":
            if is_notification:
                return Response(status_code=204)
            return await self._handle_tools_call(params, request_id, request)

        if method == "ping":
            if is_notification:
                return Response(status_code=204)
            return self._handle_ping(params, request_id)

        # Unknown method
        if is_notification:
            # Do not reply to unknown notifications
            return Response(status_code=204)

        _log.debug("MCP unknown method: %s", method)
        return self._error(request_id, -32601, f"Method not found: {method}")

    # ------------------------------------------------------------------
    # HTTP+SSE transport
    # ------------------------------------------------------------------

    def sse_endpoint(self):
        """Return a FastAPI route handler for the HTTP+SSE MCP transport.

        The SSE transport is used by clients that don't support plain HTTP POST
        (e.g. some versions of Claude Desktop, certain IDE extensions). The
        client GETs the SSE endpoint; the server sends:
          1. An ``endpoint`` event pointing back to the POST URL
          2. Responds to client-sent messages forwarded via a side-channel

        Minimal SSE handshake per MCP spec draft:
          - Server sends: ``event: endpoint\\ndata: <post_url>\\n\\n``
          - Client reads it and uses <post_url> for JSON-RPC POSTs
          - Server sends: ``event: message\\ndata: <json-rpc-response>\\n\\n``

        This implementation uses an asyncio.Queue to bridge POST → SSE.
        """

        async def _sse_handler(request: Request) -> StreamingResponse:
            queue: asyncio.Queue[str | None] = asyncio.Queue()

            # Store queue in app state keyed by connection id (best-effort)
            conn_id = id(queue)
            sse_sessions = getattr(request.app.state, "_mcp_sse_sessions", {})
            sse_sessions[conn_id] = queue
            request.app.state._mcp_sse_sessions = sse_sessions

            # Derive the POST URL from the current request
            base = str(request.base_url).rstrip("/")
            path = request.url.path.replace("/sse", "")
            post_url = f"{base}{path}"

            async def _stream():
                yield f"event: endpoint\ndata: {post_url}\n\n"
                try:
                    while True:
                        try:
                            item = await asyncio.wait_for(queue.get(), timeout=15.0)
                        except asyncio.TimeoutError:
                            yield ": keepalive\n\n"
                            continue
                        if item is None:
                            break
                        yield f"event: message\ndata: {item}\n\n"
                finally:
                    sse_sessions.pop(conn_id, None)

            return StreamingResponse(_stream(), media_type="text/event-stream")

        return _sse_handler

    async def handle_and_push_sse(self, body: dict, request: Request) -> Any:
        """Handle a JSON-RPC request and push the response to any active SSE sessions.

        Used when the client posts to the HTTP endpoint associated with an SSE
        stream — response is sent both as the HTTP reply AND via the SSE queue.
        """
        response = await self.handle(body, request)
        sse_sessions = getattr(request.app.state, "_mcp_sse_sessions", {})
        if sse_sessions and not isinstance(response, Response):
            payload = json.dumps(response)
            for q in list(sse_sessions.values()):
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    pass
        return response
