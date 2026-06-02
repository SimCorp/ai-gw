"""Root conftest for the services/ tree.

Multiple services share the package name 'app'.  pytest collects all tests in
a single process, so whichever service's conftest.py ran last wins at
sys.path[0] for the whole execution phase.  This hook re-establishes the
correct sys.path and flushes the 'app' namespace when switching between
services, so fixtures doing lazy `from app.xxx import ...` always get the
right one without breaking tests that captured module-level references at
import time.
"""

import sys
from pathlib import Path

_SERVICES_ROOT = Path(__file__).parent
_current_service: str | None = None


def _service_root(item) -> str | None:
    try:
        rel = Path(item.fspath).relative_to(_SERVICES_ROOT)
        return str(_SERVICES_ROOT / rel.parts[0])
    except (ValueError, IndexError):
        return None


def pytest_runtest_setup(item):
    global _current_service
    svc = _service_root(item)
    if svc is None or svc == _current_service:
        return
    _current_service = svc
    for k in list(sys.modules.keys()):
        if k == "app" or k.startswith("app."):
            del sys.modules[k]
    if svc in sys.path:
        sys.path.remove(svc)
    sys.path.insert(0, svc)
