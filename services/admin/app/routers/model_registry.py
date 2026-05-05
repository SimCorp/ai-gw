
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session
from app.models.model_registry import ModelRegistry

router = APIRouter(prefix="/models", tags=["models"])


class ModelCreate(BaseModel):
    name: str
    model_id: str
    provider: str
    enabled: bool = True


class ModelUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None


@router.get("")
async def list_models(
    enabled_only: bool = False,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(ModelRegistry).order_by(ModelRegistry.provider, ModelRegistry.name)
    if enabled_only:
        stmt = stmt.where(ModelRegistry.enabled.is_(True))
    result = await session.execute(stmt)
    return result.scalars().all()


@router.post("", status_code=201)
async def create_model(
    body: ModelCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    model = ModelRegistry(
        name=body.name,
        model_id=body.model_id,
        provider=body.provider,
        enabled=body.enabled,
    )
    session.add(model)
    await audit.record(
        session, request, "create_model", "model_registry",
        details={"model_id": body.model_id, "provider": body.provider},
    )
    await session.commit()
    await session.refresh(model)
    return model


@router.patch("/{model_id}")
async def update_model(
    model_id: str,
    body: ModelUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(ModelRegistry).where(ModelRegistry.model_id == model_id)
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    if body.name is not None:
        model.name = body.name
    if body.enabled is not None:
        model.enabled = body.enabled
    await audit.record(
        session, request, "update_model", "model_registry",
        resource_id=model_id,
        details=body.model_dump(exclude_none=True),
    )
    await session.commit()
    await session.refresh(model)
    return model


@router.delete("/{model_id}", status_code=204)
async def delete_model(
    model_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(ModelRegistry).where(ModelRegistry.model_id == model_id)
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    await audit.record(
        session, request, "delete_model", "model_registry", resource_id=model_id
    )
    await session.delete(model)
    await session.commit()
