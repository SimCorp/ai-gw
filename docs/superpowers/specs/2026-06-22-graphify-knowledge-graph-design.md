# Graphify — Knowledge-Graph Service Design Spec

**Date:** 2026-06-22
**Author:** benjamin
**Status:** Implemented — shipped via #100/#102 (service), #107 (admin portal page + proxy), #110/#111 (build-env fixes)

> This documents the as-built service. It is grounded in the code under
> `services/graphify/`, `services/admin/app/routers/graphify.py`, and the
> `apps/admin/app/(app)/knowledge-graphs/` portal page — not a forward-looking plan.

---

## Overview

**Graphify** registers GitHub repos, builds a queryable semantic knowledge graph of each
codebase (code parsing plus optional LLM doc/media extraction), and exposes query APIs so
agents can navigate a repo *by concept* instead of grepping files. It answers questions
like "where is auth enforced?", "what connects the cache to litellm?", or "explain this
module and its neighbourhood" against a pre-built graph rather than against raw source.

The first target repo is `ims` (issue #100).

**Goals:**
- Give agents (and the admin portal) a concept-level map of a repo, not a file listing.
- Keep all build-time LLM extraction on the governed gateway path — never a direct provider key.
- Isolate heavy builds (large repos, Whisper/media extraction) from the query API so a
  build can't OOM the request surface.

**Non-goals:** Incremental/delta indexing, per-repo build prioritisation, multi-worker
concurrency, automatic retry of failed builds. (See [Known limitations](#known-limitations).)

---

## Architecture

Graphify ships as **two containers from one image**, both added to
`infra/docker-compose.yml`:

- **`graphify`** — the query + management API, port **8012** (Caddy-fronted at
  `/api/graphify/*`).
- **`graphify-worker`** — a background build runner (`python -m app.worker`), `mem_limit:
  4g` so a large extraction can't take down the API.

They share a named volume (`graphify_out` → `/graphify-out`) holding all build artefacts,
and a Postgres registry (`graph_repos`, `graph_builds`) for repo state and the build queue.

```
admin-portal :3001 ─► admin :8005 ─(X-Service-Token)─► graphify :8012 ─► auth :8001   (sk-* validation)
agents (sk-*)      ──────────────────────────────────► graphify :8012 ─► cache :8002  (build-time extraction LLM)
                                                              │
                                  graph_repos / graph_builds  ▼  (Postgres registry + build queue)
                                                        graphify-worker  ─► git clone/pull ─► `graphify extract`
                                                              │
                                                        graphify_out volume (graph.json / graph.html / GRAPH_REPORT.md)
```

**Service responsibilities:**
- **Repo registry** — register/list/delete repos; track build status (`registered →
  building → ready | failed`) and `last_commit` / `last_built_at`.
- **Build queue** — FIFO `graph_builds` table; the worker claims jobs with `FOR UPDATE
  SKIP LOCKED`, clones/pulls, runs `graphify extract`, records node/edge counts and a
  log tail.
- **Query surface** — `GET /query` plus MCP tools (`graph_query`, `graph_path`,
  `graph_explain`, `graph_stats`, `list_repos`) that wrap the local `graphify` CLI against
  the built `graph.json`. Pure local retrieval — no LLM, no network at query time.
- **Artefact serving** — markdown report and interactive HTML graph per repo.

---

## Data model (`graph_repos`, `graph_builds`)

Schema is bootstrapped idempotently on startup (`app/db.py:bootstrap_schema`).

`graph_repos`: `id`, `name` (unique), `github_url`, `ref` (default `main`), `last_commit`,
`last_built_at`, `status` (`registered|building|ready|failed`), `enabled`, `created_at`.

`graph_builds`: `id`, `repo_id` (FK → `graph_repos` ON DELETE CASCADE), `status`
(`queued|running|succeeded|failed`), `claimed_by` (worker id), `log_tail` (last 8000
chars), `error`, `nodes`, `edges`, `queued_at`, `started_at`, `finished_at`. Indexed on
`(repo_id, queued_at DESC)` and a partial index on `queued_at WHERE status='queued'` for
the claim path.

Artefact layout under the shared volume (`app/db.py` is the single source of truth):
`/graphify-out/{name}/src` (clone) and `/graphify-out/{name}/graphify-out/{graph.json,
graph.html, GRAPH_REPORT.md}`.

---

## HTTP API

All registry/query endpoints require **either** a valid `sk-*` Bearer (validated against
`auth:8001`) **or** a matching `X-Service-Token` (constant-time compared) for trusted
internal callers such as the admin proxy. Discovery endpoints are public.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/repos` | sk-* / token | Register a repo (`{name, github_url?, ref}`), auto-queues a build (201) |
| `GET` | `/repos` | sk-* / token | List repos with status |
| `POST` | `/repos/{name}/rebuild` | sk-* / token | Queue a fresh build (202) |
| `DELETE` | `/repos/{name}` | sk-* / token | Remove repo + artefacts (204) |
| `GET` | `/repos/{name}/builds` | sk-* / token | Build history |
| `GET` | `/query` | sk-* / token | `?repo=&q=&budget=2000&dfs=false` → text subgraph; 409 if not built |
| `GET` | `/repos/{name}/report` | sk-* / token | `GRAPH_REPORT.md` (text/markdown) |
| `GET` | `/repos/{name}/graph.html` | sk-* / token | Interactive HTML graph |
| `GET` | `/health` | public | Liveness |
| `GET` | `/mcp`, `/mcp/manifest`, `/mcp/tools` | public | MCP discovery |
| `POST` | `/mcp/tools/{tool}` | sk-* | REST-style MCP tool call |
| `POST` | `/mcp` | sk-* for `tools/call` | JSON-RPC 2.0 (`initialize`, `tools/list`, `tools/call`, `ping`) |
| `GET` | `/mcp/sse` | sk-* | SSE transport |

Repo names are validated against `^[a-z0-9][a-z0-9._-]{0,99}$` and the `repo` query
param is validated at the choke point, rejecting path traversal (422). Non-GitHub HTTPS
URLs are rejected.

**MCP tools:** `list_repos`, `graph_query` (`{repo, question, budget?, dfs?}`),
`graph_path` (`{repo, source, target}`), `graph_explain` (`{repo, node}`), `graph_stats`
(`{repo, top_n?}` → counts + highest-degree "god nodes").

On startup the service best-effort registers itself as an MCP server with `admin:8005`.

---

## Build pipeline & gateway governance

`graphify-worker` polls `graph_builds`, claims the oldest queued job, then
(`app/builder.py`):

1. **Clone/pull** with `--depth 1`. The GitHub PAT is passed via a per-invocation
   `http.extraHeader` arg (never written to `.git/config`) and scrubbed from all logs.
2. **Extract** (`graphify extract`). The crucial governance rule (#110/#111):
   - The build env is **stripped of every direct provider key** (`ANTHROPIC_*`,
     `OPENAI_*`, `GEMINI_*`, …) so graphify can never auto-detect and call a provider
     directly.
   - If `GRAPHIFY_GATEWAY_KEY` is set, extraction runs `--backend openai` with
     `OPENAI_BASE_URL=http://cache:8002/v1` and the gateway key — i.e. all extraction LLM
     traffic flows through the **governed cache → litellm path**, budget- and policy-checked
     like any other caller.
   - If no gateway key is set, the build still runs **code-only** (offline); doc/PDF/media
     extraction is skipped rather than failing the whole build (#110).
3. **Record** node/edge counts (parsed from `graph.json`), a truncated log tail, and the
   HEAD commit via `db.finish_build`.

Query-time (`app/query.py`) is pure local CLI retrieval against `graph.json` — no LLM and
no network — so queries are cheap and don't consume gateway budget.

---

## Configuration

Key settings (`app/config.py`, supplied via `infra/docker-compose.yml`):

| Env var | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | — | Registry + build queue (Postgres) |
| `AUTH_URL` | `http://auth:8001` | sk-* validation |
| `GRAPHIFY_OPENAI_BASE_URL` | `http://cache:8002/v1` | Build-time extraction LLM (governed gateway) |
| `GRAPHIFY_OPENAI_MODEL` | `gpt-4o-mini` | Extraction model |
| `GRAPHIFY_GATEWAY_KEY` | `""` | sk-* for extraction; empty ⇒ code-only builds |
| `GITHUB_TOKEN` | `""` | Read-only PAT (from `pass`, never hand-written) |
| `GITHUB_ORG` | `SimCorp` | Org prefix for short-name registration |
| `GRAPHIFY_SERVICE_TOKEN` | `""` | Shared secret for the admin proxy; must match on both sides |
| `GRAPHIFY_OUT_DIR` | `/graphify-out` | Shared artefact volume |
| `WORKER_ID` | `graphify-worker-1` | Recorded in `graph_builds.claimed_by` |
| `BUILD_POLL_INTERVAL_SECONDS` | `5` | Worker idle poll interval |

Deploy prerequisites: `GITHUB_TOKEN` and `GRAPHIFY_GATEWAY_KEY` must be present in the
stack `.env` (sourced from `pass`) for private-repo cloning and doc extraction respectively.

---

## Admin portal integration

The admin **Knowledge Graphs** page (`apps/admin/app/(app)/knowledge-graphs/page.tsx`)
manages repos, watches build progress (polls every 4s while building), runs queries, and
views the report/graph. It never talks to graphify directly — it goes through the
admin backend proxy (`services/admin/app/routers/graphify.py`), which authenticates the
admin session and forwards to `graphify:8012` with the `X-Service-Token`. The interactive
graph is embedded in a sandboxed iframe (`allow-scripts` only, **no** `allow-same-origin`)
so the rendered HTML can't reach the admin token.

Proxy endpoints (prefix `/graphify`, admin-auth required): `GET/POST /repos`, `POST
/repos/{name}/rebuild`, `DELETE /repos/{name}`, `GET /repos/{name}/builds`, `GET /query`,
`GET /repos/{name}/report` (→ `{markdown}`), `GET /repos/{name}/graph_html` (→ `{html}`).

---

## Testing

- `services/graphify/tests/` — `test_repos.py` (registration, lifecycle, path-traversal
  rejection, query authz), `test_build.py` (build lifecycle, queue claim, stats parsing,
  and the **gateway-governance** assertions: provider keys scrubbed, `--backend openai`
  only when a gateway key is set), `test_mcp.py` (public discovery vs. authed tool calls,
  JSON-RPC dispatch, `X-Service-Token` bypass). Run against a real Postgres via
  `testcontainers`.
- `services/admin/tests/test_graphify.py` — the admin proxy router: admin-auth required,
  correct `X-Service-Token` forwarding, report/graph_html wrapping.

---

## Known limitations

Tracked for future work, intentionally out of scope for V1:
- **Single worker, FIFO, no priority** — a large repo build blocks smaller ones.
- **No automatic retry** of failed builds (re-trigger via rebuild).
- **No incremental indexing** — each rebuild re-indexes the whole repo.
- **Shared gateway key** — all repos extract under one key; one repo's cost can affect the
  shared budget.
- **Best-effort artefact cleanup** on delete (`shutil.rmtree(..., ignore_errors=True)`).
