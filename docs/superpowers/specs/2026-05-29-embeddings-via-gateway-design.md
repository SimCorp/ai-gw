# Route Embeddings Through the Gateway — AI Gateway Developer Platform

**Date:** 2026-05-29
**Status:** In progress
**Scope:** Close the "embedding bypass" — make internal services consume embeddings through the gateway's own litellm proxy instead of holding provider keys and calling out directly. Applies to **librarian** and **cache**.

---

## Problem

The gateway's design principle is that **litellm is the single egress for all model traffic** — it holds the provider keys (Anthropic, Gemini, GitHub Models, Azure OpenAI, Azure AI Foundry, Copilot, ollama), and every consumer routes through it for central key management, routing, fallback, and cost tracking.

Two internal services violate this for embeddings:

- **librarian** (`app/main.py:40`) builds its own `AsyncOpenAI` client against `embedding_base_url` (default `http://ollama:11434/v1`) with its own `embedding_api_key`.
- **cache** (`app/semantic.py:16`) does the same — and ironically already has `litellm_url` + `litellm_master_key` in its config (`config.py:8-9`), just unused for embeddings.

Consequences observed this session:
- Out of the box (no `--profile ollama`, no real embedding key), `_embed()` throws → librarian's `search_knowledge()` **silently returns `[]`** and ingest stores `embedding=None`. Search looks broken.
- An Anthropic ("Claude") key cannot help — Anthropic has no embeddings API; these calls need an OpenAI-compatible embeddings provider.
- Each service would need its own provider key, defeating central key management.

## Goal & principle

**Internal services authenticate to litellm with a gateway key and never hold provider keys directly — embeddings included.** Which embedding model a service uses is **configurable** (`EMBEDDING_MODEL`), and *any* embedding model the gateway exposes — now or in future — is automatically available to every service just by adding it to `services/litellm/config.yaml`. (Per user direction: "all models which are exposed from gateway should be available for gw services, also in future.")

---

## Design

### 1. litellm exposes embedding models (`services/litellm/config.yaml`)

litellm registered zero embedding models — every entry was chat/completion, so it couldn't serve `/v1/embeddings` at all. Added an embeddings section:

| `model_name` | Backend | Key (already wired) | Notes |
|---|---|---|---|
| `text-embedding-3-small` | GitHub Models (`openai/…` @ `models.inference.ai.azure.com`) | `GITHUB_MODELS_API_KEY` | **Default.** Strongest candidate — key already configured for `github-gpt-4o`, and GitHub Models offers this model. |
| `azure-text-embedding-3-small` | Azure OpenAI | `AZURE_API_*` | Requires an Azure **embeddings deployment** (separate from chat deployments — not assumed to exist). |
| `azure-text-embedding-3-large` | Azure OpenAI | `AZURE_API_*` | Higher-dim alternative. |
| `local-embed` | ollama (`nomic-embed-text`) | none | Local dev; needs `--profile ollama` + `ollama pull nomic-embed-text`. |

Adding a future embedding model = one entry here; all services can then select it by name.

### 2. Services route through litellm (config defaults repointed)

| Setting | Before | After |
|---|---|---|
| librarian `embedding_base_url` | `http://ollama:11434/v1` | `http://litellm:8003/v1` |
| librarian `embedding_api_key` | `sk-local-placeholder` | gateway key (`LITELLM_MASTER_KEY`, default `sk-litellm-local-dev`) |
| cache `embedding_base_url` | `http://ollama:11434/v1` | `http://litellm:8003/v1` |
| cache `embedding_api_key` | `sk-placeholder` | gateway key |
| `embedding_model` (both) | `text-embedding-3-small` | unchanged — **configurable**, name must match a litellm `model_name` |

`embedding_model` deliberately stays `text-embedding-3-small` so it lines up with the default litellm entry; only `base_url` + key changed.

### 3. Compose (`infra/docker-compose.yml`)

- librarian: `EMBEDDING_BASE_URL` default → `http://litellm:8003/v1`; `EMBEDDING_API_KEY` default → `${LITELLM_MASTER_KEY:-sk-litellm-local-dev}`; added `depends_on: litellm (service_healthy)`.
- cache: already `depends_on litellm` and uses `env_file`; picks up the new config.py defaults.

