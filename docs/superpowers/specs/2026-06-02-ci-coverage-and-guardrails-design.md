# CI coverage gaps + guardrails — design

**Date:** 2026-06-02
**Status:** Approved (design); pending implementation plan
**Scope:** `.github/workflows/ci.yml` (+ a one-time repo-wide `ruff format`), new
test/security jobs, and fixes to two test suites that currently can't run in CI.

## Problem

The CI pipeline (`.github/workflows/ci.yml`) is green but has real gaps:

1. **Service unit tests that exist but CI never runs.** The `unit-tests` matrix is
   `[auth, cache, observability, admin]`. Five other services ship `tests/` but are
   absent from the matrix:
   - `librarian` (1 file), `memory` (1), `scanner` (2) — verified passing locally
     (12 / 7 / 14 tests).
   - `league` (8 files) and `workflow-worker` (4 files) — **failing**; see below.
2. **Frontend tests never run.** Root `package.json` defines `"test": "turbo test"`,
   but `lint-frontend` only runs `pnpm lint` + `pnpm build`.
3. **Integration tests partially skipped on PR/push.** `tests/test_auth.py` and
   `tests/test_cache.py` (no provider keys required) run only in the release-gated
   `integration-full.yml`, not in the per-PR `integration-tests` job.
4. **No format check.** Only `ruff check` (lint) runs; `ruff format` is never verified
   — **185 of 289 files would currently be reformatted.**
5. **No security scanning.** No dependency CVE scan, no secret scan — despite the repo
   having a security-review workflow.

Out of scope (explicitly deferred): Python type checking (`mypy`). The codebase has no
type-checker configured anywhere; turning on `mypy` against untyped code is an
open-ended cleanup and is not part of this effort.

## Findings (from local investigation)

- **`ruff format --check`**: 185 files would reformat. Mechanical, but large.
- **league tests are a mix**, not drop-in unit tests:
  - ~20 tests use an in-memory SQLite async engine (`sqlite+aiosqlite:///:memory:`,
    `StaticPool`) + mocked Redis and pass.
  - ~22 tests (e.g. `test_internal_points.py`) hit the app's **real** DB session.
    They fail with `asyncpg InvalidPasswordError: ...user "x"` in a clean env (the
    default DSN uses placeholder creds), and with `asyncpg ... another operation is in
    progress` against a real Postgres — an async-fixture / event-loop isolation bug
    (`asyncio_mode = "auto"` + a shared asyncpg connection).
- **workflow-worker** splits by file:
  - `test_smoke.py` is light/unit-ish.
  - `test_chaos.py` (DB/Redis/admin **restart** mid-run), `test_acceptance.py`,
    `test_canvas_e2e.py` are full-stack tests and share a broken **session-scoped**
    fixture failing with `KeyError: 0` at setup.
- **Integration tests**: `test_auth.py` (6 tests, no skips) and `test_cache.py`
  (5 tests, several skip markers) do not require provider keys. `test_proxy.py` does
  (live LLM) and stays release-gated.

## Decisions

- **Guardrail scope:** security scanning + `ruff format --check`, all **blocking**.
  `mypy` deferred. Frontend `tsc` included **only if already clean**.
- **`pip-audit`:** blocking, **with an allowlist** (`--ignore-vuln`) for advisories
  that have no available fix — blocks new/fixable CVEs without wedging CI on unfixable
  transitive ones.
- **league + workflow-worker:** investigate and **include now** (the user opted into
  the larger scope) — fix the real test/infra bugs, don't just wire them up.

## Design

### Changes to `ci.yml`

| Change | Job | Blocking | Notes |
|---|---|---|---|
| `ruff format --check services/` | `lint-python` | ✅ | lands after a 1× `ruff format` commit |
| matrix += `librarian`, `memory`, `scanner` | `unit-tests` | ✅ | verified clean locally |
| `pnpm test` | `lint-frontend` | ✅ | only if the workspace has real tests; if `turbo test` is a no-op, omit |
| `tsc --noEmit` (per app) | `lint-frontend` | ✅ | only if already clean; otherwise drop (same rationale as deferring mypy) |
| `test_auth.py`, `test_cache.py` added to the pytest list | `integration-tests` | ✅ | no provider keys needed |
| `pip-audit` (with allowlist) + `gitleaks` | **new** `security` job | ✅ | runs on PR + push |
| league suite | **new** `league-tests` job | ✅ | Postgres service container + `db-migrate`, fix async-fixture isolation + real failures |
| workflow-worker smoke/unit | `unit-tests` matrix | ✅ | the light tests only |
| workflow-worker chaos/acceptance/e2e | **new** full-stack job | ✅ | fix `KeyError: 0` session fixture; these need the running stack incl. service restarts |

### New `security` job (sketch)

- Runs on `push` + `pull_request`.
- `pip-audit` over each service's resolved deps (per-service or a combined env),
  `--ignore-vuln <GHSA…>` allowlist kept inline with a comment justifying each entry.
- `gitleaks` secret scan over the repo (full history not required; scan the diff/tree).

### league `league-tests` job (sketch)

- Postgres service container (matching `aigateway/aigateway`), run Alembic migrations
  (`db-migrate` path) before tests.
- Provide correct test DSN so the real-DB tests authenticate.
- **Fix** the async-fixture isolation bug so real-DB tests don't trip
  `another operation is in progress` (per-test connection/transaction, not a shared
  one under `asyncio_mode=auto`).
- Any tests that are genuinely broken get fixed (not skipped) — this is the
  "investigate" scope.

### workflow-worker full-stack job (sketch)

- Reuse the Docker Compose stack pattern from `integration-tests`.
- **Fix** the `KeyError: 0` session-scoped fixture in `test_acceptance.py` /
  `test_chaos.py` / `test_canvas_e2e.py`.
- Chaos tests perform service restarts — confirm they're feasible/stable under CI
  compose; if a specific chaos test is inherently flaky in CI, that's called out during
  implementation (but the default is fix, not skip).

## Sequencing

Each step is its own commit so a regression is easy to bisect. Steps 1–5 are bounded
and low-risk; 6–7 are the open-ended investigation.

1. `ruff format` reformat (isolated, reviewable) → add `ruff format --check`.
2. `security` job: `pip-audit` (+ allowlist) + `gitleaks`.
3. `unit-tests` matrix += `librarian`, `memory`, `scanner`, + workflow-worker smoke.
4. `integration-tests` += `test_auth.py`, `test_cache.py`.
5. Frontend `pnpm test` + `tsc` (each conditional on being clean).
6. league: Postgres-backed job + migrations + async-fixture fix + real failures.
7. workflow-worker: full-stack job + `KeyError: 0` fixture fix.

## Risks / open items

- **`pip-audit` allowlist drift:** each ignored advisory needs a justification comment
  and periodic review; otherwise the allowlist silently hides fixable CVEs over time.
- **league async-fixture fix** may touch `services/league/tests/conftest.py` design
  (per-test engine vs session engine) — could ripple to several test files.
- **workflow-worker chaos tests** (service restarts) may be slow or flaky in CI compose;
  feasibility confirmed during implementation, with any genuinely CI-hostile test
  flagged rather than silently skipped.
- **Frontend `tsc`/`pnpm test`** inclusion is conditional — measured during
  implementation (requires `pnpm install`), so the final job set may drop one or both
  if they're noisy/no-op.
- **Node 20 action deprecation** (`checkout@v4`, `setup-python@v5`) is a known warning;
  not addressed here unless trivially bundled.
