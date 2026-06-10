import ipaddress
import json
import time
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter(prefix="/mcp", tags=["mcp"])

# ---------------------------------------------------------------------------
# SSRF protection
# ---------------------------------------------------------------------------

_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / AWS IMDS
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _validate_mcp_url(url: str) -> None:
    try:
        parsed = urlparse(url)
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid URL")
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=422, detail="MCP server URL must use http or https")
    hostname = parsed.hostname or ""
    if not hostname:
        raise HTTPException(status_code=422, detail="MCP server URL must include a hostname")

    # Block known private/loopback hostnames by name
    _BLOCKED_HOSTNAMES = {
        "localhost",
        "metadata.google.internal",
        "169.254.169.254",
    }
    if hostname.lower() in _BLOCKED_HOSTNAMES:
        raise HTTPException(status_code=422, detail="MCP server URL hostname is not allowed")

    # Block bare IP addresses in private/link-local ranges (standard dotted-decimal and IPv6)
    try:
        addr = ipaddress.ip_address(hostname)
        for net in _PRIVATE_NETS:
            if addr in net:
                raise HTTPException(
                    status_code=422,
                    detail="MCP server URL must not point to a private or link-local address",
                )
    except ValueError:
        pass  # Not a standard IP literal — treat as domain name

    # Block alternative IP representations (decimal, octal, hex)
    try:
        numeric = int(hostname, 0)
        if 0 <= numeric <= 0xFFFFFFFF:
            addr = ipaddress.ip_address(numeric)
            for net in _PRIVATE_NETS:
                if addr in net:
                    raise HTTPException(
                        status_code=422,
                        detail="MCP server URL must not point to a private or link-local address",
                    )
    except (ValueError, TypeError):
        pass

    # Block dotted-octal IP representations (e.g. "0177.0.0.1" == 127.0.0.1)
    parts = hostname.split(".")
    if len(parts) == 4 and all(p for p in parts):
        if any(p.startswith("0") and len(p) > 1 for p in parts):
            try:
                octets = [int(p, 8) for p in parts]
                if all(0 <= o <= 255 for o in octets):
                    addr = ipaddress.ip_address(".".join(str(o) for o in octets))
                    for net in _PRIVATE_NETS:
                        if addr in net:
                            raise HTTPException(
                                status_code=422,
                                detail="MCP server URL must not point to a private or link-local address",
                            )
            except (ValueError, TypeError):
                pass


# ---------------------------------------------------------------------------
# Secret masking
# ---------------------------------------------------------------------------


