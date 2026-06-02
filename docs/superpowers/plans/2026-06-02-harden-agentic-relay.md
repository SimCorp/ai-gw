# Harden the Agentic Relay Path — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `identity` (:8006) and `agent-relay` (:8007) from zero tests to meaningful behavioral coverage, plus one surgical fix making agent-relay honestly single-instance.

**Architecture:** agent-relay is tested mock-only (httpx `ASGITransport` for HTTP, a fake `AsyncMock` WebSocket injected into module state for the `invoke` round-trip, `AsyncMock` for Redis). identity is tested against a real Postgres via `testcontainers[postgres]` (its `/resolve` ranking and array/ILIKE SQL can't be verified with mocks) with `AsyncMock` for Redis.

**Tech Stack:** pytest, pytest-asyncio (`asyncio_mode=auto`), httpx `ASGITransport`/`AsyncClient`, starlette `TestClient` (WS lifecycle only), `testcontainers[postgres]`, PyJWT + cryptography (for the JWKS verify test).

**Spec:** `docs/superpowers/specs/2026-06-02-harden-agentic-relay-design.md`

---

## File structure

Created by this plan:

```
services/agent-relay/conftest.py            # sys.path shim (service root)
services/agent-relay/tests/__init__.py
services/agent-relay/tests/conftest.py      # client fixture + autouse global-state reset
services/agent-relay/tests/test_relay.py    # all agent-relay tests

services/identity/conftest.py               # sys.path shim (service root)
services/identity/tests/__init__.py
services/identity/tests/conftest.py         # testcontainers pg fixture + client + insert helper
services/identity/tests/test_identity.py    # endpoint tests (real Postgres)
services/identity/tests/test_verify_token.py# _verify_identity_token unit test (mocked JWKS)
```

Modified by this plan:

```
services/agent-relay/pyproject.toml         # add [dev] extras + asyncio_mode
services/agent-relay/app/main.py            # remove /invoke Redis fallback; fix docstring
services/identity/pyproject.toml            # add testcontainers[postgres] to [dev]
CLAUDE.md                                    # add identity + agent-relay to test install list
```

---

## Task 0: Scaffolding for both services

**Files:**
- Modify: `services/agent-relay/pyproject.toml`
- Modify: `services/identity/pyproject.toml`
- Create: `services/agent-relay/conftest.py`
- Create: `services/identity/conftest.py`
- Create: `services/agent-relay/tests/__init__.py`
- Create: `services/identity/tests/__init__.py`

- [ ] **Step 1: Add dev extras + pytest config to agent-relay `pyproject.toml`**

agent-relay currently has NO `[project.optional-dependencies]` and NO pytest config. Append both sections to `services/agent-relay/pyproject.toml`:

```toml
[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "pytest-mock", "httpx>=0.27"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 2: Add testcontainers to identity `pyproject.toml`**

In `services/identity/pyproject.toml`, replace the existing dev line:

```toml
dev = ["pytest>=8", "pytest-asyncio>=0.23", "pytest-mock", "httpx>=0.27"]
```

with:

```toml
dev = ["pytest>=8", "pytest-asyncio>=0.23", "pytest-mock", "httpx>=0.27", "testcontainers[postgres]>=4.8"]
```

(identity already has `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` — leave it.)

- [ ] **Step 3: Create the two service-root conftest sys.path shims**

These mirror `services/auth/conftest.py` exactly. Identical content in both files.

`services/agent-relay/conftest.py`:

```python
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
```

`services/identity/conftest.py`:

```python
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
```

- [ ] **Step 4: Create empty test package markers**

`services/agent-relay/tests/__init__.py`: empty file.
`services/identity/tests/__init__.py`: empty file.

- [ ] **Step 5: Install both services in editable+dev mode**

Run:
```bash
pip install -e "services/identity[dev]" -e "services/agent-relay[dev]"
```
Expected: completes successfully; `testcontainers` and `pytest-asyncio` resolve.

- [ ] **Step 6: Commit**

```bash
git add services/agent-relay/pyproject.toml services/identity/pyproject.toml \
        services/agent-relay/conftest.py services/identity/conftest.py \
        services/agent-relay/tests/__init__.py services/identity/tests/__init__.py
git commit -m "test(relay): scaffold test deps + conftest for identity and agent-relay"
```

---

## Task 1: agent-relay test fixtures + smoke test

**Files:**
- Create: `services/agent-relay/tests/conftest.py`
- Create: `services/agent-relay/tests/test_relay.py`

- [ ] **Step 1: Write the fixtures + a health smoke test**

`services/agent-relay/tests/conftest.py`:

```python
"""Fixtures for agent-relay tests.

agent-relay keeps connection/registration state in module-level globals and a
module-level `_redis`. ASGITransport does not run the lifespan, so `_redis`
stays None unless a test sets it. The autouse fixture below resets ALL module
state between tests so they cannot leak into each other.
"""
from unittest.mock import AsyncMock

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
```

`services/agent-relay/tests/test_relay.py`:

```python
"""Behavioral tests for the agent-relay service."""
import json
from unittest.mock import AsyncMock

import pytest


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 2: Run the smoke test**

Run: `pytest services/agent-relay/tests/test_relay.py -v`
Expected: `test_health` PASSES.

- [ ] **Step 3: Commit**

```bash
git add services/agent-relay/tests/conftest.py services/agent-relay/tests/test_relay.py
git commit -m "test(agent-relay): fixtures + health smoke test"
```

---

## Task 2: agent-relay `/invoke` round-trip (fake-WS) — the load-bearing test

This is implemented FIRST among the real tests to validate the fake-WS pattern before building the rest of the suite. `invoke` sets `_pending[invocation_id] = fut` *before* `await ws.send_text(...)`, so the fake WS's `send_text` side effect can resolve that future synchronously — no concurrent task or real WebSocket client needed.

**Files:**
- Modify: `services/agent-relay/tests/test_relay.py`

- [ ] **Step 1: Write the failing test**

Append to `services/agent-relay/tests/test_relay.py`:

```python
async def test_invoke_round_trip(client):
    from app import main

    token = "tok-roundtrip"

    async def fake_send(raw):
        # invoke() has already registered _pending[invocation_id] by now.
        msg = json.loads(raw)
        inv_id = msg["invocation_id"]
        main._pending[inv_id].set_result(
            {"invocation_id": inv_id, "outputs": {"answer": 42}, "exit_code": 0}
        )

    ws = AsyncMock()
    ws.send_text = AsyncMock(side_effect=fake_send)
    main._connections[token] = ws
    main._slug_to_token["agent-x"] = token

    resp = await client.post("/invoke/agent-x", json={"inputs": {"q": "hi"}, "env": {}})

    assert resp.status_code == 200
    assert resp.json() == {"outputs": {"answer": 42}, "exit_code": 0}
    # The payload sent to the agent carried a generated invocation_id + inputs.
    sent = json.loads(ws.send_text.call_args[0][0])
    assert sent["inputs"] == {"q": "hi"}
    assert "invocation_id" in sent
```

- [ ] **Step 2: Run it**

Run: `pytest services/agent-relay/tests/test_relay.py::test_invoke_round_trip -v`
Expected: PASS. (No production change needed — this characterizes existing behavior and proves the fake-WS pattern works. If it fails, STOP and fix the pattern before continuing.)

- [ ] **Step 3: Commit**

```bash
git add services/agent-relay/tests/test_relay.py
git commit -m "test(agent-relay): invoke<->WS round-trip via fake WebSocket"
```

---

## Task 3: agent-relay `/invoke` error paths

**Files:**
- Modify: `services/agent-relay/tests/test_relay.py`

- [ ] **Step 1: Write the tests**

Append to `services/agent-relay/tests/test_relay.py`:

```python
async def test_invoke_not_connected_returns_503(client):
    resp = await client.post("/invoke/nobody", json={"inputs": {}, "env": {}})
    assert resp.status_code == 503
    assert "not connected" in resp.json()["detail"]


async def test_invoke_timeout_returns_504(client, monkeypatch):
    from app import main

    token = "tok-timeout"
    ws = AsyncMock()
    ws.send_text = AsyncMock()  # never resolves the pending future
    main._connections[token] = ws
    main._slug_to_token["slow-agent"] = token

    # Shrink the hard-coded 300s wait so the test is fast. invoke() reads the
    # literal 300.0; patch asyncio.wait_for to use a tiny timeout instead.
    real_wait_for = main.asyncio.wait_for

    async def fast_wait_for(awaitable, timeout):
        return await real_wait_for(awaitable, timeout=0.05)

    monkeypatch.setattr(main.asyncio, "wait_for", fast_wait_for)

    resp = await client.post("/invoke/slow-agent", json={"inputs": {}, "env": {}})
    assert resp.status_code == 504
    assert "timed out" in resp.json()["detail"]
    # The pending future must be cleaned up after timeout.
    assert main._pending == {}


async def test_invoke_requires_relay_secret_when_configured(client, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "_settings", config.Settings(relay_secret="s3cret"))

    # Missing header → 401, even before connection lookup.
    resp = await client.post("/invoke/anything", json={"inputs": {}, "env": {}})
    assert resp.status_code == 401
```

- [ ] **Step 2: Run them**

Run: `pytest services/agent-relay/tests/test_relay.py -k invoke -v`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add services/agent-relay/tests/test_relay.py
git commit -m "test(agent-relay): invoke 503/504/auth error paths"
```

---

## Task 4: agent-relay `/register` and `/agents`

**Files:**
- Modify: `services/agent-relay/tests/test_relay.py`

- [ ] **Step 1: Write the tests**

Append to `services/agent-relay/tests/test_relay.py`:

```python
async def test_register_returns_token_and_populates_state(client):
    from app import main

    main._redis = AsyncMock()  # capture the Redis write

    resp = await client.post(
        "/register", json={"slug": "agent-a", "name": "Agent A", "capabilities": ["x"]}
    )
    assert resp.status_code == 200
    body = resp.json()
    token = body["relay_token"]
    assert body["slug"] == "agent-a"
    assert main._registered_agents[token]["slug"] == "agent-a"
    assert main._slug_to_token["agent-a"] == token
    main._redis.set.assert_awaited_once()
    key, value = main._redis.set.call_args[0]
    assert key == "relay:agent:agent-a:token"
    assert value == token


async def test_register_enforces_relay_secret_when_configured(client, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "_settings", config.Settings(relay_secret="s3cret"))

    bad = await client.post("/register", json={"slug": "a", "name": "A"})
    assert bad.status_code == 401

    ok = await client.post(
        "/register",
        json={"slug": "a", "name": "A"},
        headers={"X-Relay-Secret": "s3cret"},
    )
    assert ok.status_code == 200


async def test_list_agents_only_returns_connected(client):
    from app import main

    # One registered+connected, one registered but not connected.
    main._registered_agents["t1"] = {
        "slug": "online-agent",
        "name": "Online",
        "capabilities": [],
        "connected_at": "2026-06-02T00:00:00+00:00",
    }
    main._connections["t1"] = AsyncMock()
    main._registered_agents["t2"] = {
        "slug": "offline-agent",
        "name": "Offline",
        "capabilities": [],
    }

    resp = await client.get("/agents")
    assert resp.status_code == 200
    agents = resp.json()
    slugs = {a["slug"] for a in agents}
    assert slugs == {"online-agent"}
    # relay_token must never be exposed.
    assert all("relay_token" not in a for a in agents)
```

- [ ] **Step 2: Run them**

Run: `pytest services/agent-relay/tests/test_relay.py -k "register or list_agents" -v`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add services/agent-relay/tests/test_relay.py
git commit -m "test(agent-relay): register + list_agents"
```

---

## Task 5: agent-relay WebSocket lifecycle

Uses starlette's `TestClient` (sync) for the connection lifecycle, because these cases are about accept/close/cleanup, not the async blocking invoke. `TestClient` is constructed directly from the app.

**Files:**
- Modify: `services/agent-relay/tests/test_relay.py`

- [ ] **Step 1: Write the tests**

Append to `services/agent-relay/tests/test_relay.py`:

```python
def test_ws_unknown_token_is_rejected():
    from starlette.testclient import TestClient

    from app.main import app

    with TestClient(app) as tc:
        with pytest.raises(Exception):
            # Server closes with code 4004 before accepting; the context
            # manager surfaces the rejection as an exception on enter.
            with tc.websocket_connect("/connect/does-not-exist"):
                pass


def test_ws_connect_then_disconnect_cleans_up_state():
    from starlette.testclient import TestClient

    from app import main
    from app.main import app

    token = "tok-ws"
    main._registered_agents[token] = {
        "slug": "ws-agent",
        "name": "WS",
        "capabilities": [],
    }
    main._slug_to_token["ws-agent"] = token

    with TestClient(app) as tc:
        with tc.websocket_connect(f"/connect/{token}"):
            # While connected, the agent shows up in /agents.
            listed = tc.get("/agents").json()
            assert any(a["slug"] == "ws-agent" for a in listed)
        # After the WS context exits (disconnect), state is cleaned up.
        assert token not in main._connections
        assert main._slug_to_token.get("ws-agent") is None
```

Note: these two tests are synchronous `def` (not `async def`) — `TestClient` runs its own loop. `asyncio_mode=auto` ignores plain sync tests, which is correct here.

- [ ] **Step 2: Run them**

Run: `pytest services/agent-relay/tests/test_relay.py -k ws -v`
Expected: both PASS.

- [ ] **Step 3: Commit**

```bash
git add services/agent-relay/tests/test_relay.py
git commit -m "test(agent-relay): WebSocket connect/disconnect lifecycle"
```

---

## Task 6: agent-relay surgical fix — honestly single-instance

The `/invoke` Redis fallback (lines ~237–243 of `services/agent-relay/app/main.py`) suggests cross-instance routing that does not work: even if Redis resolves the token, the next line checks `relay_token not in _connections`, and `_connections` is per-process. We remove the fallback and make the docstring honest. We drive the removal with a test asserting `/invoke` performs no Redis lookup.

**Files:**
- Modify: `services/agent-relay/tests/test_relay.py`
- Modify: `services/agent-relay/app/main.py`

- [ ] **Step 1: Write the failing test**

Append to `services/agent-relay/tests/test_relay.py`:

```python
async def test_invoke_does_not_consult_redis(client):
    """invoke() is single-instance: an unknown slug 503s without a Redis lookup."""
    from app import main

    main._redis = AsyncMock()
    main._redis.get = AsyncMock(return_value="some-token-from-another-instance")

    resp = await client.post("/invoke/elsewhere", json={"inputs": {}, "env": {}})

    assert resp.status_code == 503
    main._redis.get.assert_not_called()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest services/agent-relay/tests/test_relay.py::test_invoke_does_not_consult_redis -v`
Expected: FAIL — current code calls `_redis.get` in the fallback (`assert_not_called` fails), or returns 503 only after the lookup.

- [ ] **Step 3: Remove the Redis fallback in `/invoke`**

In `services/agent-relay/app/main.py`, inside `invoke()`, delete these lines:

```python
    # Fallback: look up from Redis (another relay instance may have registered)
    if relay_token is None and _redis:
        try:
            relay_token = await _redis.get(f"relay:agent:{agent_slug}:token")
        except Exception as exc:
            _log.warning("redis lookup failed for slug=%s: %s", agent_slug, exc)

```

So the lookup-and-guard becomes:

```python
    _check_relay_secret(request)
    relay_token = _slug_to_token.get(agent_slug)

    if relay_token is None or relay_token not in _connections:
        raise HTTPException(status_code=503, detail=f"agent '{agent_slug}' not connected")
```

- [ ] **Step 4: Update the module docstring to state single-instance**

In the same file, replace the docstring lines describing multi-instance coordination. Change:

```
  3. Relay stores relay_token → websocket mapping in memory, plus slug in Redis
     for multi-instance coordination: relay:agent:{slug}:token
```

to:

```
  3. Relay stores relay_token → websocket mapping in memory, plus slug in Redis
     (relay:agent:{slug}:token) which the identity service reads to gate
     heartbeats. NOTE: this service is single-instance — invocations are routed
     only via in-process connection state; the Redis key is not used to route
     /invoke across instances.
```

- [ ] **Step 5: Run the new test + the full invoke set**

Run: `pytest services/agent-relay/tests/test_relay.py -k invoke -v`
Expected: all PASS, including `test_invoke_does_not_consult_redis` and the earlier round-trip/503/504/auth tests.

- [ ] **Step 6: Commit**

```bash
git add services/agent-relay/app/main.py services/agent-relay/tests/test_relay.py
git commit -m "fix(agent-relay): drop misleading /invoke Redis fallback; document single-instance"
```

---

## Task 7: Full agent-relay run

**Files:** none (verification only)

- [ ] **Step 1: Run the whole agent-relay suite**

Run: `pytest services/agent-relay -v`
Expected: every test PASSES, no warnings about un-awaited coroutines.

- [ ] **Step 2: Lint**

Run: `ruff check services/agent-relay && ruff format --check services/agent-relay`
Expected: clean (run `ruff format services/agent-relay` and re-commit if formatting changes).

---

## Task 8: identity test fixtures (testcontainers Postgres)

**Files:**
- Create: `services/identity/tests/conftest.py`

- [ ] **Step 1: Write the fixtures**

`services/identity/tests/conftest.py`:

```python
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

    async def _insert(slug, name=None, category=None, capabilities=None,
                      endpoint="", managed=False, token_verified=False):
        async with client.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_identities
                    (slug, name, category, capabilities, endpoint, managed, token_verified)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                slug, name or slug, category, capabilities or [],
                endpoint, managed, token_verified,
            )

    return _insert
```

- [ ] **Step 2: Write a smoke test**

Create `services/identity/tests/test_identity.py`:

```python
"""Behavioral tests for the identity service (real Postgres via testcontainers)."""


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 3: Run the smoke test**

Run: `pytest services/identity/tests/test_identity.py::test_health -v`
Expected: PASS. (First run pulls the `postgres:16-alpine` image — may take ~30s. Docker must be running.)

- [ ] **Step 4: Commit**

```bash
git add services/identity/tests/conftest.py services/identity/tests/test_identity.py
git commit -m "test(identity): testcontainers Postgres fixtures + health smoke test"
```

---

## Task 9: identity `/resolve` ranking + dedup — the load-bearing SQL test

**Files:**
- Modify: `services/identity/tests/test_identity.py`

- [ ] **Step 1: Write the test**

Append to `services/identity/tests/test_identity.py`:

```python
async def test_resolve_ranks_exact_then_capability_then_partial_and_dedups(client, insert_agent):
    # "search" is an exact slug, a capability of another agent, and a partial
    # match of a third — verifies ordering and that no slug appears twice.
    await insert_agent("search", name="Search Bot")                 # exact slug
    await insert_agent("indexer", capabilities=["search"])           # capability tag
    await insert_agent("search-helper", name="Helper")               # partial ILIKE
    await insert_agent("unrelated", name="Nothing")                  # must not appear

    resp = await client.get("/resolve/search")
    assert resp.status_code == 200
    slugs = [a["slug"] for a in resp.json()]

    # Exact first, then capability, then partial. No duplicates, no 'unrelated'.
    assert slugs == ["search", "indexer", "search-helper"]


async def test_resolve_returns_empty_list_for_no_match(client):
    resp = await client.get("/resolve/ghost")
    assert resp.status_code == 200
    assert resp.json() == []
```

- [ ] **Step 2: Run it**

Run: `pytest services/identity/tests/test_identity.py -k resolve -v`
Expected: both PASS. (If ordering fails, that's a real finding about the SQL — STOP and report, do not silently rewrite the query.)

- [ ] **Step 3: Commit**

```bash
git add services/identity/tests/test_identity.py
git commit -m "test(identity): /resolve ranking + dedup against real Postgres"
```

---

## Task 10: identity `/agents` filters

**Files:**
- Modify: `services/identity/tests/test_identity.py`

- [ ] **Step 1: Write the test**

Append to `services/identity/tests/test_identity.py`:

```python
import uuid


async def test_list_agents_filters(client, insert_agent):
    team_a = uuid.uuid4()
    await insert_agent("a1", category="research", capabilities=["web"], managed=True)
    await insert_agent("a2", category="ops", capabilities=["web", "shell"], managed=False)
    await insert_agent("a3", category="research", capabilities=["shell"], managed=True)

    # Seed one with a team_id via direct SQL (insert_agent has no team param).
    async with client.pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO agent_identities (slug, name, capabilities, team_id) "
            "VALUES ($1, $1, $2, $3)",
            "a4", [], team_a,
        )

    # capability filter (ANY)
    by_cap = await client.get("/agents", params={"capability": "shell"})
    assert {a["slug"] for a in by_cap.json()} == {"a2", "a3"}

    # category filter
    by_cat = await client.get("/agents", params={"category": "research"})
    assert {a["slug"] for a in by_cat.json()} == {"a1", "a3"}

    # managed filter
    by_managed = await client.get("/agents", params={"managed": "true"})
    assert {a["slug"] for a in by_managed.json()} == {"a1", "a3"}

    # team_id filter
    by_team = await client.get("/agents", params={"team_id": str(team_a)})
    assert {a["slug"] for a in by_team.json()} == {"a4"}

    # no filter → all four
    all_agents = await client.get("/agents")
    assert {a["slug"] for a in all_agents.json()} == {"a1", "a2", "a3", "a4"}
