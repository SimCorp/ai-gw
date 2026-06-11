"""Tests for /tools endpoints."""

from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tool_row(tool_id="uuid-generator", label="UUID generator", category="Crypto", enabled=True):
    row = MagicMock()
    data = {
        "tool_id": tool_id,
        "label": label,
        "category": category,
        "enabled": enabled,
        "updated_at": None,
    }
    row.__getitem__ = lambda self, k: data[k]
    row.keys = lambda: data.keys()
    row.items = lambda: data.items()
    return row


def _mappings_all(rows):
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    return result


def _mappings_first(row):
    result = MagicMock()
    result.mappings.return_value.first.return_value = row
    return result


# ---------------------------------------------------------------------------
# GET /tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tools_returns_catalog(client, mock_session):
    """GET /tools returns all tools from tool_config."""
    mock_session.execute.return_value = _mappings_all(
        [
            _tool_row("uuid-generator", "UUID generator", "Crypto", True),
            _tool_row(
                "base64-string-converter", "Base64 string encoder/decoder", "Converter", False
            ),
        ]
    )

    resp = await client.get("/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    tool = data[0]
    assert "tool_id" in tool
    assert "label" in tool
    assert "category" in tool
    assert "enabled" in tool


@pytest.mark.asyncio
async def test_list_tools_enabled_only(client, mock_session):
    """GET /tools?enabled_only=true returns only enabled tools."""
    mock_session.execute.return_value = _mappings_all(
        [
            _tool_row("uuid-generator", "UUID generator", "Crypto", True),
        ]
    )

    resp = await client.get("/tools?enabled_only=true")
    assert resp.status_code == 200
    data = resp.json()
    assert all(t["enabled"] for t in data)


# ---------------------------------------------------------------------------
# PATCH /tools/{tool_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_tool_toggle(client, mock_session):
    """PATCH /tools/{id} toggles the enabled flag."""
    mock_session.execute.return_value = _mappings_first(
        _tool_row("uuid-generator", "UUID generator", "Crypto", False)
    )

    resp = await client.patch("/tools/uuid-generator", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    mock_session.execute.return_value = _mappings_first(
        _tool_row("uuid-generator", "UUID generator", "Crypto", True)
    )

    resp = await client.patch("/tools/uuid-generator", json={"enabled": True})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True


@pytest.mark.asyncio
async def test_patch_tool_not_found(client, mock_session):
    """PATCH /tools/{id} returns 404 for unknown tool_id."""
    mock_session.execute.return_value = _mappings_first(None)

    resp = await client.patch("/tools/does-not-exist", json={"enabled": False})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Auth split: GET /tools = require_authenticated_user (any signed-in user),
#             PATCH /tools/{id} = require_admin_auth (admin only).
#
# These tests exercise the real auth path (no bypass): a developer session in
# the (fake) redis under session:{token}. The shared `client` fixture overrides
# auth deps with an admin principal, so here we build a fresh client without
# those overrides to drive the genuine dependencies.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_tools_reachable_by_non_admin_authenticated_user(mock_session):
    """GET /tools resolves for a developer session (non-admin), via
    require_authenticated_user, with no admin role present."""
    import json
    from unittest.mock import AsyncMock

    from app.db import get_session
    from app.main import app
    from httpx import ASGITransport, AsyncClient

    async def override_session():
        yield mock_session

    mock_session.execute.return_value = _mappings_all(
        [
            _tool_row("uuid-generator", "UUID generator", "Crypto", True),
        ]
    )

    # Real auth path: a developer session in redis under session:{token}.
    redis = AsyncMock()
    dev_session = json.dumps(
        {
            "user_id": "u-1",
            "email": "dev@simcorp.com",
            "roles": [{"role": "developer", "node_path": "/"}],
        }
    )

    async def _redis_get(key):
        return dev_session if key == "session:dev-token" else None

    redis.get = _redis_get

    app.dependency_overrides[get_session] = override_session
    app.state.redis = redis
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/tools", headers={"Authorization": "Bearer dev-token"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_patch_tool_rejects_non_admin_session(mock_session):
    """PATCH /tools/{id} requires admin — a developer-only session is 403."""
    import json
    from unittest.mock import AsyncMock

    from app.db import get_session
    from app.main import app
    from httpx import ASGITransport, AsyncClient

    async def override_session():
        yield mock_session

    redis = AsyncMock()
    dev_session = json.dumps(
        {
            "user_id": "u-1",
            "email": "dev@simcorp.com",
            "roles": [{"role": "developer", "node_path": "/"}],
        }
    )

    async def _redis_get(key):
        return dev_session if key == "session:dev-token" else None

    redis.get = _redis_get

    app.dependency_overrides[get_session] = override_session
    app.state.redis = redis
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.patch(
                "/tools/uuid-generator",
                json={"enabled": False},
                headers={"Authorization": "Bearer dev-token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_require_authenticated_user_missing_token_raises_401():
    """No credentials, no session → 401."""
    from unittest.mock import MagicMock

    from app.auth import require_authenticated_user
    from fastapi import HTTPException

    request = MagicMock()
    request.app.state.redis = None
    with pytest.raises(HTTPException) as exc:
        await require_authenticated_user(request, None, None)
    assert exc.value.status_code == 401
