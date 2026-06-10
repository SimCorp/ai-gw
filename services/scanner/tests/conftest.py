import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

_SERVICE_ROOT = str(Path(__file__).parents[1])
for _k in list(sys.modules.keys()):
    if _k == "app" or _k.startswith("app."):
        del sys.modules[_k]
sys.path.insert(0, _SERVICE_ROOT)


async def _stub_identity(request):
    return {
        "team_id": "aaaaaaaa-0000-0000-0000-000000000001",
        "user_id": "bbbbbbbb-0000-0000-0000-000000000001",
    }


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.incr = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.decr = AsyncMock(return_value=0)
    redis.lpush = AsyncMock(return_value=1)
    return redis


@pytest.fixture
def mock_session():
    session = AsyncMock()
    return session


@pytest.fixture
def client(mock_redis, mock_session):
    # Import inside the fixture so we always get the scanner modules loaded by
    # services/conftest.py's pytest_runtest_setup hook, not stale collection-time captures.
    import app.routers.jobs as _jobs_mod
    from app.db import get_session
    from app.main import app

    _jobs_mod.get_identity = _stub_identity
    app.state.redis = mock_redis

    async def override_session():
        yield mock_session

    app.dependency_overrides = {}
    app.dependency_overrides[get_session] = override_session

    yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    app.dependency_overrides = {}
