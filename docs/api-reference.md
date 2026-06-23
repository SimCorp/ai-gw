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
11. [Unified Auth API](#11-unified-auth-api)

---

## 1. Overview

The gateway is deployed to Azure Container Apps (SimCorp Landing Zone, Sweden Central) with internal ingress only — reachable from the corporate VPN. SSO uses Azure Entra ID.

### Base URLs

| Surface | Base URL | Internal port (reference only) | Notes |
|---|---|---|---|
| Inference (OpenAI-compatible) | `https://dev.aigw.scdom.net/v1` | `8002` (cache) | Cache service; proxies to LiteLLM after auth |
| Inference (Anthropic-compatible) | `https://dev.aigw.scdom.net/anthropic` | `8002` (cache) | Anthropic Messages wire protocol |
| Admin REST API | `https://dev.aigw.scdom.net/api/admin` | `8005` (admin) | JSON endpoints for platform operators |
| Developer portal | Over the corporate VPN (Entra ID SSO) | `3002` | Browser UI |
| Admin portal | Over the corporate VPN (Entra ID SSO) | `3001` | Teams, guardrails, audit, quotas |

Each service runs as an internal Container App (`ca-<service>-dev-sdc`); callers only ever reach the gateway FQDN. The cache service validates the bearer token with the auth service, checks for a cached response, then forwards cache misses to LiteLLM.

### Authentication

All inference requests require a bearer token in the `Authorization` header:

```
Authorization: Bearer sk-<your-key>
```

API keys start with the prefix `sk-` and are 32 bytes of URL-safe random data appended. They are provisioned once and the plaintext value is returned only at creation time. Keys are stored as SHA-256 hashes; there is no way to retrieve the plaintext after creation.

**Obtaining a key**

- **Developer portal** — Reachable over the corporate VPN. Once authenticated, visit `/keys` to issue a key.
- **Admin REST API** — `POST /teams/{team_id}/keys` (requires `X-Admin-Token` header).

### Quick health check

Verify your key and the gateway are working end-to-end:

```python
import httpx

resp = httpx.post(
    "https://dev.aigw.scdom.net/v1/chat/completions",
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
POST https://dev.aigw.scdom.net/v1/chat/completions
```

Fully OpenAI-compatible. Drop in any OpenAI SDK by pointing `base_url` at `https://dev.aigw.scdom.net/v1`.

### Request

```http
POST /v1/chat/completions HTTP/1.1
Host: dev.aigw.scdom.net
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
    base_url="https://dev.aigw.scdom.net/v1",
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
POST https://dev.aigw.scdom.net/anthropic/v1/messages
```

This endpoint is handled by LiteLLM's Anthropic-compatible proxy. The request and response shapes follow the [Anthropic Messages API](https://docs.anthropic.com/en/api/messages) exactly.

### Request

```http
POST /anthropic/v1/messages HTTP/1.1
Host: dev.aigw.scdom.net
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
    base_url="https://dev.aigw.scdom.net/anthropic",
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

The developer portal is reachable over the corporate VPN. It provides browser-based access:

| Route | Method | Purpose |
|---|---|---|
| `/signup` | GET/POST | Register with email + password |
| `/login` | GET/POST | Sign in |
| `/dashboard` | GET | Usage overview |
| `/keys` | GET/POST | Create / list API keys |
| `/keys/{id}/revoke` | POST | Revoke a key |
| `/quickstart` | GET | Copy-paste code examples |
| `/docs` | GET | LangChain, LlamaIndex, OpenAI Agents SDK, Claude Code CLI |
| `/profile` | GET/POST | Change display name / password |

Auth uses a session cookie (`portal_session`) backed by Redis with an 8-hour TTL.

---

## 4. Streaming

Both endpoints support server-sent events (SSE) streaming. Set `"stream": true` in the request body.

**Important:** Streamed responses are never cached. The gateway passes the SSE stream directly from LiteLLM to the caller without buffering. The `X-Cache` response header will always be `MISS` for streamed requests.

**Token tracking:** Although streamed responses are not cached, token counts are captured for observability. The gateway parses the final SSE chunk to extract usage data and posts it to the observability service. Streaming requests no longer emit zero tokens in cost records.

### OpenAI-compatible streaming

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-your-key-here",
    base_url="https://dev.aigw.scdom.net/v1",
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
    base_url="https://dev.aigw.scdom.net/anthropic",
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
GET https://dev.aigw.scdom.net/v1/models
```

Returns the list of models configured in LiteLLM. Authentication is required.

### Request

```http
GET /v1/models HTTP/1.1
Host: dev.aigw.scdom.net
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

**Fallback behaviour:** If a request to `gemini-1.5-pro` fails, the gateway automatically retries with `claude-sonnet-4-6`. LiteLLM is configured with `num_retries: 3` and `allowed_fails: 1` globally.

---

## 6a. Providers

### GitHub Copilot

**Endpoint:** `api.githubcopilot.com`

Model IDs: `copilot-gpt-4o`, `copilot-gpt-4o-mini`, `copilot-o3-mini`, `copilot-claude-3.5-sonnet`

**Obtaining a token:** Create a GitHub Personal Access Token (PAT) with the `copilot` scope at https://github.com/settings/tokens. The gateway is configured with `GITHUB_COPILOT_API_KEY` set to this token value. An active GitHub Copilot subscription (individual or enterprise) is required.

```bash
# GitHub Copilot via gateway
curl https://dev.aigw.scdom.net/v1/chat/completions \
  -H "Authorization: Bearer sk-your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "copilot-gpt-4o", "messages": [{"role": "user", "content": "Hello"}]}'
```

### Azure AI Foundry

**Endpoint:** Configured via `AZURE_API_BASE` environment variable (e.g. `https://<resource>.openai.azure.com/`).

Model IDs: `azure-gpt-4o`, `azure-gpt-4o-mini`, `azure-o3-mini`, `azure-gpt-4.1`

**Configuration:** The gateway is configured with the following environment variables:
- `AZURE_API_BASE` — your Azure OpenAI resource endpoint
- `AZURE_API_KEY` — your Azure API key from the Azure portal
- `AZURE_API_VERSION` — API version string (e.g. `2024-02-15-preview`)

See https://portal.azure.com → Azure OpenAI → Keys and Endpoint.

```bash
# Azure AI Foundry via gateway
curl https://dev.aigw.scdom.net/v1/chat/completions \
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
    url = "https://dev.aigw.scdom.net/v1/chat/completions"
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

### Cache bypass headers

To skip the semantic cache for a single request, send one of the following headers:

| Header | Value | Effect |
|---|---|---|
| `Cache-Control` | `no-cache` | Bypasses the cache; the response is fetched from LiteLLM and stored for future requests |
| `x-cache` | `bypass` | Same behaviour as `Cache-Control: no-cache` — bypasses cache for this call only |

When the cache is bypassed, the response header will be `x-cache: BYPASS` (not `MISS`).

```bash
# Using x-cache: bypass
curl https://dev.aigw.scdom.net/v1/chat/completions \
  -H "Authorization: Bearer sk-YOUR-KEY-HERE" \
  -H "x-cache: bypass" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "What is today'\''s date?"}]}'
