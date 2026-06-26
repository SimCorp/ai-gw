"""Smoke test for the /ready readiness probe."""

from unittest.mock import AsyncMock, MagicMock

import app.main as _main_mod
import pytest


@pytest.fixture
async def ready_client(client):
    """Override _pool.acquire so it works as an async context manager."""
    conn = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    _main_mod._pool.acquire = MagicMock(return_value=ctx)
    yield client


async def test_ready(ready_client):
    resp = await ready_client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}
