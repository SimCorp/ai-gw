from unittest.mock import AsyncMock, patch

import httpx
import pytest


def _resp(code: int) -> httpx.Response:
    return httpx.Response(code)


def _patch_client(side_effect=None, return_value=None):
    """Patch httpx.AsyncClient in public_status module."""
    p = patch("app.routers.public_status.httpx.AsyncClient")
    cls = p.start()
    instance = AsyncMock()
    instance.__aenter__.return_value = instance
    instance.__aexit__ = AsyncMock(return_value=False)
    if side_effect is not None:
        instance.get.side_effect = side_effect
    else:
        instance.get.return_value = return_value or _resp(200)
    cls.return_value = instance
    return p


@pytest.mark.asyncio
async def test_all_healthy_returns_ok(client):
    p = _patch_client(return_value=_resp(200))
    try:
        resp = await client.get("/status")
    finally:
        p.stop()

    assert resp.status_code == 200
    data = resp.json()
    assert data["overall"] == "ok"
    assert data["tiers"]["0"]["status"] == "ok"
    assert data["tiers"]["1"]["status"] == "ok"
    assert data["tiers"]["2"]["status"] == "ok"
    assert "timestamp" in data
    # Verify structure: each tier has name, description, services list
    for t in ["0", "1", "2"]:
        tier = data["tiers"][t]
        assert "name" in tier
        assert "description" in tier
        assert isinstance(tier["services"], list)
        for svc in tier["services"]:
            assert set(svc.keys()) == {"name", "status"}


@pytest.mark.asyncio
async def test_tier0_down_sets_overall_degraded(client):
    """If any Tier 0 service is unreachable, overall = degraded."""

    async def _se(url, **kwargs):
        if "auth" in url:
            raise httpx.ConnectError("refused")
        return _resp(200)

    p = _patch_client(side_effect=_se)
    try:
        resp = await client.get("/status")
    finally:
        p.stop()

    data = resp.json()
    assert data["overall"] == "degraded"
    assert data["tiers"]["0"]["status"] == "degraded"
    auth_svc = next(s for s in data["tiers"]["0"]["services"] if s["name"] == "auth")
    assert auth_svc["status"] == "unreachable"


@pytest.mark.asyncio
async def test_tier2_down_overall_stays_ok(client):
    """Tier 2 degradation must not affect overall."""

    async def _se(url, **kwargs):
        # graphify is Tier 2
        if "graphify" in url:
            raise httpx.ConnectError("refused")
        return _resp(200)

    p = _patch_client(side_effect=_se)
    try:
        resp = await client.get("/status")
    finally:
        p.stop()

    data = resp.json()
    assert data["overall"] == "ok"
    assert data["tiers"]["2"]["status"] == "degraded"


@pytest.mark.asyncio
async def test_non_2xx_counts_as_degraded(client):
    """A 503 from a service should produce status=degraded, not ok."""
    p = _patch_client(return_value=_resp(503))
    try:
        resp = await client.get("/status")
    finally:
        p.stop()

    data = resp.json()
    # All services return 503, so Tier 0 is degraded → overall degraded
    assert data["overall"] == "degraded"
    for svc in data["tiers"]["0"]["services"]:
        assert svc["status"] == "degraded"


@pytest.mark.asyncio
async def test_no_error_detail_leaked(client):
    """Unreachable services must not expose error messages or internal addresses."""

    async def _se(url, **kwargs):
        raise httpx.ConnectError(f"Connection refused to internal-host:8001 ({url})")

    p = _patch_client(side_effect=_se)
    try:
        resp = await client.get("/status")
    finally:
        p.stop()

    body = resp.text
    assert "Connection refused" not in body
    assert "internal-host" not in body
    assert "error" not in body.lower()
    # Only the three allowed status values
    import json

    data = json.loads(body)
    for tier in data["tiers"].values():
        for svc in tier["services"]:
            assert svc["status"] in {"ok", "degraded", "unreachable"}
            assert set(svc.keys()) == {"name", "status"}