```

- [ ] **Step 2: Run it**

Run: `pytest services/identity/tests/test_identity.py::test_list_agents_filters -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add services/identity/tests/test_identity.py
git commit -m "test(identity): /agents capability/category/managed/team filters"
```

---

## Task 11: identity get/endpoint/identity-summary + online flag

**Files:**
- Modify: `services/identity/tests/test_identity.py`

- [ ] **Step 1: Write the test**

Append to `services/identity/tests/test_identity.py`:

```python
from unittest.mock import AsyncMock


async def test_get_agent_404_and_found(client, insert_agent):
    missing = await client.get("/agents/nope")
    assert missing.status_code == 404

    await insert_agent("found", name="Found", capabilities=["x"])
    ok = await client.get("/agents/found")
    assert ok.status_code == 200
    body = ok.json()
    assert body["slug"] == "found"
    assert body["online"] is False  # redis.exists mocked to 0


async def test_get_agent_online_flag_reflects_redis(client, insert_agent):
    await insert_agent("live", name="Live")
    client.redis.exists = AsyncMock(return_value=1)
    resp = await client.get("/agents/live")
    assert resp.json()["online"] is True


async def test_endpoint_lookup(client, insert_agent):
    await insert_agent("worker", endpoint="http://workflow-worker:8000/invoke/worker", managed=True)
    resp = await client.get("/agents/worker/endpoint")
    assert resp.status_code == 200
    body = resp.json()
    assert body["endpoint"] == "http://workflow-worker:8000/invoke/worker"
    assert body["online"] is False
    assert "agent_id" in body

    assert (await client.get("/agents/ghost/endpoint")).status_code == 404