### Circuit breaker (cache) — preserved

`cache/app/semantic.py` trips a Redis-backed breaker (`embedding:circuit_open`) after repeated `embed()` failures. Repointing only changes where the module-level `AsyncOpenAI` client sends requests; the breaker logic is untouched. No behavior change beyond the destination.

### Provisioning the provider key — prefer the admin console

Operators should set the embedding provider key via the **admin console `/admin/providers`** page, not by hand-editing `.env`. That flow (`services/admin/app/routers/settings.py`) stores keys **encrypted** in `provider_keys` and **pushes them to litellm at runtime** (`_push_to_litellm`) — no restart — with Save / Test / Discover-models buttons.

Required fix (done): `_push_to_litellm` only patches models in a provider's `litellm_model_names`. The GitHub Models entry listed only `github-gpt-4o`, so a saved key would not reach the embedding model. Added `text-embedding-3-small` to that provider's `models` + `litellm_model_names`, so one GitHub Models key serves both chat and embeddings. (`.env` remains a valid fallback for non-console/dev setups.)

### Out of scope / unchanged

- litellm's `general_settings.master_key` stays the internal credential. A dedicated **virtual key** per service (instead of the master key) is a reasonable future hardening, not done here.
- `.env.example` should document `EMBEDDING_MODEL` (and that embeddings route through litellm), but the file is permission-blocked in this environment — **flagged for a human to add**.
- librarian/cache still need the `sk-*` auth fix on their MCP endpoints — that's a separate concern (see `2026-05-29-mcp-librarian-design.md`), not this change.

---

## Verification (the gate)

Provider availability was **not** assumed — it must be proven, because chat keys being present says nothing about an embeddings deployment existing. Steps:

1. Rebuild litellm (config is baked, not mounted) so the embedding models register.
2. Call litellm `/v1/embeddings` with `model=text-embedding-3-small` → must return a vector (confirms `GITHUB_MODELS_API_KEY` is live and serves embeddings). The call is made **in-container using the env var in place** — credentials are never read out.
3. Rebuild librarian; run ingest → search end-to-end against a real query → must return non-empty results.
4. If GitHub Models doesn't serve embeddings with the configured key, fall back to `azure-*` (if an embeddings deployment exists) or `local-embed` (ollama), by setting `EMBEDDING_MODEL` — no code change.

**Outcome (2026-05-29, live dev stack):**
- ✅ litellm rebuilt; **embedding model `text-embedding-3-small` registers and routes** — a `/v1/embeddings` call authenticated with the master key passed auth and reached the provider router (no longer "model not found").
- ✅ librarian + cache rebuilt and **healthy** on the new config; librarian's JSON-RPC `/mcp` (`tools/list` → search/ingest/topics) works; search degrades **gracefully** (`{"items":[]}`, HTTP 200) rather than crashing.
- ⛔ **End-to-end embeddings could not be proven in this environment — no live embedding backend.** Boolean key check: `GITHUB_MODELS_API_KEY`, `AZURE_API_KEY`, `AZURE_API_BASE`, `GEMINI_API_KEY`, `OPENAI_API_KEY` all **empty** (only `AZURE_API_VERSION` set); ollama not running (opt-in profile). The only credential available is an Anthropic key, which has no embeddings API. So litellm correctly routes but the provider call fails with `AuthenticationError` (missing api_key).

**Conclusion:** the wiring is correct and verified up to the provider boundary. A non-empty search requires one live embedding backend in litellm — provision `GITHUB_MODELS_API_KEY` (one-line, already wired) or start `--profile ollama` with `nomic-embed-text` and set `EMBEDDING_MODEL=local-embed`. No further code change needed.

---

## Files touched

- `services/litellm/config.yaml` — embedding model entries
- `services/librarian/app/config.py` — embedding defaults → litellm
- `services/cache/app/config.py` — embedding defaults → litellm
- `infra/docker-compose.yml` — librarian env defaults + `depends_on litellm`
