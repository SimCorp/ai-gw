# Graceful Service Degradation — Design

**Issue:** #185  
**Date:** 2026-06-27  
**Status:** Approved

---

## Outcome

Developers and agents can query a single, unauthenticated JSON endpoint (`/api/status`) to know whether the inference path is healthy and which supporting services are degraded. The Gatus status dashboard at `/status` gains tier groupings so engineers can read system state at a glance without ops credentials.

---

## Context

The gateway already has:
- **Gatus** at `/status` — live visual status page, served independently of the admin portal, unauthenticated within the ZPA boundary.
- **Admin `/system/health`** — deep JSON health (Redis ping, Postgres connections, LiteLLM provider count, recent errors) but gated behind admin auth.
- **Per-service `/health`** and `/ready` endpoints on all 14 services.
- `restart: unless-stopped` on every service.

What's missing: a machine-readable, unauthenticated JSON endpoint with an explicit tier contract so agents can take action on partial outages, and a formal record of which services are core vs. optional.

---

## Service Tier Contract

| Tier | Name | Services | Semantics |
|------|------|----------|-----------|
| **0** | critical | `auth`, `cache`, `litellm` | Inference path. All must be healthy for AI calls to succeed. Tier 0 status drives `overall`. |
| **1** | important | `admin`, `observability`, `portal`, `admin-portal` | User-facing. Degradation here means UI/admin features are unavailable; AI calls still work. |
| **2** | background | `identity`, `agent-relay`, `librarian`, `memory`, `league`, `graphify`, `scanner` | Optional at runtime. Callers should handle 503 gracefully; agents degrade to stateless operation. |

`caddy` is the ingress — a response from `/api/status` proves it's up. It is not separately probed.

Compose `depends_on` chains were reviewed: Tier 0 services depend only on `db-migrate`, Redis, and Postgres (infra). No Tier 0 service has a hard runtime dependency on a Tier 1 or Tier 2 container. No changes to `depends_on` chains are required.

---

## `/api/status` Endpoint

**Method:** `GET /api/status`  
**Auth:** None (unauthenticated, ZPA-protected like all other gateway routes)  
**Served by:** Caddy → `admin:8005` (the admin service hosts the aggregation logic)

### Response shape

```json
{
  "overall": "ok",
  "timestamp": "2026-06-27T10:00:00Z",
  "tiers": {
    "0": {
      "name": "critical",
      "description": "Inference path — AI calls require all to be healthy",
      "status": "ok",
      "services": [
        {"name": "auth",    "status": "ok"},
        {"name": "cache",   "status": "ok"},
        {"name": "litellm", "status": "ok"}
      ]
    },
    "1": {
      "name": "important",
      "description": "User-facing — AI calls still work when degraded",
      "status": "ok",
      "services": [
        {"name": "admin",        "status": "ok"},
        {"name": "observability","status": "ok"},
        {"name": "portal",       "status": "ok"},
        {"name": "admin-portal", "status": "ok"}
      ]
    },
    "2": {
      "name": "background",
      "description": "Optional — handle 503 gracefully",
      "status": "ok",
      "services": [
        {"name": "identity",    "status": "ok"},
        {"name": "agent-relay", "status": "ok"},
        {"name": "librarian",   "status": "ok"},
        {"name": "memory",      "status": "ok"},
        {"name": "league",      "status": "ok"},
        {"name": "graphify",    "status": "ok"},
        {"name": "scanner",     "status": "ok"}
      ]
    }
  }
}
```

**`overall` logic:** `ok` if all Tier 0 services are `ok`; `degraded` otherwise. Tier 1 and Tier 2 status never affect `overall`.

**Status values:** `ok` | `degraded` | `unreachable`. No error messages, no internal URLs, no latencies, no auth info in the public payload.

**Probe logic:** concurrent HTTP GET to each service's `/health` endpoint (or `/health/liveliness` for litellm). 3 s timeout per probe. HTTP 2xx → `ok`; non-2xx → `degraded`; exception/timeout → `unreachable`.

**Bootstrap note:** if the admin service itself is down, `/api/status` returns 502/503. The Gatus visual dashboard at `/status` remains available independently, satisfying the "status page survives portal downtime" requirement.

---

## Implementation

### New file: `services/admin/app/routers/public_status.py`

A `GET /status` FastAPI endpoint with no auth dependency. Uses a trimmed probe helper that returns only `{name, status}` — does not reuse the `_check_service` helper in `system.py` (which returns error, code, and latency fields). All probes run concurrently via `asyncio.gather`.

### Modified: `services/admin/app/main.py`

```python
from app.routers import public_status as public_status_router
# ...
app.include_router(public_status_router.router)  # no _auth dependency
```

Place before the existing health/ready routes for clarity.

### Modified: `infra/Caddyfile`

Add before `handle_path /api/admin/*`:

```
# Public tier-status JSON — no auth required.
handle /api/status {
    reverse_proxy admin:8005
}
```

Uses `handle` (not `handle_path`) so the `/status` path is passed through to admin intact.

### Modified: `infra/gatus/config.yaml`

Add `group:` to each endpoint:
- `Tier 0 — Critical` for auth, cache, litellm, litellm-providers
- `Tier 1 — Important` for admin, observability, portal, admin-portal
- `Tier 2 — Background` for identity, agent-relay, librarian, memory, league, graphify, scanner
- Readiness probes (`auth-ready`, `cache-ready`, etc.) grouped under their tier
- `tls-cert` → `Tier 0 — Critical`

### Modified: `infra/docker-compose.yml`

Add `labels` block to each application service:

```yaml
labels:
  - "aigw.tier=0"
  - "aigw.tier-name=critical"
```

(or `tier=1`/`tier=2` as appropriate). Infrastructure services (postgres, redis, caddy) are not labelled — they are dependencies, not directly probed services.

---

## Security

- The `/api/status` endpoint is intentionally unauthenticated. The response exposes only service names and `ok/degraded/unreachable` status strings. It does not leak: error messages, internal hostnames, probe latencies, auth token information, or any data from `/system/health`.
- The admin service's existing `_check_service` helper (used by the gated `/system/health`) is *not* reused; a new stripped helper is written for `public_status.py`.
- Caddy's `handle /api/status` block is placed after the `@apimetrics` block (which blocks `/api/*/metrics`) and before `handle_path /api/admin/*`. The path `/api/status` does not match `@apimetrics` (`/api/*/metrics`), so metric leakage is not a concern.

---

## Out of Scope (v1)

- Automatic provider failover if litellm's upstream is unavailable (resilience roadmap).
- Embedding the Grafana dashboard unauthenticated (requires Grafana anonymous access config).
- Push notifications or webhooks on status change.
- Historical status / uptime percentage.
