# services/league/app/routers/seasons.py
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_auth
from app.db import get_session
from app.scoring import DEFAULT_WEIGHTS

router = APIRouter(prefix="/seasons", tags=["seasons"])

_WEIGHT_KEYS = set(DEFAULT_WEIGHTS.keys())


class SeasonCreate(BaseModel):
    name: str
    starts_at: datetime
    ends_at: datetime
    scoring_weights: dict[str, float] = dict(DEFAULT_WEIGHTS)
    season_multiplier: float = 1.0

    @model_validator(mode="after")
    def check_weights(self):
        if abs(sum(self.scoring_weights.values()) - 1.0) > 0.01:
            raise ValueError("scoring_weights must sum to 1.0")
        if set(self.scoring_weights.keys()) != _WEIGHT_KEYS:
            raise ValueError(f"scoring_weights must contain exactly: {_WEIGHT_KEYS}")
        return self


class WeightsUpdate(BaseModel):
    quality: float = DEFAULT_WEIGHTS["quality"]
    robustness: float = DEFAULT_WEIGHTS["robustness"]
    token_efficiency: float = DEFAULT_WEIGHTS["token_efficiency"]
    speed: float = DEFAULT_WEIGHTS["speed"]
    cost_efficiency: float = DEFAULT_WEIGHTS["cost_efficiency"]
    improvement_rate: float = DEFAULT_WEIGHTS["improvement_rate"]
    creativity: float = DEFAULT_WEIGHTS["creativity"]

    @model_validator(mode="after")
    def check_sum(self):
        total = (self.quality + self.robustness + self.token_efficiency +
                 self.speed + self.cost_efficiency + self.improvement_rate + self.creativity)
        if abs(total - 1.0) > 0.01:
            raise ValueError("weights must sum to 1.0")
        return self


def _season_to_dict(row: Any) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "status": row["status"],
        "starts_at": row["starts_at"].isoformat() if hasattr(row["starts_at"], "isoformat") else row["starts_at"],
        "ends_at": row["ends_at"].isoformat() if hasattr(row["ends_at"], "isoformat") else row["ends_at"],
        "scoring_weights": row["scoring_weights"],
        "season_multiplier": float(row["season_multiplier"]),
        "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else row["created_at"],
    }


@router.get("")
async def list_seasons(session: AsyncSession = Depends(get_session)):
    result = await session.execute(text(
        "SELECT * FROM league_seasons ORDER BY starts_at DESC"
    ))
    return [_season_to_dict(row) for row in result.mappings().all()]


@router.post("", status_code=201)
async def create_season(
    body: SeasonCreate,
    session: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin_auth),
):
    result = await session.execute(text("""
        INSERT INTO league_seasons (name, status, starts_at, ends_at, scoring_weights, season_multiplier)
        VALUES (:name, 'upcoming', :starts_at, :ends_at, CAST(:weights AS jsonb), :multiplier)
        RETURNING *
    """), {
        "name": body.name,
        "starts_at": body.starts_at,
        "ends_at": body.ends_at,
        "weights": json.dumps(body.scoring_weights),
        "multiplier": body.season_multiplier,
    })
    await session.commit()
    return _season_to_dict(result.mappings().one())


@router.patch("/{season_id}/weights")
async def update_weights(
    season_id: UUID,
    body: WeightsUpdate,
    session: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin_auth),
):
    row = (await session.execute(
        text("SELECT * FROM league_seasons WHERE id = :id"),
        {"id": str(season_id)},
    )).mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Season not found")
    if row["status"] != "upcoming":
        raise HTTPException(status_code=409, detail="Cannot change weights once season is active or closed")
    weights = {
        "quality": body.quality, "robustness": body.robustness,
        "token_efficiency": body.token_efficiency, "speed": body.speed,
        "cost_efficiency": body.cost_efficiency, "improvement_rate": body.improvement_rate,
        "creativity": body.creativity,
    }
    await session.execute(text("""
        UPDATE league_seasons SET scoring_weights = CAST(:w AS jsonb) WHERE id = :id
    """), {"w": json.dumps(weights), "id": str(season_id)})
    await session.commit()
    return {"id": str(season_id), "scoring_weights": weights}


@router.patch("/{season_id}/status")
async def update_status(
    season_id: UUID,
    body: dict,
    session: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin_auth),
):
    new_status = body.get("status")
    if new_status not in ("upcoming", "active", "closed"):
        raise HTTPException(status_code=422, detail="status must be upcoming, active, or closed")
    await session.execute(text(
        "UPDATE league_seasons SET status = :s WHERE id = :id"
    ), {"s": new_status, "id": str(season_id)})
    await session.commit()
    return {"id": str(season_id), "status": new_status}
