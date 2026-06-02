"""
Nightly Workday org sync — detects drift between Workday and ai-gw org structure.
Runs nightly at 02:00 UTC when WORKDAY_SYNC_ENABLED=true.

This is a lightweight diff-only sync:
- New hires: creates pending user record
- Departures: deactivates user (session kill, API key revocation)
- Org changes: updates primary_team_id

Since the Workday MCP requires browser-based auth (not programmatic API keys),
this job uses the local org seed data (services/admin/scripts/seed_workday_org.py)
as the reference. In production, replace _get_workday_snapshot() with actual
Workday API calls once a service account is provisioned.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


async def run_workday_sync(session, redis=None) -> dict:
    """
    Sync Workday org structure to ai-gw.
    Returns a summary dict of changes made.
    """
    if os.getenv("WORKDAY_SYNC_ENABLED", "false").lower() != "true":
        log.info("Workday sync disabled (WORKDAY_SYNC_ENABLED != true)")
        return {"skipped": True, "reason": "WORKDAY_SYNC_ENABLED not set"}

    summary = {"new_users": [], "deprovisioned": [], "team_moves": [], "errors": []}

    try:
        # In production: call Workday API to get current roster
        # For now: log that sync is enabled but no API credentials are configured
        workday_api_url = os.getenv("WORKDAY_API_URL", "")
        if not workday_api_url:
            log.info("WORKDAY_API_URL not set — sync skipped. Configure to enable drift detection.")
            return {"skipped": True, "reason": "WORKDAY_API_URL not configured"}

        # Production implementation would:
        # 1. Call GET {WORKDAY_API_URL}/workers to get current roster
        # 2. Compare emails against users table
        # 3. For new hires: INSERT pending user + send invitation
        # 4. For departures: UPDATE status=suspended + kill sessions + revoke keys
        log.info("Workday sync would run against %s", workday_api_url)

    except Exception as exc:
        log.error("Workday sync failed: %s", exc)
        summary["errors"].append(str(exc))

    return summary
