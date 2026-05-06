# SimCorp AI Gateway — Sandbox

You are running **through the SimCorp enterprise AI Gateway** at `http://cache:8002/anthropic`.

## Quick reference

```bash
# Check gateway is reachable
gw-health

# List available models
gw-models

# Verify Claude is using the gateway
claude-check

# One-shot prompt
claude "What models are available through the gateway?"

# Interactive session
claude
```

## Gateway services (internal Docker DNS)

| Service       | URL                           | Purpose                        |
|---------------|-------------------------------|--------------------------------|
| cache         | http://cache:8002             | Proxy + semantic/exact cache   |
| auth          | http://auth:8001              | API key validation             |
| litellm       | http://litellm:8003           | Provider routing               |
| observability | http://observability:8004     | Usage logging                  |
| admin         | http://admin:8005             | Team/key management            |

## Admin portal

Open http://localhost:8005/portal in your browser to create API keys.

To create a key via CLI:
```bash
# Create a team (admin token required)
curl -s -X POST http://admin:8005/teams \
  -H "X-Admin-Token: local-dev-admin-key-change-in-prod" \
  -H "Content-Type: application/json" \
  -d '{"name":"sandbox","slug":"sandbox"}' | python3 -m json.tool

# Create a key for that team
curl -s -X POST http://admin:8005/teams/<team-id>/keys \
  -H "X-Admin-Token: local-dev-admin-key-change-in-prod" \
  -H "Content-Type: application/json" \
  -d '{"name":"sandbox-key"}' | python3 -m json.tool
```

Then set the key: `export ANTHROPIC_API_KEY=sk-...`
