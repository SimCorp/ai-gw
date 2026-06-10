import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# Config defaults were removed (Azure-only transition); set test placeholders so
# `app.config.Settings()` can import. setdefault lets CI's real env override.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("AUTH_URL", "http://auth:8001")
os.environ.setdefault("ADMIN_URL", "http://admin:8005")
os.environ.setdefault("EMBEDDING_API_KEY", "sk-test")
os.environ.setdefault("EMBEDDING_BASE_URL", "http://litellm:8003/v1")
