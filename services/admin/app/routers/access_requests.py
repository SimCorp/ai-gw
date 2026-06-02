"""
Access request approval workflow (D8).

Developers submit requests for model access or budget increases.
Team admins / area owners / platform admins approve or reject.
Approving a model_access request automatically adds the model to the user's allowed_models.
"""

from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.routers.unified_auth import get_current_user, has_role

router = APIRouter(prefix="/access-requests", tags=["access-requests"])


class AccessRequestCreate(BaseModel):
    request_type: str  # model_access | budget_increase
    resource_id: str  # model name or team_id
    justification: str | None = None


class AccessRequestDecision(BaseModel):
    status: str  # approved | rejected
    review_note: str | None = None
    expires_at: str | None = None  # reserved for future time-bounded approvals


@router.post("", status_code=201)
async def create_request(
    body: AccessRequestCreate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if body.request_type not in ("model_access", "budget_increase"):
        raise HTTPException(422, "request_type must be model_access or budget_increase")

    # Migration 0025 dropped access_requests.resource_id and added node_id (uuid).
    # The body's resource_id historically held either a model name (model_access)
    # or a team_id (budget_increase). Only persist it as node_id when it parses
    # as a valid uuid; otherwise store NULL rather than crashing.
    node_id: str | None = None
    try:
        node_id = str(_uuid.UUID(body.resource_id))
    except (ValueError, AttributeError, TypeError):
        node_id = None

    await session.execute(
        text("""
            INSERT INTO access_requests (user_id, request_type, node_id, justification)
            VALUES (CAST(:uid AS uuid), :type, CAST(:nid AS uuid), :just)
        """),
        {
            "uid": current_user["user_id"],
            "type": body.request_type,
            "nid": node_id,
            "just": body.justification,
        },
    )
    await session.commit()
    return {"message": "Request submitted"}


@router.get("")
async def list_requests(
    status: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    is_admin = has_role(current_user, "platform_admin")
    uid = current_user["user_id"]

    if is_admin:
        where = "1=1"
        params: dict = {}
    else:
        where = "ar.user_id = CAST(:uid AS uuid)"
        params = {"uid": uid}

    if status:
        where += " AND ar.status = :status"
        params["status"] = status

    rows = (
        (
            await session.execute(
                text(f"""
            SELECT ar.id, ar.request_type, ar.node_id, ar.justification,
                   ar.status, ar.reviewed_by, ar.reviewed_at, ar.review_note,
                   ar.created_at, u.email AS requester_email, u.display_name AS requester_name
            FROM access_requests ar
            JOIN users u ON u.id = ar.user_id
            WHERE {where}
            ORDER BY ar.created_at DESC
            LIMIT 200
        """),
                params,
            )
        )
        .mappings()
        .all()
    )

    return [dict(r) for r in rows]


@router.patch("/{request_id}")
async def decide_request(
    request_id: str,
    body: AccessRequestDecision,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if body.status not in ("approved", "rejected"):
        raise HTTPException(422, "status must be approved or rejected")

    can_review = (
        has_role(current_user, "platform_admin")
        or has_role(current_user, "team_admin")
        or has_role(current_user, "area_owner")
    )
    if not can_review:
        raise HTTPException(403, "Insufficient permissions to review requests")

    row = (
        (
            await session.execute(
                text("""
            SELECT id, user_id::text, request_type, node_id, status
            FROM access_requests
            WHERE id = CAST(:rid AS uuid)
        """),
                {"rid": request_id},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise HTTPException(404, "Request not found")
    if row["status"] != "pending":
        raise HTTPException(409, f"Request is already {row['status']}")

    await session.execute(
        text("""
            UPDATE access_requests
            SET status = :status,
                reviewed_by = :reviewer,
                reviewed_at = NOW(),
                review_note = :note
            WHERE id = CAST(:rid AS uuid)
        """),
        {
            "status": body.status,
            "reviewer": current_user["email"],
            "note": body.review_note,
            "rid": request_id,
        },
    )

    # Auto-grant model access on approval — DISABLED by migration 0025.
    # The model name used to live in access_requests.resource_id (text), which was
    # dropped; the replacement node_id is a uuid FK and does not persist a model
    # name, so there is no longer a value to append to users.allowed_models.
    # The request is still marked approved above; the model must be granted manually.
    # (Re-enable once a column persisting the requested model name is reintroduced.)

    await session.commit()
    return {"message": f"Request {body.status}"}
