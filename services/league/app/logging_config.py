"""Structured JSON logging + request/trace correlation for gateway services.

Copied verbatim per-service (build contexts are isolated, matching the existing
per-service ``app/observability.py``). ``init_logging()`` installs a JSON formatter on
stdout (picked up by Docker -> Alloy -> Loki). ``CorrelationIdMiddleware`` is a *pure
ASGI* middleware (deliberately NOT ``@app.middleware`` / Starlette BaseHTTPMiddleware,
which runs in a separate task context where the contextvar set there is invisible to
the log filter during the endpoint call) — it binds the request's ``x-request-id`` and
``x-session-trace-id`` to contextvars so every log line carries them.

Set ``LOG_FORMAT=text`` to opt out of JSON; ``LOG_LEVEL`` to change the level.
"""

from __future__ import annotations

import logging
import os
import uuid
from contextvars import ContextVar

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
session_trace_id_ctx: ContextVar[str] = ContextVar("session_trace_id", default="-")


class _CorrelationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        record.session_trace_id = session_trace_id_ctx.get()
        return True


def init_logging(service_name: str) -> None:
    """Configure root logging once at startup. Clears existing handlers so it overrides
    any prior ``logging.basicConfig``."""
    fmt = os.environ.get("LOG_FORMAT", "json").lower()
    level = os.environ.get("LOG_LEVEL", "INFO").upper()

    handler = logging.StreamHandler()
    handler.addFilter(_CorrelationFilter())

    if fmt == "text":
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s [req=%(request_id)s]: %(message)s"))
    else:
        from pythonjsonlogger import jsonlogger

        handler.setFormatter(
            jsonlogger.JsonFormatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s %(session_trace_id)s",
                rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
                static_fields={"service": service_name},
            )
        )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True


class CorrelationIdMiddleware:
    """Pure ASGI middleware: bind correlation IDs to contextvars for the duration of the
    request and echo ``x-request-id`` on the response. Registered via
    ``app.add_middleware(CorrelationIdMiddleware)``."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        rid = headers.get("x-request-id") or headers.get("x-correlation-id") or str(uuid.uuid4())
        stid = headers.get("x-session-trace-id", "-")
        rid_token = request_id_ctx.set(rid)
        stid_token = session_trace_id_ctx.set(stid)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((b"x-request-id", rid.encode("latin-1")))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            request_id_ctx.reset(rid_token)
            session_trace_id_ctx.reset(stid_token)
