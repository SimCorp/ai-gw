"""Internal points grant API.

Used by other in-cluster services (e.g. admin) to award points to engineers
for activities tracked outside the league service itself — currently AI
Champions content contributions. Auth is via the shared `X-Admin-Token`
header, not user sessions.
"""

import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session

router = APIRouter(prefix="/league/internal", tags=["league-internal"])

# Only allow service-to-service grants for reasons we recognise. Currently
# anything beginning with `champion_` (e.g. `champion_content`). Keeping this
# allowlist on the receiver side prevents a compromised caller from minting
# arbitrary point histories.
_ALLOWED_REASON_PREFIXES = ("champion_",)


class GrantRequest(BaseModel):
    engineer_id: UUID
    delta: int = Field(..., description="Points to add (positive) or remove (negative)")
    reason: str = Field(..., min_length=1)
    ref_id: UUID | None = None


async def _require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    expected = settings.admin_token
    if not expected or not x_admin_token or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="Missing or invalid X-Admin-Token")


@router.post("/points/grant", status_code=201, dependencies=[Depends(_require_admin_token)])
async def grant_points(
    body: GrantRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not any(body.reason.startswith(p) for p in _ALLOWED_REASON_PREFIXES):
        raise HTTPException(
            status_code=400,
            detail=f"Reason must start with one of {_ALLOWED_REASON_PREFIXES}",
        )

    await session.execute(
        text(
            """
            INSERT INTO league_points_ledger (engineer_id, delta, reason, ref_id)
            VALUES (:engineer_id, :delta, :reason, :ref_id)
            """
        ),
        {
            "engineer_id": str(body.engineer_id),
            "delta": body.delta,
            "reason": body.reason,
            "ref_id": str(body.ref_id) if body.ref_id else None,
        },
    )
    await session.commit()
    return {"ok": True, "delta": body.delta, "reason": body.reason}
