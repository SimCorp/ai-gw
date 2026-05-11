# Visual Workflow Designer + Async Task Handoff

**Date:** 2026-05-11
**Status:** Draft — awaiting approval
**Supersedes:** Adds a new layer to the 2026-05-05 AI Gateway Design (does not change v1 components)
**Owner:** TBD

---

## Context

The AI Gateway v1 (auth/cache/litellm/observability/admin) is shipping. The next
layer the platform needs is a way for engineers *and* analysts to assemble
multi-step agent workflows visually, and for those workflows to execute
asynchronously across hosted and remote agents.

Today the repo has registration scaffolding for MCP servers and plugins but no
agent runtime, no task queue, no DAG executor, and no workflow UI. The
`devops_agent` router and `optimization_worker` are point-solutions executing
inside HTTP request lifetimes or fixed-interval asyncio loops — there is no
infrastructure to compose multiple agents into a workflow, persist run state,
or observe runs as they happen.

This spec defines the **target architecture**, then breaks delivery into three
phased milestones (v0.1, v0.5, v1.0) so each milestone is independently
shippable and demoable.

### Non-goals

- Replacing the existing v1 layers (auth/cache/litellm/observability/admin) — this is additive
- A general-purpose workflow engine for arbitrary code; scope is AI-agent composition
- Multi-region deployment (inherits v1 single-region constraint)
- Identity Pool / Agent-DNS pillar — separate spec; this design leaves hooks for it

### Decisions in scope

| Decision | Choice |
|---|---|
| Agent runtime unit | Container image with manifest |
| MVP capabilities | Persisted runs + live observability + versioned templates |
| Topology support | Full DAG including loops (with iteration limits) |
| Async handoff | Durable, at-least-once (Postgres work table + claim-based workers) |
| Local execution | In-cluster v0.1 + v0.5; laptop relay in v1.0 |
| Build/buy | Build in-house; React Flow (xyflow) as the canvas *library* only |
| Persona | Engineers + analysts (simple + advanced canvas modes) |

---

## Target Architecture

```
                                      ┌──────────────────────────────┐
                                      │   Portal (Next.js)           │
                                      │   - Canvas (React Flow)      │
                                      │   - Run viewer (SSE client)  │
                                      └──────────┬───────────────────┘
                                                 │ HTTPS + SSE
                                                 ↓
[Auth (8001)] ── ── ── ── ── ── ── ── ── ── ──── [Admin (8005)]
                                                 │   - /agents       (registry)
                                                 │   - /workflows    (definitions, versions)
                                                 │   - /runs         (submit, list, stream)
                                                 │   - /runs/{id}/stream (SSE event firehose)
                                                 ↓
                                       ┌─────────────────────┐
                                       │   Postgres          │
                                       │  - agents           │
                                       │  - workflows        │
                                       │  - workflow_runs    │
                                       │  - run_nodes        │
                                       │  - run_events       │
                                       │  - work_queue       │← claim-based
                                       └──────────┬──────────┘
                                                  │ SELECT … FOR UPDATE SKIP LOCKED
                                                  ↓
                                       ┌─────────────────────┐
                                       │  workflow-worker    │ (new service)
                                       │  - claims jobs      │
                                       │  - runs containers  │
                                       │  - writes events    │
                                       └──────────┬──────────┘
                                                  │ docker (local) / K8s Job (AKS)
                                                  ↓
                                       ┌─────────────────────┐
                                       │  agent containers   │  ← user-built images
                                       │  (registered images)│     conforming to manifest
                                       └─────────────────────┘
                                                  │
                                                  │  v1.0: also routes through
                                                  ↓
                                       ┌─────────────────────┐
                                       │  agent-relay (v1.0) │
                                       │  - WS to laptops    │
                                       │  - proxies /run     │
                                       └─────────────────────┘
```

**Key principles:**

1. **Workflow definitions are data, not code.** A workflow is a JSON DAG persisted in `workflows`.
   Versions are immutable; an edit creates a new version row.
2. **Runs are durable state machines.** A run is a row in `workflow_runs`. Each node's
   per-run state lives in `run_nodes`. Workers crash-safely resume by reclaiming
   stale entries in `work_queue`.
3. **Events are append-only.** Every state transition writes to `run_events`. The SSE
   stream is a tail of this table, so live observers and post-mortem viewers use the
   same data.
4. **Agents have one contract.** A registered agent is an image + manifest declaring inputs,
   outputs, env vars, and a single entrypoint that reads JSON from a mounted file and writes
   JSON to another. The same contract works for in-cluster Pods/Jobs (v0.1/v0.5) and for
   laptop-hosted relays (v1.0) — the relay just proxies the contract over WS.

