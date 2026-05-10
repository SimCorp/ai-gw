from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session
from app.models.policy import Policy

router = APIRouter(prefix="/teams/{team_id}/policy", tags=["policies"])
summary_router = APIRouter(prefix="/policies", tags=["policies"])


class PolicyUpdate(BaseModel):
    project_id: UUID | None = None
    cache_ttl_seconds: int = 3600
    cache_similarity_threshold: float = 0.95
    cache_opt_out: bool = False
    embedding_model: str = "text-embedding-3-small"
    rate_limit_rpm: int = 1000
    allowed_models: list[str] = []


@router.get("")
async def get_policy(team_id: UUID, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Policy).where(Policy.team_id == team_id, Policy.project_id.is_(None))
    )
    return result.scalars().first() or {}


@router.put("")
async def upsert_policy(team_id: UUID, body: PolicyUpdate, request: Request, session: AsyncSession = Depends(get_session)):
    stmt = (
        insert(Policy)
        .values(
            team_id=team_id,
            project_id=body.project_id,
            cache_ttl_seconds=body.cache_ttl_seconds,
            cache_similarity_threshold=body.cache_similarity_threshold,
            cache_opt_out=body.cache_opt_out,
            embedding_model=body.embedding_model,
            rate_limit_rpm=body.rate_limit_rpm,
            allowed_models=body.allowed_models,
        )
        .on_conflict_do_update(
            index_elements=["team_id"],
            index_where=Policy.project_id.is_(None),
            set_={
                "cache_ttl_seconds": body.cache_ttl_seconds,
                "cache_similarity_threshold": body.cache_similarity_threshold,
                "cache_opt_out": body.cache_opt_out,
                "embedding_model": body.embedding_model,
                "rate_limit_rpm": body.rate_limit_rpm,
                "allowed_models": body.allowed_models,
            },
        )
        .returning(Policy)
    )
    result = await session.execute(stmt)
    await audit.record(
        session, request, "upsert_policy", "policy",
        resource_id=str(team_id),
        details=body.model_dump(),
    )
    await session.commit()

    # Sync policy to Redis so cache + auth services pick up the new values immediately.
    redis = request.app.state.redis
    cache_key = f"policy:{team_id}"
    if body.project_id:
        cache_key = f"{cache_key}:{body.project_id}"
    import json as _json
    await redis.hset(cache_key, mapping={
        "ttl_seconds": body.cache_ttl_seconds,
        "similarity_threshold": body.cache_similarity_threshold,
        "opt_out": str(body.cache_opt_out).lower(),
        "embedding_model": body.embedding_model,
        "rate_limit_rpm": body.rate_limit_rpm,
        "allowed_models": _json.dumps(body.allowed_models or []),
    })

    return result.scalar_one()


@summary_router.get("")
async def list_all_policies(session: AsyncSession = Depends(get_session)):
    sql = text("""
        SELECT
            t.id          AS team_id,
            t.name        AS team_name,
            t.slug        AS team_slug,
            p.id          AS policy_id,
            p.cache_ttl_seconds,
            p.cache_similarity_threshold,
            p.cache_opt_out,
            p.embedding_model,
            p.rate_limit_rpm,
            p.allowed_models,
            p.updated_at
        FROM teams t
        LEFT JOIN policies p
            ON p.team_id = t.id
            AND p.project_id IS NULL
        ORDER BY t.name
    """)
    rows = (await session.execute(sql)).mappings().all()

    result = []
    for row in rows:
        policy = None
        if row["policy_id"] is not None:
            policy = {
                "id": str(row["policy_id"]),
                "cache_ttl_seconds": row["cache_ttl_seconds"],
                "cache_similarity_threshold": row["cache_similarity_threshold"],
                "cache_opt_out": row["cache_opt_out"],
                "embedding_model": row["embedding_model"],
                "rate_limit_rpm": row["rate_limit_rpm"],
                "allowed_models": row["allowed_models"] or [],
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            }
        result.append({
            "team_id": str(row["team_id"]),
            "team_name": row["team_name"],
            "team_slug": row["team_slug"],
            "policy": policy,
        })
    return result
