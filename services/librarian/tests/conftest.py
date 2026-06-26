"""Shared fixtures for librarian tests.

ASGITransport does not run the lifespan, so the module-level DB pool and Redis
client are never initialised. Tests that exercise tool handlers set them to
mocks directly. The auth boundary (resolve_caller) is patched per-test.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

_SERVICE_ROOT = str(Path(__file__).parents[1])
for _k in list(sys.modules.keys()):
    if _k == "app" or _k.startswith("app."):
        del sys.modules[_k]
sys.path.insert(0, _SERVICE_ROOT)

# Module-level import so test files that do `import app.main as main` at
# collection time bind the same object that this fixture uses at runtime.
import app.main as _main_mod  # noqa: E402


@pytest.fixture
async def client():
    # get_pool()/get_redis() raise unless these module globals are set.
    # pool.acquire() is used as `async with pool.acquire() as conn:` in the ingest
    # path; a plain AsyncMock returns a coroutine on call, not an async context manager.
    conn_mock = AsyncMock()
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn_mock)
    acquire_cm.__aexit__ = AsyncMock(return_value=False)
    pool_mock = MagicMock()
    pool_mock.acquire.return_value = acquire_cm
    _main_mod._pool = pool_mock
    _main_mod._redis = AsyncMock()

    async with AsyncClient(transport=ASGITransport(app=_main_mod.app), base_url="http://test") as c:
        yield c
