# services/league/app/routers/store.py
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_auth, require_dev_auth
from app.db import get_session

router = APIRouter(prefix="/store", tags=["store"])


@router.get("/balance")
async def get_balance(
    session: AsyncSession = Depends(get_session),
    user=Depends(require_dev_auth),
):
    balance = (await session.execute(text(
        "SELECT COALESCE(SUM(delta), 0) FROM league_points_ledger WHERE engineer_id = :uid"
    ), {"uid": user["user_id"]})).scalar()
    return {"balance": int(balance)}


@router.get("/items")
async def list_items(session: AsyncSession = Depends(get_session), _user=Depends(require_dev_auth)):
    result = await session.execute(text(
        "SELECT id, name, type, point_cost, asset_url, exclusive_season_id, exclusive_top_n FROM league_store_items WHERE active = TRUE ORDER BY point_cost"
    ))
    return [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "type": r["type"],
            "point_cost": r["point_cost"],
            "asset_url": r["asset_url"],
            "exclusive_season_id": str(r["exclusive_season_id"]) if r["exclusive_season_id"] else None,
            "exclusive_top_n": r["exclusive_top_n"],
        }
        for r in result.mappings().all()
    ]


@router.post("/purchase/{item_id}")
async def purchase_item(
    item_id: UUID,
    session: AsyncSession = Depends(get_session),
    user=Depends(require_dev_auth),
):
    item = (await session.execute(text(
        "SELECT id, point_cost, active, exclusive_season_id, exclusive_top_n FROM league_store_items WHERE id = :id"
    ), {"id": str(item_id)})).mappings().one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if not item["active"]:
        raise HTTPException(status_code=410, detail="Item no longer available")
    if item["exclusive_season_id"] is not None:
        raise HTTPException(status_code=403, detail="This is an exclusive item and cannot be purchased")

    balance = (await session.execute(text(
        "SELECT COALESCE(SUM(delta), 0) FROM league_points_ledger WHERE engineer_id = :uid"
    ), {"uid": user["user_id"]})).scalar()
    if int(balance) < item["point_cost"]:
        raise HTTPException(status_code=402, detail="Insufficient points balance")

    already_owned = (await session.execute(text(
        "SELECT COUNT(*) FROM league_purchases WHERE engineer_id = :uid AND item_id = :iid"
    ), {"uid": user["user_id"], "iid": str(item_id)})).scalar()
    if already_owned:
        raise HTTPException(status_code=409, detail="Item already owned")

    await session.execute(text(
        "INSERT INTO league_purchases (engineer_id, item_id, points_spent) VALUES (:uid, :iid, :pts)"
    ), {"uid": user["user_id"], "iid": str(item_id), "pts": item["point_cost"]})
    await session.execute(text("""
        INSERT INTO league_points_ledger (engineer_id, delta, reason, ref_id)
        VALUES (:uid, :delta, 'store_purchase', :ref)
    """), {"uid": user["user_id"], "delta": -item["point_cost"], "ref": str(item_id)})
    await session.commit()

    new_balance = int(balance) - item["point_cost"]
    return {"item_id": str(item_id), "new_balance": new_balance}


@router.get("/owned")
async def my_items(session: AsyncSession = Depends(get_session), user=Depends(require_dev_auth)):
    result = await session.execute(text("""
        SELECT si.id, si.name, si.type, si.asset_url, p.purchased_at
        FROM league_purchases p
        JOIN league_store_items si ON si.id = p.item_id
        WHERE p.engineer_id = :uid
        ORDER BY p.purchased_at DESC
    """), {"uid": user["user_id"]})
    return [
        {"id": str(r["id"]), "name": r["name"], "type": r["type"],
         "asset_url": r["asset_url"], "purchased_at": r["purchased_at"].isoformat()}
        for r in result.mappings().all()
    ]
