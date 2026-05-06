# Tests

Integration and smoke tests for the SimCorp AI Gateway.

## Prerequisites

- Docker and Docker Compose v2
- The gateway stack must be running (or started together with the test profile)
- For the Claude agent: a valid gateway API key (`sk-` prefixed, issued by the admin service)

## Running tests

### Quick start — gateway + tests in one command

```bash
# Start gateway and immediately run the full test suite
docker compose -f infra/docker-compose.yml -f infra/docker-compose.test.yml \
    --profile test up --wait && \
docker compose -f infra/docker-compose.yml -f infra/docker-compose.test.yml \
    --profile test run --rm test-runner
```

### Using Make (recommended)

```bash
# Start gateway first (if not already running)
make up

# Full test suite
make test

# Smoke tests only
make test-smoke

# Proxy/cache tests only
make test-proxy
```

### Directly with docker compose

```bash
COMPOSE="docker compose -f infra/docker-compose.yml -f infra/docker-compose.test.yml --profile test"

# All tests
$COMPOSE run --rm test-runner

# Specific file
$COMPOSE run --rm test-runner tests/smoke/test_health.py

# Specific pytest marker
$COMPOSE run --rm test-runner -v -m smoke

# Pass any pytest flag
$COMPOSE run --rm test-runner --co -q   # collect-only, list all tests
```

### Without Docker (unit tests, no live services needed)

```bash
pip install -e "services/auth[dev]" -e "services/cache[dev]" \
            -e "services/observability[dev]" -e "services/admin[dev]"
pytest services/ -v
```

## Test markers

| Marker   | What it covers                                       |
|----------|------------------------------------------------------|
| `smoke`  | Minimal health checks; fast; safe to run on every PR |
| `proxy`  | Cache proxy behaviour, hit/miss, semantic matching   |
| `auth`   | Token validation, rate limiting, key issuance        |
| `admin`  | Team management, dashboard endpoints                 |

Mark tests in their source file:

```python
import pytest

@pytest.mark.smoke
def test_cache_health(cache_url):
    ...
```

## Environment variables available inside test-runner

| Variable            | Default                              | Description                  |
|---------------------|--------------------------------------|------------------------------|
| `AUTH_URL`          | `http://auth:8001`                   | Auth service base URL        |
| `CACHE_URL`         | `http://cache:8002`                  | Cache proxy base URL         |
| `LITELLM_URL`       | `http://litellm:8003`                | LiteLLM base URL             |
| `OBSERVABILITY_URL` | `http://observability:8004`          | Observability base URL       |
| `ADMIN_URL`         | `http://admin:8005`                  | Admin portal base URL        |
| `ADMIN_TOKEN`       | `local-dev-admin-key-change-in-prod` | Admin API bearer token       |

## Launching the Claude agent

The `claude-agent` container runs a Claude Code session that routes all LLM calls
through the SimCorp AI Gateway instead of directly to Anthropic.

```bash
# Export a gateway API key (issued from the admin service)
export ANTHROPIC_API_KEY=sk-your-gateway-key-here

# Launch interactive session
make claude-agent

# Or directly:
docker compose -f infra/docker-compose.yml -f infra/docker-compose.test.yml \
    --profile test run --rm -it claude-agent
```

The container runs `bootstrap.sh` on startup which:
1. Validates `ANTHROPIC_API_KEY` is set
2. Checks the cache service health endpoint
3. Probes the models endpoint
4. Prints a connection banner
5. Drops into an interactive `claude` REPL

The agent's `CLAUDE.md` (auto-loaded by Claude Code) documents the gateway topology,
available models, and usage patterns.

### Getting a gateway API key

```bash
# Create a team (if needed)
curl -X POST -H "Authorization: Bearer ${ADMIN_TOKEN}" \
     -H "Content-Type: application/json" \
     -d '{"name": "my-team"}' \
     http://localhost:8005/teams

# Issue an API key for the team
curl -X POST -H "Authorization: Bearer ${ADMIN_TOKEN}" \
     -H "Content-Type: application/json" \
     -d '{"team_id": "<team-id>", "description": "claude-agent dev key"}' \
     http://localhost:8005/keys
```

## Directory layout

```
tests/
├── Dockerfile              # test-runner container image
├── README.md               # this file
├── conftest.py             # shared pytest fixtures (create as needed)
├── smoke/                  # fast health-check tests (marker: smoke)
├── proxy/                  # cache proxy tests (marker: proxy)
├── auth/                   # auth service tests (marker: auth)
└── claude-agent/
    ├── Dockerfile          # Claude agent container image
    ├── bootstrap.sh        # startup script
    └── CLAUDE.md           # context auto-loaded by Claude Code
```
