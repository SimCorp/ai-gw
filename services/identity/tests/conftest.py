"""Fixtures for identity tests.

identity is almost entirely raw asyncpg SQL, so these tests run against a REAL
Postgres started via testcontainers (requires Docker). Redis is mocked because
it only stores heartbeat presence flags. The DDL is taken from app.main so the
schema always matches production.
"""

from unittest.mock import AsyncMock

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def pg_url():
    """Start one Postgres for the whole test session; yield an asyncpg URL."""
    with PostgresContainer("postgres:16-alpine", driver=None) as pg:
        url = pg.get_connection_url()
        # Normalise any SQLAlchemy-style driver suffix to a plain asyncpg URL.
        url = url.replace("+psycopg2", "").replace("+asyncpg", "")
        yield url


@pytest_asyncio.fixture
async def client(pg_url):
    from app.main import _ALTER_TOKEN_VERIFIED, _CREATE_TABLE, app

    pool = await asyncpg.create_pool(pg_url, min_size=1, max_size=4)
    async with pool.acquire() as conn:
        await conn.execute(_CREATE_TABLE)
        await conn.execute(_ALTER_TOKEN_VERIFIED)
        await conn.execute("TRUNCATE agent_identities")

    redis = AsyncMock()
    redis.exists = AsyncMock(return_value=0)  # default: offline
    redis.get = AsyncMock(return_value=None)  # default: no stored relay token
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()

    app.state.pool = pool
    app.state.redis = redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.pool = pool  # expose for direct seeding inside tests
        c.redis = redis
        yield c

    await pool.close()


@pytest_asyncio.fixture
async def insert_agent(client):
    """Return an async helper that inserts an agent_identities row directly."""

    async def _insert(
        slug,
        name=None,
        category=None,
        capabilities=None,
        endpoint="",
        managed=False,
        token_verified=False,
    ):
        async with client.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_identities
                    (slug, name, category, capabilities, endpoint, managed, token_verified)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                slug,
                name or slug,
                category,
                capabilities or [],
                endpoint,
                managed,
                token_verified,
            )

    return _insert
