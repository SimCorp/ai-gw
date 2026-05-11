"""Ensure the cache service's app module is importable when pytest collects
from the repo root (multiple services share the 'app' package name)."""
import sys
from pathlib import Path

# Insert this service's root first so `import app` resolves to cache/app
_SERVICE_ROOT = str(Path(__file__).parents[1])
if _SERVICE_ROOT not in sys.path:
    sys.path.insert(0, _SERVICE_ROOT)
