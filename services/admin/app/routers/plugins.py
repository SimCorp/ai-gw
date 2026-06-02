from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter(prefix="/plugins", tags=["plugins"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PluginCreate(BaseModel):
    name: str = Field(..., max_length=200)
    slug: str = Field(..., max_length=100, pattern="^[a-z0-9-]+$")
    description: str | None = Field(default=None, max_length=2000)
    version: str = Field(default="0.1.0", max_length=50)
    author: str = Field(default="community", max_length=200)
    category: str = Field(default="tool", pattern="^(tool|integration|data|security|workflow)$")
    scopes: list[str] = Field(default=[], max_length=20)
    homepage_url: str | None = Field(default=None, max_length=2048)
    icon_url: str | None = Field(default=None, max_length=2048)
    enabled: bool = True


class PluginUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    version: str | None = None
    author: str | None = None
    category: str | None = None
    scopes: list[str] | None = None
    homepage_url: str | None = None
    icon_url: str | None = None
    enabled: bool | None = None


class PluginTeamOverrideCreate(BaseModel):
    team_id: str
    enabled: bool = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_plugins(session: AsyncSession = Depends(get_session)):
    rows = (
        (
            await session.execute(
                text("""
        SELECT p.*, COUNT(DISTINCT o.id) AS override_count
        FROM plugins p
        LEFT JOIN plugin_team_overrides o ON o.plugin_id = p.id
        GROUP BY p.id
        ORDER BY p.name
    """)
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


@router.get("/summary")
async def plugin_summary(session: AsyncSession = Depends(get_session)):
    counts_row = (
        (
            await session.execute(
                text("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE enabled) AS enabled,
            COUNT(*) FILTER (WHERE NOT enabled) AS disabled
        FROM plugins
    """)
            )
        )
        .mappings()
        .first()
    )

    category_rows = (
        (
            await session.execute(
                text("""
        SELECT category, COUNT(*) AS cnt
        FROM plugins
        GROUP BY category
        ORDER BY category
    """)
            )
        )
        .mappings()
        .all()
    )

    overrides_row = (
        (
            await session.execute(
                text("""
        SELECT COUNT(*) AS total_overrides FROM plugin_team_overrides
    """)
            )
        )
        .mappings()
        .first()
    )

    per_category = {r["category"]: r["cnt"] for r in category_rows}

    return {
        "total": counts_row["total"] if counts_row else 0,
        "enabled": counts_row["enabled"] if counts_row else 0,
        "disabled": counts_row["disabled"] if counts_row else 0,
        "per_category": per_category,
        "total_overrides": overrides_row["total_overrides"] if overrides_row else 0,
    }


@router.post("", status_code=201)
async def create_plugin(body: PluginCreate, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        text("""
            INSERT INTO plugins (name, slug, description, version, author, category, scopes, homepage_url, icon_url, enabled)
            VALUES (:name, :slug, :description, :version, :author, :category, string_to_array(NULLIF(:scopes, ''), ','), :homepage_url, :icon_url, :enabled)
            RETURNING *
        """),
        {
            "name": body.name,
            "slug": body.slug,
            "description": body.description,
            "version": body.version,
            "author": body.author,
            "category": body.category,
            "scopes": ",".join(body.scopes),
            "homepage_url": body.homepage_url,
            "icon_url": body.icon_url,
            "enabled": body.enabled,
        },
    )
    await session.commit()
    return dict(result.mappings().first())


@router.get("/{plugin_id}")
async def get_plugin(plugin_id: str, session: AsyncSession = Depends(get_session)):
    plugin_row = (
        (
            await session.execute(
                text("SELECT * FROM plugins WHERE id = CAST(:id AS uuid)"),
                {"id": plugin_id},
            )
        )
        .mappings()
        .first()
    )
    if not plugin_row:
        raise HTTPException(status_code=404, detail="Plugin not found")

    overrides = (
        (
            await session.execute(
                text("""
            SELECT o.id, o.plugin_id, o.team_id, t.name AS team_name, o.enabled, o.created_at
            FROM plugin_team_overrides o
            JOIN organization_nodes t ON t.id = o.team_id
            WHERE o.plugin_id = CAST(:plugin_id AS uuid)
            ORDER BY t.name
        """),
                {"plugin_id": plugin_id},
            )
        )
        .mappings()
        .all()
    )

    return {
        "plugin": dict(plugin_row),
        "team_overrides": [dict(r) for r in overrides],
    }


@router.put("/{plugin_id}")
async def update_plugin(
    plugin_id: str,
    body: PluginUpdate,
    session: AsyncSession = Depends(get_session),
):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    _ALLOWED_PLUGIN_FIELDS = {
        "name",
        "description",
        "version",
        "author",
        "category",
        "scopes",
        "homepage_url",
        "icon_url",
        "enabled",
    }
    for field in updates:
        if field not in _ALLOWED_PLUGIN_FIELDS:
            raise HTTPException(status_code=400, detail=f"Unknown field: {field}")

    set_clauses: list[str] = []
    params: dict[str, Any] = {"id": plugin_id}

    for field, value in updates.items():
        if field == "scopes":
            set_clauses.append("scopes = string_to_array(NULLIF(:scopes, ''), ',')")
            params["scopes"] = ",".join(value)
        else:
            set_clauses.append(f"{field} = :{field}")
            params[field] = value

    set_clauses.append("updated_at = NOW()")

    sql = text(f"""
        UPDATE plugins
        SET {", ".join(set_clauses)}
        WHERE id = CAST(:id AS uuid)
        RETURNING *
    """)
    result = await session.execute(sql, params)
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Plugin not found")
    await session.commit()
    return dict(row)


@router.delete("/{plugin_id}", status_code=204)
async def delete_plugin(plugin_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        text("DELETE FROM plugins WHERE id = CAST(:id AS uuid) RETURNING id"),
        {"id": plugin_id},
    )
    if not result.first():
        raise HTTPException(status_code=404, detail="Plugin not found")
    await session.commit()


@router.get("/{plugin_id}/teams")
async def list_plugin_teams(plugin_id: str, session: AsyncSession = Depends(get_session)):
    plugin_row = (
        await session.execute(
            text("SELECT id FROM plugins WHERE id = CAST(:id AS uuid)"),
            {"id": plugin_id},
        )
    ).first()
    if not plugin_row:
        raise HTTPException(status_code=404, detail="Plugin not found")

    rows = (
        (
            await session.execute(
                text("""
            SELECT o.id, o.plugin_id, o.team_id, t.name AS team_name, o.enabled, o.created_at
            FROM plugin_team_overrides o
            JOIN organization_nodes t ON t.id = o.team_id
            WHERE o.plugin_id = CAST(:plugin_id AS uuid)
            ORDER BY t.name
        """),
                {"plugin_id": plugin_id},
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


@router.post("/{plugin_id}/teams", status_code=201)
async def set_plugin_team_override(
    plugin_id: str,
    body: PluginTeamOverrideCreate,
    session: AsyncSession = Depends(get_session),
):
    plugin_row = (
        await session.execute(
            text("SELECT id FROM plugins WHERE id = CAST(:id AS uuid)"),
            {"id": plugin_id},
        )
    ).first()
    if not plugin_row:
        raise HTTPException(status_code=404, detail="Plugin not found")

    team_row = (
        await session.execute(
            text(
                "SELECT id FROM organization_nodes WHERE id = CAST(:id AS uuid) AND type = 'team'"
            ),
            {"id": body.team_id},
        )
    ).first()
    if not team_row:
        raise HTTPException(status_code=404, detail="Team not found")

    result = await session.execute(
        text("""
            INSERT INTO plugin_team_overrides (plugin_id, team_id, enabled)
            VALUES (CAST(:plugin_id AS uuid), CAST(:team_id AS uuid), :enabled)
            ON CONFLICT (plugin_id, team_id) DO UPDATE SET enabled = EXCLUDED.enabled
            RETURNING *
        """),
        {"plugin_id": plugin_id, "team_id": body.team_id, "enabled": body.enabled},
    )
    await session.commit()
    return dict(result.mappings().first())


@router.delete("/{plugin_id}/teams/{team_id}", status_code=204)
async def delete_plugin_team_override(
    plugin_id: str,
    team_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        text("""
            DELETE FROM plugin_team_overrides
            WHERE plugin_id = CAST(:plugin_id AS uuid) AND team_id = CAST(:team_id AS uuid)
            RETURNING id
        """),
        {"plugin_id": plugin_id, "team_id": team_id},
    )
    if not result.first():
        raise HTTPException(status_code=404, detail="Override not found")
    await session.commit()
