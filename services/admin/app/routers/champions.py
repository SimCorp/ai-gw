"""Developer-facing champions endpoints — directory, profile, content submission, feed."""

import json
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.league_client import grant_points
from app.llm.champion_metadata import classify_content

router = APIRouter(prefix="/champions", tags=["champions"])


# ---------- Wave 2 schemas ----------

class AskCreate(BaseModel):
    title: str
    description: str
    created_by: UUID
    team_id: UUID | None = None
    tags: list[str] = []


class AskClaim(BaseModel):
    champion_id: UUID


class AskResolve(BaseModel):
    champion_id: UUID


class AskConfirm(BaseModel):
    asker_id: UUID


class BookingCreate(BaseModel):
    requested_by: UUID
    slot_text: str
    topic: str | None = None
    team_id: UUID | None = None


class BookingChampionAction(BaseModel):
    champion_id: UUID


class BookingCancel(BaseModel):
    actor_id: UUID


class UpvoteBody(BaseModel):
    developer_id: UUID


class FlagBody(BaseModel):
    developer_id: UUID
    reason: str | None = None


# ---------- librarian helper ----------

async def ingest_to_librarian(
    *,
    title: str,
    content: str,
    source_url: str | None,
    tags: list[str],
) -> str | None:
    """POST /ingest to librarian. Returns the librarian item id, or None on failure."""
    payload = {
        "title": title,
        "content": content,
        "source_url": source_url,
        "topic": "champions",
        "tags": tags,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{settings.librarian_url}/ingest",
                json=payload,
                headers={"X-Service-Token": settings.librarian_service_token},
            )
        if resp.status_code in (200, 201):
            try:
                return resp.json().get("id")
            except Exception:
                return None
    except Exception:
        return None
    return None


# ---------- schemas ----------

class ContentSubmit(BaseModel):
    champion_id: UUID
    type: str
    url: str | None = None
    text: str | None = None
    optional_title: str | None = None

    @model_validator(mode="after")
    def _need_url_or_text(self):
        if not self.url and not self.text:
            raise ValueError("either url or text is required")
        return self


# ---------- directory ----------

@router.get("")
async def list_directory(session: AsyncSession = Depends(get_session)):
    result = await session.execute(text("""
        SELECT developer_id, bio, focus_areas, office_hours_text, active, nominated_at
        FROM champions
        WHERE active = TRUE
        ORDER BY nominated_at DESC
    """))
    return [
        {
            "developer_id": str(r["developer_id"]),
            "bio": r["bio"],
            "focus_areas": list(r["focus_areas"]) if r["focus_areas"] is not None else [],
            "office_hours_text": r["office_hours_text"],
            "active": r["active"],
        }
        for r in result.mappings().all()
    ]


# ---------- content feed (must be declared BEFORE /{developer_id}) ----------

@router.get("/content")
async def list_content(session: AsyncSession = Depends(get_session)):
    result = await session.execute(text("""
        SELECT id, champion_id, type, submitted_at, auto_metadata, upvotes, views
        FROM champion_contributions
        ORDER BY submitted_at DESC
        LIMIT 50
    """))
    return [
        {
            "id": str(r["id"]),
            "champion_id": str(r["champion_id"]),
            "type": r["type"],
            "submitted_at": r["submitted_at"].isoformat() if r["submitted_at"] else None,
            "metadata": r["auto_metadata"] or {},
            "upvotes": r["upvotes"],
            "views": r["views"],
        }
        for r in result.mappings().all()
    ]


# ---------- content submission ----------

@router.post("/content", status_code=201)
async def submit_content(body: ContentSubmit, session: AsyncSession = Depends(get_session)):
    body_text = (body.text or body.url or "")[:8000]
    metadata = await classify_content(text=body_text)
    title = body.optional_title or metadata["title"]

    librarian_id = await ingest_to_librarian(
        title=title,
        content=body_text,
        source_url=body.url,
        tags=metadata["tags"],
    )

    inserted_id = (await session.execute(
        text("""
            INSERT INTO champion_contributions (champion_id, type, librarian_item_id, auto_metadata)
            VALUES (:champion_id, :type, :lib_id, CAST(:meta AS JSONB))
            RETURNING id
        """),
        {
            "champion_id": str(body.champion_id),
            "type": body.type,
            "lib_id": librarian_id,
            "meta": json.dumps({**metadata, "title": title}, default=str),
        },
    )).scalar_one()
    await session.commit()

    try:
        await grant_points(
            engineer_id=str(body.champion_id),
            delta=50,
            reason="champion_content",
            ref_id=str(inserted_id),
        )
    except RuntimeError:
        pass

    return {"id": str(inserted_id), "title": title, "summary": metadata["summary"]}


