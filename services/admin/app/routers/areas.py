from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session
from app.models.area_policy import AreaPolicy
from app.routers.unified_auth import get_current_user, _can_manage_area

router = APIRouter(prefix="/areas", tags=["areas"])


class AreaCreate(BaseModel):
    name: str
    slug: str
    description: str | None = None
    color: str | None = None


class AreaUpdate(BaseModel):
    name: str
    slug: str
    description: str | None = None
    color: str | None = None


class AreaPolicyUpdate(BaseModel):
    cache_ttl_seconds: int = 3600
    cache_similarity_threshold: float = 0.95
    cache_opt_out: bool = False
    embedding_model: str = "text-embedding-3-small"
    rate_limit_rpm: int = 1000
    allowed_models: list[str] = []


def _row_to_area_dict(row) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "slug": row.slug,
        "description": row.description,
        "color": row.color,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("")
async def list_areas(session: AsyncSession = Depends(get_session)):
    result = await session.execute(text("""
        SELECT a.id, a.name, a.slug, a.description, a.color, a.created_at,
               COUNT(t.id) AS team_count,
               CASE WHEN ap.area_id IS NOT NULL THEN TRUE ELSE FALSE END AS has_policy
        FROM areas a
        LEFT JOIN teams t ON t.area_id = a.id
        LEFT JOIN area_policies ap ON ap.area_id = a.id
        GROUP BY a.id, ap.area_id
        ORDER BY a.name
    """))
    rows = result.mappings().all()
    return [
        {
            "id": str(row["id"]),
            "name": row["name"],
            "slug": row["slug"],
            "description": row["description"],
            "color": row["color"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "team_count": row["team_count"],
            "has_policy": row["has_policy"],
        }
        for row in rows
    ]


@router.post("", status_code=201)
async def create_area(
    body: AreaCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    if not await _can_manage_area(user, ""):  # only platform_admin can create areas
        raise HTTPException(status_code=403, detail="Platform admin required to create areas")
    result = await session.execute(
        text("""
            INSERT INTO areas (name, slug, description, color)
            VALUES (:name, :slug, :description, :color)
            RETURNING id, name, slug, description, color, created_at
        """),
        {"name": body.name, "slug": body.slug, "description": body.description, "color": body.color},
    )
    row = result.mappings().one()
    area_id = row["id"]
    await audit.record(session, request, "create_area", "area", resource_id=area_id)
    await session.commit()
    return {
        "id": str(area_id),
        "name": row["name"],
        "slug": row["slug"],
        "description": row["description"],
        "color": row["color"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


@router.get("/{area_id}")
async def get_area(area_id: UUID, session: AsyncSession = Depends(get_session)):
    area_result = await session.execute(
        text("SELECT id, name, slug, description, color, created_at FROM areas WHERE id = :id"),
        {"id": area_id},
    )
    area_row = area_result.mappings().one_or_none()
    if not area_row:
        raise HTTPException(status_code=404, detail="Area not found")

    teams_result = await session.execute(
        text("""
            SELECT id, name, slug, created_at, monthly_budget_usd, budget_alert_pct, budget_action
            FROM teams WHERE area_id = :area_id ORDER BY name
        """),
        {"area_id": area_id},
    )
    teams = [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "slug": r["slug"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "monthly_budget_usd": float(r["monthly_budget_usd"]) if r["monthly_budget_usd"] is not None else None,
            "budget_alert_pct": r["budget_alert_pct"],
            "budget_action": r["budget_action"],
        }
        for r in teams_result.mappings().all()
    ]

    policy_result = await session.execute(
        text("""
            SELECT id, cache_ttl_seconds, cache_similarity_threshold, cache_opt_out,
                   embedding_model, rate_limit_rpm, allowed_models, updated_at
            FROM area_policies WHERE area_id = :area_id
        """),
        {"area_id": area_id},
    )
    policy_row = policy_result.mappings().one_or_none()
    policy = None
    if policy_row:
        policy = {
            "id": str(policy_row["id"]),
            "cache_ttl_seconds": policy_row["cache_ttl_seconds"],
            "cache_similarity_threshold": policy_row["cache_similarity_threshold"],
            "cache_opt_out": policy_row["cache_opt_out"],
            "embedding_model": policy_row["embedding_model"],
            "rate_limit_rpm": policy_row["rate_limit_rpm"],
            "allowed_models": policy_row["allowed_models"] or [],
            "updated_at": policy_row["updated_at"].isoformat() if policy_row["updated_at"] else None,
        }

    return {
        "area": {
            "id": str(area_row["id"]),
            "name": area_row["name"],
            "slug": area_row["slug"],
            "description": area_row["description"],
            "color": area_row["color"],
            "created_at": area_row["created_at"].isoformat() if area_row["created_at"] else None,
        },
        "teams": teams,
        "policy": policy,
    }


@router.put("/{area_id}")
async def update_area(
    area_id: UUID,
    body: AreaUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    if not await _can_manage_area(user, str(area_id)):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    result = await session.execute(
        text("""
            UPDATE areas SET name = :name, slug = :slug, description = :description, color = :color
            WHERE id = :id
            RETURNING id, name, slug, description, color, created_at
        """),
        {"id": area_id, "name": body.name, "slug": body.slug, "description": body.description, "color": body.color},
    )
    row = result.mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Area not found")
    await audit.record(
        session, request, "update_area", "area", resource_id=area_id,
        details={"name": body.name, "slug": body.slug},
    )
    await session.commit()
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "slug": row["slug"],
        "description": row["description"],
        "color": row["color"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


@router.delete("/{area_id}", status_code=204)
async def delete_area(
    area_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    if not await _can_manage_area(user, str(area_id)):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    result = await session.execute(
        text("DELETE FROM areas WHERE id = :id RETURNING id"),
        {"id": area_id},
    )
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Area not found")
    await audit.record(session, request, "delete_area", "area", resource_id=area_id)
    await session.commit()


@router.get("/{area_id}/policy")
async def get_area_policy(area_id: UUID, session: AsyncSession = Depends(get_session)):
    # Verify area exists
    area_exists = (await session.execute(
        text("SELECT id FROM areas WHERE id = :id"), {"id": area_id}
    )).one_or_none()
    if not area_exists:
        raise HTTPException(status_code=404, detail="Area not found")

    row = (await session.execute(
        text("""
            SELECT id, area_id, cache_ttl_seconds, cache_similarity_threshold, cache_opt_out,
                   embedding_model, rate_limit_rpm, allowed_models, updated_at
            FROM area_policies WHERE area_id = :area_id
        """),
        {"area_id": area_id},
    )).mappings().one_or_none()

    if not row:
        return {}

    return {
        "id": str(row["id"]),
        "area_id": str(row["area_id"]),
        "cache_ttl_seconds": row["cache_ttl_seconds"],
        "cache_similarity_threshold": row["cache_similarity_threshold"],
        "cache_opt_out": row["cache_opt_out"],
        "embedding_model": row["embedding_model"],
        "rate_limit_rpm": row["rate_limit_rpm"],
        "allowed_models": row["allowed_models"] or [],
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


@router.put("/{area_id}/policy")
async def upsert_area_policy(
    area_id: UUID,
    body: AreaPolicyUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    if not await _can_manage_area(user, str(area_id)):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    # Verify area exists
    area_exists = (await session.execute(
        text("SELECT id FROM areas WHERE id = :id"), {"id": area_id}
    )).one_or_none()
    if not area_exists:
        raise HTTPException(status_code=404, detail="Area not found")

    stmt = (
        insert(AreaPolicy)
        .values(
            area_id=area_id,
            cache_ttl_seconds=body.cache_ttl_seconds,
            cache_similarity_threshold=body.cache_similarity_threshold,
            cache_opt_out=body.cache_opt_out,
            embedding_model=body.embedding_model,
            rate_limit_rpm=body.rate_limit_rpm,
            allowed_models=body.allowed_models,
        )
        .on_conflict_do_update(
            index_elements=["area_id"],
            set_={
                "cache_ttl_seconds": body.cache_ttl_seconds,
                "cache_similarity_threshold": body.cache_similarity_threshold,
                "cache_opt_out": body.cache_opt_out,
                "embedding_model": body.embedding_model,
                "rate_limit_rpm": body.rate_limit_rpm,
                "allowed_models": body.allowed_models,
                "updated_at": text("NOW()"),
            },
        )
        .returning(
            AreaPolicy.id,
            AreaPolicy.area_id,
            AreaPolicy.cache_ttl_seconds,
            AreaPolicy.cache_similarity_threshold,
            AreaPolicy.cache_opt_out,
            AreaPolicy.embedding_model,
            AreaPolicy.rate_limit_rpm,
            AreaPolicy.allowed_models,
            AreaPolicy.updated_at,
        )
    )
    result = await session.execute(stmt)
    row = result.mappings().one()

    await audit.record(
        session, request, "upsert_area_policy", "area_policy",
        resource_id=str(area_id),
        details=body.model_dump(),
    )
    await session.commit()

    # Sync to Redis
    redis = request.app.state.redis
    await redis.hset(f"policy:area:{area_id}", mapping={
        "ttl_seconds": body.cache_ttl_seconds,
        "similarity_threshold": body.cache_similarity_threshold,
        "opt_out": str(body.cache_opt_out).lower(),
        "embedding_model": body.embedding_model,
        "rate_limit_rpm": body.rate_limit_rpm,
    })

    return {
        "id": str(row["id"]),
        "area_id": str(row["area_id"]),
        "cache_ttl_seconds": row["cache_ttl_seconds"],
        "cache_similarity_threshold": row["cache_similarity_threshold"],
        "cache_opt_out": row["cache_opt_out"],
        "embedding_model": row["embedding_model"],
        "rate_limit_rpm": row["rate_limit_rpm"],
        "allowed_models": row["allowed_models"] or [],
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }
