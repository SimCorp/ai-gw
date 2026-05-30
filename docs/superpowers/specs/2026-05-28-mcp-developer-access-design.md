# MCP Developer Access — AI Gateway Developer Platform

**Date:** 2026-05-28
**Status:** Draft — needs reconciliation (see "Open issues" below)
**Scope:** Expose AI Gateway capabilities as MCP servers so developers' own AI agents can consume gateway services, authenticated with their existing `sk-*` API keys (~2000 engineers)

> ⚠️ **Open issues (found on post-recovery codebase review, 2026-05-29).** The original brainstorm was unaware the gateway already has an MCP story, and its admin section uses scope names that don't exist. Before implementing:
> 1. **The gateway already exposes MCP to developers — in the *opposite* direction.** `services/admin/app/routers/mcp.py` is a shipped **outbound MCP registry**: admins register *external* MCP servers (SSRF-guarded, ping/handshake, tool sync, a tool-call proxy, per-team access grants via `mcp_server_access`), surfaced in **both** portals (`apps/admin/app/admin/mcp/page.tsx`, `apps/portal/app/portal/mcp/page.tsx`) with a tool-runner UI. This spec proposes the *inbound* direction (gateway services *as* MCP servers). Decide whether the two are complementary or overlapping before building — and pick names/paths that don't make "MCP" mean two opposite things.
> 2. **The admin MCP tool section (Section 5) is blocked.** Its scopes (`keys:self.write`, `team:manage`, `team:read`) don't exist. The real taxonomy (`services/admin/app/scopes.py`) is `ai-gw:<resource>:<action>` — e.g. `ai-gw:key:create`, `ai-gw:key:revoke`, `ai-gw:team:write`. The `developer` role holds **none** of these, so the "self-service tier" has no basis under the current model without either granting developers key scopes (a security change) or inventing a self-scope (new taxonomy). This is a design decision, not a rename.
> 3. **librarian + observability sections are sound** and can proceed independently of the above.

---

## Overview

Developers building agentic workflows on the AI Gateway want their own AI agents (Claude Code, Cursor, etc.) to reach gateway capabilities directly — searching the knowledge base, checking their usage and rate limits, and performing self-service key/team operations — without hand-rolling REST clients. This design exposes those capabilities as **Model Context Protocol (MCP)** endpoints that a developer adds to their IDE/agent config, authenticated with the same `sk-*` key they already use for LLM traffic.

**Primary goals:**
- Let developer agents consume gateway services through a standard MCP surface, reusing existing `sk-*` auth
- Reuse the per-service MCP pattern the codebase already has, rather than building a new gateway service
- Keep the surface safe: read-only where possible, strict team scoping, scope-gated control-plane ops, no prompt/response content leakage
- Ship as a low-risk experiment that can grow per-tool if developers actually adopt it

**Non-goals (this iteration):** a federated single-URL MCP gateway, MCP tools on identity/agent-relay, and a new transport beyond the JSON-RPC-over-HTTP-POST the codebase already uses.

---

## Design decision: per-service MCP, not a new gateway

The brainstorm initially considered three approaches:

- **A. Thin proxy MCP service** — a new `services/mcp-gateway` on `:8011`, proxied at `/mcp/`, authenticating `sk-*` and forwarding each tool call to the relevant internal service. Ships in ~a week, low risk.
- **B. Smart MCP service** — same as A but enriching calls (auto team-scoping, agent-tuned formatting). Better UX, but risks the MCP layer becoming a second source of truth.
- **C. MCP-first redesign** — every service exposes its own MCP tools, federated by a gateway. Most flexible, but rewrites service boundaries for an unproven use case. YAGNI.

While scoping A, we found the codebase **already has a per-service MCP pattern**:

- `services/memory/app/main.py` already exposes `/mcp`, `/mcp/tools`, `/mcp/manifest` with ~20 mempalace tools.
- The `MCPServer` implementation lives in `services/admin/app/mcp_protocol.py` (memory copies it inline).

That changed the choice. **Decision: add per-service MCP endpoints matching the memory pattern — no new gateway service.** Developers add one MCP server per service to their IDE config, each authenticated with their own `sk-*` key.

---

## Architecture

Three services gain (or already have) MCP endpoints. Each follows the memory pattern exactly: **JSON-RPC 2.0 over HTTP POST**, an `MCPServer` instance per app, tools registered at module load, per-request caller context bound to a `ContextVar`. `MCP_PROTOCOL_VERSION = "2024-11-05"`.