async def test_identity_summary(client, insert_agent):
    await insert_agent("verified-agent", capabilities=["a", "b"], token_verified=True)
    resp = await client.get("/agents/verified-agent/identity")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "slug": "verified-agent",
        "token_verified": True,
        "capabilities": ["a", "b"],
        "online": False,
    }

    assert (await client.get("/agents/ghost/identity")).status_code == 404
```

- [ ] **Step 2: Run it**

Run: `pytest services/identity/tests/test_identity.py -k "get_agent or endpoint or identity_summary" -v`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add services/identity/tests/test_identity.py
git commit -m "test(identity): get/endpoint/identity-summary + online flag"
```

---

## Task 12: identity `/heartbeat`

**Files:**
- Modify: `services/identity/tests/test_identity.py`

- [ ] **Step 1: Write the test**

Append to `services/identity/tests/test_identity.py`:

```python
async def test_heartbeat_404_for_unknown_slug(client):
    resp = await client.post("/agents/ghost/heartbeat")
    assert resp.status_code == 404


async def test_heartbeat_sets_redis_key_and_updates_last_seen(client, insert_agent):
    await insert_agent("beater", name="Beater")
    resp = await client.post("/agents/beater/heartbeat")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "ttl": 60}
    client.redis.setex.assert_awaited_once()
    key, ttl, val = client.redis.setex.call_args[0]
    assert key == "identity:online:beater"
    assert ttl == 60


async def test_heartbeat_fails_open_when_no_stored_relay_token(client, insert_agent):
    await insert_agent("open-agent")
    client.redis.get = AsyncMock(return_value=None)  # no relay token registered
    resp = await client.post("/agents/open-agent/heartbeat")
    assert resp.status_code == 200


async def test_heartbeat_rejects_wrong_relay_token(client, insert_agent):
    await insert_agent("guarded")
    client.redis.get = AsyncMock(return_value="correct-token")
    bad = await client.post(
        "/agents/guarded/heartbeat", headers={"X-Relay-Token": "wrong"}
    )
    assert bad.status_code == 401
    good = await client.post(
        "/agents/guarded/heartbeat", headers={"X-Relay-Token": "correct-token"}
    )
    assert good.status_code == 200
```

