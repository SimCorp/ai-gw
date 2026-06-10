"""Pytest configuration for workflow-worker tests.
Ensures the worker's app package is first in sys.path when collected from root."""

import os
import sys
from pathlib import Path

_SERVICE_ROOT = str(Path(__file__).parents[1])
if _SERVICE_ROOT not in sys.path:
    sys.path.insert(0, _SERVICE_ROOT)

# Settings.from_env() requires these (localhost/docker defaults removed in the
# Azure-only transition). setdefault lets CI's real env override.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("AGENT_RELAY_URL", "http://agent-relay:8007")
os.environ.setdefault("ADMIN_URL", "http://admin:8005")
