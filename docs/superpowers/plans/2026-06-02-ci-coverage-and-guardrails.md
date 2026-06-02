# CI Coverage + Guardrails Implementation Plan (Plan A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the bounded CI coverage gaps and add blocking format + security guardrails, without touching the two broken test suites (league, workflow-worker — see Plan B).

**Architecture:** Edits to `.github/workflows/ci.yml` plus a one-time repo-wide `ruff format`. No application logic changes. Each task is independently verifiable by running its command locally and/or observing the CI run after push.

**Tech Stack:** GitHub Actions, ruff, pytest, pip-audit, gitleaks, Docker Compose.

**Source spec:** `docs/superpowers/specs/2026-06-02-ci-coverage-and-guardrails-design.md`

**Scope notes (read before starting):**
- **Frontend is intentionally untouched.** No frontend package defines a real `test` script and there are zero `*.test.*`/`*.spec.*` files, so `pnpm test` would be a no-op. Type errors are already caught by the existing `pnpm build` (Next.js fails the build on type errors). Adding `tsc`/`pnpm test` is YAGNI.
- **workflow-worker is NOT added to the unit-tests matrix here.** The matrix runs the whole `tests/` dir per service; workflow-worker's `tests/` contains broken chaos/acceptance/e2e tests. It belongs entirely to Plan B.
- **mypy is deferred** (untyped codebase — out of scope).

---

## File Structure

- `.github/workflows/ci.yml` — all CI changes live here (single workflow file, existing pattern).
- `services/**/*.py` — touched only by the mechanical `ruff format` in Task 1.
- No new application files.

---

## Task 1: Repo-wide `ruff format` + add `ruff format --check` gate

The `lint-python` job runs `ruff check` (lint) but never verifies formatting. 185 of 289 files are currently unformatted. Reformat once (mechanical, semantics-preserving), then add the blocking check.

**Files:**
- Modify (mechanical): `services/**/*.py` (~185 files)
- Modify: `.github/workflows/ci.yml` (the `lint-python` job, around lines 33-34)

- [ ] **Step 1: Apply the formatter**

Run:
```bash
ruff format services/
```
Expected: `185 files reformatted, 104 files left unchanged` (counts may vary slightly).

- [ ] **Step 2: Verify the formatter is now idempotent**

Run:
```bash
ruff format --check services/
```
Expected: `289 files already formatted` and exit code 0.

- [ ] **Step 3: Verify reformatting broke nothing — run the existing unit suites**

Run (the four services already in CI):
```bash
for s in auth cache observability admin; do
  echo "== $s =="
  ( cd "services/$s" && DEV_BYPASS_AUTH=true BUS_PROVIDER=memory ENVIRONMENT=test \
    DATABASE_URL=postgresql+asyncpg://aigateway:aigateway@localhost:5432/aigateway \
    REDIS_URL=redis://localhost:6379/0 python3 -m pytest tests/ -q )
done
```
Expected: all four suites pass (same as before the reformat). `ruff format` only changes whitespace/quotes, so behavior is unchanged.

- [ ] **Step 4: Commit the reformat as its own isolated commit**

```bash
git add services/
git commit -m "style: apply ruff format across services/ (one-time)

Mechanical reformat only — no behavior change. Precedes the
ruff format --check CI gate added next.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

- [ ] **Step 5: Add the `ruff format --check` step to `lint-python`**

In `.github/workflows/ci.yml`, in the `lint-python` job, add a step immediately after the existing `ruff check` step (after line 34):

```yaml
      - name: ruff format --check
        run: ruff format --check services/
