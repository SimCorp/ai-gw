from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.pricing import ModelPricing

router = APIRouter(prefix="/pricing", tags=["pricing"])


class PricingUpsert(BaseModel):
    model_prefix: str
    price_input_per_1k: float
    price_output_per_1k: float


@router.get("")
async def list_pricing(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(ModelPricing).order_by(ModelPricing.model_prefix))
    return result.scalars().all()


@router.put("", status_code=200)
async def upsert_pricing(body: PricingUpsert, session: AsyncSession = Depends(get_session)):
    stmt = (
        insert(ModelPricing)
        .values(
            model_prefix=body.model_prefix,
            price_input_per_1k=body.price_input_per_1k,
            price_output_per_1k=body.price_output_per_1k,
        )
        .on_conflict_do_update(
            index_elements=["model_prefix"],
            set_={
                "price_input_per_1k": body.price_input_per_1k,
                "price_output_per_1k": body.price_output_per_1k,
                "updated_at": text("NOW()"),
            },
        )
        .returning(ModelPricing)
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.scalar_one()


@router.delete("/{model_prefix}", status_code=204)
async def delete_pricing(model_prefix: str, session: AsyncSession = Depends(get_session)):
    row = await session.get(ModelPricing, model_prefix)
    if row:
        await session.delete(row)
        await session.commit()