Note: `from unittest.mock import AsyncMock` was already imported in Task 11; do not import it twice.

- [ ] **Step 2: Run it**

Run: `pytest services/identity/tests/test_identity.py -k heartbeat -v`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add services/identity/tests/test_identity.py
git commit -m "test(identity): heartbeat presence + relay-token gating"
```

---

## Task 13: identity `/register`, `/deregister`, `/capabilities`

**Files:**
- Modify: `services/identity/tests/test_identity.py`

- [ ] **Step 1: Write the test**

Append to `services/identity/tests/test_identity.py`:

```python
async def test_register_inserts_then_upserts(client):
    first = await client.post(
        "/agents/register",
        json={"slug": "reg", "name": "Reg One", "capabilities": ["a"]},
    )
    assert first.status_code == 201
    assert first.json()["name"] == "Reg One"
    assert first.json()["token_verified"] is False

    # Same slug → ON CONFLICT updates in place (no duplicate, new name).
    second = await client.post(
        "/agents/register",
        json={"slug": "reg", "name": "Reg Two", "capabilities": ["a", "b"]},
    )
    assert second.status_code == 201
    assert second.json()["name"] == "Reg Two"
    assert second.json()["capabilities"] == ["a", "b"]

    listed = await client.get("/agents")
    assert sum(1 for a in listed.json() if a["slug"] == "reg") == 1


