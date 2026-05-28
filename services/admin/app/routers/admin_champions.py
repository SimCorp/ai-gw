"""Admin-only endpoints to nominate and retire AI Champions."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.auth import require_admin_auth
from app.db import get_session

router = APIRouter(prefix="/admin/champions", tags=["admin-champions"])


class FlagResolveBody(BaseModel):
    action: Literal["dismiss", "remove"]


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


# ---------- flag moderation ----------

@router.get("/flags")
async def list_flags(
    session: AsyncSession = Depends(get_session),
    _auth: dict | None = Depends(require_admin_auth),
):
    """List open flags joined with contribution metadata for moderation review."""
    result = await session.execute(text("""
        SELECT f.id, f.contribution_id, f.flagged_by, f.reason, f.created_at,
               COALESCE(c.auto_metadata->>'title', '') AS contribution_title
        FROM champion_flags f
        LEFT JOIN champion_contributions c ON c.id = f.contribution_id
        WHERE f.status = 'open'
        ORDER BY f.created_at DESC
        LIMIT 200
    """))
    return [
        {
            "id": str(r["id"]),
            "contribution_id": str(r["contribution_id"]),
            "contribution_title": r["contribution_title"],
            "flagged_by": str(r["flagged_by"]),
            "reason": r["reason"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in result.mappings().all()
    ]


@router.post("/flags/{flag_id}/resolve")
async def resolve_flag(
    flag_id: UUID,
    body: FlagResolveBody,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _auth: dict | None = Depends(require_admin_auth),
):
    """Moderate a flag.

    - dismiss: mark the flag itself as 'dismissed'.
    - remove: soft-delete the underlying contribution by setting its flag_count to 999,
      which the public feed query filters out (WHERE flag_count < 999). This is a
      deliberate hack to avoid a schema migration; the marker doubles as a tombstone.
    """
    row = (await session.execute(
        text("SELECT contribution_id FROM champion_flags WHERE id = :id"),
        {"id": str(flag_id)},
    )).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="flag not found")

    if body.action == "dismiss":
        await session.execute(
            text("UPDATE champion_flags SET status = 'dismissed' WHERE id = :id"),
            {"id": str(flag_id)},
        )
    else:  # remove
        # Hack: flag_count = 999 acts as a tombstone so the feed filter hides it
        # without adding a `hidden` / `deleted_at` column.
        await session.execute(
            text("""
                UPDATE champion_contributions
                SET flag_count = 999
                WHERE id = :cid
            """),
            {"cid": str(row["contribution_id"])},
        )
        await session.execute(
            text("""
                UPDATE champion_flags
                SET status = 'removed'
                WHERE contribution_id = :cid
            """),
            {"cid": str(row["contribution_id"])},
        )
    await session.commit()
    await audit.record(
        session, request, f"flag_{body.action}", "champion_flag", resource_id=str(flag_id)
    )
    return {"ok": True, "id": str(flag_id), "action": body.action}
