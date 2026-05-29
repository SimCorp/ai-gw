"""Shared pytest fixtures for admin service tests.

Run from services/admin/:
    pytest tests/ -v

The app.state.redis must be set manually because ASGITransport does not
trigger the lifespan (which normally creates the Redis connection).

Authentication is bypassed by setting DEV_BYPASS_AUTH=true before the
settings singleton is first imported.  The import must happen AFTER os.environ
is patched; since conftest runs before test modules are collected, putting the
patch here is safe.
"""

import os

# Must be set before any app import so pydantic-settings picks it up.
os.environ.setdefault("DEV_BYPASS_AUTH", "true")
os.environ.setdefault("ENVIRONMENT", "development")


from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Session mock
# ---------------------------------------------------------------------------

@pytest.fixture
async def mock_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.get = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# HTTP client wired to the FastAPI app
# ---------------------------------------------------------------------------

@pytest.fixture
async def client(mock_session):
    from app.auth import require_admin_auth
    from app.db import get_session
    from app.main import app

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_admin_auth] = lambda: None
    app.state.redis = AsyncMock()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Pytest-asyncio configuration (applies to all tests in this package)
# ---------------------------------------------------------------------------

def pytest_configure(config):
    """Register asyncio mode so async tests run without per-test markers."""
    pass
