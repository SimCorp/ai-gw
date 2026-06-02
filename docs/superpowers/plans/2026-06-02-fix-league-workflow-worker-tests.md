# Fix league + workflow-worker Test Suites for CI (Plan B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:systematic-debugging for each investigation below. These are real, undiagnosed bugs — do NOT write speculative fixes. Diagnose first (reproduce → isolate → root cause → minimal fix → verify), then wire into CI. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the `league` and `workflow-worker` test suites pass and run in CI.

**Why this is a separate, debugging-driven plan:** Unlike Plan A (wiring up already-passing tests), these suites are genuinely broken. The exact fixes are not knowable without diagnosis, so this plan deliberately does NOT contain pre-written fix code — that would be fabrication. It provides a symptom dossier and the CI-integration target; the fixes come from systematic-debugging at execution time.

**Source spec:** `docs/superpowers/specs/2026-06-02-ci-coverage-and-guardrails-design.md` (§Findings, steps 6-7)

**Prerequisite:** Plan A merged (so CI is otherwise green and changes here are bisectable).

---

## Symptom Dossier (observed 2026-06-02)

### league (`services/league/tests/`, 8 files)
- Clean env (`ENVIRONMENT=test`, no Postgres URL): **22 failed, 20 passed, 3 errors**.
- Against live Postgres (correct creds): **~21 failed, ~21 passed, 3 errors** — different error.
- **The ~20 passing tests** use the in-memory SQLite fixture in `services/league/tests/conftest.py` (`sqlite+aiosqlite:///:memory:`, `StaticPool`) + mocked Redis. This pattern works.
- **The failing tests** (e.g. `test_internal_points.py`) use FastAPI `TestClient(app)` with a `mock_session` override of `get_session` and a placeholder DSN `postgresql+asyncpg://x:x@localhost/x`. They are *meant* to be fully mocked, but:
  - clean env → `asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "x"` at **fixture/lifespan setup** (something connects to the real engine — likely app lifespan startup, which the `get_session` override does NOT cover).
  - live Postgres → `asyncpg.exceptions.InterfaceError: cannot perform operation: another operation is in progress` (async fixture / event-loop isolation bug under `asyncio_mode = "auto"` with a shared asyncpg connection).
- Relevant code: `services/league/app/db.py` creates `engine = create_async_engine(settings.database_url)` at import; `services/league/app/main.py` lifespan (check what it connects to on startup).

### workflow-worker (`services/workflow-worker/tests/`, 4 files)
- `test_smoke.py`: light (was only ever observed bundled — isolate it first; it may already pass).
- `test_chaos.py`, `test_acceptance.py`, `test_canvas_e2e.py`: **`KeyError: 0`** at setup of a **`scope="session"` fixture** (`services/workflow-worker/tests/test_acceptance.py:49`). Chaos tests literally restart DB/Redis/admin mid-run → they need the full running stack, not the lightweight unit-tests job.

---

## Task 1: Diagnose + fix the league suite

**Sub-skill:** superpowers:systematic-debugging.

- [ ] **Step 1: Reproduce in isolation**

Run:
```bash
cd services/league && ENVIRONMENT=test python3 -m pytest tests/test_internal_points.py -q --tb=short
```
Capture the exact failing setup path. Confirm whether the connection attempt originates from app **lifespan startup** vs a handler.

- [ ] **Step 2: Root-cause the "connects despite mocks" failure**

Investigate `services/league/app/main.py` lifespan and `services/league/app/db.py`. Determine what connects at `TestClient` context-enter. Form ONE hypothesis (e.g. "lifespan pings DB/redis with the real engine") and confirm it before fixing.

- [ ] **Step 3: Root-cause the async-concurrency failure**

For the live-DB path, determine why `another operation is in progress` occurs (shared connection across event loops / `asyncio_mode=auto` fixture scoping). Decide the fix direction: make these tests use the existing SQLite `db_session` fixture pattern (preferred — consistent with the passing tests), OR give them a properly-isolated per-test engine.

- [ ] **Step 4: Apply the minimal fix, TDD-style, one failing test at a time**

For each failing test: fix → run that single test → green. Do not batch-fix blindly. Prefer converging the failing tests onto the working SQLite-fixture pattern over adding real-DB infrastructure, unless a test genuinely needs Postgres-specific behavior.

- [ ] **Step 5: Whole-suite green**

Run:
```bash
cd services/league && ENVIRONMENT=test python3 -m pytest tests/ -q
```
Expected: all pass (target: the full ~42 tests).

- [ ] **Step 6: Add `league` to the unit-tests matrix (only if it now passes via the standard job mechanism)**

If the fixed suite passes with the unit-tests job's env (`DEV_BYPASS_AUTH=true`, `BUS_PROVIDER=memory`, the Postgres/Redis URLs) and needs no extra services, add `league` to the matrix in `.github/workflows/ci.yml` line 86. If it requires a real migrated Postgres beyond what the unit job provides, instead add a dedicated `league-tests` job with a Postgres service container + migrations (mirror the `integration-tests` setup). Decide based on Step 4's outcome.

- [ ] **Step 7: Commit** (message describing the actual root cause found).

---

## Task 2: Diagnose + fix the workflow-worker suite

**Sub-skill:** superpowers:systematic-debugging.

- [ ] **Step 1: Isolate `test_smoke.py`**

Run:
```bash
cd services/workflow-worker && ENVIRONMENT=test python3 -m pytest tests/test_smoke.py -q --tb=short
```
If it passes standalone, it can go in the unit-tests matrix once the *other* files are quarantined into a separate job (the matrix runs the whole dir, so smoke can't be matrix-added while siblings are broken).

- [ ] **Step 2: Root-cause the `KeyError: 0` session fixture**

Open `services/workflow-worker/tests/test_acceptance.py:49` (the `scope="session"` fixture). Find why indexing `[0]` raises `KeyError` at setup (empty collection / mis-shaped fixture data / fixture depending on a not-yet-running service). One hypothesis, confirmed before fixing.

- [ ] **Step 3: Decide the harness for chaos/acceptance/e2e tests**

These restart DB/Redis/admin mid-run and need the full stack. Design a dedicated `workflow-worker-integration` job using the Docker Compose stack (mirror `integration-tests`), separate from the unit matrix. Confirm chaos tests (service restarts) are feasible/stable under CI compose; if a specific test is inherently CI-hostile, surface it explicitly rather than silently skipping.

- [ ] **Step 4: Fix the fixture + get each file green**

Fix the session fixture, then run each file: `test_smoke`, `test_canvas_e2e`, `test_acceptance`, `test_chaos`. Green one at a time.

- [ ] **Step 5: Wire into CI**

Add the dedicated full-stack job (and, if smoke is cleanly separable, add `workflow-worker` smoke to the unit matrix or run smoke within the new job). Validate YAML.

- [ ] **Step 6: Commit** (message describing the actual root cause found).

---

## Final verification

- [ ] Push branch; `gh run watch <run-id> --exit-status`. Expected: the new league/workflow-worker job(s) green alongside all Plan A jobs.

---

## Self-Review (completed during authoring)

- **No fabricated fix code:** by design — these are undiagnosed bugs; the plan mandates systematic-debugging and supplies a symptom dossier instead of invented patches. This is the correct treatment per the writing-plans no-speculation principle.
- **Spec coverage:** covers spec steps 6 (league) and 7 (workflow-worker).
- **Consistency:** CI integration decisions (matrix vs dedicated job) are made conditionally on diagnosis outcome, with both branches specified.