```

- [ ] **Step 6: Confirm the workflow YAML is valid**

Run:
```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('YAML OK')"
```
Expected: `YAML OK`

- [ ] **Step 7: Commit the gate**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add blocking ruff format --check to lint-python

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Add `librarian`, `memory`, `scanner` to the unit-tests matrix

These three services ship `tests/` that pass cleanly but are absent from the matrix.

**Files:**
- Modify: `.github/workflows/ci.yml` (the `unit-tests` matrix, line 86)

- [ ] **Step 1: Verify each suite passes standalone (pre-condition)**

Run:
```bash
for s in librarian memory scanner; do
  echo "== $s =="
  ( cd "services/$s" && DEV_BYPASS_AUTH=true BUS_PROVIDER=memory ENVIRONMENT=test \
    DATABASE_URL=postgresql+asyncpg://aigateway:aigateway@localhost:5432/aigateway \
    REDIS_URL=redis://localhost:6379/0 python3 -m pytest tests/ -q )
done
```
Expected: librarian `12 passed`, memory `7 passed`, scanner `14 passed`.

- [ ] **Step 2: Extend the matrix**

In `.github/workflows/ci.yml`, change line 86 from:
```yaml
        service: [auth, cache, observability, admin]
```
to:
```yaml
        service: [auth, cache, observability, admin, librarian, memory, scanner]
```

- [ ] **Step 3: Confirm the new services install with the `[dev]` extra (the job's install step)**

The job runs `pip install "services/${{ matrix.service }}[dev]"`. Verify each has a dev extra:
```bash
for s in librarian memory scanner; do
  echo "== $s =="; grep -A2 "optional-dependencies\|^dev =\|dev =" "services/$s/pyproject.toml" | head -3
done
```
Expected: each shows a `dev = [...]` (or `[project.optional-dependencies]` with `dev`) entry.

- [ ] **Step 4: Validate YAML**

Run:
```bash
python3 -c "import yaml; d=yaml.safe_load(open('.github/workflows/ci.yml')); print(d['jobs']['unit-tests']['strategy']['matrix']['service'])"
```
Expected: `['auth', 'cache', 'observability', 'admin', 'librarian', 'memory', 'scanner']`

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run librarian/memory/scanner unit tests

These services ship passing test suites that the unit-tests matrix
never ran (12/7/14 tests).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Add `test_auth.py` + `test_cache.py` to the integration job

Both run without provider keys: `test_auth.py` exercises auth validation; `test_cache.py` `pytest.skip()`s gracefully when there is no live upstream (it never hard-fails without keys). `test_proxy.py` is intentionally left out (needs a live LLM — stays in `integration-full.yml`).

**Files:**
- Modify: `.github/workflows/ci.yml` (the `Run integration tests` pytest list, lines 166-179)

- [ ] **Step 1: Add the two files to the pytest invocation**

In `.github/workflows/ci.yml`, in the `Run integration tests` step, add two lines to the pytest list (after `tests/test_smoke.py`, line 167):

```yaml
            tests/test_smoke.py \
            tests/test_auth.py \
            tests/test_cache.py \
            tests/test_admin.py \
```
(Insert the `test_auth.py` and `test_cache.py` lines; leave the rest of the list unchanged.)

- [ ] **Step 2: Validate YAML**

Run:
```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('YAML OK')"
```
Expected: `YAML OK`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run auth + cache integration tests on PR/push

test_auth (auth validation) and test_cache (skips gracefully without
a live upstream) need no provider keys; previously they ran only in
the release-gated full job.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

- [ ] **Step 4: Verification is by CI run**

These tests require the running stack (brought up by the integration job). Local verification needs `docker compose up auth cache litellm observability admin`; otherwise confirm via the CI run after push (Task 5 / final push). Expected in CI: `test_auth` passes; `test_cache` passes or skips — neither fails.

---

## Task 4: New `security` job — pip-audit + gitleaks

Add a blocking `security` job. `pip-audit` runs **per service in an isolated venv** (auditing the service's declared deps, not the runner's ambient packages). The allowlist is populated from the **first CI run's** findings — exact advisory IDs are empirical data from the clean runner (a local run is polluted by system packages and will not match), so the procedure is specified here, not a hardcoded ID list.

**Files:**
- Modify: `.github/workflows/ci.yml` (add a new `security` job after the `integration-tests` job, before `build-push`)

- [ ] **Step 1: Add the `security` job**

In `.github/workflows/ci.yml`, insert this job after the `integration-tests` job (after line 200) and before the `build-push` job:

```yaml
  # ────────────────────────────────────────────────────────────────────────────
  # Security — dependency CVE scan (pip-audit) + secret scan (gitleaks)
  # ────────────────────────────────────────────────────────────────────────────
  security:
    name: Security scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # gitleaks scans history

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install pip-audit
        run: pip install --quiet pip-audit

      - name: pip-audit (per service, isolated venv)
        run: |
          set -euo pipefail
          # Advisories with no available fix are allowlisted here with a
          # justification. Populate from the FIRST CI run's findings — do not
          # invent IDs. Format: one --ignore-vuln per advisory.
          IGNORE=(
            # e.g. --ignore-vuln GHSA-xxxx-xxxx-xxxx  # no fixed version yet (dep X)
          )
          fail=0
          for svc in auth cache observability admin librarian memory scanner; do
            echo "::group::pip-audit $svc"
            python3 -m venv "/tmp/venv-$svc"
            "/tmp/venv-$svc/bin/pip" install --quiet "services/$svc"
            "/tmp/venv-$svc/bin/pip" install --quiet pip-audit
            "/tmp/venv-$svc/bin/pip-audit" "${IGNORE[@]}" || fail=1
            echo "::endgroup::"
          done
          exit $fail

      - name: gitleaks secret scan
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **Step 2: Validate YAML**

Run:
```bash
python3 -c "import yaml; d=yaml.safe_load(open('.github/workflows/ci.yml')); assert 'security' in d['jobs']; print('security job OK')"
```
Expected: `security job OK`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add security job — pip-audit (per-service) + gitleaks

pip-audit audits each service's declared deps in an isolated venv;
unfixable advisories get an allowlisted --ignore-vuln with
justification. gitleaks scans for committed secrets.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

- [ ] **Step 4: First-run allowlist tuning (REQUIRED follow-up after push)**

After the first push, watch the `security` job:
```bash
gh run watch <run-id> --exit-status || true
gh run view <run-id> --log-failed --job <security-job-id>
```
For each `pip-audit` finding, decide:
- **Has a fixed version** → bump the dependency in the service's `pyproject.toml` (separate commit), do NOT allowlist.
- **No fix available** → add `--ignore-vuln <ID>  # <reason, dep, date>` to the `IGNORE` array.

For gitleaks: if it flags placeholder/dev secrets (e.g. in `.env.example`, compose), add a `.gitleaks.toml` allowlist with a justifying comment (or `# gitleaks:allow` inline). Commit allowlist/bumps until the job is green. **Do not merge with the job red.**

---

## Final integration: push and verify the whole pipeline

- [ ] **Step 1: Push all commits**

```bash
git push origin <branch>
```

- [ ] **Step 2: Watch the run end-to-end**

```bash
gh run list --limit 1 --branch <branch> --json databaseId -q '.[0].databaseId'
gh run watch <run-id> --exit-status
```
Expected jobs green: `lint-python` (now incl. format check), `unit-tests` (now 7 services), `integration-tests` (now incl. auth+cache), `security` (after allowlist tuning), and the existing `lint-frontend` / `build-push`.

- [ ] **Step 3: If `security` is red on first run, complete Task 4 Step 4, recommit, repush, re-watch until green.**

---

## Self-Review (completed during authoring)

- **Spec coverage:** Spec §Design rows mapped → ruff format (T1), librarian/memory/scanner (T2), test_auth/test_cache (T3), pip-audit+gitleaks (T4). Frontend `pnpm test`/`tsc`: dropped with rationale (no tests; build type-checks) — a deliberate spec deviation noted in Scope notes. league + workflow-worker: deferred to Plan B (see below). mypy: deferred per spec.
- **Placeholder scan:** The pip-audit `IGNORE` array is empty-by-design with a documented first-run procedure (Task 4 Step 4), not a TODO — exact IDs are empirical CI data. No other placeholders.
- **Consistency:** Service list `[auth, cache, observability, admin, librarian, memory, scanner]` is identical in Task 2 (matrix) and Task 4 (pip-audit loop). `<branch>`/`<run-id>` are runtime values, not undefined symbols.

---

## Follow-up: Plan B

league and workflow-worker test suites are genuinely broken (not wiring gaps) and require diagnosis, so they are a separate plan executed with **systematic-debugging**:
`docs/superpowers/plans/2026-06-02-fix-league-workflow-worker-tests.md`