# ---------- asks ----------

@router.post("/asks", status_code=201)
async def create_ask(body: AskCreate, session: AsyncSession = Depends(get_session)):
    inserted_id = (await session.execute(
        text("""
            INSERT INTO champion_asks (title, description, created_by, team_id, tags, status)
            VALUES (:title, :description, :created_by, :team_id, :tags, 'open')
            RETURNING id
        """),
        {
            "title": body.title,
            "description": body.description,
            "created_by": str(body.created_by),
            "team_id": str(body.team_id) if body.team_id else None,
            "tags": body.tags,
        },
    )).scalar_one()
    await session.commit()
    return {"id": str(inserted_id)}


@router.get("/asks")
async def list_asks(status: str | None = None, session: AsyncSession = Depends(get_session)):
    if status:
        query = text("""
            SELECT id, title, description, created_by, team_id, status, claimed_by,
                   resolved_at, confirmed_at, auto_confirm_at, created_at, tags
            FROM champion_asks
            WHERE status = :status
            ORDER BY created_at DESC
            LIMIT 100
        """)
        params = {"status": status}
    else:
        query = text("""
            SELECT id, title, description, created_by, team_id, status, claimed_by,
                   resolved_at, confirmed_at, auto_confirm_at, created_at, tags
            FROM champion_asks
            ORDER BY created_at DESC
            LIMIT 100
        """)
        params = {}
    result = await session.execute(query, params)
    return [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "description": r["description"],
            "created_by": str(r["created_by"]),
            "team_id": str(r["team_id"]) if r["team_id"] else None,
            "status": r["status"],
            "claimed_by": str(r["claimed_by"]) if r["claimed_by"] else None,
            "resolved_at": r["resolved_at"].isoformat() if r["resolved_at"] else None,
            "confirmed_at": r["confirmed_at"].isoformat() if r["confirmed_at"] else None,
            "auto_confirm_at": r["auto_confirm_at"].isoformat() if r["auto_confirm_at"] else None,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "tags": list(r["tags"]) if r["tags"] is not None else [],
        }
        for r in result.mappings().all()
    ]


@router.post("/asks/{ask_id}/claim")
async def claim_ask(ask_id: UUID, body: AskClaim, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        text("""
            UPDATE champion_asks
            SET status = 'claimed', claimed_by = :champion_id
            WHERE id = :ask_id AND status = 'open'
        """),
        {"ask_id": str(ask_id), "champion_id": str(body.champion_id)},
    )
    await session.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=409, detail="ask not open or not found")
    return {"ok": True, "id": str(ask_id), "claimed_by": str(body.champion_id)}


@router.post("/asks/{ask_id}/resolve")
async def resolve_ask(ask_id: UUID, body: AskResolve, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        text("""
            UPDATE champion_asks
            SET status = 'resolved_pending',
                resolved_at = NOW(),
                auto_confirm_at = NOW() + INTERVAL '7 days'
            WHERE id = :ask_id AND status = 'claimed' AND claimed_by = :champion_id
        """),
        {"ask_id": str(ask_id), "champion_id": str(body.champion_id)},
    )
    await session.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=409, detail="ask not in claimed state or not claimed by this champion")
    return {"ok": True, "id": str(ask_id), "status": "resolved_pending"}


@router.post("/asks/{ask_id}/confirm")
async def confirm_ask(ask_id: UUID, body: AskConfirm, session: AsyncSession = Depends(get_session)):
    row = (await session.execute(
        text("SELECT status, created_by, claimed_by FROM champion_asks WHERE id = :ask_id"),
        {"ask_id": str(ask_id)},
    )).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="ask not found")
    if str(row["created_by"]) != str(body.asker_id):
        raise HTTPException(status_code=403, detail="only the asker can confirm")
    if row["status"] != "resolved_pending":
        raise HTTPException(status_code=409, detail="ask not in resolved_pending state")

    await session.execute(
        text("""
            UPDATE champion_asks
            SET status = 'resolved', confirmed_at = NOW()
            WHERE id = :ask_id
        """),
        {"ask_id": str(ask_id)},
    )
    await session.commit()

    claimed_by = row["claimed_by"]
    if claimed_by:
        try:
            await grant_points(
                engineer_id=str(claimed_by),
                delta=200,
                reason="champion_ask_resolved",
                ref_id=str(ask_id),
            )
        except RuntimeError:
            pass

    return {"ok": True, "id": str(ask_id), "status": "resolved"}


