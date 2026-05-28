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
