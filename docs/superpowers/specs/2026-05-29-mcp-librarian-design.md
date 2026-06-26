# Librarian MCP Endpoint — AI Gateway Developer Platform

**Date:** 2026-05-29
**Status:** Superseded — librarian MCP already exists; this is now a verify-and-harden task, not a build
**Scope:** Expose the librarian knowledge base as an MCP server so developers' own AI agents can search it, authenticated with their existing `sk-*` API keys

> 🛑 **Premise disproven (codebase check, 2026-05-29).** This spec was written assuming librarian had no `/mcp` endpoint ("greenfield"). **It already has a full one** — `services/librarian/app/main.py:802–1095` implements REST-style MCP tools (`POST /mcp/tools/search|ingest|topics`), a complete **JSON-RPC 2.0** endpoint (`POST /mcp`: initialize, tools/list, tools/call, ping), an **SSE transport** (`GET /mcp/sse`), and manifest/discovery. It's wired into docker-compose and nginx and self-creates its `knowledge_items` table on startup. So there is nothing to "build."
>
> **The real, verified gaps (this is the actual work):**
> 1. ~~**No auth on the MCP read surface.**~~ **DONE (2026-05-30).** `POST /mcp`, `/mcp/tools/search`, `/mcp/tools/topics`, `/mcp/sse` now require a valid `sk-*` Bearer via `app/auth.py:resolve_caller` → auth `/validate` (access-gating only; the knowledge base is shared, so no row scoping). REST failures → HTTP 401/429; JSON-RPC failures → `-32000`. Discovery (`GET /mcp`, `/mcp/tools`, `/mcp/manifest`) stays public. Covered by `services/librarian/tests/test_mcp.py`. Ingest still uses its own `_check_ingest_token` (separate concern).
> 2. **Search is probably non-functional in a default setup.** Embeddings default to `http://ollama:11434/v1` (`config.py:12`), but ollama is opt-in (`--profile ollama`). With no ollama and no real embedding key, `_embed()` throws → `search_knowledge()` catches it and **returns `[]`**, and `ingest` stores `embedding=None`. So search silently looks dead. Needs an embedding backend configured + an end-to-end run to confirm.
> 3. ~~**Zero tests.**~~ **DONE (2026-06-26).** `services/librarian/tests/` now exists. `test_mcp.py` covers the MCP surface and auth. `test_ingest.py` (added in #175) adds 6 tests for the `/ingest` endpoint: happy path, embedding failure (fail-open), content > 50 000 chars → 422, invalid `source_url` scheme → 422, valid `https://` URL, and topic + tags metadata. Both suites run in CI under the `librarian` matrix entry.
>
> Treat the "Tool", "Architecture", and "Rollout" sections below as a **target end-state to reconcile the existing implementation against** (add auth, align JSON-RPC shape, add tests), not a from-scratch build. The `packages/mcp-common/` extraction is still valid — note librarian's inline comment at `main.py:890` explicitly says it couldn't import the admin package, which is exactly the duplication the package would fix.

> This was the first slice carved out of [`2026-05-28-mcp-developer-access-design.md`](2026-05-28-mcp-developer-access-design.md). The observability and admin tool sections from that design remain **deferred** — observability has no queryable event store (events are fire-and-forget to a bus; usage data lives in admin's `cost_records`), and the admin tools overlap with the already-shipped outbound MCP registry (`services/admin/app/routers/mcp.py`). Both need a placement decision before they can be specced.

---

## Overview

Developers building agentic workflows want their AI agents (Claude Code, Cursor, etc.) to search the gateway's knowledge base directly, without hand-rolling a REST client. This adds an MCP endpoint to the **librarian** service that exposes a single tool, `librarian_search`, authenticated with the same `sk-*` key the developer already uses for LLM traffic.

**Why this slice first:** it's greenfield (librarian has no `/mcp` today), it wraps an existing, tested function (`search_knowledge()`), it adds no new data model, no new persistence, and no cross-service data reads. It proves the inbound-MCP pattern end to end with minimal risk.

**Primary goals:**
- Let developer agents query the knowledge base over MCP, reusing existing `sk-*` auth
- Establish the reusable inbound-MCP scaffolding (`packages/mcp-common/`) that later slices build on
- Ship in a single PR with no DB migrations and no nginx changes

---

## Architecture

The librarian service (`:8008`, proxied at `/librarian/`) gains three endpoints, following the **memory service's existing pattern exactly** (`services/memory/app/main.py`):

```
POST /librarian/mcp           → JSON-RPC 2.0: initialize, tools/list, tools/call
GET  /librarian/mcp/tools     → tool name list (debug/inspection)
GET  /librarian/mcp/manifest  → MCP manifest
```

- **Transport:** JSON-RPC 2.0 over HTTP POST. `MCP_PROTOCOL_VERSION = "2024-11-05"`.
- **Server:** an `MCPServer` instance created per app, tools registered at module load (memory does this with `mcp_server.add_tool(...)`).
- **Per-request context:** the caller's identity is bound to a `ContextVar` in the route handler before tool dispatch — memory uses `_current_developer: ContextVar[str]` set from `get_developer_id(request)`.

No nginx change — the existing `/librarian/` proxy already covers `/librarian/mcp`. No new compose service. No DB migration.

### Shared package: `packages/mcp-common/`

Today the `MCPServer` class lives in `services/admin/app/mcp_protocol.py` and is **copy-pasted inline** into `services/memory/app/main.py` (the file says so: `# MCPServer (copied from services/admin/app/mcp_protocol.py)`). Adding a third copy to librarian would make three. Extract it once:

```
packages/mcp-common/
├── pyproject.toml            # name: ai-gateway-mcp-common
└── ai_gateway_mcp/
    ├── __init__.py
    ├── server.py             # MCPServer (verbatim from admin/app/mcp_protocol.py — behavior unchanged)
    └── auth.py               # resolve_caller(request) -> CallerContext  (Bearer sk-* → auth /validate)
```

`packages/` already hosts Python packages (`aigw-agent`, `contracts`), so this fits the existing layout. Each consuming service installs it editable (`-e packages/mcp-common`).

**Migration in this PR:** memory and admin switch to `from ai_gateway_mcp.server import MCPServer`; the two existing copies are deleted. `MCPServer.handle(body, request)` stays byte-for-byte identical, so memory's behavior is unchanged. Memory's `get_developer_id()` becomes a thin wrapper over the shared `resolve_caller()`.

> Scope guard: if the memory/admin migration turns out to be riskier than expected (e.g. subtle divergence between the two copies), fall back to adding `packages/mcp-common/` and wiring **librarian only**, leaving memory/admin on their current copies. The extraction is a cleanup, not a blocker for shipping librarian's tool.

---

## Tool: `librarian_search`

A thin wrap of the existing `search_knowledge()` (`services/librarian/app/main.py:274`), which already takes `query`, `topic`, `tags`, `limit` and returns a list of result dicts. No new query logic.

| Field | Type | Required | Notes |
|---|---|---|---|
| `query` | string | yes | search text |
| `topic` | string | no | filter by topic |
| `tags` | string[] | no | filter — matches if any tag overlaps (`tags && $`) |
| `limit` | int (1–50) | no | default 10 |

**Returns:** array of `{title, snippet, source_url, topic, tags, score}`.

The handler reads the librarian's existing asyncpg pool and Redis client (same ones the REST `/search` route uses), calls `search_knowledge(pool=..., redis=..., query=..., topic=..., tags=..., limit=...)`, and shapes each row into the return contract (`content` → truncated `snippet`).

### Auth

Every `/librarian/mcp` POST is authenticated up front, the same way memory's `get_developer_id()` does it:

1. Read `Authorization: Bearer sk-*`; missing/malformed → `401`.
2. Call `POST {AUTH_URL}/validate` with the token (5s timeout, matching cache).
3. On success, bind caller context to a `ContextVar` for the request.
4. On `401`/`429` from auth, surface as JSON-RPC error (`-32000`, message `"unauthorized"` / `"rate_limit_exceeded"`).

`librarian_search` reads no team-scoped data — the knowledge base is shared — so auth here is **access gating only** (a valid `sk-*` is required), not row scoping. No `WHERE team_id` concerns for this tool.

### Errors (standard JSON-RPC 2.0)

- `-32700` parse error · `-32600` invalid request · `-32601` unknown tool · `-32602` invalid params (e.g. `limit=200`)
- `-32000` application errors: auth failure, rate limit, downstream timeout (`"service_unavailable"`, 10s search timeout)

---

## Testing

`services/librarian/tests/test_mcp.py` (new), runnable via `pytest services/ -v` (no Docker):

- `tools/list` returns `librarian_search` with its input schema.
- `tools/call librarian_search` with a valid query → calls `search_knowledge()` (stubbed pool + redis), returns shaped results.
- Unauthorized request (no/invalid Bearer) → `401` / JSON-RPC `-32000` **before** tool dispatch (assert `search_knowledge` not called).
- Schema validation: `limit=200` rejected with `-32602`; `query` missing rejected.
- Downstream timeout → `-32000` `"service_unavailable"`.

`packages/mcp-common/tests/` (new):
- `test_server.py` — JSON-RPC framing: valid request, parse error, unknown method, schema validation failure, handler exception → `-32000`.
- `test_auth.py` — mock auth `/validate` returning 200/401/429 → correct `CallerContext` / error mapping.

If memory/admin are migrated, their existing MCP tests must still pass unchanged (regression guard on the extraction).

---

## Rollout (single PR)

1. Create `packages/mcp-common/` with `MCPServer` (extracted from `admin/app/mcp_protocol.py`) + `auth.py` (`resolve_caller`).
2. Migrate admin + memory to import from it; delete the two duplicates. *(Fallback: librarian-only if risky.)*
3. Add librarian `/mcp`, `/mcp/tools`, `/mcp/manifest` + `librarian_search` tool.
4. Add tests (above).
5. Update `infra/html/index.html` dev hub with the librarian MCP URL.
6. README `mcp/` section: how to add the librarian MCP server to Claude Code / Cursor with an `sk-*` key.

No DB migrations. No nginx config changes. No new compose services.

---

## Deferred (separate design needed)

- **observability usage tools** (`usage_summary`, `recent_errors`, `rate_limit_status`, `recent_calls`) — the data isn't in observability: events are fire-and-forget to an `EventBus`, queryable usage lives in admin's `cost_records`, rate limits in Redis (auth). Needs a service-placement decision first.
- **admin tools** (`list_my_api_keys`, `rotate_my_api_key`, team ops) — concept overlap with the shipped outbound MCP registry (`services/admin/app/routers/mcp.py`), and the proposed scopes don't exist in `app/scopes.py`. Needs reconciliation.
- Federated single-URL gateway; identity/agent-relay tools; Streamable HTTP transport.
