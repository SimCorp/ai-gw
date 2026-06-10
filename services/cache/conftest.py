import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# Config defaults were removed (Azure-only transition); set test placeholders so
# `app.config.Settings()` can import. setdefault lets CI's real env override.
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("LITELLM_URL", "http://litellm:8003")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-test")
os.environ.setdefault("AUTH_URL", "http://auth:8001")
os.environ.setdefault("OBSERVABILITY_URL", "http://observability:8004")
os.environ.setdefault("EMBEDDING_API_KEY", "sk-test")
os.environ.setdefault("EMBEDDING_BASE_URL", "http://litellm:8003/v1")
os.environ.setdefault("INTERNAL_API_KEY", "sk-internal-test")
