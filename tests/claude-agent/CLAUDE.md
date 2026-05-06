# SimCorp AI Gateway — Agent Context

This Claude Code session is running **through the SimCorp enterprise AI Gateway**, not
directly against the Anthropic API. All requests are proxied, authenticated, cached,
and logged by the gateway stack.

## Gateway topology

| Service        | Internal URL                       | Purpose                           |
|----------------|------------------------------------|-----------------------------------|
| cache          | http://cache:8002                  | Semantic + exact cache proxy      |
| auth           | http://auth:8001                   | JWT / API key validation          |
| litellm        | http://litellm:8003                | Provider routing (OpenAI-compat.) |
| observability  | http://observability:8004          | Async event ingestion             |
| admin          | http://admin:8005                  | Team management & dashboards      |

## Active routing

`ANTHROPIC_BASE_URL` is set to `http://cache:8002/anthropic`, so the Anthropic SDK
routes through the cache service which applies:
- Exact-match caching (identical prompts return instantly from Redis)
- Semantic caching (near-duplicate prompts served from cache)
- Rate limiting and cost tracking per API key

## Available models

Models are configured in LiteLLM at `http://litellm:8003`. The full list is available at:

```
curl http://cache:8002/v1/models
```

Typical models available in local dev:
- `gpt-4o` (via OpenAI passthrough)
- `gpt-4o-mini`
- `claude-3-5-sonnet-20241022` (via Anthropic passthrough)
- `ollama/llama3.2` (local Ollama, when started with `--profile ollama`)

## Authentication

Requests are authenticated via `ANTHROPIC_API_KEY`, which in this environment is a
gateway `sk-` prefixed key managed by the admin service. It is **not** a real Anthropic
API key.

To issue a new key or inspect usage:

```
# List teams
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://admin:8005/teams

# Create an API key
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"team_id": "...", "description": "test key"}' \
     http://admin:8005/keys
```

## Notes for agent tasks

- Prefer the internal service URLs listed above when making HTTP requests.
- The gateway records all completions; avoid sending PII or sensitive data.
- Rate limits are enforced per API key; long-running batch tasks should be spread out.
