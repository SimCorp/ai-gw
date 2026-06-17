import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# Required config (no local-dev defaults remain in app.config). Set before any
# test module imports app.config / instantiates Settings(). cors_origins is a
# list[str] so pydantic-settings parses it from env as JSON.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("LITELLM_URL", "http://litellm:8003")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-test")
os.environ.setdefault("CORS_ORIGINS", '["http://test"]')
