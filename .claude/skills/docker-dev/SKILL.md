---
name: docker-dev
description: Docker Compose dev environment commands for ai-gw — up, down, rebuild a service, tail logs
disable-model-invocation: true
---

Common docker compose commands for this project. All commands use `infra/docker-compose.yml`.

## Start everything
```bash
docker compose -f infra/docker-compose.yml up --build
```

## Stop everything
```bash
docker compose -f infra/docker-compose.yml down
```

## Rebuild and restart a single service (e.g. auth, cache, observability, admin, litellm)
```bash
docker compose -f infra/docker-compose.yml up --build --no-deps -d <service>
```

## Tail logs for a service
```bash
docker compose -f infra/docker-compose.yml logs -f <service>
```

## Reset everything (volumes too)
```bash
docker compose -f infra/docker-compose.yml down -v
```

## Run tests without Docker
```bash
pip install \
  -e "services/auth[dev]" \
  -e "services/cache[dev]" \
  -e "services/observability[dev]" \
  -e "services/admin[dev]"

pytest services/ -v
```

## Service ports
| Service | URL |
|---|---|
| auth | http://localhost:8001 |
| cache | http://localhost:8002 |
| litellm | http://localhost:8003 |
| observability | http://localhost:8004 |
| admin | http://localhost:8005 |
| dex (mock OIDC) | http://localhost:5556 |
| ollama | http://localhost:11434 |
