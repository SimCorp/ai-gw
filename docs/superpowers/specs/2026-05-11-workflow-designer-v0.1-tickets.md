# Workflow Designer v0.1 — Implementation Tickets

**Parent spec:** [2026-05-11-visual-workflow-designer.md](./2026-05-11-visual-workflow-designer.md)
**Milestone goal:** vertical slice — prove the architecture end-to-end with the minimum viable execution
**Status:** ready for assignment

## Ticket map (dependency graph)

```
                  ┌──────────────────────────────────┐
                  │ T0 — Wire Alembic baseline       │ (prereq)
                  └──────────────┬───────────────────┘
                                 ↓
              ┌──────────────────┴──────────────────┐
              ↓                                     ↓
   ┌─────────────────────┐               ┌─────────────────────┐
   │ T1 — agents +       │               │ T2 — workflow_runs  │
   │   workflows tables  │               │   + run_nodes +     │
   │                     │               │   work_queue tables │
   └──────────┬──────────┘               └──────────┬──────────┘
              ↓                                     ↓
   ┌─────────────────────┐               ┌─────────────────────┐
   │ T3 — Scoped API key │               │ T4 — Workflow event │
   │     issuance/revoke │               │     bus publisher   │
   └──────────┬──────────┘               └──────────┬──────────┘
              │                                     │
              └──────────────┬──────────────────────┘
                             ↓
              ┌──────────────┴──────────────┐
              ↓                             ↓
   ┌────────────────────┐         ┌────────────────────┐
   │ T5 — /agents +     │         │ T10 — Container-   │
   │     /workflows API │         │      Runtime port  │
   │                    │         │      + DockerRuntime│
   └─────────┬──────────┘         └─────────┬──────────┘
             ↓                              ↓
   ┌────────────────────┐         ┌────────────────────┐
   │ T6 — /runs POST/   │         │ T8 — workflow-     │
   │     GET (rate-lim) │         │     worker service │
   └─────────┬──────────┘         └─────────┬──────────┘
             ↓                              ↓
   ┌────────────────────┐         ┌────────────────────┐
   │ T7 — /runs/:id/    │         │ T9 — DAG evaluator │
   │     stream (SSE)   │         │     (linear succ.) │
   └─────────┬──────────┘         └─────────┬──────────┘
             │                              │
             └──────────────┬───────────────┘
                            ↓
              ┌─────────────┴─────────────┐
              ↓                           ↓
   ┌────────────────────┐       ┌────────────────────┐
   │ T11 — Portal run-  │       │ T12 — echo-agent   │
   │      viewer page   │       │     example image  │
   └─────────┬──────────┘       └─────────┬──────────┘
             │                            │
             └──────────────┬─────────────┘
                            ↓
                  ┌─────────────────────┐
                  │ T13 — Compose wiring │
                  │      workflow-worker │
                  └──────────┬──────────┘
                             ↓
                  ┌─────────────────────┐
                  │ T14 — e2e test +    │
                  │      acceptance     │
                  │      suite          │
                  └─────────────────────┘
```

**Critical path:** T0 → T1 → T3 → T5 → T6 → T13 → T14
**Parallel tracks:** {T1, T2}, {T3, T4}, {T5+T6+T7, T8+T9+T10}, {T11, T12}

---

## T0 — Wire Alembic baseline (prereq companion task)

**Effort:** M (1–2 days)
**Depends on:** —
**Files touched:**
- `services/admin/alembic.ini` (new)
- `services/admin/migrations/env.py` (new)
- `services/admin/migrations/versions/0001_baseline_init_sql.py` (new)
- `infra/docker-compose.yml` (modify `db-migrate` service)
- `services/admin/pyproject.toml` (lock alembic to a specific version; already a declared dep)

**Scope:**
1. Add `alembic.ini` configured for the admin service's async engine
2. Add `migrations/env.py` that imports `Base` from `services/admin/app/db.py` and includes all model metadata
3. Autogenerate or hand-craft a baseline migration that produces the exact schema currently in `infra/postgres/init.sql` (including: teams, projects, members, areas, area_policies, api_keys, audit_log, mcp_servers, mcp_tools, mcp_server_access, plugins, plugin_team_overrides, model_registry, pricing, policies, ai_insights, and any others — verify the full list against `init.sql`)
4. Change `infra/docker-compose.yml`'s `db-migrate` service from `psql -f init.sql` to running `alembic -c /app/alembic.ini upgrade head` against the admin image
5. Keep `init.sql` in repo for one cycle as a comment-only reference; remove in v0.2

**Acceptance:**
- `pg_dump --schema-only` on a fresh DB after `alembic upgrade head` is byte-identical (modulo formatting / extension ordering) to `pg_dump --schema-only` after the legacy `psql -f init.sql` path
- `docker compose up` starts cleanly with the new `db-migrate` step
- `services/admin` test suite still passes
- Running `alembic revision --autogenerate -m test` against the baseline produces an empty diff (no drift)

---

## T1 — Schema: agents + workflows + workflow_versions

**Effort:** S
**Depends on:** T0
**Files touched:**
- `services/admin/app/models/agent.py` (new)
- `services/admin/app/models/workflow.py` (new)
- `services/admin/app/models/__init__.py` or main.py import list
- `services/admin/migrations/versions/0002_agents_and_workflows.py` (new)

**Scope:**
- `Agent` SQLAlchemy model matching the spec's `agents` table (uuid pk, slug unique, image, manifest JSONB, category, managed bool, owner_team_id, owner_project_id nullable, enabled, timestamps)
- `Workflow` and `WorkflowVersion` models matching the spec
- Indexes:
  - `agents`: index on `category` (palette filtering), unique on `slug`
  - `workflows`: unique on (`team_id`, `project_id`, `slug`); index on `team_id`
- Migration adds the three tables + FKs to `teams`, `projects`

**Acceptance:**
- `alembic upgrade head` creates the three tables
- `alembic downgrade -1` cleanly removes them
- Empty-DB roundtrip: `select` from each works
- Model imports in `services/admin/app/main.py` so metadata is registered before `Base.metadata.create_all`-style operations

---

## T2 — Schema: workflow_runs + run_nodes + work_queue

**Effort:** S
**Depends on:** T0 (parallel with T1)
**Files touched:**
- `services/admin/app/models/workflow_run.py` (new — contains all three)
- `services/admin/migrations/versions/0003_workflow_runs.py` (new)

**Scope:**
- `run_status` enum: `pending|running|succeeded|failed|cancelled`
- `WorkflowRun`, `RunNode`, `WorkQueueItem` models per spec
- Indexes:
  - `workflow_runs`: index on (`team_id`, `created_at desc`), index on `status` for pending sweeps
  - `run_nodes`: pk (`run_id`, `node_id`, `iteration`)
  - `work_queue`: partial index `WHERE claimed_by IS NULL` on `available_at` (already in spec); index on `claim_expires` for sweeper

**Acceptance:**
- Migration up/down clean
- Concurrent `SELECT … FOR UPDATE SKIP LOCKED` on `work_queue` from two sessions returns disjoint rows (manual psql verification)
- FK to `workflows(id)` enforced (orphan run insert fails)

---

## T3 — Scoped API key issuance + revocation

**Effort:** M
**Depends on:** T0
**Files touched:**
- `services/admin/app/api_keys.py` (new helper module; reuses existing `api_keys` table)
- `services/admin/app/models/api_key.py` (extend if needed — add `scope`, `expires_at`, `parent_key_id` if not present)
- `services/admin/migrations/versions/0004_api_key_scope.py` (only if schema changes needed)

**Scope:**
- Function `issue_scoped_key(team_id, project_id, parent_caller_id, ttl_seconds, scope='workflow-run') -> (plaintext_key, key_id)` — generates a key, hashes it, writes to `api_keys` with TTL, returns plaintext once
- Function `revoke_key(key_id)` — sets `revoked_at`
- Auth validation in `services/auth/app/validators/api_key.py` must respect `expires_at` (reject if past)
- Scope must not exceed parent: the issued key's `team_id` + `project_id` must equal the parent's (no privilege escalation)

**Acceptance:**
- Unit test: issue a key, validate via auth flow → returns correct `{team_id, project_id, key_id}`
- Unit test: expired key (TTL past) rejected with 401
- Unit test: revoked key rejected with 401
- Unit test: scope escalation attempt (different team_id) rejected at issue time

---

## T4 — Workflow event bus publisher

**Effort:** S
**Depends on:** T0
**Files touched:**
- `services/admin/app/events/workflow.py` (new)
- Reuses existing observability bus client (Service Bus prod / in-memory local)

**Scope:**
- Helper that publishes structured events with this taxonomy:
  - `workflow.run.started` `{run_id, workflow_id, version, team_id, project_id}`
  - `workflow.run.finished` `{run_id, status, finished_at}`
  - `workflow.node.started` `{run_id, node_id, iteration, agent_id}`
  - `workflow.node.log` `{run_id, node_id, line}` (subset of stdout, sampled)
  - `workflow.node.finished` `{run_id, node_id, iteration, status, outputs|error}`
- Fail-silent semantics matching v1 observability (never blocks the caller)

**Acceptance:**
- Unit test against in-memory bus: each helper publishes the expected envelope
- Integration test: bus failure does not raise to caller

---

## T5 — Admin routers: /agents + /workflows

**Effort:** M
**Depends on:** T1, T3
**Files touched:**
- `services/admin/app/routers/agents.py` (new)
- `services/admin/app/routers/workflows.py` (new)
- `services/admin/app/main.py` (register routers)

**Scope:**
- `GET /agents` — list enabled agents (palette source); filter by `category`, `team_id` visibility
- `POST /agents` — admin-only; register/upsert; validates manifest JSON schema
- `GET /workflows` — list team workflows
- `POST /workflows` — create (slug+team+project unique)
- `POST /workflows/{id}/versions` — append a new immutable version row; validates DAG against `dag.schema.json`
- `GET /workflows/{id}/versions/{v}` — fetch DAG
- All endpoints behind existing `require_admin_auth` / team-scoped dependency

**Acceptance:**
- pytest coverage on each endpoint (happy path + auth-failure path)
- Manifest schema lives in `services/admin/app/schemas/agent_manifest.schema.json`
- DAG schema lives in `services/admin/app/schemas/workflow_dag.schema.json` (linear-only fully validated; branch/loop fields tolerated in schema for v0.5 compat but rejected at runtime in v0.1)

---

## T6 — Admin router: /runs POST + GET (rate-limited)

**Effort:** M
**Depends on:** T2, T3, T4, T5
**Files touched:**
- `services/admin/app/routers/runs.py` (new)
- `services/admin/app/rate_limit.py` (extend existing rate-limiter module, or new helper that follows the same Redis-counter pattern)
- `services/admin/app/main.py` (register router)

**Scope:**
- `POST /runs` — body `{workflow_id, version, inputs}`. Steps:
  1. Authorize caller; resolve `{team_id, project_id, triggered_by, triggered_by_kind}`
  2. Apply Redis-counter rate limit `runs:{team_id}` window 1h, default 100; configurable per team via existing rate-limit policy table
  3. Issue scoped API key via T3
  4. Insert `workflow_runs` row with `status='pending'`
  5. Enqueue first node(s) (entry nodes) into `work_queue`
  6. Publish `workflow.run.started` via T4
  7. Return `{run_id}`
