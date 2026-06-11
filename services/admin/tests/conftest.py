"""Shared pytest fixtures for admin service tests.

Run from services/admin/:
    pytest tests/ -v

The app.state.redis must be set manually because ASGITransport does not
trigger the lifespan (which normally creates the Redis connection).

Authentication is NOT bypassed in production code. Tests supply a fake
authenticated principal via FastAPI dependency_overrides (idiomatic test DI),
overriding require_admin_auth / require_authenticated_user / get_current_user.

Required settings are supplied here as test placeholders so the config
singleton (pydantic-settings, no defaults) imports cleanly. This module runs at
collection time, before any test module is imported, so these env vars are in
place before app.config.Settings() is constructed. CORS_ORIGINS is a list field
and pydantic-settings parses it as JSON, so it must be valid JSON.
"""

import os
import uuid

# Must be set before any app import so pydantic-settings picks them up.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://placeholder/placeholder")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-real")
os.environ.setdefault("OIDC_ISSUER", "http://localhost:5556")
os.environ.setdefault("OIDC_CLIENT_ID", "test")
os.environ.setdefault("OIDC_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-test")
os.environ.setdefault("IDENTITY_KEY_SECRET", "test-identity-key-secret")
os.environ.setdefault("AUTH_URL", "http://auth:8001")
os.environ.setdefault("CACHE_URL", "http://cache:8002")
os.environ.setdefault("LITELLM_URL", "http://litellm:8003")
os.environ.setdefault("OBSERVABILITY_URL", "http://observability:8004")
os.environ.setdefault("LEAGUE_URL", "http://league:8010")
os.environ.setdefault("LIBRARIAN_URL", "http://librarian:8008")
os.environ.setdefault("CORS_ORIGINS", '["http://test"]')


from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

# Fake authenticated principal: a platform_admin scoped to root "/", a prefix of
# every node path, so can_access() passes for every permission tier.
FAKE_ADMIN = {
    "user_id": str(uuid.uuid4()),
    "email": "admin@simcorp.com",
    "display_name": "Admin",
    "role": "superadmin",
    "roles": [{"role": "platform_admin", "node_path": "/"}],
}


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
    from app.auth import require_admin_auth, require_authenticated_user
    from app.db import get_session
    from app.main import app
    from app.routers.unified_auth import get_current_user

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_admin_auth] = lambda: FAKE_ADMIN
    app.dependency_overrides[require_authenticated_user] = lambda: FAKE_ADMIN
    app.dependency_overrides[get_current_user] = lambda: FAKE_ADMIN
    app.state.redis = AsyncMock()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Pytest-asyncio configuration (applies to all tests in this package)
# ---------------------------------------------------------------------------


def pytest_configure(config):
    """Register asyncio mode so async tests run without per-test markers."""
    pass