def _mask_server(row: dict) -> dict:
    d = dict(row)
    if d.get("auth_secret"):
        d["auth_secret"] = "***"
    return d


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class McpServerCreate(BaseModel):
    name: str = Field(..., max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    url: str = Field(..., max_length=2048)
    auth_type: str = Field(default="none", pattern="^(none|bearer|api_key)$")
    auth_header: str | None = Field(default=None, max_length=200)
    auth_secret: str | None = Field(default=None, max_length=2048)
    enabled: bool = True


class McpServerUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    url: str | None = None
    auth_type: str | None = None
    auth_header: str | None = None
    auth_secret: str | None = None
    enabled: bool | None = None


# ---------------------------------------------------------------------------
# Column allowlist for update_server
# ---------------------------------------------------------------------------

_ALLOWED_SERVER_FIELDS = {
    "name",
    "description",
    "url",
    "auth_type",
    "auth_header",
    "auth_secret",
    "enabled",
}


class McpToolUpdate(BaseModel):
    enabled: bool


class McpAccessGrant(BaseModel):
    team_id: str


# ---------------------------------------------------------------------------
# Servers
# ---------------------------------------------------------------------------


@router.get("/servers")
async def list_servers(session: AsyncSession = Depends(get_session)):
    rows = (
        (
            await session.execute(
                text("""
        SELECT s.*, COUNT(DISTINCT t.id) AS tool_count, COUNT(DISTINCT a.id) AS access_count
        FROM mcp_servers s
        LEFT JOIN mcp_tools t ON t.server_id = s.id
        LEFT JOIN mcp_server_access a ON a.server_id = s.id
        GROUP BY s.id
        ORDER BY s.name
    """)
            )
        )
        .mappings()
        .all()
    )
    return [_mask_server(dict(r)) for r in rows]


@router.post("/servers", status_code=201)
async def create_server(body: McpServerCreate, session: AsyncSession = Depends(get_session)):
    _validate_mcp_url(body.url)
    result = await session.execute(
        text("""
            INSERT INTO mcp_servers (name, description, url, auth_type, auth_header, auth_secret, enabled)
            VALUES (:name, :description, :url, :auth_type, :auth_header, :auth_secret, :enabled)
            RETURNING *
        """),
        {
            "name": body.name,
            "description": body.description,
            "url": body.url,
            "auth_type": body.auth_type,
            "auth_header": body.auth_header,
            "auth_secret": body.auth_secret,
            "enabled": body.enabled,
        },
    )
    await session.commit()
    return _mask_server(dict(result.mappings().first()))


@router.get("/servers/{server_id}")
async def get_server(server_id: str, session: AsyncSession = Depends(get_session)):
    server_row = (
        (
            await session.execute(
                text("SELECT * FROM mcp_servers WHERE id = CAST(:id AS uuid)"),
                {"id": server_id},
            )
        )
        .mappings()
        .first()
    )
    if not server_row:
        raise HTTPException(status_code=404, detail="MCP server not found")

    tools = (
        (
            await session.execute(
                text(
                    "SELECT * FROM mcp_tools WHERE server_id = CAST(:server_id AS uuid) ORDER BY name"
                ),
                {"server_id": server_id},
            )
        )
        .mappings()
        .all()
    )

    access = (
        (
            await session.execute(
                text("""
            SELECT a.server_id, a.team_id, t.name AS team_name, a.granted_at
            FROM mcp_server_access a
            JOIN organization_nodes t ON t.id = a.team_id
            WHERE a.server_id = CAST(:server_id AS uuid)
            ORDER BY t.name
        """),
                {"server_id": server_id},
            )
        )
        .mappings()
        .all()
    )

    return {
        "server": _mask_server(dict(server_row)),
        "tools": [dict(r) for r in tools],
        "access": [dict(r) for r in access],
    }


@router.put("/servers/{server_id}")
async def update_server(
    server_id: str,
    body: McpServerUpdate,
    session: AsyncSession = Depends(get_session),
):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    if "url" in updates:
        _validate_mcp_url(updates["url"])

    if "auth_secret" in updates and (not updates["auth_secret"] or updates["auth_secret"] == "***"):
        del updates["auth_secret"]

    for field in updates:
        if field not in _ALLOWED_SERVER_FIELDS:
            raise HTTPException(status_code=400, detail=f"Unknown field: {field}")

    set_clauses = []
    params: dict[str, Any] = {"id": server_id}
    for field, value in updates.items():
        set_clauses.append(f"{field} = :{field}")
        params[field] = value
    set_clauses.append("updated_at = NOW()")

    sql = text(f"""
        UPDATE mcp_servers
        SET {", ".join(set_clauses)}
        WHERE id = CAST(:id AS uuid)
        RETURNING *
    """)
    result = await session.execute(sql, params)
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="MCP server not found")
    await session.commit()
    return _mask_server(dict(row))


@router.delete("/servers/{server_id}", status_code=204)
async def delete_server(server_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        text("DELETE FROM mcp_servers WHERE id = CAST(:id AS uuid) RETURNING id"),
        {"id": server_id},
    )
    if not result.first():
        raise HTTPException(status_code=404, detail="MCP server not found")
    await session.commit()


# ---------------------------------------------------------------------------
# Ping / tool sync
# ---------------------------------------------------------------------------


