import hashlib
import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session
from app.models.api_key import APIKey

router = APIRouter(prefix="/teams/{team_id}/keys", tags=["api-keys"])


class KeyCreate(BaseModel):
    name: str
    project_id: UUID | None = None


@router.get("")
async def list_keys(team_id: UUID, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(APIKey).where(APIKey.team_id == team_id, APIKey.revoked_at.is_(None))
    )
    return result.scalars().all()


@router.post("", status_code=201)
async def create_key(
    team_id: UUID,
    body: KeyCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    raw_key = "sk-" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    api_key = APIKey(
        team_id=team_id,
        project_id=body.project_id,
        name=body.name,
        key_hash=key_hash,
    )
    session.add(api_key)
    await session.flush()
    await audit.record(
        session, request, "create_api_key", "api_key", resource_id=api_key.id,
        details={"name": body.name, "team_id": str(team_id)},
    )
    await session.commit()
    await session.refresh(api_key)

    return {
        "id": str(api_key.id),
        "name": api_key.name,
        "key": raw_key,  # returned once only; not stored
        "created_at": api_key.created_at,
    }


@router.delete("/{key_id}", status_code=204)
async def revoke_key(
    team_id: UUID,
    key_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    key = await session.get(APIKey, key_id)
    if not key or key.team_id != team_id:
        raise HTTPException(status_code=404, detail="Key not found")
    key.revoked_at = datetime.now(timezone.utc)
    await audit.record(
        session, request, "revoke_api_key", "api_key", resource_id=key_id,
        details={"name": key.name, "team_id": str(team_id)},
    )
    await session.commit()