async def test_register_verifies_identity_token(client, monkeypatch):
    from app import main

    async def fake_verify(token, admin_url):
        return token == "good-token"

    monkeypatch.setattr(main, "_verify_identity_token", fake_verify)

    verified = await client.post(
        "/agents/register",
        json={"slug": "v", "name": "V", "identity_token": "good-token"},
    )
    assert verified.json()["token_verified"] is True

    unverified = await client.post(
        "/agents/register",
        json={"slug": "u", "name": "U", "identity_token": "bad-token"},
    )
    assert unverified.json()["token_verified"] is False


async def test_register_enforces_service_token_when_configured(client, monkeypatch):
    from app import main

    monkeypatch.setattr(main.settings, "identity_service_token", "svc-secret")

    bad = await client.post("/agents/register", json={"slug": "s", "name": "S"})
    assert bad.status_code == 401

    ok = await client.post(
        "/agents/register",
        json={"slug": "s", "name": "S"},
        headers={"X-Service-Token": "svc-secret"},
    )
    assert ok.status_code == 201


async def test_deregister(client, insert_agent, monkeypatch):
    await insert_agent("byebye")
    resp = await client.delete("/agents/byebye")
    assert resp.status_code == 204
    client.redis.delete.assert_awaited_with("identity:online:byebye")
    assert (await client.get("/agents/byebye")).status_code == 404

    # 404 when already gone.
    assert (await client.delete("/agents/byebye")).status_code == 404


