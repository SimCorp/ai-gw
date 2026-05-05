# AI Gateway Design — SimCorp Developer Platform

**Date:** 2026-05-05  
**Status:** Approved  
**Scope:** Enterprise AI gateway for SimCorp's developer organisation (~2000 engineers)

---

## Overview

An enterprise-grade AI gateway that provides SimCorp developers and agents with unified, observable, and cost-efficient access to multiple AI providers. Built on LiteLLM as the provider-abstraction core, with custom enterprise services for authentication, semantic caching, observability, and administration.

**Primary goals:**
- Reduce token costs through configurable caching (semantic + exact match)
- Provide enterprise-grade access control via Entra ID SSO and API keys
- Give full observability into usage, cost, and performance per team/project
- Support extensible provider registration including BYO/self-hosted models
- Run identically in local dev (Docker Compose) and production (AKS, Azure)

---

## Architecture

Five independently deployable layers on Azure Kubernetes Service (AKS), single region with extensibility hooks for multi-region:

```
[Developer / Agent]
        ↓
[Ingress + Auth Layer]          ← Entra ID OIDC + API key validation
        ↓
[Semantic Cache Engine]         ← Redis + embeddings; check before hitting provider
        ↓
[LiteLLM Proxy Core]            ← Provider routing, protocol translation
        ↓
[Provider Adapters]             ← Anthropic, Gemini, GitHub Copilot, BYO/self-hosted
        ↓ (response path back up)
[Observability Pipeline]        ← Async; intercepts req/res for logging, metrics, cost
```

**Shared Azure services:**
- Azure Cache for Redis (Premium tier with vector search / RediSearch) — caching + rate limit counters
- Azure Database for PostgreSQL Flexible Server — teams, API keys, policies, cost records
- Azure Key Vault — provider API keys, signing keys, secrets
- Azure Monitor + Application Insights — metrics, logs, distributed traces
- Azure Entra ID — identity, SSO, JWT issuance
- Azure Service Bus — async observability event stream (production)
- Azure Container Registry — container images

**Local dev equivalents (Docker Compose):**
- Redis (with RedisSearch module)
- PostgreSQL
- Dex (mock Entra ID / OIDC provider)
- Ollama (BYO/self-hosted model)
- In-memory event bus (replaces Service Bus)

---

## Components

### 1. Ingress & Auth Service (custom)

Single entry point for all AI requests.

- Validates Azure Entra ID JWT tokens (OIDC) for interactive/user-facing callers
- Validates SimCorp-issued API keys for programmatic/agent-to-agent callers
- Resolves every request to a `team + project` identity used for policy enforcement and cost attribution downstream
- Enforces rate limits via Redis counters — configurable per team, per model, per tier
- Returns 401 on auth failure, 429 with `Retry-After` on rate limit, both logged

### 2. Semantic Cache Engine (custom)

Intercepts requests between auth and LiteLLM; prevents unnecessary provider calls.

- **Exact match:** SHA-256 hash of normalised prompt → Redis key lookup
- **Semantic match:** Embeds prompt using a configurable embedding model (default: `text-embedding-3-small` via OpenAI API, or a self-hosted model via Ollama for air-gapped/cost-sensitive deployments) → vector similarity search in Redis (RediSearch). Embedding calls bypass the cache engine entirely to prevent recursion; the embedding model API key is stored separately in Key Vault.
- Cache policy is configurable per team and per model: TTL, similarity threshold (0.0–1.0), opt-out flag, embedding model selection
- On hit: returns cached response + emits cache-hit event; provider is never called
- On miss: request passes through; response stored in Redis after provider returns
- On Redis failure: fails open — request proceeds to provider, miss recorded
- Streaming: full response assembled from stream before caching; streaming passthrough unaffected

### 3. LiteLLM Proxy Core (OSS, configured)

Provider routing and protocol normalisation.

- All providers exposed via OpenAI-compatible API — callers use one consistent interface
- Config-driven provider registration — adding a provider is a config change, not a code change
- Injects provider API keys from Key Vault at request time — keys never exposed to callers
- Retry with exponential backoff on provider errors
- Configurable fallback routing: if primary provider fails, route to secondary (e.g. Anthropic → Gemini)

### 4. Provider Adapters

