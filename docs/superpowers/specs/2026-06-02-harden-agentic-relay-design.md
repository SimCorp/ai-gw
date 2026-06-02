# Harden the Agentic Relay Path

**Date:** 2026-06-02
**Status:** Approved — ready for implementation plan
**Scope:** Feature #1 of 4 in the platform-hardening sequence
(1: harden relay → 2: finish half-built features → 3: cost anomaly detection → 4: request-path safety guardrails)

## Summary

`identity` (:8006, 563 LOC) and `agent-relay` (:8007, 303 LOC) are fully
functional but have **zero tests** — 866 LOC the entire agentic invocation path
depends on. This is the highest-risk gap in an otherwise mature platform.

This feature brings both services to meaningful behavioral test coverage and
applies one surgical honesty fix to agent-relay. It is a **test-and-harden**
task, not a new subsystem.

Both services already declare `[dev]` test dependencies (pytest,
pytest-asyncio, pytest-mock, httpx) and have a `pyproject.toml`; they lack only
a `tests/` directory and conftest scaffolding.

## Decisions made during brainstorming

- **agent-relay multi-instance routing → make it honestly single-instance.**
  The docstring claims multi-instance routing via Redis, but `_pending` futures
  and `_connections` live in per-process memory, so an `/invoke` hitting an
  instance that doesn't hold the WebSocket returns 503 even though Redis
  resolves the token. Rather than build a distributed WS bus (a separate, much
  larger feature), we make the service honest about being single-instance.
- **identity testing → testcontainers[postgres].** identity is almost entirely
  raw asyncpg SQL (the `/resolve` ranking + dedup, `ANY(capabilities)`,
  `ILIKE`, `UNNEST capabilities`). Mocks cannot verify that SQL, so we use a
  real Postgres for identity's tests. agent-relay has no SQL and uses
  mocks/fakeredis regardless.

## Component A — agent-relay (mock-based, zero infra)

### Production code change (the only one in this feature)

- Remove the misleading Redis fallback in `/invoke`
  (`services/agent-relay/app/main.py` lines 237–243). The
  `relay:agent:{slug}:token` **write** in `/register` stays — identity's
  heartbeat relay-token check reads that key.
- Update the module docstring to state that agent-relay is **single-instance**.
  (It always was; the docstring overclaimed.)

We deliberately do **not** fix the fail-open auth (`_check_relay_secret`) — it
is a documented dev-mode pattern across the repo. We characterize it with
tests instead.

### Tests

Transport choices:
- httpx `ASGITransport` + `AsyncClient` for HTTP endpoints (the repo's standard
  pattern, used by auth/cache/observability).
- starlette `TestClient.websocket_connect` only for connection-lifecycle cases
  that do not block on a concurrent invoke.
- **Fake-WS injection** for the invoke↔WS round-trip: inject an `AsyncMock`
  WebSocket into `_connections` and resolve the pending future from a
  concurrent task. httpx+ASGITransport does not support WebSockets, and a real
  WS client interleaves badly with a blocking `invoke`.

Test cases:
- **autouse fixture** clearing the four module-level globals
  (`_registered_agents`, `_connections`, `_pending`, `_slug_to_token`) before
  each test — prevents cross-test contamination.
- `register`: returns a token, populates in-memory state, writes the Redis key;
  relay-secret auth (configured → 401 on bad/missing header; empty → fail-open
  allows).
- `list_agents`: returns only currently-connected agents; `relay_token` is
  omitted from the response.
- **`invoke` happy path** (implement FIRST to validate the fake-WS pattern):
  inject `AsyncMock` WS into `_connections`, set `_slug_to_token`, call
  `invoke`, resolve `_pending[invocation_id]` from a concurrent task → assert
  `outputs` and `exit_code`.
- `invoke`: agent not connected → 503; timeout → 504 (monkeypatch the 300s
  timeout to ~0.05s); relay-secret auth enforced.
- WS lifecycle via `TestClient`: unknown relay_token → connection closed with
  code 4004; connect → `list_agents` shows the agent → disconnect → in-memory
  state and Redis key cleaned up.

Redis is mocked (`AsyncMock`) or faked (fakeredis) — no running Redis required.

## Component B — identity (testcontainers Postgres + mocked Redis)

### Production code change

None. We characterize current behavior, including the intentional fail-open
auth (`_check_service_token`, heartbeat relay-token check).

### Tests

Fixture setup:
- Real Postgres via `testcontainers[postgres]`. The fixture runs `_CREATE_TABLE`
  and `_ALTER_TOKEN_VERIFIED`, then injects a real asyncpg pool as
  `app.state.pool`.
- `app.state.redis` is an `AsyncMock` (controls the `online` heartbeat flag);
  no real Redis required.

Test cases:
- **`/resolve` ranking + dedup** (the load-bearing SQL test): exact slug →
  capability tag → partial ILIKE order, with no duplicate slugs across the
  three result sets.
- `list_agents`: each filter exercised — `capability` (via `ANY()`),
  `category`, `team_id`, `managed`.
- `register`: fresh insert and `ON CONFLICT` upsert; service-token auth;
  `identity_token` path with `_verify_identity_token` mocked (verified /
  unverified).
- `get_agent` / `endpoint` / `identity` summary: 404 when missing; `online`
  flag reflects mocked Redis.
- `heartbeat`: 404 when slug missing; sets the Redis heartbeat key; relay-token
  check (fail-open when no stored token, 401 when stored token mismatches).
- `deregister`: service-token auth; 404 when missing; deletes the Redis
  heartbeat key.
- `capabilities`: `UNNEST` returns distinct sorted capabilities.
- `_verify_identity_token`: unit test with mocked JWKS endpoint (httpx mocked)
  — RS256 verify success path plus failure paths (bad signature, JWKS fetch
  failure, no RSA keys).

## Cross-cutting

- Add `services/identity/conftest.py` and `services/agent-relay/conftest.py`
  (sys.path shim matching `services/auth/conftest.py`).
- Add `tests/` and `tests/conftest.py` (fixtures) to each service.
- Add `testcontainers[postgres]>=4.8` to identity's `[dev]` extras (matching the
  admin service). agent-relay's deps are unchanged.
- Update CLAUDE.md "Running tests" to include `identity` and `agent-relay` in
  the `pip install -e` list.

## Success criteria

- `pytest services/identity services/agent-relay -v` passes.
- Every endpoint on both services is exercised.
- The `/resolve` SQL ranking/dedup and the `invoke`↔WS round-trip are both
  covered.
- All auth modes (configured token/secret enforced, dev-mode fail-open) are
  characterized.

## Risks and mitigations

- **WebSocket testing** (primary risk): httpx+ASGITransport can't do
  WebSockets, and a real WS client interleaves badly with a blocking `invoke`.
  Mitigated by the fake-WS injection pattern, sequenced as the first test so the
  approach is validated before the rest of the suite is built.
- **testcontainers needs Docker**: confined to identity's test file;
  agent-relay needs no infrastructure. This is a deliberate tradeoff against the
  "tests, no Docker needed" quickstart — accepted because mocks cannot verify
  identity's SQL, and the admin service already establishes the testcontainers
  precedent.

## Out of scope

- Cross-instance / distributed WebSocket routing for agent-relay (would be its
  own feature with its own spec).
- Changing any fail-open auth behavior (intentional, documented repo pattern).
- The other three hardening features (covered by their own specs).
