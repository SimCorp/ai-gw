"""Fixtures for agent-relay tests.

agent-relay keeps connection/registration state in module-level globals and a
module-level `_redis`. ASGITransport does not run the lifespan, so `_redis`
stays None unless a test sets it. The autouse fixture below resets ALL module
state between tests so they cannot leak into each other.
"""


import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def reset_state():
    """Clear agent-relay's module globals and cached settings before each test."""
    from app import config, main

    main._registered_agents.clear()
    main._connections.clear()
    main._pending.clear()
    main._slug_to_token.clear()
    main._redis = None
    config._settings = None
    yield
    main._registered_agents.clear()
    main._connections.clear()
    main._pending.clear()
    main._slug_to_token.clear()
    main._redis = None
    config._settings = None


@pytest_asyncio.fixture
async def client():
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
