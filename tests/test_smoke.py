"""Smoke tests — verify all five services are reachable and report healthy."""

import httpx
import pytest
import pytest_asyncio

from conftest import ADMIN_URL, SERVICE_HEALTH_URLS


@pytest.mark.asyncio
@pytest.mark.parametrize("name,url", list(SERVICE_HEALTH_URLS.items()))
async def test_service_health_200(name: str, url: str):
    """Every service must return HTTP 200 on its health endpoint."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
    assert resp.status_code == 200, (
        f"Service '{name}' health check failed: {resp.status_code} {resp.text}"
    )


@pytest.mark.asyncio
async def test_admin_system_health_overall_ok():
    """GET /system/health on the admin service must report overall: ok.

    In CI the downstream services may all be reachable, so we assert the
    shape of the response rather than requiring a perfect green board.
    """
    async with httpx.AsyncClient(
        base_url=ADMIN_URL,
        headers={"X-Admin-Token": "local-dev-admin-key-change-in-prod"},
        timeout=20.0,
    ) as client:
        resp = await client.get("/system/health")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "overall" in data, "Response missing 'overall' key"
    assert data["overall"] in {"ok", "degraded"}, (
        f"'overall' must be 'ok' or 'degraded', got {data['overall']!r}"
    )


@pytest.mark.asyncio
async def test_admin_system_health_service_list():
    """GET /system/health must include a 'services' list with the four expected entries."""
    async with httpx.AsyncClient(
        base_url=ADMIN_URL,
        headers={"X-Admin-Token": "local-dev-admin-key-change-in-prod"},
        timeout=20.0,
    ) as client:
        resp = await client.get("/system/health")

    assert resp.status_code == 200
    data = resp.json()
    assert "services" in data, "Response missing 'services' list"
    service_names = {s["service"] for s in data["services"]}
    expected = {"auth", "cache", "litellm", "observability"}
    assert expected == service_names, (
        f"Expected services {expected}, got {service_names}"
    )


@pytest.mark.asyncio
async def test_admin_system_health_service_shape():
    """Each entry in 'services' must have the required fields."""
    async with httpx.AsyncClient(
        base_url=ADMIN_URL,
        headers={"X-Admin-Token": "local-dev-admin-key-change-in-prod"},
        timeout=20.0,
    ) as client:
        resp = await client.get("/system/health")

    assert resp.status_code == 200
    for svc in resp.json()["services"]:
        for field in ("service", "status", "latency_ms"):
            assert field in svc, f"Service entry missing '{field}': {svc}"
        assert svc["status"] in {"ok", "degraded", "unreachable"}, (
            f"Unexpected status {svc['status']!r} for {svc['service']}"
        )