- `GET /runs/{id}` — caller must be on same team; returns run + all `run_nodes` rows
- `POST /runs/{id}/cancel` — cooperative cancel: writes a flag to `workflow_runs.status='cancelled'` and revokes the scoped key; worker checks before each node start

**Acceptance:**
- pytest: JWT-triggered run → row inserted, `triggered_by_kind='user'`
- pytest: API-key-triggered run → row inserted, `triggered_by_kind='api_key'`
- pytest: 101st run in an hour returns 429 with `Retry-After`
- pytest: cross-team `GET /runs/{id}` returns 403
- pytest: cancel marks status + revokes scoped key

---

## T7 — Admin router: /runs/{id}/stream (SSE)

**Effort:** M
**Depends on:** T4, T6
**Files touched:**
- `services/admin/app/routers/runs.py` (add SSE endpoint)
- `services/admin/app/events/sse.py` (new — subscriber wrapper around bus)

**Scope:**
- `GET /runs/{id}/stream` — Server-Sent Events endpoint
- Subscribes to the observability bus with a consumer group `sse:{run_id}:{conn_id}`, filter `workflow.*` events where `payload.run_id = {id}`
- Emits each event as an SSE `data:` frame; `event:` line carries the kind
- On connect: backfills the current snapshot from `workflow_runs` + `run_nodes` so a late subscriber sees current state, then streams new events
- On disconnect: tears down the consumer group
- Heartbeat every 15s to keep proxies happy

**Acceptance:**
- pytest with `httpx.AsyncClient`: subscribe, trigger a node.started publish, receive it
- Late-subscribe test: run already in progress; subscriber sees a snapshot frame plus live frames
- Manual: browser SSE connection holds open across a 30s idle period

---

## T8 — workflow-worker service skeleton

**Effort:** L
**Depends on:** T2, T4
**Files touched:**
- `services/workflow-worker/` (new service)
  - `pyproject.toml`
  - `Dockerfile`
  - `app/__init__.py`
  - `app/main.py` (entrypoint)
  - `app/config.py`
  - `app/claim.py` (work-queue claim loop)
  - `app/sweeper.py` (stale-claim reclaim loop)
  - `tests/` (unit test scaffold)

**Scope:**
- Async main loop that:
  - Polls `work_queue` with `FOR UPDATE SKIP LOCKED LIMIT 1`
  - Claims the row (sets `claimed_by`, `claim_expires = NOW() + 2 minutes`)
  - Handler is a no-op stub at this ticket — just marks the row done and publishes `workflow.node.finished` with empty outputs
  - Concurrent containers governed by `asyncio.Semaphore(N)` (configurable via env, default 5)
- Sweeper task running every 30s that resets `claim_expires < NOW()` rows back to `claimed_by=NULL`
- Graceful shutdown on SIGTERM

**Acceptance:**
- Unit test: claim a row → sweeper does not reclaim until expiry
- Unit test: simulate worker crash by skipping the row's completion → sweeper reclaims after expiry
- Two worker instances + 10 queue rows = each consumes ~5 rows (no double-processing)

---

## T9 — DAG evaluator (linear successor scheduling)

**Effort:** M
**Depends on:** T8
**Files touched:**
- `services/workflow-worker/app/dag.py` (new)
- `services/workflow-worker/tests/test_dag.py` (new)

**Scope:**
- Function `next_nodes(dag, run_nodes_state) -> list[node_id]` — given the DAG definition and current `run_nodes` rows, returns nodes whose predecessors are all `succeeded`
- Linear chain support only in v0.1 (per spec); schema permits branches/loops but evaluator returns the single successor or empty
- Detects "no successors" → caller marks `workflow_runs.status='succeeded'` and publishes `workflow.run.finished`
- Detects "predecessor failed" → caller marks run as failed (no retry in v0.1)

**Acceptance:**
- Unit test: 3-node chain → after node A done, returns [B]; after B done, returns [C]; after C done, returns []
- Unit test: predecessor failed → returns "abort"
- Property test: given any linear chain length 1..10, evaluator produces correct sequence