---

## Data Model

```sql
-- Agent registry (extends MCP/Plugin pattern from services/admin/app/models/)
CREATE TABLE agents (
  id            UUID PRIMARY KEY,
  slug          TEXT UNIQUE NOT NULL,        -- e.g. "summarizer"
  name          TEXT NOT NULL,
  description   TEXT,
  image         TEXT NOT NULL,               -- e.g. "registry.simcorp/agents/summarizer:1.2.0"
  manifest      JSONB NOT NULL,              -- inputs/outputs schema, env, resources
  category      TEXT,                        -- for the canvas palette
  managed       BOOLEAN NOT NULL DEFAULT false,
  owner_team_id UUID,
  enabled       BOOLEAN NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Workflow definitions (versioned, immutable per version)
CREATE TABLE workflows (
  id            UUID PRIMARY KEY,
  slug          TEXT NOT NULL,
  team_id       UUID NOT NULL,
  name          TEXT NOT NULL,
  description   TEXT,
  latest_version INT NOT NULL DEFAULT 1,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (team_id, slug)
);

CREATE TABLE workflow_versions (
  workflow_id   UUID NOT NULL REFERENCES workflows(id),
  version       INT NOT NULL,
  dag           JSONB NOT NULL,              -- nodes, edges, conditions, loop bounds
  created_by    UUID NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (workflow_id, version)
);

-- Run state
CREATE TYPE run_status AS ENUM ('pending','running','succeeded','failed','cancelled');

CREATE TABLE workflow_runs (
  id            UUID PRIMARY KEY,
  workflow_id   UUID NOT NULL REFERENCES workflows(id),
  version       INT NOT NULL,
  status        run_status NOT NULL DEFAULT 'pending',
  inputs        JSONB,
  outputs       JSONB,
  error         TEXT,
  triggered_by  UUID NOT NULL,
  team_id       UUID NOT NULL,
  started_at    TIMESTAMPTZ,
  finished_at   TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE run_nodes (
  run_id        UUID NOT NULL REFERENCES workflow_runs(id),
  node_id       TEXT NOT NULL,               -- DAG-local id
  iteration     INT NOT NULL DEFAULT 0,      -- for loops
  status        run_status NOT NULL DEFAULT 'pending',
  agent_id      UUID REFERENCES agents(id),
  inputs        JSONB,
  outputs       JSONB,
  error         TEXT,
  started_at    TIMESTAMPTZ,
  finished_at   TIMESTAMPTZ,
  PRIMARY KEY (run_id, node_id, iteration)
);

-- Append-only event log; backing store for SSE
CREATE TABLE run_events (
  id            BIGSERIAL PRIMARY KEY,
  run_id        UUID NOT NULL REFERENCES workflow_runs(id),
  ts            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  kind          TEXT NOT NULL,               -- 'run.started', 'node.started', 'node.token', 'node.finished', 'run.finished'
  payload       JSONB
);

-- Claim-based work queue (no Redis dependency for queueing)
CREATE TABLE work_queue (
  id            BIGSERIAL PRIMARY KEY,
  run_id        UUID NOT NULL REFERENCES workflow_runs(id),
  node_id       TEXT NOT NULL,
  iteration     INT NOT NULL DEFAULT 0,
  available_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  claimed_by    TEXT,                        -- worker id, null until claimed
  claim_expires TIMESTAMPTZ,                 -- reclaim if expired
  attempts      INT NOT NULL DEFAULT 0
);
CREATE INDEX work_queue_available_idx ON work_queue (available_at) WHERE claimed_by IS NULL;
```

---

## Worker Service

New service: `services/workflow-worker/`. FastAPI not required — pure asyncio app.

Worker loop (pseudo):

```
while running:
    job = SELECT * FROM work_queue
          WHERE claimed_by IS NULL AND available_at <= NOW()
          ORDER BY available_at
          FOR UPDATE SKIP LOCKED
          LIMIT 1
    if not job: sleep(short); continue

    UPDATE work_queue SET claimed_by=$worker_id, claim_expires=NOW()+'2m'
    emit run_event 'node.started'
    pull image (cached)
    run container with inputs.json mounted; stream stdout → run_events as 'node.token'
    on exit:
        write outputs to run_nodes; emit 'node.finished'
        evaluate DAG: enqueue successor nodes whose preds are satisfied
        if no more nodes: mark run finished, emit 'run.finished'
    delete work_queue row

# stale claims (worker crashed) are reclaimed by a sweeper task that resets claim_expires
```

