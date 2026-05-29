"""
Budget alert configuration and alert history.
Alerts fire when a team's daily spend exceeds threshold × rolling average.
Alert config is persisted in org_settings (same pattern as budget.py).
Alert history is read from audit_log rows with action='budget_spike_alert'.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter(prefix="/budget/alerts", tags=["alerts"])

_CONFIG_KEY = "budget_alert_config"


class AlertConfig(BaseModel):
    spike_multiplier: float = 3.0   # fire when daily > avg * this
    webhook_url: str | None = None
    email_enabled: bool = True


async def _read_alert_config(session: AsyncSession) -> dict:
    try:
        row = (await session.execute(
            text("SELECT value FROM org_settings WHERE key = :k"),
            {"k": _CONFIG_KEY},
        )).first()
        if row:
            return json.loads(row[0])
    except Exception:
        pass
    return {"spike_multiplier": 3.0, "webhook_url": None, "email_enabled": True}


@router.get("/config")
async def get_alert_config(
    session: AsyncSession = Depends(get_session),
):
    return await _read_alert_config(session)


@router.put("/config")
async def set_alert_config(
    body: AlertConfig,
    session: AsyncSession = Depends(get_session),
):
    try:
        await session.execute(
            text(
                "INSERT INTO org_settings (key, value, updated_at) VALUES (:key, :value, NOW()) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()"
            ),
            {"key": _CONFIG_KEY, "value": json.dumps(body.dict())},
        )
        await session.commit()
    except Exception:
        await session.rollback()
    return {"message": "Alert config updated"}


@router.get("")
async def list_alerts(
    team_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    session: AsyncSession = Depends(get_session),
):
    """Return recent budget spike alerts stored in audit_log as action='budget_spike_alert'."""
    try:
        where = "action = 'budget_spike_alert'"
        params: dict = {"limit": limit}
        if team_id:
            where += " AND resource_id = :team_id"
            params["team_id"] = team_id
        rows = (await session.execute(text(f"""
            SELECT id, timestamp, actor, resource_id, details
            FROM audit_log WHERE {where}
            ORDER BY timestamp DESC LIMIT :limit
        """), params)).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        return []
