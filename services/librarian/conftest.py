import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# Config defaults were removed (Azure-only transition); set test placeholders so
# `app.config.Settings()` can import. setdefault lets CI's real env override.
# LIBRARIAN_SERVICE_TOKEN is empty (fail-open) — tests patch the auth boundary.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("AUTH_URL", "http://auth:8001")
os.environ.setdefault("EMBEDDING_API_KEY", "sk-test")
os.environ.setdefault("EMBEDDING_BASE_URL", "http://litellm:8003/v1")
os.environ.setdefault("CACHE_URL", "http://cache:8002")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3002,http://localhost:8080")
os.environ.setdefault("LIBRARIAN_SERVICE_TOKEN", "")