# ---------- upvotes ----------

@router.post("/content/{contribution_id}/upvote")
async def upvote_content(
    contribution_id: UUID,
    body: UpvoteBody,
    session: AsyncSession = Depends(get_session),
):
    existing = (await session.execute(
        text("""
            SELECT 1 FROM champion_upvotes
            WHERE developer_id = :dev AND contribution_id = :cid
        """),
        {"dev": str(body.developer_id), "cid": str(contribution_id)},
    )).scalar_one_or_none()

    if existing is not None:
        # toggle off: delete + decrement
        await session.execute(
            text("""
                DELETE FROM champion_upvotes
                WHERE developer_id = :dev AND contribution_id = :cid
            """),
            {"dev": str(body.developer_id), "cid": str(contribution_id)},
        )
        upvotes = (await session.execute(
            text("""
                UPDATE champion_contributions
                SET upvotes = GREATEST(upvotes - 1, 0)
                WHERE id = :cid
                RETURNING upvotes
            """),
            {"cid": str(contribution_id)},
        )).scalar_one()
        await session.commit()
        return {"upvoted": False, "upvotes": upvotes}

    # toggle on: insert + increment + grant
    await session.execute(
        text("""
            INSERT INTO champion_upvotes (developer_id, contribution_id)
            VALUES (:dev, :cid)
        """),
        {"dev": str(body.developer_id), "cid": str(contribution_id)},
    )
    row = (await session.execute(
        text("""
            UPDATE champion_contributions
            SET upvotes = upvotes + 1
            WHERE id = :cid
            RETURNING upvotes, champion_id
        """),
        {"cid": str(contribution_id)},
    )).mappings().one()
    await session.commit()

    try:
        await grant_points(
            engineer_id=str(row["champion_id"]),
            delta=5,
            reason="champion_upvote",
            ref_id=str(contribution_id),
        )
    except RuntimeError:
        pass

    return {"upvoted": True, "upvotes": row["upvotes"]}


# ---------- flags ----------

@router.post("/content/{contribution_id}/flag", status_code=201)
async def flag_content(
    contribution_id: UUID,
    body: FlagBody,
    session: AsyncSession = Depends(get_session),
):
    flag_id = (await session.execute(
        text("""
            INSERT INTO champion_flags (contribution_id, flagged_by, reason, status)
            VALUES (:cid, :dev, :reason, 'open')
            RETURNING id
        """),
        {
            "cid": str(contribution_id),
            "dev": str(body.developer_id),
            "reason": body.reason,
        },
    )).scalar_one()
    await session.execute(
        text("""
            UPDATE champion_contributions
            SET flag_count = flag_count + 1
            WHERE id = :cid
        """),
        {"cid": str(contribution_id)},
    )
    await session.commit()
    return {"id": str(flag_id)}


# ---------- profile (catch-all on /{developer_id} declared AFTER /content) ----------

@router.get("/{developer_id}")
async def profile(developer_id: UUID, session: AsyncSession = Depends(get_session)):
    row = (await session.execute(
        text("SELECT developer_id, bio, focus_areas, office_hours_text, active FROM champions WHERE developer_id = :d"),
        {"d": str(developer_id)},
    )).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="champion not found")
    return {
        "developer_id": str(row["developer_id"]),
        "bio": row["bio"],
        "focus_areas": list(row["focus_areas"]) if row["focus_areas"] is not None else [],
        "office_hours_text": row["office_hours_text"],
        "active": row["active"],
    }


# ---------- Wave 3: bookings ----------

@router.post("/{champion_id}/book", status_code=201)
async def create_booking(
    champion_id: UUID,
    body: BookingCreate,
    session: AsyncSession = Depends(get_session),
):
    inserted_id = (await session.execute(
        text("""
            INSERT INTO champion_bookings (champion_id, requested_by, slot_text, topic, team_id, status)
            VALUES (:champion_id, :requested_by, :slot_text, :topic, :team_id, 'requested')
            RETURNING id
        """),
        {
            "champion_id": str(champion_id),
            "requested_by": str(body.requested_by),
            "slot_text": body.slot_text,
            "topic": body.topic,
            "team_id": str(body.team_id) if body.team_id else None,
        },
    )).scalar_one()
    await session.commit()
    return {"booking_id": str(inserted_id)}


