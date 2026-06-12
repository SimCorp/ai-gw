"""Azure-native observability bootstrap (OpenTelemetry -> Application Insights).

Opt-in and fail-safe: a no-op unless APPLICATIONINSIGHTS_CONNECTION_STRING (or the
legacy APPINSIGHTS_CONNECTION_STRING) is set, and any initialization error is
swallowed so telemetry can never block service startup.

When enabled it ships structured logs, distributed traces (incoming FastAPI
requests + outbound httpx/requests calls) and metrics to Application Insights, so
incidents like a crash-on-startup are searchable centrally instead of requiring a
live `az containerapp logs` tail.
"""

from __future__ import annotations

import logging
import os

_log = logging.getLogger(__name__)
_initialised = False


def init_observability(app=None, *, service_name: str) -> None:
    """Wire Azure Monitor / OpenTelemetry if a connection string is configured."""
    global _initialised
    if _initialised:
        return
    conn = (
        os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
        or os.environ.get("APPINSIGHTS_CONNECTION_STRING")
        or ""
    ).strip()
    if not conn:
        return
    try:
        os.environ.setdefault("OTEL_SERVICE_NAME", service_name)
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(connection_string=conn)
        if app is not None:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
        _initialised = True
        _log.info("observability: Azure Monitor enabled (service=%s)", service_name)
    except Exception as exc:  # never block startup on telemetry
        _log.warning("observability: init skipped (%s)", exc)
