# AI Gateway — API Reference

Enterprise AI gateway for the SimCorp Developer Platform. This reference covers the public inference API, streaming, models, error codes, caching, rate limiting, and the admin REST API.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Chat Completions — OpenAI-compatible](#2-chat-completions--openai-compatible)
3. [Chat Completions — Anthropic-compatible](#3-chat-completions--anthropic-compatible)
4. [Streaming](#4-streaming)
5. [Models — GET /v1/models](#5-models)
6. [Available Models](#6-available-models)
7. [Error Codes](#7-error-codes)
8. [Rate Limiting](#8-rate-limiting)
9. [Caching](#9-caching)
10. [Admin REST API](#10-admin-rest-api)

---

## 1. Overview

### Base URLs

| Surface | Base URL | Notes |
|---|---|---|
| Inference (primary) | `http://localhost:8002` | Cache service; proxies to LiteLLM after auth |
| Auth service | `http://localhost:8001` | Internal — not called directly by API clients |
| LiteLLM | `http://localhost:8003` | Internal — not called directly by API clients |
| Admin REST API | `http://localhost:8005` | JSON endpoints for platform operators |
| Developer portal | `http://localhost:3002/portal` | Browser UI; email+password auth |
| Admin portal | `http://localhost:3001/admin/dashboard` | Teams, guardrails, audit, quotas |
| claude-sandbox (SSH) | `ssh claude@localhost -p 2222` | `make sandbox`; run `go` inside to configure and launch Claude |

All inference requests go through port **8002**. The cache service validates the bearer token with the auth service, checks for a cached response, then forwards cache misses to LiteLLM at :8003.

### Authentication

All inference requests require a bearer token in the `Authorization` header:

```
Authorization: Bearer sk-<your-key>
```

API keys start with the prefix `sk-` and are 32 bytes of URL-safe random data appended. They are provisioned once and the plaintext value is returned only at creation time. Keys are stored as SHA-256 hashes; there is no way to retrieve the plaintext after creation.

**Obtaining a key**

- **Developer portal** — Register with email and password at `http://localhost:3002/portal` (self-service, no OIDC required). Once authenticated, visit `/portal/keys` to issue a key.
- **Admin REST API** — `POST /teams/{team_id}/keys` (requires `X-Admin-Token` header).

### Quick health check

Verify your key and the gateway are working end-to-end:

```python
import httpx

resp = httpx.post(
    "http://localhost:8002/v1/chat/completions",
    headers={"Authorization": "Bearer sk-YOUR-KEY-HERE"},
    json={"model": "claude-haiku-4-5",
          "messages": [{"role": "user", "content": "ping"}],
          "max_tokens": 10},
    timeout=30.0,
)
if resp.status_code == 200:
    print("Gateway OK:", resp.json()["choices"][0]["message"]["content"])
elif resp.status_code == 401:
    print("Auth failed — check your key")
else:
    print(f"Unexpected {resp.status_code}:", resp.text)
```

### Versioning

The gateway follows the OpenAI API versioning convention. The current version is `v1`. All chat completion and model listing endpoints are under `/v1/`.

---

## 2. Chat Completions — OpenAI-compatible

```
POST http://localhost:8002/v1/chat/completions
```

Fully OpenAI-compatible. Drop in any OpenAI SDK by pointing `base_url` at `http://localhost:8002`.

### Request

```http
POST /v1/chat/completions HTTP/1.1
Host: localhost:8002
Authorization: Bearer sk-<your-key>
Content-Type: application/json

{
  "model": "claude-sonnet-4-6",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful assistant."
    },
    {
      "role": "user",
      "content": "Summarise the key risks in a DCF valuation."
    }
  ],
  "max_tokens": 1024,
  "temperature": 0.7,
  "top_p": 1.0,
  "stream": false
}
```

**Body parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `model` | string | Yes | Model ID. See [Available Models](#6-available-models). |
| `messages` | array | Yes | List of message objects with `role` (`system`, `user`, `assistant`) and `content` (string). |
| `max_tokens` | integer | No | Maximum tokens to generate. |
| `temperature` | number | No | Sampling temperature, 0–2. Default `1.0`. |
| `top_p` | number | No | Nucleus sampling probability. Default `1.0`. |
| `stream` | boolean | No | If `true`, responses are streamed as SSE. Default `false`. |
| `stop` | string or array | No | Sequences where generation stops. |
| `n` | integer | No | Number of completions to generate. Default `1`. |
| `presence_penalty` | number | No | Penalise new tokens based on presence in the text so far. |
| `frequency_penalty` | number | No | Penalise new tokens based on frequency in the text so far. |
| `user` | string | No | Opaque end-user identifier for abuse monitoring. |

Unknown parameters are silently dropped by LiteLLM (`drop_params: true`).

### Response

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1746518400,
  "model": "claude-sonnet-4-6",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "DCF valuations carry several key risks: terminal value sensitivity, discount rate assumptions, forecast uncertainty beyond 3–5 years, and working capital cycle changes."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 42,
    "completion_tokens": 51,
    "total_tokens": 93
  }
}
```

### Python example (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-your-key-here",
    base_url="http://localhost:8002",
)

response = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Summarise the key risks in a DCF valuation."},
    ],
    max_tokens=1024,
    temperature=0.7,
)

print(response.choices[0].message.content)
```

---

## 3. Chat Completions — Anthropic-compatible

```
POST http://localhost:8002/anthropic/v1/messages
```

This endpoint is handled by LiteLLM's Anthropic-compatible proxy. The request and response shapes follow the [Anthropic Messages API](https://docs.anthropic.com/en/api/messages) exactly.

### Request

```http
POST /anthropic/v1/messages HTTP/1.1
Host: localhost:8002
Authorization: Bearer sk-<your-key>
Content-Type: application/json
anthropic-version: 2023-06-01

{
  "model": "claude-sonnet-4-6",
  "max_tokens": 1024,
  "messages": [
    {
      "role": "user",
      "content": "What is the capital of France?"
    }
  ]
}
```

**Body parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `model` | string | Yes | Model ID. See [Available Models](#6-available-models). |
| `messages` | array | Yes | List of message objects with `role` (`user`, `assistant`) and `content`. |
| `max_tokens` | integer | Yes | Maximum tokens to generate. |
| `system` | string | No | System prompt (top-level field, not inside messages). |
| `temperature` | number | No | Sampling temperature, 0–1. |
| `top_p` | number | No | Nucleus sampling. |
| `top_k` | integer | No | Top-K sampling. |
| `stop_sequences` | array | No | Strings that stop generation. |
| `stream` | boolean | No | If `true`, responses are streamed as SSE. |
| `metadata` | object | No | Opaque object for `user_id` and similar identifiers. |

### Response

```json
{
  "id": "msg_01XFDUDYJgAACzvnptvVoYEL",
  "type": "message",
  "role": "assistant",
  "model": "claude-sonnet-4-6",
  "content": [
    {
      "type": "text",
      "text": "The capital of France is Paris."
    }
  ],
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {
    "input_tokens": 14,
    "output_tokens": 9
  }
}
```

### Python example (Anthropic SDK)

```python
import anthropic

client = anthropic.Anthropic(
    api_key="sk-your-key-here",
    base_url="http://localhost:8002",
)

message = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "What is the capital of France?"}
    ],
)

print(message.content[0].text)
```

---

## 3a. Developer Portal

The self-service portal at `http://localhost:3002/portal` provides browser-based access:

| Route | Method | Purpose |
|---|---|---|
| `/portal/signup` | GET/POST | Register with email + password |
| `/portal/login` | GET/POST | Sign in |
| `/portal/dashboard` | GET | Usage overview |
| `/portal/keys` | GET/POST | Create / list API keys |
| `/portal/keys/{id}/revoke` | POST | Revoke a key |
| `/portal/quickstart` | GET | Copy-paste code examples |
| `/portal/docs` | GET | LangChain, LlamaIndex, OpenAI Agents SDK, Claude Code CLI |
| `/portal/profile` | GET/POST | Change display name / password |

Auth uses a session cookie (`portal_session`) backed by Redis with an 8-hour TTL.

---

## 4. Streaming

Both endpoints support server-sent events (SSE) streaming. Set `"stream": true` in the request body.

**Important:** Streamed responses are never cached. The gateway passes the SSE stream directly from LiteLLM to the caller without buffering. The `X-Cache` response header will always be `MISS` for streamed requests.

### OpenAI-compatible streaming

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-your-key-here",
    base_url="http://localhost:8002",
)

with client.chat.completions.stream(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "Write a haiku about distributed systems."}],
    max_tokens=100,
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

### Anthropic-compatible streaming

```python
import anthropic

client = anthropic.Anthropic(
    api_key="sk-your-key-here",
    base_url="http://localhost:8002",
)

with client.messages.stream(
    model="claude-sonnet-4-6",
    max_tokens=100,
    messages=[{"role": "user", "content": "Write a haiku about distributed systems."}],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

### Raw SSE format (OpenAI)

Each SSE event is a `data:` line with a JSON delta payload, terminated by `data: [DONE]`:

```
data: {"id":"chatcmpl-abc","object":"chat.completion.chunk","created":1746518400,"model":"claude-sonnet-4-6","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}

data: {"id":"chatcmpl-abc","object":"chat.completion.chunk","created":1746518400,"model":"claude-sonnet-4-6","choices":[{"index":0,"delta":{"content":"Nodes"},"finish_reason":null}]}

data: [DONE]
```

---

## 5. Models

```
GET http://localhost:8002/v1/models
```

Returns the list of models configured in LiteLLM. Authentication is required.

### Request

```http
GET /v1/models HTTP/1.1
Host: localhost:8002
Authorization: Bearer sk-<your-key>
```

### Response

```json
{
  "object": "list",
  "data": [
    {
      "id": "claude-sonnet-4-6",
      "object": "model",
      "created": 1746518400,
      "owned_by": "anthropic"
    },
    {
      "id": "claude-opus-4-7",
      "object": "model",
      "created": 1746518400,
      "owned_by": "anthropic"
    },
    {
      "id": "claude-haiku-4-5",
      "object": "model",
      "created": 1746518400,
      "owned_by": "anthropic"
    },
    {
      "id": "gemini-1.5-pro",
      "object": "model",
      "created": 1746518400,
      "owned_by": "google"
    },
    {
      "id": "github-gpt-4o",
      "object": "model",
      "created": 1746518400,
      "owned_by": "openai"
    },
    {
      "id": "local",
      "object": "model",
      "created": 1746518400,
      "owned_by": "ollama"
    }
  ]
}
```

---

## 6. Available Models

These are the exact model IDs defined in `services/litellm/config.yaml`. Use these strings in the `model` field of your requests.

| Model ID | Provider | Underlying Model | Notes |
|---|---|---|---|
| `claude-sonnet-4-6` | Anthropic | `anthropic/claude-sonnet-4-6` | Default fallback target for `gemini-1.5-pro` failures |
| `claude-opus-4-7` | Anthropic | `anthropic/claude-opus-4-7` | Highest capability Anthropic model |
| `claude-haiku-4-5` | Anthropic | `anthropic/claude-haiku-4-5-20251001` | Fast, low-cost |
| `gemini-1.5-pro` | Google | `gemini/gemini-1.5-pro` | Falls back to `claude-sonnet-4-6` on failure |
| `github-gpt-4o` | GitHub Models (Azure) | `openai/gpt-4o` via `models.inference.ai.azure.com` | Requires `GITHUB_MODELS_API_KEY` |
| `copilot-gpt-4o` | GitHub Copilot | `openai/gpt-4o` via `api.githubcopilot.com` | Requires `GITHUB_COPILOT_API_KEY` (PAT with Copilot access) |
| `copilot-gpt-4o-mini` | GitHub Copilot | `openai/gpt-4o-mini` via `api.githubcopilot.com` | Requires `GITHUB_COPILOT_API_KEY` |
| `copilot-o3-mini` | GitHub Copilot | `openai/o3-mini` via `api.githubcopilot.com` | Requires `GITHUB_COPILOT_API_KEY` |
| `copilot-claude-3.5-sonnet` | GitHub Copilot | `anthropic/claude-3-5-sonnet` via `api.githubcopilot.com` | Requires `GITHUB_COPILOT_API_KEY` |
| `azure-gpt-4o` | Azure AI Foundry | `openai/gpt-4o` via Azure endpoint | Requires `AZURE_API_BASE` and `AZURE_API_KEY` |
| `azure-gpt-4o-mini` | Azure AI Foundry | `openai/gpt-4o-mini` via Azure endpoint | Requires `AZURE_API_BASE` and `AZURE_API_KEY` |
| `azure-o3-mini` | Azure AI Foundry | `openai/o3-mini` via Azure endpoint | Requires `AZURE_API_BASE` and `AZURE_API_KEY` |
| `azure-gpt-4.1` | Azure AI Foundry | `openai/gpt-4.1` via Azure endpoint | Requires `AZURE_API_BASE` and `AZURE_API_KEY` |
| `local` | Ollama (self-hosted) | `ollama/llama3.2` | Served at `http://ollama:11434`; available in Docker Compose only |

**Fallback behaviour:** If a request to `gemini-1.5-pro` fails, the gateway automatically retries with `claude-sonnet-4-6`. LiteLLM is configured with `num_retries: 3` and `allowed_fails: 1` globally.

---

## 6a. Providers

### GitHub Copilot

**Endpoint:** `api.githubcopilot.com`

Model IDs: `copilot-gpt-4o`, `copilot-gpt-4o-mini`, `copilot-o3-mini`, `copilot-claude-3.5-sonnet`

**Obtaining a token:** Create a GitHub Personal Access Token (PAT) with the `copilot` scope at https://github.com/settings/tokens. Set `GITHUB_COPILOT_API_KEY` in your `.env` to this token value. An active GitHub Copilot subscription (individual or enterprise) is required.

```bash
# GitHub Copilot via gateway
curl http://localhost:8002/v1/chat/completions \
  -H "Authorization: Bearer sk-your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "copilot-gpt-4o", "messages": [{"role": "user", "content": "Hello"}]}'
```

### Azure AI Foundry

**Endpoint:** Configured via `AZURE_API_BASE` environment variable (e.g. `https://<resource>.openai.azure.com/`).

Model IDs: `azure-gpt-4o`, `azure-gpt-4o-mini`, `azure-o3-mini`, `azure-gpt-4.1`

**Configuration:** Set the following in your `.env`:
- `AZURE_API_BASE` — your Azure OpenAI resource endpoint
- `AZURE_API_KEY` — your Azure API key from the Azure portal
- `AZURE_API_VERSION` — API version string (e.g. `2024-02-15-preview`)

See https://portal.azure.com → Azure OpenAI → Keys and Endpoint.

```bash
# Azure AI Foundry via gateway
curl http://localhost:8002/v1/chat/completions \
  -H "Authorization: Bearer sk-your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "azure-gpt-4o", "messages": [{"role": "user", "content": "Hello"}]}'
```

---

## 7. Error Codes

All error responses return JSON with a top-level `"error"` field. The exact shape differs slightly between gateway errors (from the cache service) and LiteLLM errors.

### 401 Unauthorized

Returned when the bearer token is missing, malformed, revoked, or does not match a known API key or valid JWT.

```json
{
  "error": "Unauthorized"
}
```

The auth service returns more detail internally:

```json
{
  "detail": "Missing token"
}
```

### 429 Too Many Requests

Returned when the team has exceeded its per-minute request rate limit. The window is 60 seconds (fixed window, resets on the first request of each window).

```json
{
  "detail": "Rate limit exceeded"
}
```

Response headers:

```
Retry-After: 60
```

See [Rate Limiting](#8-rate-limiting) for full details.

### 404 Not Found

Returned by the admin API when a requested resource (team, key) does not exist.

```json
{
  "detail": "Team not found"
}
```

```json
{
  "detail": "Key not found"
}
```

### 500 Internal Server Error

Returned when an upstream provider returns an error or when an unhandled exception occurs. LiteLLM surfaces upstream errors with their original status codes and detail messages.

```json
{
  "error": {
    "message": "Error in LiteLLM: ...",
    "type": "internal_server_error",
    "code": 500
  }
}
```

### Error code summary

| HTTP Status | Meaning | When it occurs |
|---|---|---|
| `400` | Bad Request | Malformed JSON body or missing required fields |
| `401` | Unauthorized | Invalid, missing, or revoked bearer token |
| `404` | Not Found | Unknown model ID or missing admin resource |
| `429` | Too Many Requests | Rate limit exceeded for the team |
| `500` | Internal Server Error | Upstream provider error or unhandled exception |

---

## 8. Rate Limiting

Rate limits are enforced per team in a fixed 60-second window. The limit is set at the team level in Redis under the key `policy:{team_id}` (field `rate_limit_rpm`). If no team-specific limit is stored, the gateway default from configuration applies.

### Window behaviour

- The first request in a window creates the counter with a 60-second TTL.
- Subsequent requests within the same window increment the counter without extending the TTL.
- When the counter exceeds the team's RPM limit, the request is rejected with HTTP `429`.
- The window resets naturally when the Redis key expires (every 60 seconds from the first request of that window).

### Response headers

A `429` response always includes:

```
Retry-After: 60
```

There are no `X-RateLimit-Limit`, `X-RateLimit-Remaining`, or `X-RateLimit-Reset` headers in the current implementation. To check remaining budget, contact the platform team or read from the admin dashboard.

### Handling 429 in client code

```python
import time
import httpx

def chat_with_retry(payload: dict, api_key: str, max_attempts: int = 3) -> dict:
    url = "http://localhost:8002/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}

    for attempt in range(max_attempts):
        response = httpx.post(url, json=payload, headers=headers, timeout=120)
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            if attempt < max_attempts - 1:
                time.sleep(retry_after)
                continue
        response.raise_for_status()
        return response.json()

    raise RuntimeError("Rate limit not cleared after retries")
```

---

## 9. Caching

The cache service at :8002 implements two levels of cache before forwarding to LiteLLM.

### Cache levels

**Level 1 — Exact match**

A SHA-256 hash of the complete request body is used as the cache key in Redis. If an identical request has been seen within the TTL window, the stored response is returned immediately without calling LiteLLM.

**Level 2 — Semantic match**

If there is no exact match, the prompt text is embedded and compared against previously stored embeddings using cosine similarity. If a stored response has similarity above the per-team threshold (default configurable via `similarity_threshold`), it is returned.

### When responses are cached

- Only non-streaming (`"stream": false`) responses are stored in the cache.
- Streaming responses are passed through without caching and always produce `X-Cache: MISS`.
- Only HTTP 200 responses from LiteLLM are stored.
- Cache is bypassed entirely if the team policy sets `opt_out: true`.

### X-Cache response header

Every response from the cache service includes an `X-Cache` header:

| Value | Meaning |
|---|---|
| `HIT` | Response was served from cache (exact or semantic match) |
| `MISS` | Response was fetched from LiteLLM and stored (or not stored, if streaming) |

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Cache: HIT
```

### TTL

Cache TTL is configured per-team in Redis (`policy:{team_id}`, field `ttl_seconds`). The service default applies when no team policy is present.

### Cache opt-out

To disable caching for a specific team or project, set `opt_out: true` in the team's Redis policy hash. This can be done via the admin REST API (policies endpoint) or directly via the admin portal UI.

To opt out on a per-request basis in the current implementation, there is no request-level header — team-level policy is the only control.

---

## 10. Admin REST API

The admin REST API is available at `http://localhost:8005`. All endpoints require the `X-Admin-Token` header (value from the `ADMIN_TOKEN` environment variable). When `DEV_BYPASS_AUTH=true` (local development), the header is not checked.

```
X-Admin-Token: <admin-token>
```

The developer portal routes under `/portal/*` are excluded from admin auth and manage their own session-cookie authentication.

### Teams

```
GET    /teams                          List all teams
POST   /teams                          Create a team
GET    /teams/{team_id}                Get a team
PUT    /teams/{team_id}                Update a team
DELETE /teams/{team_id}                Delete a team

GET    /teams/{team_id}/projects       List projects for a team
POST   /teams/{team_id}/projects       Create a project
```

**Create team — request body**

```json
{
  "name": "Platform Engineering",
  "slug": "platform-eng"
}
```

**Create team — response (201)**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "name": "Platform Engineering",
  "slug": "platform-eng",
  "created_at": "2026-05-06T09:00:00Z"
}
```

**Create project — request body**

```json
{
  "name": "Cost Analyser",
  "slug": "cost-analyser"
}
```

### API Keys

```
GET    /teams/{team_id}/keys           List active keys for a team
POST   /teams/{team_id}/keys           Create a key (returns plaintext once)
DELETE /teams/{team_id}/keys/{key_id}  Revoke a key
```

**Create key — request body**

```json
{
  "name": "ci-runner",
  "project_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

`project_id` is optional.

**Create key — response (201)**

```json
{
  "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "name": "ci-runner",
  "key": "sk-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
  "created_at": "2026-05-06T09:00:00Z"
}
```

The `"key"` field is returned **only once** at creation. It is not stored in plaintext and cannot be retrieved again.

**List keys — response (200)**

```json
[
  {
    "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "team_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "name": "ci-runner",
    "created_at": "2026-05-06T09:00:00Z",
    "revoked_at": null
  }
]
```

**Revoke key — response (204 No Content)**

No body.

### System Health

```
GET /system/health
```

Returns the health of all services. Does not require admin auth in practice (auth is applied at the router level; the health check is within the authenticated router).

**Response (200)**

```json
{
  "overall": "ok",
  "last_updated": "09:00:00 UTC",
  "services": [
    {"service": "auth",          "status": "ok",  "code": 200, "latency_ms": 3.2,  "error": null},
    {"service": "cache",         "status": "ok",  "code": 200, "latency_ms": 2.8,  "error": null},
    {"service": "litellm",       "status": "ok",  "code": 200, "latency_ms": 15.1, "error": null},
    {"service": "observability", "status": "ok",  "code": 200, "latency_ms": 4.0,  "error": null}
  ],
  "redis": {
    "status": "ok",
    "ping_ms": 0.5,
    "used_memory_mb": 12.4,
    "connected_clients": 8,
    "error": null
  },
  "postgres": {
    "status": "ok",
    "ping_ms": 1.2,
    "active_connections": 3,
    "error": null
  },
  "litellm": {
    "status": "ok",
    "models_available": 6,
    "providers_with_keys": ["anthropic", "gemini", "openai"],
    "error": null
  },
  "gateway": {
    "status": "ok",
    "requests_last_60s": 47,
    "cache_hit_rate_last_60s": 0.34,
    "error": null
  },
  "recent_errors": []
}
```

`"overall"` is `"ok"` only when every sub-check reports `"ok"`; otherwise it is `"degraded"`.

Service status values: `"ok"`, `"degraded"`, `"unreachable"`.