async def test_deregister_enforces_service_token_when_configured(client, insert_agent, monkeypatch):
    from app import main

    await insert_agent("protected")
    monkeypatch.setattr(main.settings, "identity_service_token", "svc-secret")
    assert (await client.delete("/agents/protected")).status_code == 401


async def test_capabilities_distinct_sorted(client, insert_agent):
    await insert_agent("c1", capabilities=["web", "shell"])
    await insert_agent("c2", capabilities=["web", "vision"])
    resp = await client.get("/capabilities")
    assert resp.status_code == 200
    assert resp.json() == {"capabilities": ["shell", "vision", "web"]}
```

- [ ] **Step 2: Run it**

Run: `pytest services/identity/tests/test_identity.py -k "register or deregister or capabilities" -v`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add services/identity/tests/test_identity.py
git commit -m "test(identity): register/deregister/capabilities + service-token auth"
```

---

## Task 14: identity `_verify_identity_token` unit test (mocked JWKS)

This is a pure async function. We generate a real RSA keypair, publish its public JWK through a fake httpx client, and sign a real RS256 token — exercising the actual signature-verification path.

**Files:**
- Create: `services/identity/tests/test_verify_token.py`

- [ ] **Step 1: Write the test**

Create `services/identity/tests/test_verify_token.py`:

