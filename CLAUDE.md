# AI Gateway — SimCorp Developer Platform

Enterprise AI gateway for ~2000 engineers. Deployed to Azure. The Docker Compose setup exists for local testing only and is rarely needed.

## Running tests

```bash
pip install \
  -e "services/auth[dev]" \
  -e "services/cache[dev]" \
  -e "services/observability[dev]" \
  -e "services/admin[dev]" \
  -e "services/identity[dev]" \
  -e "services/agent-relay[dev]"

pytest services/ -v
```

> Note: most service tests run without Docker. The `identity` suite is the
> exception — it uses `testcontainers[postgres]` and needs a running Docker
> daemon (matching the `admin` service's approach).

## Linting

```bash
ruff check services/
ruff format services/
```

## Architecture

See `docs/superpowers/specs/2026-05-05-ai-gateway-design.md` for the full design.

Request path: `caller → auth → cache → litellm → provider`
