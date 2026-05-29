import hashlib
import json
import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session
from app.models.api_key import APIKey
from app.scopes import DEFAULT_KEY_SCOPES

router = APIRouter(prefix="/teams/{team_id}/keys", tags=["api-keys"])

# Portal-facing router — authenticated via developer session token (Bearer header)
# Enforces that the developer is a member of the requested team.
portal_keys_router = APIRouter(prefix="/portal/teams/{team_id}/keys", tags=["portal-api-keys"])


async def _require_team_member(
    team_id: UUID,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict:
    """Validate the developer session token and assert team membership."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.removeprefix("Bearer ").strip()
    raw = await request.app.state.redis.get(f"dev_session:{token}")
    if not raw:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    session_data: dict = json.loads(raw)
    developer_id = session_data.get("developer_id")
    if not developer_id:
        raise HTTPException(status_code=401, detail="Invalid session")
    return session_data


@portal_keys_router.get("")
async def portal_list_keys(
    team_id: UUID,
    request: Request,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    session_data = await _require_team_member(team_id, request, authorization)
    developer_id = session_data["developer_id"]
    # Verify the developer is a member of the requested team
    membership = (await session.execute(
        text("""
            SELECT 1 FROM team_members
            WHERE team_id = CAST(:team_id AS uuid)
              AND developer_id = CAST(:developer_id AS uuid)
        """),
        {"team_id": str(team_id), "developer_id": developer_id},
    )).first()
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this team")
    result = await session.execute(
        select(APIKey).where(APIKey.team_id == team_id, APIKey.revoked_at.is_(None))
    )
    return result.scalars().all()


@portal_keys_router.post("", status_code=201)
async def portal_create_key(
    team_id: UUID,
    body: "KeyCreate",
    request: Request,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    session_data = await _require_team_member(team_id, request, authorization)
    developer_id = session_data["developer_id"]
    membership = (await session.execute(
        text("""
            SELECT 1 FROM team_members
            WHERE team_id = CAST(:team_id AS uuid)
              AND developer_id = CAST(:developer_id AS uuid)
        """),
        {"team_id": str(team_id), "developer_id": developer_id},
    )).first()
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this team")
    scopes = body.scopes if body.scopes else DEFAULT_KEY_SCOPES
    raw_key = "sk-" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = APIKey(
        team_id=team_id,
        project_id=body.project_id,
        name=body.name,
        key_hash=key_hash,
        scopes=scopes,
    )
    session.add(api_key)
    await session.flush()
    await audit.record(
        session, request, "create_api_key", "api_key", resource_id=api_key.id,
        details={"name": body.name, "team_id": str(team_id), "developer_id": developer_id, "scopes": scopes},
    )
    await session.commit()
    await session.refresh(api_key)
    return {
        "id": str(api_key.id),
        "name": api_key.name,
        "key": raw_key,
        "scopes": api_key.scopes,
        "created_at": api_key.created_at,
    }


@portal_keys_router.delete("/{key_id}", status_code=204)
async def portal_revoke_key(
    team_id: UUID,
    key_id: UUID,
    request: Request,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    session_data = await _require_team_member(team_id, request, authorization)
    developer_id = session_data["developer_id"]
    membership = (await session.execute(
        text("""
            SELECT 1 FROM team_members
            WHERE team_id = CAST(:team_id AS uuid)
              AND developer_id = CAST(:developer_id AS uuid)
        """),
        {"team_id": str(team_id), "developer_id": developer_id},
    )).first()
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this team")
    key = await session.get(APIKey, key_id)
    if not key or key.team_id != team_id:
        raise HTTPException(status_code=404, detail="Key not found")
    key.revoked_at = datetime.now(timezone.utc)
    await audit.record(
        session, request, "revoke_api_key", "api_key", resource_id=key_id,
        details={"name": key.name, "team_id": str(team_id), "developer_id": developer_id},
    )
    await session.commit()


class KeyCreate(BaseModel):
    name: str
    project_id: UUID | None = None
    scopes: list[str] = ["ai-gw:inference:*"]
    expires_at: str | None = None


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
    scopes = body.scopes if body.scopes else DEFAULT_KEY_SCOPES

    raw_key = "sk-" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    expires_at = None
    if body.expires_at:
        from datetime import datetime as _dt
        expires_at = _dt.fromisoformat(body.expires_at.replace("Z", "+00:00"))

    api_key = APIKey(
        team_id=team_id,
        project_id=body.project_id,
        name=body.name,
        key_hash=key_hash,
        scopes=scopes,
        expires_at=expires_at,
    )
    session.add(api_key)
    await session.flush()
    await audit.record(
        session, request, "create_api_key", "api_key", resource_id=api_key.id,
        details={"name": body.name, "team_id": str(team_id), "scopes": scopes},
    )
    await session.commit()
    await session.refresh(api_key)

    return {
        "id": str(api_key.id),
        "name": api_key.name,
        "key": raw_key,  # returned once only; not stored
        "scopes": api_key.scopes,
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
