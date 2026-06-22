import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# Config has no local defaults for required vars; set test placeholders so
# `app.config.Settings()` can import. setdefault lets CI's real env override.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("AUTH_URL", "http://auth:8001")
os.environ.setdefault("GRAPHIFY_GATEWAY_KEY", "sk-test")
os.environ.setdefault("GITHUB_TOKEN", "")
os.environ.setdefault("CORS_ORIGINS", "*")