```python
"""Unit tests for identity._verify_identity_token (mocked JWKS endpoint)."""
import base64
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _b64url_uint(n: int) -> str:
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _make_keypair():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nums = priv.public_key().public_numbers()
    jwk = {"kty": "RSA", "n": _b64url_uint(nums.n), "e": _b64url_uint(nums.e)}
    pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return pem, jwk


def _sign(pem: bytes) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": "agent-1", "iss": "ai-gw", "iat": now, "exp": now + 300},
        pem,
        algorithm="RS256",
    )


class _FakeResp:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def json(self):
        return self._data


class _FakeClient:
    def __init__(self, data, status=200):
        self._data = data
        self._status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        return _FakeResp(self._data, self._status)


def _patch_httpx(monkeypatch, data, status=200):
    from app import main

    monkeypatch.setattr(
        main.httpx, "AsyncClient", lambda *a, **k: _FakeClient(data, status)
    )


async def test_verify_valid_token_returns_true(monkeypatch):
    from app.main import _verify_identity_token

    pem, jwk = _make_keypair()
    token = _sign(pem)
    _patch_httpx(monkeypatch, {"keys": [jwk]})

    assert await _verify_identity_token(token, "http://admin") is True


async def test_verify_wrong_key_returns_false(monkeypatch):
    from app.main import _verify_identity_token

    signing_pem, _ = _make_keypair()
    _, other_jwk = _make_keypair()  # JWKS publishes a DIFFERENT key
    token = _sign(signing_pem)
    _patch_httpx(monkeypatch, {"keys": [other_jwk]})

    assert await _verify_identity_token(token, "http://admin") is False


async def test_verify_jwks_fetch_failure_returns_false(monkeypatch):
    from app.main import _verify_identity_token

    pem, _ = _make_keypair()
    token = _sign(pem)
    _patch_httpx(monkeypatch, {}, status=500)

    assert await _verify_identity_token(token, "http://admin") is False


async def test_verify_no_keys_returns_false(monkeypatch):
    from app.main import _verify_identity_token

    pem, _ = _make_keypair()
    token = _sign(pem)
    _patch_httpx(monkeypatch, {"keys": []})

    assert await _verify_identity_token(token, "http://admin") is False
```

