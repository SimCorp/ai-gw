"""Admin-only endpoints to nominate and retire AI Champions."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.auth import require_admin_auth
from app.db import get_session

router = APIRouter(prefix="/admin/champions", tags=["admin-champions"])


class NominateRequest(BaseModel):
    developer_id: UUID
    bio: str | None = None
    focus_areas: list[str] = []
    office_hours_text: str | None = None


@router.post("", status_code=201)
async def nominate(
    body: NominateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    auth: dict | None = Depends(require_admin_auth),
):
    await session.execute(
        text(
            """
            INSERT INTO champions (developer_id, bio, focus_areas, office_hours_text, active, nominated_by)
            VALUES (:dev, :bio, :focus, :hours, TRUE, :by)
            ON CONFLICT (developer_id) DO UPDATE
              SET bio = EXCLUDED.bio,
                  focus_areas = EXCLUDED.focus_areas,
                  office_hours_text = EXCLUDED.office_hours_text,
                  active = TRUE
            """
        ),
        {
            "dev": str(body.developer_id),
            "bio": body.bio,
            "focus": body.focus_areas,
            "hours": body.office_hours_text,
            "by": (auth or {}).get("user_id") if isinstance(auth, dict) else None,
        },
    )
    await session.commit()
    await audit.record(
        session, request, "nominate_champion", "champion", resource_id=str(body.developer_id)
    )
    return {"ok": True, "developer_id": str(body.developer_id)}


@router.delete("/{developer_id}", status_code=204)
async def retire(
    developer_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    auth: dict | None = Depends(require_admin_auth),
):
    result = await session.execute(
        text("UPDATE champions SET active = FALSE WHERE developer_id = :dev"),
        {"dev": str(developer_id)},
    )
    await session.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="champion not found")
    await audit.record(
        session, request, "retire_champion", "champion", resource_id=str(developer_id)
    )
    return Response(status_code=204)