- **Anthropic Claude** — native LiteLLM support
- **Google Gemini** — native LiteLLM support
- **GitHub Models API** (via GitHub Copilot Enterprise subscription) — native LiteLLM support; provides access to models hosted on GitHub's infrastructure
- **BYO / self-hosted** — Ollama-compatible endpoint registration; works in local dev and production
- **New providers** — config registration + optional thin adapter if LiteLLM lacks native support

### 5. Observability Pipeline (custom, async)

Never blocks the request path — fully async.

- Every request/response publishes an event to Azure Service Bus (prod) or in-memory bus (local)
- Workers consume events and write to:
  - Application Insights: latency, error rates, request counts, p99 metrics
  - PostgreSQL: token usage, cost estimates, cache hit/miss records, model breakdowns
  - Structured logs: full request/response logging for debugging (configurable retention)
- Surfaces: per-team cost dashboards, cache hit rate reports, model usage breakdowns, error rate alerts, chargeback data

### 6. Admin Portal (custom, lightweight web app)

- Team and project management (CRUD)
- API key issuance, rotation, revocation
- Per-team policy configuration: cache settings (TTL, threshold, opt-out), rate limits, allowed models
- Cost and usage dashboards powered by observability data
- Secured via Entra ID SSO

---

## Data Flow

### Cache Miss (provider called)

1. Caller sends OpenAI-compatible request with Bearer token or API key
2. Auth Service validates identity → resolves to `team/project` → checks rate limit
3. Cache Engine embeds prompt → searches Redis → miss
4. LiteLLM selects provider based on requested model → injects provider key from Key Vault
5. Provider returns response (streaming supported end-to-end)
6. Cache Engine stores response + embedding in Redis per policy
7. Observability Pipeline receives async event: tokens, latency, model, team, cost estimate
8. Response returned to caller

### Cache Hit (provider not called)

1. Caller sends request
2. Auth Service validates identity → resolves to `team/project` → checks rate limit
3. Cache Engine finds hit (exact or semantic above threshold) → returns cached response
4. Observability Pipeline records cache hit event (zero token cost)
5. Response returned to caller — provider never called

### Error Cases

| Scenario | Behaviour |
|---|---|
| Auth failure | 401 immediately, logged |
| Rate limit exceeded | 429 + `Retry-After` header, logged |
| Provider timeout/error | Retry with backoff → fallback provider if configured → 502 |
| Cache layer failure | Fail open — request proceeds, miss recorded |
| Observability failure | Fail silent — never blocks request path |

---

## Testing Strategy

### Local Dev (Docker Compose)

- Unit tests for each custom service: auth validation, cache policy logic, cost calculation, admin portal
- Integration tests against full local stack: real Redis, PostgreSQL, Dex (mock Entra ID), Ollama
- Provider adapters tested against recorded fixtures (VCR-style) — no real API calls in CI

### CI Pipeline (GitHub Actions)

- Unit + integration tests on every PR
- Contract tests for provider adapters — validates LiteLLM adapter request/response shape
- Load tests (k6) against local stack to validate cache performance and latency targets

### Key Test Scenarios

**Auth:** valid JWT, expired JWT, invalid API key, revoked API key, rate limit enforcement  
**Cache:** exact hit, semantic hit above threshold, semantic miss below threshold, TTL expiry, policy opt-out, Redis failure (fail-open)  
**Routing:** correct provider per model, fallback on provider error, Key Vault key injection  
**Observability:** events emitted correctly, cost records accurate, cache hit/miss recorded, pipeline failure does not block requests

### Acceptance Criteria

- Gateway adds < 50ms p99 latency (excluding provider latency)
- Cache layer failure does not degrade request success rate
- 2000 concurrent engineers within Redis Premium tier without throttling
- Zero provider API keys exposed to callers at any point

---

## Extensibility

- **New AI provider:** register in LiteLLM config + optional thin adapter
- **New auth method:** Auth Service has pluggable validator interface
- **Multi-region:** Redis replication + PostgreSQL read replicas + AKS multi-region deployment (not in scope for v1 but designed to accommodate)
- **New observability sink:** add a consumer to the Service Bus topic

---

## Out of Scope (v1)

- Multi-region active-active deployment
- Fine-grained prompt/response content filtering (PII, policy enforcement)
- Model fine-tuning or training pipelines
- End-user (non-developer) facing interfaces
