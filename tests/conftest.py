"""Shared pytest fixtures for the AI Gateway integration test suite.

These fixtures hit real running services (Docker Compose stack).
Base URLs default to localhost for host-side runs; override via environment
variables when running inside the compose network.

    ADMIN_URL   defaults to http://localhost:8005
    GATEWAY_URL defaults to http://localhost:8002
    ADMIN_TOKEN defaults to local-dev-admin-key-change-in-prod
"""

import os
import uuid

import httpx
import pytest
import pytest_asyncio

# ── Base URLs ────────────────────────────────────────────────────────────────

ADMIN_URL = os.environ.get("ADMIN_URL", "http://localhost:8005")
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8002")
AUTH_URL = os.environ.get("AUTH_URL", "http://localhost:8001")
CACHE_URL = os.environ.get("CACHE_URL", "http://localhost:8002")
LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:8003")
OBSERVABILITY_URL = os.environ.get("OBSERVABILITY_URL", "http://localhost:8004")

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "local-dev-admin-key-change-in-prod")
DEV_BYPASS_AUTH = os.environ.get("DEV_BYPASS_AUTH", "false").lower() in ("true", "1", "yes")

# Expose service URL map for smoke tests
SERVICE_HEALTH_URLS: dict[str, str] = {
    "auth": f"{AUTH_URL}/health",
    "cache": f"{CACHE_URL}/health",
    "litellm": f"{LITELLM_URL}/health/liveliness",
    "observability": f"{OBSERVABILITY_URL}/health",
    "admin": f"{ADMIN_URL}/health",
}


# ── Clients ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def admin_client():
    """httpx.AsyncClient pointed at the admin service with admin auth header."""
    async with httpx.AsyncClient(
        base_url=ADMIN_URL,
        headers={"X-Admin-Token": ADMIN_TOKEN},
        follow_redirects=False,
        timeout=30.0,
    ) as client:
        yield client


# ── Team + API key lifecycle ─────────────────────────────────────────────────


@pytest_asyncio.fixture
async def test_team(admin_client: httpx.AsyncClient):
    """Create a throwaway team, yield its ID, delete on teardown.

    A UUID suffix guarantees uniqueness even if a prior run crashed without
    cleaning up.
    """
    uid = uuid.uuid4().hex[:8]
    payload = {"name": f"test-team-{uid}", "slug": f"test-team-{uid}"}
    resp = await admin_client.post("/teams", json=payload)
    assert resp.status_code == 201, f"Failed to create test team: {resp.text}"
    team_id = resp.json()["id"]

    yield team_id

    # Teardown — delete the team (cascades to api_keys, projects)
    await admin_client.delete(f"/teams/{team_id}")


@pytest_asyncio.fixture
async def test_api_key(admin_client: httpx.AsyncClient, test_team: str):
    """Create an API key under test_team, yield the raw sk- secret, revoke on teardown."""
    resp = await admin_client.post(
        f"/teams/{test_team}/keys",
        json={"name": "integration-test-key"},
    )
    assert resp.status_code == 201, f"Failed to create API key: {resp.text}"
    data = resp.json()
    raw_key: str = data["key"]
    key_id: str = data["id"]

    assert raw_key.startswith("sk-"), "API key must start with sk-"

    yield raw_key

    # Teardown — revoke the key
    await admin_client.delete(f"/teams/{test_team}/keys/{key_id}")


@pytest_asyncio.fixture
async def gateway_client(test_api_key: str):
    """httpx.AsyncClient pointed at the gateway, authenticated with the test API key."""
    async with httpx.AsyncClient(
        base_url=GATEWAY_URL,
        headers={"Authorization": f"Bearer {test_api_key}"},
        follow_redirects=False,
        timeout=60.0,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def portal_client():
    """httpx.AsyncClient for portal tests — cookie jar preserved, redirects not followed.

    Passes a unique X-Test-Client-ID header so each test fixture gets its own
    rate-limit bucket (prevents 429s when many tests run from the same IP).
    """
    test_id = uuid.uuid4().hex
    async with httpx.AsyncClient(
        base_url=ADMIN_URL,
        headers={"X-Test-Client-ID": test_id},
        follow_redirects=False,
        timeout=30.0,
    ) as client:
        yield client