- [ ] **Step 2: Run it**

Run: `pytest services/identity/tests/test_verify_token.py -v`
Expected: all four PASS. (No Postgres/Docker needed for this file.)

- [ ] **Step 3: Commit**

```bash
git add services/identity/tests/test_verify_token.py
git commit -m "test(identity): _verify_identity_token RS256/JWKS paths"
```

---

## Task 15: Full identity run + lint

**Files:** none (verification only)

- [ ] **Step 1: Run the whole identity suite**

Run: `pytest services/identity -v`
Expected: every test PASSES.

- [ ] **Step 2: Lint**

Run: `ruff check services/identity && ruff format --check services/identity`
Expected: clean (run `ruff format services/identity` and re-commit if needed).

---

## Task 16: Update docs + final full run

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add the two services to the test-install list in CLAUDE.md**

In the "Running tests (no Docker needed)" section, change the `pip install` block from:

```bash
pip install \
  -e "services/auth[dev]" \
  -e "services/cache[dev]" \
  -e "services/observability[dev]" \
  -e "services/admin[dev]"
```

to:

```bash
pip install \
  -e "services/auth[dev]" \
  -e "services/cache[dev]" \
  -e "services/observability[dev]" \
  -e "services/admin[dev]" \
  -e "services/identity[dev]" \
  -e "services/agent-relay[dev]"
```

Then add this note immediately after that code block:

```markdown
> Note: most service tests run without Docker. The `identity` suite is the
> exception — it uses `testcontainers[postgres]` and needs a running Docker
> daemon (matching the `admin` service's approach).
```

- [ ] **Step 2: Run both services together**

Run: `pytest services/identity services/agent-relay -v`
Expected: every test PASSES (Docker running for the identity suite).

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add identity + agent-relay to test install list"
```

- [ ] **Step 4: Push the branch**

```bash
git push
```

---

## Verification checklist (run before declaring done)

- [ ] `pytest services/agent-relay -v` — all green.
- [ ] `pytest services/identity -v` — all green (Docker running).
- [ ] `ruff check services/identity services/agent-relay` — clean.
- [ ] agent-relay `/invoke` no longer references `_redis` (grep the function).
- [ ] agent-relay module docstring states single-instance.
- [ ] CLAUDE.md lists both new services + the Docker note.
- [ ] Every endpoint on both services is exercised by at least one test.
