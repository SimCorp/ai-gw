"""Ensure the auth service's app module is importable when pytest collects
from the repo root (multiple services share the 'app' package name)."""

import os
import sys
from pathlib import Path

# Config fields are required (no local-dev defaults); supply test placeholders
# before any `app.*` import triggers `Settings()` at module load.
os.environ.setdefault("REDIS_URL", "redis://test-redis.invalid:6379/0")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@test-db.invalid:5432/test")
os.environ.setdefault("JWKS_URI", "https://test-idp.invalid/keys")
os.environ.setdefault("ENTRA_TENANT_ID", "test-tenant")
os.environ.setdefault("ENTRA_CLIENT_ID", "test-client")
os.environ.setdefault("ADMIN_URL", "http://test-admin.invalid:8005")

_SERVICE_ROOT = str(Path(__file__).parents[1])
for _k in list(sys.modules.keys()):
    if _k == "app" or _k.startswith("app."):
        del sys.modules[_k]
sys.path.insert(0, _SERVICE_ROOT)