```

### X-Cache response header

Every response from the cache service includes an `X-Cache` header:

| Value | Meaning |
|---|---|
| `HIT` | Response was served from cache (exact or semantic match) |
| `MISS` | Response was fetched from LiteLLM and stored (or not stored, if streaming) |
| `BYPASS` | Cache was explicitly bypassed via `Cache-Control: no-cache` or `x-cache: bypass` header |

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Cache: HIT
```

### TTL

Cache TTL is configured per-team in Redis (`policy:{team_id}`, field `ttl_seconds`). The service default applies when no team policy is present.

### Intent classification

The cache service classifies each request into one of eight intent categories based on keywords in the prompt. No prompt text is stored — only the classified intent label.

| Intent | Description |
|---|---|
| `debugging` | Diagnosing errors or unexpected behaviour |
| `testing` | Writing or reviewing tests |
| `refactoring` | Code restructuring without behaviour changes |
| `code_review` | Reviewing existing code for quality or correctness |
| `documentation` | Writing or updating docs, comments, README files |
| `code_generation` | Writing new code from a description |
| `question` | General questions about code or concepts |
| `general` | Catch-all for requests that do not match the above |

Intent distribution is visible in aggregate via `GET /reports/intents` on the admin API (see [Admin REST API](#10-admin-rest-api)).

### Cache opt-out

To disable caching for a specific team or project, set `opt_out: true` in the team's Redis policy hash. This can be done via the admin REST API (policies endpoint) or directly via the admin portal UI.

For per-request bypass, use the `x-cache: bypass` or `Cache-Control: no-cache` header (see [Cache bypass headers](#cache-bypass-headers) above).

---

## 10. Admin REST API

The admin REST API is available at `https://dev.aigw.scdom.net/api/admin`. All endpoints require the `X-Admin-Token` header (value from the `ADMIN_TOKEN` environment variable).

```
X-Admin-Token: <admin-token>
```

The developer portal routes under `/*` are excluded from admin auth and manage their own session-cookie authentication.

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

### Analytics Reports

All report endpoints require the `X-Admin-Token` header. Role requirements are noted per endpoint.

```
GET /reports/developers        Developer productivity leaderboard (admin+)
GET /reports/outcomes          Cost-per-PR / cost-per-commit per developer (admin+)
GET /reports/model-calibration Per-developer model tier distribution (admin+)
GET /reports/sessions          Session quality aggregate by developer (admin+)
GET /reports/guardrails        Guardrail hit analytics, top triggering developers (superadmin only)
GET /reports/intents           Intent distribution across sessions (no role requirement)
GET /reports/team-efficiency   Team-level efficiency metrics (no role requirement)
```

### Developer Management

```
GET /developers                   List all developers with email and team (admin+)
GET /developers/{id}              Individual developer profile (admin+)
GET /developers/{id}/stats        Detailed stats; optional ?period= query param; includes by_model and by_repo breakdowns (admin+)
GET /developers/at-risk           Developers with struggle signals (superadmin only)
```

### Budget Notifications

```
GET  /org/notifications        Get the currently configured webhook URL
PUT  /org/notifications        Set a Slack-compatible webhook URL for budget alerts
POST /org/notifications/test   Fire a test notification to the configured webhook
```

Budget alert webhooks send an HTTP POST to the configured URL when a team approaches or exceeds its budget. A Redis dedup key prevents duplicate alerts within the same alert window.

**PUT /org/notifications — request body**

```json
{
  "webhook_url": "https://hooks.slack.com/services/T.../B.../..."
}
```

### GitHub Webhook

```
POST /webhooks/github
```

Receives GitHub push and pull-request events and attributes commits to developer sessions. The request must include a valid `X-Hub-Signature-256` HMAC header (computed with the `GITHUB_WEBHOOK_SECRET` env var). Configure the webhook in your GitHub repository or organisation settings to point at `https://dev.aigw.scdom.net/api/admin/webhooks/github`.

### Budget Forecast

```
GET /budget/forecast
```

Returns the projected end-of-month spend per team based on the month-to-date burn rate. No role requirement beyond a valid `X-Admin-Token`.

---

## 10a. Admin Role-Based Access Control

The `require_admin_auth` dependency checks the `role` field on the authenticated admin session. Three roles are recognised:

| Role | Access |
|---|---|
| `viewer` | Read-only access to aggregate stats, cost reports by team / area / model. Cannot access any endpoint that returns individual developer PII (email, per-developer breakdowns). |
| `admin` | Full read access including developer email lists, individual stats, and model calibration reports. Can manage teams, API keys, and policies. |
| `superadmin` | All `admin` capabilities plus access to `/developers/at-risk` and `/reports/guardrails` (individually-identified behavioural data). Required for all destructive operations (team deletion, key revocation at scale). |

Role is stored on the admin user record.

---

---

## 11. Unified Auth API

All endpoints at `/auth/*` are served by the admin service on `:8005`.
Session tokens are passed as `Authorization: Bearer <token>`.
The legacy `/admin-auth/*` and `/dev-auth/*` routes remain for backwards compatibility and delegate to these endpoints internally.

### 11.1 Login

```
POST /auth/login
```

**Request body**

```json
{
  "email": "dev@simcorp.com",
  "password": "YourPassword123!",
  "remember_me": false
}
```

**Response**

```json
{
  "token": "<session-token>",
  "user": {
    "user_id": "uuid",
    "email": "dev@simcorp.com",
    "display_name": "Dev User",
    "roles": [{"role": "engineer", "scope_type": "global", "scope_id": null}],
    "primary_team_id": "uuid | null",
    "team_name": "Engineering | null"
  },
  "must_change_password": false
}
```

Session TTL: 8 h for admins (30 days with `remember_me: true`), 7 days for developers (30 days with `remember_me: true`).

If `must_change_password` is `true`, the session is valid only for `POST /auth/change-password`. All other endpoints return `403` until the password is changed.

### 11.2 Self-service registration

```
POST /auth/register
```

Creates a developer account. Restricted to corporate email domains if `ALLOWED_EMAIL_DOMAINS` is configured.

**Request body**

```json
{
  "email": "dev@simcorp.com",
  "display_name": "Dev User",
  "password": "YourPassword123!"
}
```

Password requirements: 12+ characters, uppercase, lowercase, digit, special character.

### 11.3 Current user

```
GET /auth/me
Authorization: Bearer <token>
```

Returns the full session payload (same shape as the `user` object in the login response).

### 11.4 Logout

```
POST /auth/logout
Authorization: Bearer <token>
```

Deletes the Redis session immediately. Returns `{"ok": true}`.

### 11.5 Change password

```
POST /auth/change-password
Authorization: Bearer <token>
```

```json
{
  "current_password": "OldPassword123!",
  "new_password": "NewPassword456@"
}
```

Clears the current session on success. Re-login required.

### 11.6 SSO / OIDC

```
GET /auth/oidc/login
```

Redirects to the configured OIDC provider (Azure Entra ID). Sets a short-lived `oidc_state` cookie for CSRF protection.

```
GET /auth/oidc/callback?code=...&state=...
```

Exchanges the authorization code for an id_token, extracts `email` and `name` claims, then:
- Finds the existing user record by email, or creates a new one with the `engineer` role
- Issues a session token
- Redirects to `/admin?sso_token=<token>` (for admin-role users) or `/?sso_token=<token>` (for developers)

Both portal frontends read `?sso_token=` on mount and store it as a session.

### 11.7 Invitations

Invite links are the only way to onboard users when `ALLOWED_EMAIL_DOMAINS` is not set or when you want to pre-assign a specific role.

**Create invite**

```
POST /auth/invitations
Authorization: Bearer <token>    (gateway_admin or team_admin)
```

```json
{
  "email": "newdev@simcorp.com",
  "role": "engineer",
  "scope_type": "global",
  "scope_id": null
}
```

`team_admin` callers: `role` must be `engineer` or `reporter`; `scope_type` must be `team` and `scope_id` must be a team the caller manages.

**Response** — includes a ready-to-copy `accept_url`:

```json
{
  "invite_id": "uuid",
  "email": "newdev@simcorp.com",
  "role": "engineer",
  "expires_at": "2026-05-15T10:00:00+00:00",
  "accept_url": "https://dev.aigw.scdom.net/api/admin/auth/invitations/accept?token=...",
  "token": "<raw-token>"
}
```

The raw token is shown **once** and not stored. Share the `accept_url` with the recipient.

**List invitations**

```
GET /auth/invitations
Authorization: Bearer <token>
```

**Revoke pending invite**

```
DELETE /auth/invitations/{invite_id}
Authorization: Bearer <token>
```

**Accept invite** (public endpoint)

```
POST /auth/invitations/accept
```

```json
{
  "token": "<raw-token-from-url>",
  "display_name": "New Developer",
  "password": "NewPassword123!"
}
```

Creates the user account, grants the pre-assigned role, and returns a session token ready for immediate use.

### 11.8 Service accounts

Service accounts are API-key-only principals — no portal login.

**Create**

```
POST /auth/service-accounts
Authorization: Bearer <token>
```

```json
{
  "name": "CI Pipeline",
  "description": "GitHub Actions integration",
  "team_id": "uuid | null"
}
```

**Response** — `api_key` is shown **once**:

```json
{
  "id": "uuid",
  "name": "CI Pipeline",
  "key_prefix": "sa_0ly5dAAL",
  "api_key": "sa_0ly5dAALXUAHb...",
  "team_id": null
}
```

**List / update status / rotate key**

```
GET    /auth/service-accounts
PATCH  /auth/service-accounts/{id}/status?status=suspended
POST   /auth/service-accounts/{id}/rotate-key
```

### 11.9 User management (gateway_admin only)

```
GET    /auth/users                          List all users
POST   /auth/users/{id}/roles              Grant role
DELETE /auth/users/{id}/roles/{role}       Revoke role
PATCH  /auth/users/{id}/status?status=...  active | suspended
```

```
GET  /admin/users?search=&status=&role=&limit=&offset=   Paginated user list
GET  /admin/users/{id}                                    User detail with roles + team
```

### 11.10 RBAC roles reference

| Role | Scope | Capabilities |
|---|---|---|
| `gateway_admin` | global | All admin APIs, all portals |
| `area_owner` | area | Manage teams + policies within their area |
| `team_admin` | team | Manage team members, keys, budgets; invite engineers/reporters to their team |
| `engineer` | global | Developer portal; personal API keys; transformation stats |
| `reporter` | global | Read-only developer portal |
| `service_account` | — | API key bearer only; no portal access |

---

*Last updated: 2026-05-13*