@router.get("/{champion_id}/bookings")
async def list_bookings(champion_id: UUID, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        text("""
            SELECT id, champion_id, requested_by, slot_text, topic, team_id, status, created_at
            FROM champion_bookings
            WHERE champion_id = :cid
            ORDER BY created_at DESC
            LIMIT 200
        """),
        {"cid": str(champion_id)},
    )
    return [
        {
            "id": str(r["id"]),
            "champion_id": str(r["champion_id"]),
            "requested_by": str(r["requested_by"]),
            "slot_text": r["slot_text"],
            "topic": r["topic"],
            "team_id": str(r["team_id"]) if r["team_id"] else None,
            "status": r["status"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in result.mappings().all()
    ]


@router.post("/bookings/{booking_id}/confirm")
async def confirm_booking(
    booking_id: UUID,
    body: BookingChampionAction,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        text("""
            UPDATE champion_bookings
            SET status = 'confirmed'
            WHERE id = :bid AND champion_id = :cid AND status = 'requested'
        """),
        {"bid": str(booking_id), "cid": str(body.champion_id)},
    )
    await session.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=409, detail="booking not in requested state or not for this champion")
    return {"ok": True, "id": str(booking_id), "status": "confirmed"}


@router.post("/bookings/{booking_id}/done")
async def done_booking(
    booking_id: UUID,
    body: BookingChampionAction,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        text("""
            UPDATE champion_bookings
            SET status = 'done'
            WHERE id = :bid AND champion_id = :cid AND status = 'confirmed'
        """),
        {"bid": str(booking_id), "cid": str(body.champion_id)},
    )
    await session.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=409, detail="booking not in confirmed state or not for this champion")

    try:
        await grant_points(
            engineer_id=str(body.champion_id),
            delta=150,
            reason="champion_office_hours",
            ref_id=str(booking_id),
        )
    except RuntimeError:
        pass

    return {"ok": True, "id": str(booking_id), "status": "done"}


@router.post("/bookings/{booking_id}/cancel")
async def cancel_booking(
    booking_id: UUID,
    body: BookingCancel,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        text("""
            UPDATE champion_bookings
            SET status = 'cancelled'
            WHERE id = :bid AND status IN ('requested', 'confirmed')
        """),
        {"bid": str(booking_id)},
    )
    await session.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=409, detail="booking not cancellable")
    return {"ok": True, "id": str(booking_id), "status": "cancelled", "actor_id": str(body.actor_id)}


# ---------- Wave 3: smart routing ----------

@router.post("/asks/{ask_id}/route")
async def route_ask(ask_id: UUID, session: AsyncSession = Depends(get_session)):
    ask_row = (await session.execute(
        text("SELECT id, tags FROM champion_asks WHERE id = :id"),
        {"id": str(ask_id)},
    )).mappings().one_or_none()
    if ask_row is None:
        raise HTTPException(status_code=404, detail="ask not found")

    ask_tags = set(ask_row["tags"] or [])

    rows = (await session.execute(text("""
        SELECT c.developer_id,
               c.focus_areas,
               MAX(cc.submitted_at) AS last_submitted_at
        FROM champions c
        LEFT JOIN champion_contributions cc ON cc.champion_id = c.developer_id
        WHERE c.active = TRUE
        GROUP BY c.developer_id, c.focus_areas
    """))).mappings().all()

    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)

    scored = []
    for r in rows:
        focus = list(r["focus_areas"] or [])
        overlap = len(ask_tags.intersection(focus))
        focus_score = overlap / max(1, len(focus))

        last = r["last_submitted_at"]
        if last is None:
            recency_score = 0.3
        else:
            # Ensure tz-aware comparison
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            age = now - last
            if age <= timedelta(days=7):
                recency_score = 1.0
            elif age <= timedelta(days=30):
                recency_score = 0.6
            else:
                recency_score = 0.3

        score = focus_score * 0.6 + recency_score * 0.4
        scored.append({
            "developer_id": str(r["developer_id"]),
            "score": round(score, 4),
            "focus_areas": focus,
        })

    scored.sort(key=lambda x: (-x["score"], x["developer_id"]))
    top3 = scored[:3]

    if top3:
        await session.execute(
            text("UPDATE champion_asks SET routed_to = :ids WHERE id = :id"),
            {"ids": [s["developer_id"] for s in top3], "id": str(ask_id)},
        )
        await session.commit()

    return {"ask_id": str(ask_id), "suggestions": top3}
