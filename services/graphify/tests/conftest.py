"""Fixtures for graphify tests.

graphify is raw asyncpg SQL, so these run against a REAL Postgres started via
testcontainers (requires Docker). The DDL is taken from app.db so the schema
always matches production. The graphify CLI subprocess is never invoked — the
build worker and query wrappers are tested with builder/query monkeypatched.
"""

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def pg_url():
    with PostgresContainer("postgres:16-alpine", driver=None) as pg:
        url = pg.get_connection_url()
        url = url.replace("+psycopg2", "").replace("+asyncpg", "")
        yield url


@pytest_asyncio.fixture
async def pool(pg_url):
    from app import db

    pool = await asyncpg.create_pool(pg_url, min_size=1, max_size=4)
    await db.bootstrap_schema(pool)
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE graph_builds, graph_repos CASCADE")
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def client(pool, monkeypatch):
    from app import main

    # Always authorise the caller — auth boundary is exercised separately.
    monkeypatch.setattr(main, "_pool", pool)

    async def _ok(_request):
        return None

    monkeypatch.setattr(main, "resolve_caller", _ok)

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as c:
        c.headers["Authorization"] = "Bearer sk-test"
        c.pool = pool
        yield c