---

## T10 — ContainerRuntime port + DockerRuntime

**Effort:** M
**Depends on:** T0 (only)
**Files touched:**
- `services/workflow-worker/app/runtime/__init__.py` (port definition)
- `services/workflow-worker/app/runtime/docker.py` (DockerRuntime impl)
- `services/workflow-worker/tests/test_docker_runtime.py`

**Scope:**
- Port: `class ContainerRuntime(Protocol)` with `async def run(image, env, inputs, timeout) -> RunResult` returning `{exit_code, stdout_stream, outputs_json}`
- DockerRuntime uses `aiodocker` (or `docker` lib) via `/var/run/docker.sock`
- Mounts `inputs.json` as a read-only volume at `/run/inputs.json`; expects agent to write `/run/outputs.json`
- Injects `AIGW_API_KEY` and `AIGW_BASE_URL=http://cache:8002` from per-run config
- Attaches container to the `aigateway` network
- Captures stdout as an async stream (line-buffered) for `workflow.node.log` events
- Timeout kills container

**Acceptance:**
- Integration test (runs locally with docker): spawn `alpine:latest` running `sh -c 'cat /run/inputs.json > /run/outputs.json'`; verify output round-trip
- Integration test: timeout kills container after T seconds
- Integration test: stdout streamed line-by-line (not buffered to end)

---

## T11 — Portal run-viewer page (read-only, SSE)

**Effort:** M
**Depends on:** T7
**Files touched:**
- `apps/portal/app/portal/workflows/[id]/runs/[runId]/page.tsx` (new)
- `apps/portal/app/portal/workflows/page.tsx` (new — list view, minimal)
- `apps/portal/lib/workflows/sse-client.ts` (new — EventSource wrapper with reconnect)
- `apps/portal/lib/workflows/run-types.ts` (TS types matching the run/node DTOs)

**Scope:**
- Workflows index lists user's team workflows (links only; full CRUD is v0.5)
- Run viewer at `/portal/workflows/[id]/runs/[runId]`:
  - Initial fetch of `GET /runs/{runId}` for snapshot
  - Opens SSE to `/runs/{runId}/stream`
  - Renders nodes as simple list with status badges (`idle | running | done | error`)
  - Shows last 50 `workflow.node.log` lines per node in a collapsible section
  - Shows final outputs when `run.finished`
- No canvas / no React Flow yet — that's v0.5

**Acceptance:**
- Playwright/manual: trigger a run via curl, open the viewer; see live status transitions
- SSE reconnects on transient network drop (test with proxy kill+restart)
- Renders correctly when subscribed to a run that's already completed (uses snapshot only)

---

## T12 — Example echo-agent image

**Effort:** S
**Depends on:** —
**Files touched:**
- `agents/echo-agent/` (new directory)
  - `Dockerfile`
  - `main.py` (read /run/inputs.json, write /run/outputs.json with `{"echoed": <input>}`)
  - `manifest.json` (declares inputs/outputs schema)
  - `README.md` (build + push instructions)

**Scope:**
- Trivial agent: copies inputs to outputs with an `echoed` wrapper
- Manifest declares no LLM access (simplest path)
- A second variant `agents/llm-echo-agent/` that makes a single LLM call via `cache:8002` using `AIGW_API_KEY` — needed for the cost-attribution acceptance criterion

**Acceptance:**
- `docker build agents/echo-agent -t echo-agent:dev` succeeds
- Run via T10's DockerRuntime: outputs match expectation
- llm-echo-agent: cost record appears in observability tied to the parent run

---

## T13 — Compose wiring: workflow-worker service

**Effort:** S
**Depends on:** T8, T10, T12
**Files touched:**
- `infra/docker-compose.yml`

