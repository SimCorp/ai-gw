import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# Config defaults were removed (Azure-only transition); set test placeholders so
# `app.config.Settings()` can import. setdefault lets CI's real env override.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("INTERNAL_API_KEY", "sk-internal-test")
