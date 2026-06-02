from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_auth, require_authenticated_user
from app.db import get_session

router = APIRouter(prefix="/skills", tags=["skills"])


def _row(r) -> dict:
    return {
        "id": str(r["id"]),
        "name": r["name"],
        "slug": r["slug"],
        "version": r["version"],
        "model": r["model"],
        "description": r["description"],
        "system_prompt": r["system_prompt"],
        "tools": list(r["tools"] or []),
        "tags": list(r["tags"] or []),
        "visibility": r["visibility"],
        "team_id": str(r["team_id"]) if r["team_id"] else None,
        "author": r["author"],
        "uses_total": r["uses_total"],
        "stars_avg": float(r["stars_avg"]),
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
    }


@router.get("")
async def list_skills(
    visibility: str | None = None,
    team_id: str | None = None,
    tag: str | None = None,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_authenticated_user),
) -> list[dict]:
    where = ["1=1"]
    params: dict[str, Any] = {}
    if visibility:
        where.append("visibility = :visibility")
        params["visibility"] = visibility
    if team_id:
        where.append("(team_id = :team_id OR visibility = 'org')")
        params["team_id"] = team_id
    if tag:
        where.append(":tag = ANY(tags)")
        params["tag"] = tag
    q = f"SELECT * FROM skills WHERE {' AND '.join(where)} ORDER BY uses_total DESC, name"
    rows = (await session.execute(text(q), params)).mappings().all()
    return [_row(r) for r in rows]


class SkillCreate(BaseModel):
    name: str
    slug: str
    version: str = "v1.0"
    model: str = "claude-sonnet-4-6"
    description: str = ""
    system_prompt: str = ""
    tools: list[str] = []
    tags: list[str] = []
    visibility: str = "team"
    team_id: str | None = None
    author: str = ""


@router.post("", status_code=201)
async def create_skill(
    body: SkillCreate,
    session: AsyncSession = Depends(get_session),
    _admin: dict = Depends(require_admin_auth),
) -> dict:
    row = (
        (
            await session.execute(
                text("""
        INSERT INTO skills (name, slug, version, model, description, system_prompt, tools, tags, visibility, team_id, author)
        VALUES (:name, :slug, :version, :model, :description, :system_prompt, :tools, :tags, :visibility, :team_id, :author)
        RETURNING *
    """),
                {
                    **body.model_dump(),
                    "tools": body.tools,
                    "tags": body.tags,
                    "team_id": body.team_id,
                },
            )
        )
        .mappings()
        .first()
    )
    await session.commit()
    return _row(row)


@router.get("/{skill_id}")
async def get_skill(
    skill_id: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_authenticated_user),
) -> dict:
    row = (
        (await session.execute(text("SELECT * FROM skills WHERE id = :id"), {"id": skill_id}))
        .mappings()
        .first()
    )
    if not row:
        raise HTTPException(404, "skill not found")
    return _row(row)


class SkillUpdate(BaseModel):
    name: str | None = None
    version: str | None = None
    model: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    tools: list[str] | None = None
    tags: list[str] | None = None
    visibility: str | None = None


@router.patch("/{skill_id}")
async def update_skill(
    skill_id: str,
    body: SkillUpdate,
    session: AsyncSession = Depends(get_session),
    _admin: dict = Depends(require_admin_auth),
) -> dict:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "no fields to update")
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    row = (
        (
            await session.execute(
                text(f"""
        UPDATE skills SET {set_clause}, updated_at = NOW()
        WHERE id = :id RETURNING *
    """),
                {**updates, "id": skill_id},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise HTTPException(404, "skill not found")
    await session.commit()
    return _row(row)


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(
    skill_id: str,
    session: AsyncSession = Depends(get_session),
    _admin: dict = Depends(require_admin_auth),
):
    result = await session.execute(text("DELETE FROM skills WHERE id = :id"), {"id": skill_id})
    if result.rowcount == 0:
        raise HTTPException(404, "skill not found")
    await session.commit()


@router.post("/{skill_id}/use", status_code=204)
async def record_use(
    skill_id: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(require_authenticated_user),
):
    await session.execute(
        text("UPDATE skills SET uses_total = uses_total + 1, updated_at = NOW() WHERE id = :id"),
        {"id": skill_id},
    )
    await session.commit()
