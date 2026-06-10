import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# Config defaults were removed (Azure-only transition); set test placeholders so
# `config.Settings()` can build. setdefault lets CI's real env override.
# RELAY_SECRET is empty (fail-open) — the enforced path is covered by tests that
# build Settings(relay_secret="s3cret") directly.
os.environ.setdefault("REDIS_URL", "redis://redis:6379/0")
os.environ.setdefault("RELAY_SECRET", "")
