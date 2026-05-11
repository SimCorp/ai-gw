"""Pytest configuration for workflow-worker tests.
Ensures the worker's app package is first in sys.path when collected from root."""
import sys
from pathlib import Path

_SERVICE_ROOT = str(Path(__file__).parents[1])
if _SERVICE_ROOT not in sys.path:
    sys.path.insert(0, _SERVICE_ROOT)
