"""Ensure the cache service's app module is importable when pytest collects
from the repo root (multiple services share the 'app' package name)."""

import os
import sys
from pathlib import Path

_SERVICE_ROOT = str(Path(__file__).parents[1])
for _k in list(sys.modules.keys()):
    if _k == "app" or _k.startswith("app."):
        del sys.modules[_k]
sys.path.insert(0, _SERVICE_ROOT)

# Provide required env vars so importing app.config doesn't raise when no .env is present.
os.environ.setdefault("DATABASE_URL", "postgresql://placeholder/placeholder")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("LITELLM_URL", "http://localhost:8003")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-test")
os.environ.setdefault("AUTH_URL", "http://localhost:8001")
os.environ.setdefault("OBSERVABILITY_URL", "http://localhost:8004")
os.environ.setdefault("EMBEDDING_API_KEY", "sk-test")
os.environ.setdefault("EMBEDDING_BASE_URL", "http://localhost:8003")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal")
