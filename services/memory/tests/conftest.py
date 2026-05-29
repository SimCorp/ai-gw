from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client():
    from app.main import app
    mock_pool = AsyncMock()
    mock_http = AsyncMock()
    app.state.pool = mock_pool
    app.state.http = mock_http
    # Bypass auth — patch resolve_developer on the name bound in main
    import app.main as main_module
    main_module.resolve_developer = AsyncMock(return_value="dev-uuid-test")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