@router.post("/servers/{server_id}/ping")
async def ping_server(server_id: str, session: AsyncSession = Depends(get_session)):
    server_row = (
        (
            await session.execute(
                text("SELECT * FROM mcp_servers WHERE id = CAST(:id AS uuid)"),
                {"id": server_id},
            )
        )
        .mappings()
        .first()
    )
    if not server_row:
        raise HTTPException(status_code=404, detail="MCP server not found")

    server = dict(server_row)
    headers: dict[str, str] = {}
    auth_type = server.get("auth_type", "none")
    if auth_type == "bearer" and server.get("auth_secret"):
        headers["Authorization"] = f"Bearer {server['auth_secret']}"
    elif auth_type == "api_key" and server.get("auth_secret"):
        header_name = server.get("auth_header") or "X-API-Key"
        headers[header_name] = server["auth_secret"]

    tools: list[dict] = []
    status = "active"
    error_msg = None
    latency_ms = 0

    _rpc_headers = {
        **headers,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    def _extract_tools_from_rpc(body: bytes) -> list[dict]:
        """Parse tools/list result from JSON-RPC response (plain JSON or SSE stream)."""
        text_body = body.decode(errors="replace")
        # SSE: extract last `data: {...}` line
        for line in reversed(text_body.splitlines()):
            if line.startswith("data: ") and line != "data: [DONE]":
                text_body = line[6:]
                break
        try:
            rpc = json.loads(text_body)
        except Exception:
            return []
        raw = rpc.get("result", {}).get("tools") or rpc.get("tools") or []
        return raw if isinstance(raw, list) else []

    try:
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            mcp_url = server["url"]

            # ── Strategy 1: MCP session handshake (initialize → tools/list) ─
            init_resp = await client.post(
                mcp_url,
                headers=_rpc_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "ai-gateway-admin", "version": "1.0"},
                    },
                },
            )
            if init_resp.status_code == 200:
                session_id = init_resp.headers.get("mcp-session-id")
                list_headers = {
                    **_rpc_headers,
                    **({"Mcp-Session-Id": session_id} if session_id else {}),
                }
                list_resp = await client.post(
                    mcp_url,
                    headers=list_headers,
                    json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                )
                if list_resp.status_code == 200:
                    tools = _extract_tools_from_rpc(list_resp.content)
                elif list_resp.status_code >= 400:
                    status = "error"
                    error_msg = f"HTTP {list_resp.status_code}: {list_resp.text[:200]}"

            elif init_resp.status_code in (404, 405):
                # ── Strategy 2: direct tools/list (no session required) ──────
                list_resp = await client.post(
                    mcp_url,
                    headers=_rpc_headers,
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                )
                if list_resp.status_code == 200:
                    tools = _extract_tools_from_rpc(list_resp.content)
                elif list_resp.status_code in (404, 405):
                    # ── Strategy 3: GET /tools (non-JSON-RPC servers) ─────────
                    tools_url = mcp_url.rstrip("/") + "/tools"
                    get_resp = await client.get(tools_url, headers=headers)
                    if get_resp.status_code == 404:
                        get_resp = await client.get(mcp_url, headers=headers)
                    if get_resp.status_code < 400:
                        data = get_resp.json()
                        if isinstance(data, list):
                            tools = data
                        elif isinstance(data, dict) and "tools" in data:
                            tools = data["tools"]
                        elif isinstance(data, dict):
                            tools = [
                                {"name": k, **v} for k, v in data.items() if isinstance(v, dict)
                            ]
                    else:
                        status = "error"
                        error_msg = f"HTTP {get_resp.status_code}: {get_resp.text[:200]}"
                else:
                    status = "error"
                    error_msg = f"HTTP {list_resp.status_code}: {list_resp.text[:200]}"
            else:
                status = "error"
                error_msg = f"HTTP {init_resp.status_code}: {init_resp.text[:200]}"

        latency_ms = int((time.monotonic() - start) * 1000)

    except Exception as exc:
        status = "error"
        error_msg = str(exc)[:500]
        latency_ms = 0

    # Upsert tools
    if tools and status == "active":
        for tool in tools:
            tool_name = tool.get("name") or tool.get("tool_name")
            if not tool_name:
                continue
            tool_description = tool.get("description") or tool.get("summary")
            input_schema = (
                tool.get("input_schema") or tool.get("parameters") or tool.get("inputSchema") or {}
            )
            await session.execute(
                text("""
                    INSERT INTO mcp_tools (server_id, name, description, input_schema)
                    VALUES (CAST(:server_id AS uuid), :name, :description, CAST(:schema AS jsonb))
                    ON CONFLICT (server_id, name) DO UPDATE SET
                        description = EXCLUDED.description,
                        input_schema = EXCLUDED.input_schema
                """),
                {
                    "server_id": server_id,
                    "name": tool_name,
                    "description": tool_description,
                    "schema": json.dumps(input_schema),
                },
            )

    tool_count = (
        len(tools)
        if tools
        else (
            (
                await session.execute(
                    text("SELECT COUNT(*) FROM mcp_tools WHERE server_id = CAST(:id AS uuid)"),
                    {"id": server_id},
                )
            ).scalar()
            or 0
        )
    )

    await session.execute(
        text("""
            UPDATE mcp_servers
            SET status = :status,
                last_ping_at = NOW(),
                last_ping_ms = :latency_ms,
                last_error = :error_msg,
                tool_count = :tool_count,
                updated_at = NOW()
            WHERE id = CAST(:id AS uuid)
        """),
        {
            "id": server_id,
            "status": status,
            "latency_ms": latency_ms,
            "error_msg": error_msg,
            "tool_count": tool_count,
        },
    )
    await session.commit()

    return {
        "status": status,
        "tool_count": tool_count,
        "latency_ms": latency_ms,
        "tools": tools,
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@router.get("/servers/{server_id}/tools")
async def list_tools(server_id: str, session: AsyncSession = Depends(get_session)):
    server_row = (
        await session.execute(
            text("SELECT id FROM mcp_servers WHERE id = CAST(:id AS uuid)"),
            {"id": server_id},
        )
    ).first()
    if not server_row:
        raise HTTPException(status_code=404, detail="MCP server not found")

    rows = (
        (
            await session.execute(
                text(
                    "SELECT * FROM mcp_tools WHERE server_id = CAST(:server_id AS uuid) ORDER BY name"
                ),
                {"server_id": server_id},
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


@router.patch("/servers/{server_id}/tools/{tool_name}")
async def update_tool(
    server_id: str,
    tool_name: str,
    body: McpToolUpdate,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        text("""
            UPDATE mcp_tools
            SET enabled = :enabled
            WHERE server_id = CAST(:server_id AS uuid) AND name = :name
            RETURNING *
        """),
        {"server_id": server_id, "name": tool_name, "enabled": body.enabled},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Tool not found")
    await session.commit()
    return dict(row)


# ---------------------------------------------------------------------------
# Tool call proxy
# ---------------------------------------------------------------------------


class ToolCallRequest(BaseModel):
    arguments: dict = Field(default_factory=dict)


@router.post("/servers/{server_id}/tools/{tool_name}/call")
async def call_tool(
    server_id: str,
    tool_name: str,
    body: ToolCallRequest,
    session: AsyncSession = Depends(get_session),
):
    server_row = (
        (
            await session.execute(
                text("SELECT * FROM mcp_servers WHERE id = CAST(:id AS uuid)"),
                {"id": server_id},
            )
        )
        .mappings()
        .first()
    )
    if not server_row:
        raise HTTPException(status_code=404, detail="MCP server not found")

    server = dict(server_row)
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    auth_type = server.get("auth_type", "none")
    if auth_type == "bearer" and server.get("auth_secret"):
        headers["Authorization"] = f"Bearer {server['auth_secret']}"
    elif auth_type == "api_key" and server.get("auth_secret"):
        headers[server.get("auth_header") or "X-API-Key"] = server["auth_secret"]

    mcp_url = server["url"]

    def _parse_rpc_body(content: bytes) -> Any:
        text_body = content.decode(errors="replace")
        for line in reversed(text_body.splitlines()):
            if line.startswith("data: ") and line != "data: [DONE]":
                text_body = line[6:]
                break
        try:
            return json.loads(text_body)
        except Exception:
            return {"raw": text_body}

    try:
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            # Initialize to get session ID
            session_id: str | None = None
            init_resp = await client.post(
                mcp_url,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "ai-gateway-admin", "version": "1.0"},
                    },
                },
            )
            if init_resp.status_code == 200:
                session_id = init_resp.headers.get("mcp-session-id")

            call_headers = {**headers, **({"Mcp-Session-Id": session_id} if session_id else {})}
            call_resp = await client.post(
                mcp_url,
                headers=call_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": body.arguments},
                },
            )

        latency_ms = int((time.monotonic() - start) * 1000)

        if call_resp.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"MCP server returned HTTP {call_resp.status_code}: {call_resp.text[:300]}",
            )

        rpc = _parse_rpc_body(call_resp.content)
        return {
            "latency_ms": latency_ms,
            "result": rpc.get("result"),
            "error": rpc.get("error"),
            "raw": rpc,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------


@router.get("/servers/{server_id}/access")
async def list_access(server_id: str, session: AsyncSession = Depends(get_session)):
    server_row = (
        await session.execute(
            text("SELECT id FROM mcp_servers WHERE id = CAST(:id AS uuid)"),
            {"id": server_id},
        )
    ).first()
    if not server_row:
        raise HTTPException(status_code=404, detail="MCP server not found")

    rows = (
        (
            await session.execute(
                text("""
            SELECT a.server_id, a.team_id, t.name AS team_name, a.granted_at
            FROM mcp_server_access a
            JOIN organization_nodes t ON t.id = a.team_id
            WHERE a.server_id = CAST(:server_id AS uuid)
            ORDER BY t.name
        """),
                {"server_id": server_id},
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


@router.post("/servers/{server_id}/access", status_code=201)
async def grant_access(
    server_id: str,
    body: McpAccessGrant,
    session: AsyncSession = Depends(get_session),
):
    server_row = (
        await session.execute(
            text("SELECT id FROM mcp_servers WHERE id = CAST(:id AS uuid)"),
            {"id": server_id},
        )
    ).first()
    if not server_row:
        raise HTTPException(status_code=404, detail="MCP server not found")

    team_row = (
        await session.execute(
            text(
                "SELECT id FROM organization_nodes WHERE id = CAST(:id AS uuid) AND type = 'team'"
            ),
            {"id": body.team_id},
        )
    ).first()
    if not team_row:
        raise HTTPException(status_code=404, detail="Team not found")

    result = await session.execute(
        text("""
            INSERT INTO mcp_server_access (server_id, team_id)
            VALUES (CAST(:server_id AS uuid), CAST(:team_id AS uuid))
            ON CONFLICT (server_id, team_id) DO NOTHING
            RETURNING *
        """),
        {"server_id": server_id, "team_id": body.team_id},
    )
    await session.commit()
    row = result.mappings().first()
    return dict(row) if row else {"server_id": server_id, "team_id": body.team_id}


@router.delete("/servers/{server_id}/access/{team_id}", status_code=204)
async def revoke_access(
    server_id: str,
    team_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        text("""
            DELETE FROM mcp_server_access
            WHERE server_id = CAST(:server_id AS uuid) AND team_id = CAST(:team_id AS uuid)
            RETURNING id
        """),
        {"server_id": server_id, "team_id": team_id},
    )
    if not result.first():
        raise HTTPException(status_code=404, detail="Access grant not found")
    await session.commit()


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


@router.get("/summary")
async def mcp_summary(session: AsyncSession = Depends(get_session)):
    row = (
        (
            await session.execute(
                text("""
        SELECT
            COUNT(*) AS server_count,
            COUNT(*) FILTER (WHERE status = 'active') AS active_count,
            COUNT(*) FILTER (WHERE status = 'disabled' OR NOT enabled) AS disabled_count,
            COUNT(*) FILTER (WHERE status = 'error') AS error_count,
            COUNT(*) FILTER (WHERE status = 'pending') AS pending_count
        FROM mcp_servers
    """)
            )
        )
        .mappings()
        .first()
    )

    tools_row = (
        (
            await session.execute(
                text("""
        SELECT
            COUNT(*) AS total_tools,
            COUNT(*) FILTER (WHERE enabled) AS enabled_tools
        FROM mcp_tools
    """)
            )
        )
        .mappings()
        .first()
    )

    access_row = (
        (
            await session.execute(
                text("""
        SELECT COUNT(DISTINCT team_id) AS teams_with_access
        FROM mcp_server_access
    """)
            )
        )
        .mappings()
        .first()
    )

    return {
        "server_count": row["server_count"] if row else 0,
        "active_count": row["active_count"] if row else 0,
        "disabled_count": row["disabled_count"] if row else 0,
        "error_count": row["error_count"] if row else 0,
        "pending_count": row["pending_count"] if row else 0,
        "total_tools": tools_row["total_tools"] if tools_row else 0,
        "enabled_tools": tools_row["enabled_tools"] if tools_row else 0,
        "teams_with_access": access_row["teams_with_access"] if access_row else 0,
    }
