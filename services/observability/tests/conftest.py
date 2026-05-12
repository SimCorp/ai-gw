"""Ensure the observability service's app module is importable when pytest
collects from the repo root (multiple services share the 'app' package name)."""
import sys
from pathlib import Path

_SERVICE_ROOT = str(Path(__file__).parents[1])
for _k in list(sys.modules.keys()):
    if _k == "app" or _k.startswith("app."):
        del sys.modules[_k]
sys.path.insert(0, _SERVICE_ROOT)