DAG evaluation handles:
- Linear, branching (edges have JSONPath conditions)
- Parallel fan-out / join (multiple successors, join nodes wait for all preds)
- Loops (loop node has `max_iterations`; iteration count stored in `run_nodes`)
- Cost cap per run (sum of token+container-time exceeds budget → fail run)

---

## APIs (admin service)

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/agents` | List registered agents (palette source) |
| `POST` | `/agents` | Register/upsert agent (admin only) |
| `GET`  | `/workflows` | List team workflows |
| `POST` | `/workflows` | Create new workflow (slug+team unique) |
| `POST` | `/workflows/{id}/versions` | Save new version of DAG |
| `GET`  | `/workflows/{id}/versions/{v}` | Fetch DAG |
| `POST` | `/runs` | Submit run (`workflow_id`, `version`, `inputs`) |
| `GET`  | `/runs/{id}` | Fetch run + node status |
| `GET`  | `/runs/{id}/stream` | **SSE** firehose of events for live observability |
| `POST` | `/runs/{id}/cancel` | Cooperative cancel |

Auth: all endpoints behind existing `require_admin_auth` / team-scoped checks.

---

## Frontend (apps/portal)

Reuses existing Next.js + React 19 patterns (see `apps/portal/app/portal/mcp/page.tsx`).

New pages:
- `/portal/workflows` — list + create
- `/portal/workflows/[id]/designer` — canvas editor (React Flow)
- `/portal/workflows/[id]/runs` — run history
- `/portal/workflows/[id]/runs/[runId]` — live run viewer (SSE)

Canvas modes:
- **Simple** (default) — analyst-friendly: palette → drop → connect → run. Forms for inputs. No JSON.
- **Advanced** — engineer-friendly: edit raw DAG JSON, see resource manifests, configure retry/loop bounds.

Toggle stored per-user.

---

## Phased Roadmap

### v0.1 — Vertical slice ("Hello DAG")
**Goal:** prove the entire architecture works end-to-end with the minimum viable execution.

**In:**
- DB tables: `agents`, `workflows`, `workflow_versions`, `workflow_runs`, `run_nodes`, `run_events`, `work_queue`
- Admin routes: `/agents` (GET), `/workflows` POST+GET, `/runs` POST+GET+SSE
- New `workflow-worker` service running `docker run` for each node
- One example agent image (e.g. `echo-agent`) committed to the repo
- Portal: read-only run viewer at `/portal/workflows/[id]/runs/[runId]` with live SSE status (no editing)
- Linear DAGs only at the executor level; schema supports branches but UI/runtime defers them

**Out:** canvas editing, branching, loops, templates UI, AKS deploy.

**Acceptance:**
- A user can `POST /runs` with a hand-written 3-node workflow JSON; worker picks up jobs;
  portal run viewer shows nodes transitioning idle→running→done; final output visible
- Kill worker mid-run → restart → run resumes (claim expiry reclaim works)
- Full integration test in `services/workflow-worker/tests/` runs the above end-to-end against a real Postgres + Docker

### v0.5 — Full features (in-cluster)
**Goal:** make it usable.

**In:**
- Canvas editor at `/portal/workflows/[id]/designer` (React Flow)
- Branching/conditional edges (JSONPath on prior output → boolean)
- Loop nodes with iteration cap + cycle detection
- Workflow versioning UI (diff between versions; clone)
- Per-team RBAC: only team members can edit/run team workflows
- Cost attribution per run (token spend + container seconds rolled into observability)
- Node retry policy in manifest
- AKS deploy (workflow-worker as Deployment; agent containers as K8s Jobs)

**Acceptance:**
- Analyst persona test: write a 5-node branching workflow without touching JSON
- Engineer persona test: edit the same workflow in advanced mode
- 100 concurrent runs → SLO: p99 enqueue→complete (excluding container time) < 2s
- Cost dashboard shows workflow run breakdown per team

### v1.0 — Laptop relay + hardening
**Goal:** support remote/laptop-hosted agents and harden for production.

**In:**
- `agent-relay` service: gateway-initiated WebSocket; laptop CLI (`aigw-agent`) registers
- Agent identity: signed registration tokens (groundwork for the Identity Pool pillar)
- Relay-aware worker: when agent's manifest is `kind: relay`, dispatch via WS instead of K8s Job
- Chaos test suite: kill worker, kill Postgres connection, kill relay mid-run
- Load test: 1000 concurrent runs, 50 relay-hosted agents
- Runbook for ops: workflow-stuck triage, queue backlog alerts

**Acceptance:**
- Demo: a developer runs `aigw-agent serve ./my-agent` on a laptop; the agent appears in the
  portal palette; a workflow uses it; the run executes through the relay
- All chaos scenarios recover without data loss
- Cost ceiling enforced: a loop with no progress is killed at $5 spend

---

## Critical Files

**New code:**
- `services/admin/app/models/agent.py` — extends pattern from `mcp.py:1`
- `services/admin/app/models/workflow.py`
- `services/admin/app/models/workflow_run.py`
- `services/admin/app/routers/agents.py` — extends pattern from `services/admin/app/routers/devops_agent.py:1`
- `services/admin/app/routers/workflows.py`
- `services/admin/app/routers/runs.py` (includes SSE)
- `services/workflow-worker/` — new service (Dockerfile, pyproject, app/main.py, app/executor.py, app/dag.py, tests/)
- `apps/portal/app/portal/workflows/` — new pages
- `apps/portal/lib/workflows/` — React Flow components

**Modified:**
- `infra/docker-compose.yml` — add `workflow-worker` service (and `agent-relay` at v1.0)
- `infra/postgres/init.sql` — schema migrations
- `services/admin/app/main.py` — register new routers
- `apps/portal/app/portal/agents/page.tsx` — currently stub; flesh out as palette source

**Reused functions/patterns (do not duplicate):**
- DB engine + session pattern: `services/admin/app/db.py`
- Redis client pattern: `services/admin/app/redis_utils.py`
- Auth dependency: `services/admin/app/auth.py:require_admin_auth`
- Async worker pattern: `services/admin/app/workers/optimization_worker.py` (loop+cancel structure)
- Portal page pattern: `apps/portal/app/portal/mcp/page.tsx`
- Existing MCP/Plugin registry shape: `services/admin/app/models/mcp.py`, `plugin.py`

---

## Risks and Open Questions

| Risk | Mitigation |
|---|---|
| Container cold-start dominates run latency | Image pre-pull on worker boot; consider warm pool in v0.5 |
| Image registry: where do agent images live? | **Open question** — use existing ACR? Add private Harbor? Decide before v0.1 |
| Loops as DoS vector | Mandatory `max_iterations` + cost ceiling per run |
| SSE doesn't fan out — 100 viewers on a hot run | v0.1 accepts; v1.0 introduces Redis pubsub fan-out |
| Laptop relay auth | mTLS via short-lived certs issued by admin service; punted to v1.0 spec deep-dive |
| Workflow-version migration | DAG schema validated against versioned JSON schema in repo; old runs immutable |
| Permissions on write-capable agents | Manifest declares `write_capable: true`; admin must approve agent for team |

**Open questions to resolve before v0.1 implementation:**
1. Image registry choice (ACR vs internal Harbor vs none)
2. Worker concurrency model (one container per worker process, or one worker per pool of containers)
3. Whether `triggered_by` in `workflow_runs` accepts API-key callers or only user JWTs
4. Quota model: token cost vs container seconds vs both

---

## Verification

### v0.1
- Unit: DAG evaluator (branch satisfaction, join logic, loop iteration tracking)
- Integration test in `services/workflow-worker/tests/test_e2e.py`:
  1. Start Docker + Postgres + admin + worker
  2. POST a 3-node linear workflow definition
  3. POST a run
  4. Poll `GET /runs/{id}` until `succeeded`
  5. Assert event log contains 3 `node.started` + 3 `node.finished` + 1 `run.finished`
- Crash test: kill worker, assert run resumes within `claim_expires`
- Portal manual smoke: run viewer shows live status

### v0.5
- Playwright: build a 5-node branching workflow in the canvas, run it, see output
- Load (k6): 100 concurrent runs; p99 enqueue→complete < 2s (excluding container time)
- RBAC: cross-team access denied
- Cost dashboard reflects run spend

### v1.0
- Smoke: `aigw-agent` CLI registers a laptop agent, workflow runs through relay
- Chaos: kill worker / Postgres / relay mid-run; verify recovery
- Load: 1000 concurrent runs with 50 relay-hosted agents
- Runbook drill: ops team resolves a stuck-run incident using runbook

---

## Out of Scope (this spec)

- Identity Pool / Agent-DNS pillar (separate spec; this design leaves the hook in `agents.id` + relay token signing)
- Auto-Drive routing (separate spec; reads from `run_events` but doesn't change runtime)
- AI Librarian / shared grounding store (separate spec)
- Multi-region active-active
- Workflow marketplace / cross-team sharing (v1.5+)