**Scope:**
- Add a `workflow-worker` service:
  - Build context `../services/workflow-worker`
  - Mounts `/var/run/docker.sock:/var/run/docker.sock`
  - Env: `DATABASE_URL`, `REDIS_URL`, `OBSERVABILITY_BUS_URL`, `WORKER_CONCURRENCY=5`
  - Network: `aigateway` (same network agent containers will join)
  - `depends_on: { db-migrate: { condition: service_completed_successfully }, redis: healthy }`
  - No exposed port (worker is not an HTTP service)
- Pre-pull example agent images on worker startup (best-effort)

**Acceptance:**
- `docker compose up workflow-worker` starts cleanly after `db-migrate` completes
- Worker logs show "ready; concurrency=5"
- Worker can `docker run` a sibling container (verifies socket mount)

---

## T14 — v0.1 e2e + acceptance test suite

**Effort:** L
**Depends on:** T1–T13
**Files touched:**
- `services/workflow-worker/tests/test_e2e.py` (new — integration suite)
- `.github/workflows/workflow-designer-e2e.yml` (new CI job)

**Scope:** one test file with one test per acceptance criterion from the parent spec:

1. **`test_jwt_user_runs_3_node_chain`** — POST a workflow with 3 echo-agent nodes; POST a run with a JWT; poll until status=`succeeded`; assert each `run_nodes` row is `succeeded`; assert output reflects all 3 echoes
2. **`test_api_key_trigger`** — POST a run with a service-account API key; assert `triggered_by_kind='api_key'`
3. **`test_worker_crash_recovery`** — start run; `docker kill` worker mid-run; restart; assert run resumes and completes
4. **`test_rate_limit`** — POST 100 runs rapidly; 101st returns 429 with `Retry-After`
5. **`test_agent_llm_cost_attribution`** — workflow uses `llm-echo-agent`; run; query observability cost records; assert one row tagged with `run_id`
6. **`test_concurrent_node_fanout`** — workflow with 5 parallel nodes; start; observe all 5 `node.started` events within 1s; all complete
7. **`test_cross_team_access_denied`** — team A creates workflow; team B caller `GET /runs/{a_run_id}` → 403

CI runs against a real Postgres + Redis + admin + cache + litellm (with mocked provider) + workflow-worker stack via `docker compose -f infra/docker-compose.test.yml`.

**Acceptance:**
- All 7 tests pass in CI
- Suite runs in < 5 minutes
- Failure of any test blocks the v0.1 milestone tag

---

## Effort summary

| Bucket | Tickets | Total |
|---|---|---|
| Schema | T0, T1, T2 | M + S + S |
| Backend infra | T3, T4 | M + S |
| Admin API | T5, T6, T7 | M + M + M |
| Worker | T8, T9, T10 | L + M + M |
| Frontend | T11 | M |
| Example agent | T12 | S |
| Compose | T13 | S |
| Tests | T14 | L |

Rough estimate: 14 tickets, **~4–6 engineer-weeks** for one focused engineer; 2–3 weeks with 2 engineers running parallel tracks (one on schema+API, one on worker+runtime).

## Open question for execution

1. Who owns each ticket? Recommend assigning T0 first to whoever lands fastest (it blocks everything).
2. Branch strategy: one feature branch per ticket merged into `main-next`, or a long-lived `feat/workflow-designer-v0.1` integration branch with sub-PRs?
3. CI: do we add the new `workflow-designer-e2e.yml` job as required-to-merge from T14 onward, or only at milestone tag time?

---

## What's not in v0.1 (explicit)

- Canvas editor (drag-drop) — v0.5
- Branching / loops / parallel fan-out runtime — v0.5 (T9 only handles linear; v0.5 extends)
- Per-team RBAC beyond simple team-membership check — v0.5
- AKS deployment + K8s ContainerRuntime — v0.5
- Cost ceiling per run — v0.5
- Laptop relay — v1.0
- Templates marketplace — v1.5+
