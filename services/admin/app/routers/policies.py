from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.policy import Policy

router = APIRouter(prefix="/teams/{team_id}/policy", tags=["policies"])


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
    return result.scalar_one_or_none() or {}


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
            index_elements=["team_id", "project_id"],
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
    await session.commit()

    # Invalidate Redis policy cache so cache service picks up the new values.
    redis = request.app.state.redis
    cache_key = f"policy:{team_id}"
    if body.project_id:
        cache_key = f"{cache_key}:{body.project_id}"
    await redis.delete(cache_key)

    return result.scalar_one()
