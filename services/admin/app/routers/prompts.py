from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_auth, require_authenticated_user
from app.db import get_session

router = APIRouter(prefix="/prompts", tags=["prompts"])


def _row(r) -> dict:
    return {
        "id": str(r["id"]),
        "title": r["title"],
        "slug": r["slug"],
        "version": r["version"],
        "description": r["description"],
        "content": r["content"],
        "author": r["author"],
        "team_id": str(r["team_id"]) if r["team_id"] else None,
        "model": r["model"],
        "tags": list(r["tags"] or []),
        "visibility": r["visibility"],
        "uses_total": r["uses_total"],
        "stars_avg": float(r["stars_avg"]),
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
    }


@router.get("")
async def list_prompts(
    team_id: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_authenticated_user),
) -> list[dict]:
    where = ["visibility IN ('team', 'org')"]
    params: dict[str, Any] = {}
    if team_id:
        where.append("(team_id = :team_id OR visibility = 'org')")
        params["team_id"] = team_id
    if tag:
        where.append(":tag = ANY(tags)")
        params["tag"] = tag
    if q:
        where.append("(title ILIKE :q OR description ILIKE :q)")
        params["q"] = f"%{q}%"
    sql = f"SELECT * FROM prompt_templates WHERE {' AND '.join(where)} ORDER BY uses_total DESC, title"
    rows = (await session.execute(text(sql), params)).mappings().all()
    return [_row(r) for r in rows]


class PromptCreate(BaseModel):
    title: str
    slug: str
    version: str = "v1.0"
    description: str = ""
    content: str
    author: str = ""
    team_id: str | None = None
    model: str | None = None
    tags: list[str] = []
    visibility: str = "team"


@router.post("", status_code=201)
async def create_prompt(
    body: PromptCreate,
    session: AsyncSession = Depends(get_session),
    _admin: dict = Depends(require_admin_auth),
) -> dict:
    row = (
        (
            await session.execute(
                text("""
        INSERT INTO prompt_templates (title, slug, version, description, content, author, team_id, model, tags, visibility)
        VALUES (:title, :slug, :version, :description, :content, :author, :team_id, :model, :tags, :visibility)
        RETURNING *
    """),
                body.model_dump(),
            )
        )
        .mappings()
        .first()
    )
    await session.commit()
    return _row(row)


@router.get("/{prompt_id}")
async def get_prompt(
    prompt_id: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_authenticated_user),
) -> dict:
    row = (
        (
            await session.execute(
                text("SELECT * FROM prompt_templates WHERE id = :id"), {"id": prompt_id}
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise HTTPException(404, "prompt not found")
    return _row(row)


@router.delete("/{prompt_id}", status_code=204)
async def delete_prompt(
    prompt_id: str,
    session: AsyncSession = Depends(get_session),
    _admin: dict = Depends(require_admin_auth),
):
    result = await session.execute(
        text("DELETE FROM prompt_templates WHERE id = :id"), {"id": prompt_id}
    )
    if result.rowcount == 0:
        raise HTTPException(404, "prompt not found")
    await session.commit()


@router.post("/{prompt_id}/use", status_code=204)
async def record_use(
    prompt_id: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_authenticated_user),
):
    await session.execute(
        text("UPDATE prompt_templates SET uses_total = uses_total + 1 WHERE id = :id"),
        {"id": prompt_id},
    )
    await session.commit()
