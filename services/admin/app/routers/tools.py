from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter(prefix="/tools", tags=["tools"])


class ToolToggle(BaseModel):
    enabled: bool


@router.get("")
async def list_tools(
    enabled_only: bool = Query(False),
    session: AsyncSession = Depends(get_session),
):
    query = "SELECT tool_id, label, category, enabled, updated_at FROM tool_config"
    if enabled_only:
        query += " WHERE enabled = true"
    query += " ORDER BY category, label"
    rows = (await session.execute(text(query))).mappings().all()
    return [dict(r) for r in rows]


@router.patch("/{tool_id}")
async def toggle_tool(
    tool_id: str,
    body: ToolToggle,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        text("""
            UPDATE tool_config
            SET enabled = :enabled, updated_at = NOW()
            WHERE tool_id = :tool_id
            RETURNING tool_id, label, category, enabled, updated_at
        """),
        {"tool_id": tool_id, "enabled": body.enabled},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Tool not found")
    await session.commit()
    return dict(row)
