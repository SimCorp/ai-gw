# Visual Workflow Designer + Async Task Handoff

**Date:** 2026-05-11
**Status:** Approved (all open questions resolved; ready to spec v0.1 implementation tickets)
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
| Identity scope | **Team + project** (consistent with 2026-05-05 v1 design) |
| Event pipeline | **Unified with existing observability bus** — workflow events publish to Service Bus (prod) / in-memory bus (local); SSE is a consumer-group subscriber. No separate `run_events` table. |
| Agent → LLM calls | **Must route through the gateway.** Each run is issued a short-lived scoped API key; agent containers receive it via env and call `cache:8002` like any other caller. Inherits auth, cache, cost attribution, audit. |
| Quotas | **Redis-counter rate limit per team** on `POST /runs` (e.g. 100 runs/hour/team, configurable per team like other rate limits). Per-run cost ceiling deferred to v0.5. |
| Local container spawn | **Worker mounts host docker socket** (`/var/run/docker.sock`). Worker uses host docker to spawn sibling agent containers on the same `aigateway` network. |
| Image registry | **ACR for managed/curated agents** (same registry as v1 services); user-submitted agents may declare any registry in the manifest with admin approval. Local dev allows local-only tags (e.g. `ai-gateway-echo-agent:dev`). |
| Worker concurrency | **Single async worker process, configurable concurrent-container limit** (default 5, governed by an `asyncio.Semaphore`). Horizontal scale by adding worker replicas. |
| Run triggers | **Both user JWTs and service-account API keys** can trigger runs. Auth layer already returns identical `{team_id, project_id, key_id}` for both; `workflow_runs.triggered_by` stores the caller UUID and `triggered_by_kind` (`user` / `api_key`) for audit. |
| Schema migrations | **Alembic** (already a declared dep in `services/admin/pyproject.toml`, not yet wired). One baseline migration captures today's `infra/postgres/init.sql`; new migrations add the 6 designer tables. Companion task before v0.1 implementation. |

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
                      ┌──────────────────────────────────────┐
                      │            Admin (8005)              │
                      │ /agents /workflows /runs             │
                      │ /runs/{id}/stream (SSE) ──┐          │
                      └────┬────────────────────┬─┘          │
                           │                    │            │
                           │                    │ subscribes consumer-group
                           │                    ↓            │
                           │           ┌─────────────────────┴───┐
                           │           │ Observability Bus       │
                           │           │ (Service Bus / in-mem)  │← workflow events
                           │           └─────────────────────────┘
                           ↓
                      ┌────────────────┐    publishes events
                      │   Postgres     │←─────────────────────┐
                      │ - agents       │                      │
                      │ - workflows    │                      │
                      │ - workflow_runs│                      │
                      │ - run_nodes    │                      │
                      │ - work_queue   │← claim-based         │
                      └────────┬───────┘                      │
                               │ SELECT … FOR UPDATE          │
                               │ SKIP LOCKED                  │
                               ↓                              │
                      ┌────────────────┐                      │
                      │ workflow-worker│──────────────────────┘
                      │  - claims jobs │
                      │  - issues scoped API key per run
                      │  - runs containers via host docker
                      │  - publishes events to obs bus
                      └────────┬───────┘
                               │ docker.sock (local) / K8s Job (AKS)
                               ↓
                      ┌────────────────┐
                      │ agent          │  user-built images
                      │ containers     │  env: AIGW_API_KEY, AIGW_BASE_URL=http://cache:8002
                      │                │  LLM calls flow back through auth→cache→litellm
                      └────────────────┘
                               │
                               │  v1.0: also routes through
                               ↓
                      ┌────────────────┐
                      │ agent-relay    │  (v1.0)
                      │  - WS to       │
                      │    laptops     │
                      └────────────────┘
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
  id              UUID PRIMARY KEY,
  slug            TEXT UNIQUE NOT NULL,        -- e.g. "summarizer"
  name            TEXT NOT NULL,
  description     TEXT,
  image           TEXT NOT NULL,               -- e.g. "registry.simcorp/agents/summarizer:1.2.0"
  manifest        JSONB NOT NULL,              -- inputs/outputs schema, env, resources, declared LLM models
  category        TEXT,                        -- for the canvas palette
  managed         BOOLEAN NOT NULL DEFAULT false,
  owner_team_id   UUID,
  owner_project_id UUID,                       -- nullable; some agents are team-wide
  enabled         BOOLEAN NOT NULL DEFAULT true,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Workflow definitions (versioned, immutable per version)
