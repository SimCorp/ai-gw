from unittest.mock import AsyncMock, patch

import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient


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
    app.state.redis = mock_redis

    async def override_session():
        yield mock_session

    app.dependency_overrides = {}

    from app.db import get_session

    app.dependency_overrides[get_session] = override_session

    with patch(
        "app.routers.jobs.get_identity",
        return_value={
            "team_id": "aaaaaaaa-0000-0000-0000-000000000001",
            "user_id": "bbbbbbbb-0000-0000-0000-000000000001",
        },
    ):
        yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    app.dependency_overrides = {}
