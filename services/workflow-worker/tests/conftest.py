"""Pytest configuration for workflow-worker tests.

Ensures the worker's app package is first in sys.path when collected from root,
and sets the env Settings.from_env() reads (localhost/docker defaults removed in
the Azure-only transition). setdefault lets CI's real env override.
"""

import os
import sys
from pathlib import Path

# Multiple services are installed editable and all expose a top-level `app`
# package. Flush any stale `app.*` captured by another service and force this
# service's root to the front of sys.path (mirrors services/conftest.py). This
# is needed because the editable installs make a sibling service's `app`
# importable at collection time even when this suite runs alone.
_SERVICE_ROOT = str(Path(__file__).parents[1])
for _k in list(sys.modules.keys()):
    if _k == "app" or _k.startswith("app."):
        del sys.modules[_k]
if _SERVICE_ROOT in sys.path:
    sys.path.remove(_SERVICE_ROOT)
sys.path.insert(0, _SERVICE_ROOT)

# Required by Settings.from_env() via os.environ[...]. Use the +asyncpg driver
# form: workflow-worker's from_env strips the suffix, and it keeps the scanner
# service's async SQLAlchemy engine valid when both suites share this process.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("AGENT_RELAY_URL", "http://agent-relay:8007")
os.environ.setdefault("ADMIN_URL", "http://admin:8005")

# ACA-Jobs runtime config (only consumed when AGENT_CONTAINER_RUNTIME=aca_job).
os.environ.setdefault("AGENT_RUNNER_JOB_NAME", "job-agent-runner-test-sdc")
os.environ.setdefault("AZURE_RESOURCE_GROUP", "rg-test")
os.environ.setdefault("AZURE_SUBSCRIPTION_ID", "00000000-0000-0000-0000-000000000000")
os.environ.setdefault("AIGW_RUNS_SHARE", "aigw-runs")
os.environ.setdefault("AIGW_RUNS_STORAGE_ACCOUNT", "stsdctest")
