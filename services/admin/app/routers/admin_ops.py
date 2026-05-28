"""Admin operational endpoints: manual trigger for background jobs."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import engine
from app.routers.unified_auth import require_platform_admin

router = APIRouter(prefix="/admin/ops", tags=["admin-ops"])


@router.post("/sync-workday")
async def trigger_workday_sync(
    current_user: dict = Depends(require_platform_admin),
):
    """Manually trigger a Workday sync run."""
    if os.getenv("WORKDAY_SYNC_ENABLED", "false").lower() != "true":
        return {
            "message": "Workday sync is disabled. Set WORKDAY_SYNC_ENABLED=true to enable.",
            "ran": False,
        }

    from app.jobs.workday_sync import run_workday_sync

    async with AsyncSession(engine) as session:
        result = await run_workday_sync(session)
    return {"ran": True, "result": result}


@router.post("/send-weekly-digest")
async def trigger_weekly_digest(
    current_user: dict = Depends(require_platform_admin),
):
    """Manually trigger the weekly manager digest."""
    from app.jobs.weekly_digest import send_weekly_digests

    async with AsyncSession(engine) as session:
        await send_weekly_digests(session)
    return {"message": "Weekly digest sent"}
