import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# Config defaults were removed (Azure-only transition); set test placeholders so
# `app.config.Settings()` can import. setdefault lets CI's real env override.
# IDENTITY_SERVICE_TOKEN is empty here on purpose: these tests exercise the
# registration path in fail-open mode; the enforced path is covered by tests
# that monkeypatch the token to a non-empty value.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ADMIN_URL", "http://admin:8005")
os.environ.setdefault("IDENTITY_SERVICE_TOKEN", "")
