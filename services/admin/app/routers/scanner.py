import json
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_session

router = APIRouter(prefix="/scanner", tags=["scanner"])


class TargetCreate(BaseModel):
    url: str
    label: str
    openapi_spec_url: str | None = None
    requested_scan_types: list[str] = ["ai", "api", "network"]
    team_id: str
    created_by: str


class TargetApprove(BaseModel):
    allowed_scan_types: list[str]
    notes: str | None = None
    approved_by: str | None = None


class QuotaUpdate(BaseModel):
    daily_limit: int | None = None
    allow_external_targets: bool | None = None
    max_tier: str | None = None


class RevokeBody(BaseModel):
    notes: str | None = None


_INTERNAL_IP_PREFIXES = ("10.", "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.", "172.26.",
    "172.27.", "172.28.", "172.29.", "172.30.", "172.31.", "192.168.", "127.")


def _is_external(url: str) -> bool:
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    if host.endswith(".simcorp.internal"):
        return False
    return not any(host.startswith(pfx) for pfx in _INTERNAL_IP_PREFIXES)


@router.get("/targets")
async def list_targets(
    team_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    where_clauses, params = [], {}
    if team_id:
        where_clauses.append("team_id = CAST(:team_id AS uuid)")
        params["team_id"] = team_id
    if status:
        where_clauses.append("status = :status")
        params["status"] = status
    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    rows = (await session.execute(
        text(f"SELECT * FROM scan_targets {where} ORDER BY created_at DESC"),
        params,
    )).mappings().all()
    return [dict(r) for r in rows]


@router.post("/targets", status_code=201)
async def register_target(body: TargetCreate, session: AsyncSession = Depends(get_session)):
    if _is_external(body.url):
        quota_row = (await session.execute(
            text("SELECT scanner_quota FROM teams WHERE id = CAST(:tid AS uuid)"),
            {"tid": body.team_id},
        )).mappings().first()
        quota = quota_row["scanner_quota"] if quota_row else {}
        if not quota.get("allow_external_targets", False):
            raise HTTPException(status_code=403, detail="Team is not permitted to register external targets")
    result = await session.execute(
        text("""
            INSERT INTO scan_targets (team_id, url, label, openapi_spec_url, allowed_scan_types, created_by)
            VALUES (CAST(:team_id AS uuid), :url, :label, :openapi_spec_url,
                    CAST(:scan_types AS text[]), CAST(:created_by AS uuid))
            RETURNING *
        """),
        {
            "team_id": body.team_id,
            "url": body.url,
            "label": body.label,
            "openapi_spec_url": body.openapi_spec_url,
            "scan_types": "{" + ",".join(body.requested_scan_types) + "}",
            "created_by": body.created_by,
        },
    )
    await session.commit()
    return dict(result.mappings().first())


@router.post("/targets/{target_id}/approve")
async def approve_target(
    target_id: str, body: TargetApprove, session: AsyncSession = Depends(get_session)
):
    row = (await session.execute(
        text("SELECT id FROM scan_targets WHERE id = CAST(:id AS uuid)"),
        {"id": target_id},
    )).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Target not found")
    await session.execute(
        text("""
            UPDATE scan_targets
            SET status = 'approved',
                allowed_scan_types = CAST(:types AS text[]),
                approved_by = CAST(:approved_by AS uuid),
                approved_at = NOW(),
                notes = :notes
            WHERE id = CAST(:id AS uuid)
        """),
        {
            "id": target_id,
            "types": "{" + ",".join(body.allowed_scan_types) + "}",
            "approved_by": body.approved_by,
            "notes": body.notes,
        },
    )
    await session.commit()
    return {"status": "approved"}


@router.post("/targets/{target_id}/revoke")
async def revoke_target(
    target_id: str,
    body: RevokeBody = RevokeBody(),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        text("""
            UPDATE scan_targets SET status = 'revoked', notes = :notes
            WHERE id = CAST(:id AS uuid) RETURNING id
        """),
        {"id": target_id, "notes": body.notes},
    )
    if not result.mappings().first():
        raise HTTPException(status_code=404, detail="Target not found")
    await session.commit()
    return {"status": "revoked"}


@router.get("/quotas")
async def list_quotas(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        text("SELECT id, name, scanner_quota FROM teams ORDER BY name")
    )).mappings().all()
    return [dict(r) for r in rows]


@router.patch("/quotas/{team_id}")
async def update_quota(
    team_id: str, body: QuotaUpdate, session: AsyncSession = Depends(get_session)
):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    # Explicit whitelist mapping prevents dynamic key injection into SQL.
    _QUOTA_SQL_KEYS: dict[str, str] = {
        "daily_limit": "daily_limit",
        "allow_external_targets": "allow_external_targets",
        "max_tier": "max_tier",
    }
    set_parts = []
    params: dict[str, Any] = {"team_id": team_id}
    for k, v in updates.items():
        sql_key = _QUOTA_SQL_KEYS[k]  # KeyError is impossible — keys come from QuotaUpdate.model_dump()
        param_name = f"quota_{sql_key}"
        set_parts.append(
            f"scanner_quota = scanner_quota || jsonb_build_object('{sql_key}', CAST(:{param_name} AS jsonb))"
        )
        params[param_name] = json.dumps(v)
    result = await session.execute(
        text(f"UPDATE teams SET {', '.join(set_parts)} WHERE id = CAST(:team_id AS uuid) RETURNING scanner_quota"),
        params,
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Team not found")
    await session.commit()
    return {"scanner_quota": row["scanner_quota"]}


@router.post("/kill-switch")
async def set_kill_switch(request: Request, enabled: bool = True):
    redis = request.app.state.redis
    if enabled:
        await redis.set("scanner:disabled", "1")
    else:
        await redis.delete("scanner:disabled")
    return {"scanner_disabled": enabled}