```
Developer's AI agent (Claude Code / Cursor)  — configured with sk-* key
        │
        ├── POST /librarian/mcp        → librarian service (:8008)   [new]
        ├── POST /observability/mcp    → observability service (:8004) [new]
        ├── POST /admin/mcp            → admin service (:8005)        [new]
        └── POST /memory/mcp           → memory service (:8009)       [existing, unchanged]

Each /mcp endpoint:
   1. Authenticates Bearer sk-* via auth /validate
   2. Binds caller context (team_id, scopes) to a ContextVar
   3. Dispatches the JSON-RPC tool call to a handler that reuses existing service logic
```

No new nginx config — existing `/librarian/`, `/observability/`, `/admin/`, `/memory/` proxies already cover the new `/mcp` paths. No new compose services. No DB migrations.

### Shared package: `packages/mcp-common/`

`mcp_protocol.py` is currently duplicated between `services/admin/` and copy-pasted inline into `services/memory/`. Adding two more copies would mean four. **Decision: extract it to `packages/mcp-common/`** (we already have `packages/` for shared code) as part of this work, since we touch all four call sites anyway.

```
packages/mcp-common/
├── pyproject.toml          # name: ai-gateway-mcp-common
└── ai_gateway_mcp/
    ├── __init__.py
    ├── server.py           # MCPServer class (extracted from admin/app/mcp_protocol.py)
    └── auth.py             # resolve_caller(request) -> CallerContext
```

`MCPServer.handle(body, request)` stays byte-for-byte identical to today's behavior. Memory + admin are migrated to import from the package in the same PR (a one-line change each, behavior unchanged). Memory's existing `get_developer_id()` becomes a thin wrapper around the shared `resolve_caller()`.

---

## Tool inventory

### librarian (new) — 1 tool

Thin wrap of the existing `/search`, no new logic.

| Tool | Inputs | Returns |
|---|---|---|
| `librarian_search` | `query` (string, required), `topic` (string, optional), `tags` (string[], optional), `limit` (int 1–50, default 10) | Array of `{title, snippet, source_url, topic, tags, score}` — calls existing `search_knowledge()` |

### observability (new) — 4 tools, all team-scoped, read-only

The caller's `team_id` is resolved via auth `/validate` (same pattern memory uses for `developer_id`); agents only ever see their own team's data. Observability is write-only today (just `POST /events`), so this work adds read endpoints under the hood (`GET /usage`, `GET /errors`, `GET /rate-limit`) and the MCP tools wrap them.

| Tool | Inputs | Returns |
|---|---|---|
| `usage_summary` | `period` ("today" \| "7d" \| "30d", default "7d") | `{requests, tokens_input, tokens_output, cost_usd, cache_hit_rate, top_models: [{model, requests, cost_usd}]}` |
| `recent_errors` | `limit` (1–50, default 10) | Array of `{timestamp, model, error_type, error_message, latency_ms}` — last N error events |
| `rate_limit_status` | none | `{requests_remaining, window_reset_at, daily_budget_remaining_usd}` — current state from Redis counters |
| `recent_calls` | `limit` (1–20, default 5), `only_errors` (bool, default false) | Array of recent `GatewayEvent`s, **redacted** — metadata only, no prompts/responses |

**Deliberate omissions (YAGNI):** no write tools (agents shouldn't mutate telemetry); no cross-team queries (privacy + auth complexity); `recent_calls` never returns prompt/response content (that's a separate, sensitive feature).

### admin (new) — self-service + manager tiers, scope-gated

`admin/app/mcp_protocol.py` has the `MCPServer` class but no tools wired up yet. Auth nuance: `sk-*` keys are **data-plane** (LLM traffic); admin ops normally go through **portal session tokens** (human-in-browser). So we must decide what an agent holding a user's `sk-*` is allowed to do. `app/scopes.py` already defines control-plane scopes — tool handlers check the scope returned by auth `/validate` and gate accordingly.

**Self-service tier** (any `sk-*` key — caller acting on their own resources):

| Tool | Inputs | Returns | Required scope |
|---|---|---|---|
| `list_my_api_keys` | none | Array of `{key_id, name, scopes, created_at, last_used_at}` (key_id never exposes the raw secret) | none — implicit from caller identity |
| `rotate_my_api_key` | `key_id` (uuid) | `{new_key: "sk-...", key_id, expires_at_of_old}` — old key revoked after a 60s grace window | `keys:self.write` |
| `revoke_my_api_key` | `key_id` (uuid) | `{revoked: true}` | `keys:self.write` |
| `list_my_teams` | none | Array of `{team_id, name, role}` for teams the caller belongs to | none |
| `team_info` | `team_id` (uuid) | `{name, members: [{developer_id, role}], projects: [{id, name}]}` — only for teams the caller is in | `team:read` |