CREATE TABLE workflows (
  id             UUID PRIMARY KEY,
  slug           TEXT NOT NULL,
  team_id        UUID NOT NULL REFERENCES teams(id),
  project_id     UUID REFERENCES projects(id),      -- nullable, matching api_keys/policies pattern
  name           TEXT NOT NULL,
  description    TEXT,
  latest_version INT NOT NULL DEFAULT 1,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (team_id, project_id, slug)
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
  triggered_by  UUID NOT NULL,                -- user UUID or API-key UUID
  triggered_by_kind TEXT NOT NULL,            -- 'user' | 'api_key' (audit)
  team_id       UUID NOT NULL REFERENCES teams(id),
  project_id    UUID REFERENCES projects(id),      -- nullable, inherited from workflow
  scoped_api_key_id UUID REFERENCES api_keys(id),  -- short-lived key issued for this run's agents
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

**Note: no `run_events` table.** Workflow state transitions publish to the existing observability bus (Azure Service Bus in prod, in-memory bus locally). The SSE endpoint subscribes to that bus with a `workflow_run` filter and a consumer group per connected client. Persistence/replay of run history is served by joining `workflow_runs` + `run_nodes` (the source of truth for terminal state); event-level history for forensics is in the observability sink (Application Insights + structured logs).

---

## Worker Service

New service: `services/workflow-worker/`. FastAPI not required — pure asyncio app.

Worker loop (pseudo):

```
on run start (called from admin /runs POST handler):
    issue scoped API key: row in api_keys with team_id+project_id, ttl=run-duration+5m,
        scope='workflow-run', stored as workflow_runs.scoped_api_key_id
    publish bus event 'workflow.run.started' {run_id, team_id, project_id, ...}

while running:                            # workflow-worker main loop
    job = SELECT * FROM work_queue
          WHERE claimed_by IS NULL AND available_at <= NOW()
          ORDER BY available_at
          FOR UPDATE SKIP LOCKED
          LIMIT 1
    if not job: sleep(short); continue

    UPDATE work_queue SET claimed_by=$worker_id, claim_expires=NOW()+'2m'
    publish bus event 'workflow.node.started'
    pull image (cached)
    docker run -e AIGW_API_KEY=<scoped key> \
               -e AIGW_BASE_URL=http://cache:8002 \
               -v inputs.json:/run/inputs.json \
               --network aigateway \
               <image>
    # any LLM call the agent makes lands on cache:8002 with the scoped key —
    # inherits auth, cache, cost attribution, audit automatically
    stream stdout → publish bus events 'workflow.node.log'
    on exit:
        write outputs to run_nodes; publish 'workflow.node.finished'
        evaluate DAG: enqueue successor nodes whose preds are satisfied
        if no more nodes: mark run finished, publish 'workflow.run.finished',
            revoke scoped api key

# stale claims (worker crashed) reclaimed by sweeper that resets expired claim_expires
```

**Container spawning:** workflow-worker is itself a container in compose; it mounts
`/var/run/docker.sock` so it can use the host's docker daemon to spawn sibling agent
containers on the same `aigateway` network. In AKS, the worker runs as a Deployment with
RBAC to create Pods/Jobs in its namespace; the docker.sock pattern is replaced with the
Kubernetes API. Spawning mechanism is abstracted behind a `ContainerRuntime` port
(`runtime.run(image, env, mounts) -> stdout_stream, exit_code`) with two implementations:
`DockerRuntime` and `KubernetesRuntime`.

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
| `POST` | `/runs` | Submit run (`workflow_id`, `version`, `inputs`). Rate-limited per team via Redis counters; default 100 runs/hour/team, overridable per team like other rate limits. Returns 429 + `Retry-After` on excess. |
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

**Prereq (Alembic companion task):**
- `alembic upgrade head` against an empty DB produces a schema byte-identical to today's `init.sql` (verified by `pg_dump --schema-only` diff)
- `db-migrate` compose service runs `alembic upgrade head` instead of `psql -f init.sql`

**Acceptance:**
- A user (JWT) can `POST /runs` with a hand-written 3-node workflow JSON; worker picks up jobs;
  portal run viewer shows nodes transitioning idle→running→done; final output visible
- A service-account API key can `POST /runs`; `workflow_runs.triggered_by_kind = 'api_key'`
- Kill worker mid-run → restart → run resumes (claim expiry reclaim works)
- Rate-limit enforcement: 101st run in an hour returns 429 with `Retry-After`
- Example agent makes an LLM call via `cache:8002` with its scoped API key; cost record appears
  in observability tied to the workflow run (verifies scoped key + gateway path end-to-end)
- Worker can run 5 containers concurrently against the same run (parallel fan-out path)
- Full integration test in `services/workflow-worker/tests/test_e2e.py` runs the above end-to-end
  against a real Postgres + Docker + admin + cache + litellm stack

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
| Loops as DoS vector | Mandatory `max_iterations` + per-team rate limit (v0.1) + cost ceiling (v0.5) |
| docker.sock mount privilege footprint | Worker runs as non-root with explicit allowlist of agent images it can spawn; production AKS path uses K8s RBAC instead of socket |
| SSE consumer-group fan-out cost on bus | v0.1 in-memory bus accepts; production Service Bus has built-in fan-out; verify cost at v0.5 |
| Laptop relay auth | mTLS via short-lived certs issued by admin service; punted to v1.0 spec deep-dive |
| Workflow-version migration | DAG schema validated against versioned JSON schema in repo; old runs immutable |
| Permissions on write-capable agents | Manifest declares `write_capable: true`; admin must approve agent for team+project |
| Scoped API key lifecycle | Key TTL = run duration + 5m grace; revoked on run terminal state; key scope cannot exceed parent caller's scope |
| Project boundary on existing tables | `teams` and `projects` tables must exist with `project_id` FK before this work — verify v1 has these |

**All open questions resolved (2026-05-11 review):**
- ~~Identity scope~~ → team + project (consistent with 2026-05-05); `project_id` nullable to match `api_keys`/`policies` pattern
- ~~Event pipeline~~ → unified on existing observability bus; no `run_events` table
- ~~Agent → LLM call path~~ → must route through gateway via scoped API key
- ~~Quotas~~ → Redis rate limit per team on `POST /runs` (v0.1); cost ceiling deferred to v0.5
- ~~Local container spawn~~ → mount host docker.sock; abstract behind `ContainerRuntime` port
- ~~`projects` table exists~~ → confirmed in `services/admin/app/models/team.py:Project`
- ~~Image registry~~ → ACR for managed agents (same as v1 services); manifest-declared registry allowed for user-submitted with admin approval; any tag locally
- ~~Worker concurrency~~ → single async worker process; configurable container concurrency cap (default 5, asyncio.Semaphore); horizontal scale via replicas
- ~~Run triggers~~ → both user JWTs and service-account API keys; `triggered_by_kind` records which class
- ~~Schema migrations~~ → wire Alembic (already declared in `services/admin/pyproject.toml`); baseline migration ports today's `init.sql`; new migrations add designer tables

**Companion task identified (must land before v0.1 implementation):**
- **Wire Alembic in `services/admin/`.** Add `alembic.ini`, `migrations/env.py`, autogenerate a baseline migration matching current `infra/postgres/init.sql`, switch the `db-migrate` Compose service from `psql -f init.sql` to `alembic upgrade head`. Smoke test: an empty DB after `alembic upgrade head` produces the same schema as today's `init.sql`. ~1-2 days; prerequisite for all subsequent schema work, not just this spec.

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
