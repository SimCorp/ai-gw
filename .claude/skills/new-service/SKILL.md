---
name: new-service
description: Scaffold a new FastAPI microservice in services/ matching the existing service structure
disable-model-invocation: true
---

To add a new service, follow this structure (mirroring services/auth or services/cache):

## Directory layout
```
services/<name>/
  Dockerfile
  pyproject.toml
  app/
    __init__.py
    config.py       # Settings via pydantic-settings, reads from env
    main.py         # FastAPI app + lifespan + health endpoint
    router.py       # Service-specific routes
  tests/
    __init__.py
    test_<name>.py
```

## Dockerfile (copy from any existing service)
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -e ".[dev]"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80XX"]
```

## pyproject.toml template
```toml
[project]
name = "ai-gw-<name>"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic-settings>=2.0",
    # add service-specific deps here
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.24", "httpx>=0.27"]

[build-system]
requires = ["setuptools"]
build-backend = "setuptools.backends.legacy:BuildBackend"
```

## main.py template
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .router import router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    yield
    # shutdown

app = FastAPI(title="ai-gw-<name>", lifespan=lifespan)
app.include_router(router)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

## After scaffolding
1. Add to `infra/docker-compose.yml` (copy an existing service block, update port)
2. Add to `infra/postgres/init.sql` if the service needs its own tables
3. Add `"services/<name>[dev]"` to the pip install steps in `CLAUDE.md` and `.github/workflows/ci.yml`
4. Update `CLAUDE.md` service ports table
