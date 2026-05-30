"""Shared fixtures for librarian tests.

ASGITransport does not run the lifespan, so the module-level DB pool and Redis
client are never initialised. Tests that exercise tool handlers set them to
mocks directly. The auth boundary (resolve_caller) is patched per-test.
"""

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client():
    import app.main as main

    # get_pool()/get_redis() raise unless these module globals are set.
    main._pool = AsyncMock()
    main._redis = AsyncMock()

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as c:
        yield c