**Manager tier** (gated on `team:manage` — most `sk-*` keys won't have it):

| Tool | Inputs | Returns | Required scope |
|---|---|---|---|
| `add_team_member` | `team_id`, `developer_id`, `role` ("member" \| "manager") | `{added: true}` | `team:manage` |
| `remove_team_member` | `team_id`, `developer_id` | `{removed: true}` | `team:manage` |

Scope-check failure → JSON-RPC `-32000` with message `"insufficient_scope"` and `data.required_scope` so the agent can tell the user what's missing.

**Deliberately NOT exposed** (high-risk + low-frequency — keep humans in the loop): creating/deleting teams; scanner targets/quotas/kill-switch; SCIM user provisioning; identity token issuance (already admin-only); cross-team or org-wide queries.

Each admin tool handler reuses the existing route functions in `services/admin/app/routers/api_keys.py` and `routers/teams.py` directly — import + call, no API roundtrip. Audit-log entries are tagged `source: "mcp"` so operators can see which actions came through agents.

### memory (existing) — unchanged

Memory's `/mcp` and its ~20 mempalace tools stay as-is, beyond migrating to import `MCPServer` from `packages/mcp-common/`.

---

## Auth, error handling, timeouts

### Auth flow

Every `/mcp` POST is authenticated up front, the same way the cache service authenticates today:

1. Pull `Authorization: Bearer sk-*` header.
2. Call `POST {AUTH_URL}/validate` with the token.
3. Auth returns `{team_id, project_id, key_id, scope}` on success; `401` / `429` otherwise.
4. Bind `team_id` (and scopes) to a `ContextVar` for the request duration.
5. Tool handlers read the `ContextVar` to scope queries and gate control-plane ops.

Rate-limit `429`s from auth pass through to the MCP caller as JSON-RPC error `-32000` / `"rate_limit_exceeded"` so the agent's MCP client surfaces it cleanly.

### Error handling (standard JSON-RPC 2.0)

- `-32700` parse error
- `-32600` invalid request
- `-32601` method not found (unknown tool)
- `-32602` invalid params (schema validation failure)
- `-32000` application errors (auth, downstream service down, rate limit, `insufficient_scope`) — message + optional `data` field with details

### Timeouts

5s for auth `/validate` (matches cache), 10s for librarian search, 5s for observability queries. Timeout → `-32000` / `"service_unavailable"`.

---

## Testing

Each service gets its own test module following memory's existing pattern. All runs via `pytest services/ -v` — no Docker required.

**`packages/mcp-common/tests/`** (new)
- `test_server.py` — JSON-RPC framing: valid request, parse error, unknown method, schema validation failure, handler exception → `-32000`.
- `test_auth.py` — mock auth `/validate` returning 200/401/429; assert correct `CallerContext` / error mapping.

**`services/librarian/tests/test_mcp.py`** (new)
- `tools/list` returns `librarian_search` with schema.
- `tools/call librarian_search` with a valid query → hits `search_knowledge()` (stubbed pool/redis), returns shaped results.
- Unauthorized request → 401 before tool dispatch.
- Schema validation: `limit=200` rejected.

**`services/observability/tests/test_mcp.py`** (new)
- One test per tool: stubbed Postgres + Redis, assert returned shape and team scoping.
- **Critical regression guard:** assert each tool's SQL includes `WHERE team_id = $1` — prevents cross-team leaks.
- Verify `recent_calls` strips any prompt/response fields if present on the row.

**`services/admin/tests/test_mcp.py`** (new)
- Self-service tools resolve to the caller's own resources only.
- Manager-tier tools rejected with `insufficient_scope` when the key lacks `team:manage`; succeed when present.
- Audit-log entries tagged `source: "mcp"`.

---

## Rollout

Single PR — the package extraction and the new endpoints touch overlapping files. Order within the PR:

1. Create `packages/mcp-common/` with extracted `MCPServer` + `auth.py`.
2. Migrate admin + memory to import from it (delete the two duplicates).
3. Add librarian `/mcp` + tools + tests.
4. Add observability read endpoints + `/mcp` + tools + tests.
5. Add admin `/mcp` tools (self-service + manager tiers) + tests.
6. Update `infra/html/index.html` dev hub with the MCP URLs.
7. Add an `mcp/` section to the README documenting how to configure Claude Code / Cursor.

No DB migrations. No nginx config changes. No new compose services.

---

## Out of scope (deferred)

- Federated gateway / single MCP URL — revisit if developers complain about juggling multiple servers.
- Identity + agent-relay MCP tools.
- WebSocket / Streamable HTTP transport — sticking with JSON-RPC over plain POST that memory already uses.
- High-risk admin ops (team create/delete, scanner control, SCIM provisioning, identity token issuance) — stay human-in-the-loop via the portal.

---

## Provenance

Recovered from brainstorming/design session `9fc19c06` (2026-05-28). The session ended on an API socket error immediately after approval to write specs ("looks right wrtie specs"), so the spec was never persisted at the time — this document reconstructs it from the conversation transcript.
