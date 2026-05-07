"""HTML UI routes — form-based frontend for human operators."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session
from app.models.api_key import APIKey
from app.models.audit_log import AuditLog
from app.models.model_registry import ModelRegistry
from app.models.pricing import ModelPricing
from app.models.team import Team
from app.routers.api_keys import KeyCreate
from app.routers.teams import TeamCreate

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory="app/templates")

# Format large numbers with thousands separators
templates.env.filters["format_number"] = lambda v: f"{int(v or 0):,}"


# ── Dashboard ────────────────────────────────────────────────────────────────

_STATS_QUERY = """
    SELECT
        t.name AS team_name,
        COUNT(cr.id) AS request_count,
        SUM(cr.tokens_input) AS tokens_input,
        SUM(cr.tokens_output) AS tokens_output,
        SUM(cr.tokens_input + cr.tokens_output) AS total_tokens,
        ROUND(SUM(cr.cost_usd)::numeric, 4) AS total_cost_usd,
        ROUND(AVG(CASE WHEN cr.cache_hit THEN 1.0 ELSE 0.0 END) * 100, 1) AS cache_hit_pct
    FROM teams t
    LEFT JOIN cost_records cr ON cr.team_id = t.id
    {where}
    GROUP BY t.id, t.name
    ORDER BY total_tokens DESC NULLS LAST
"""


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    days: int = Query(default=30),
    session: AsyncSession = Depends(get_session),
):
    if days > 0:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        where = "WHERE cr.created_at >= :since OR cr.id IS NULL"
        params = {"since": since}
        range_label = f"Last {days} days"
    else:
        where = ""
        params = {}
        range_label = "All time"

    rows = (await session.execute(text(_STATS_QUERY.format(where=where)), params)).mappings().all()

    totals = {
        "requests": sum(r["request_count"] or 0 for r in rows),
        "tokens": sum(r["total_tokens"] or 0 for r in rows),
        "tokens_in": sum(r["tokens_input"] or 0 for r in rows),
        "tokens_out": sum(r["tokens_output"] or 0 for r in rows),
        "cost": sum(float(r["total_cost_usd"] or 0) for r in rows),
        "cache_pct": (
            f"{sum(float(r['cache_hit_pct'] or 0) for r in rows) / len(rows):.1f}"
            if rows else "0.0"
        ),
    }
    return templates.TemplateResponse(
        request, "dashboard.html",
        {"rows": rows, "totals": totals, "days": days, "range_label": range_label},
    )


# ── Teams ────────────────────────────────────────────────────────────────────

@router.get("/ui/teams", response_class=HTMLResponse)
async def teams_page(request: Request, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Team).order_by(Team.created_at))
    return templates.TemplateResponse(
        request, "teams.html", {"teams": result.scalars().all()}
    )


@router.post("/ui/teams")
async def create_team_ui(
    request: Request,
    name: str = Form(...),
    slug: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    from app.models.team import Team as TeamModel
    team = TeamModel(name=name, slug=slug)
    session.add(team)
    await session.flush()
    await audit.record(session, request, "create_team", "team", resource_id=team.id)
    await session.commit()
    return RedirectResponse("/ui/teams", status_code=303)


@router.post("/ui/teams/{team_id}")
async def update_team_ui(
    team_id: UUID,
    request: Request,
    name: str = Form(...),
    slug: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    team = await session.get(Team, team_id)
    if team:
        team.name = name
        team.slug = slug
        await audit.record(session, request, "update_team", "team", resource_id=team_id,
                           details={"name": name, "slug": slug})
        await session.commit()
    return RedirectResponse("/ui/teams", status_code=303)


@router.post("/ui/teams/{team_id}/delete")
async def delete_team_ui(
    team_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    team = await session.get(Team, team_id)
    if team:
        await audit.record(session, request, "delete_team", "team", resource_id=team_id)
        await session.delete(team)
        await session.commit()
    return RedirectResponse("/ui/teams", status_code=303)


# ── API Keys ─────────────────────────────────────────────────────────────────

@router.get("/ui/api-keys", response_class=HTMLResponse)
async def api_keys_page(
    request: Request,
    team_id: UUID | None = Query(default=None),
    new_key: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    teams_result = await session.execute(select(Team).order_by(Team.name))
    teams = teams_result.scalars().all()

    selected_team = None
    if team_id:
        selected_team = await session.get(Team, team_id)
        stmt = (
            select(APIKey)
            .where(APIKey.team_id == team_id)
            .order_by(APIKey.created_at.desc())
        )
    else:
        stmt = select(APIKey).order_by(APIKey.created_at.desc())

    keys_result = await session.execute(stmt)
    keys = keys_result.scalars().all()

    # Build team name lookup for "all teams" view
    team_map = {str(t.id): t.name for t in teams}
    for key in keys:
        key.team_name = team_map.get(str(key.team_id), "")

    return templates.TemplateResponse(
        request, "api_keys.html",
        {
            "teams": teams,
            "keys": keys,
            "selected_team": selected_team,
            "selected_team_id": str(team_id) if team_id else None,
            "new_key": new_key,
        },
    )


@router.post("/ui/api-keys")
async def create_key_ui(
    request: Request,
    team_id: UUID = Query(...),
    name: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    import hashlib
    import secrets as _secrets
    raw_key = "sk-" + _secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = APIKey(team_id=team_id, name=name, key_hash=key_hash)
    session.add(api_key)
    await session.flush()
    await audit.record(session, request, "create_api_key", "api_key",
                       resource_id=api_key.id, details={"name": name, "team_id": str(team_id)})
    await session.commit()
    return RedirectResponse(f"/ui/api-keys?team_id={team_id}&new_key={raw_key}", status_code=303)


@router.post("/ui/api-keys/{key_id}/revoke")
async def revoke_key_ui(
    key_id: UUID,
    request: Request,
    team_id: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    key = await session.get(APIKey, key_id)
    if key:
        key.revoked_at = datetime.now(timezone.utc)
        await audit.record(session, request, "revoke_api_key", "api_key",
                           resource_id=key_id, details={"name": key.name})
        await session.commit()
    redirect = f"/ui/api-keys?team_id={team_id}" if team_id else "/ui/api-keys"
    return RedirectResponse(redirect, status_code=303)


# ── Audit Log ────────────────────────────────────────────────────────────────

@router.get("/ui/audit-log", response_class=HTMLResponse)
async def audit_log_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(200)
    )
    return templates.TemplateResponse(
        request, "audit_log.html", {"entries": result.scalars().all()}
    )


# ── Pricing ───────────────────────────────────────────────────────────────────

@router.get("/ui/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(ModelPricing).order_by(ModelPricing.model_prefix))
    return templates.TemplateResponse(request, "pricing.html", {"rows": result.scalars().all()})


@router.post("/ui/pricing")
async def upsert_pricing_ui(
    request: Request,
    model_prefix: str = Form(...),
    price_input_per_1k: float = Form(...),
    price_output_per_1k: float = Form(...),
    session: AsyncSession = Depends(get_session),
):
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    stmt = (
        pg_insert(ModelPricing)
        .values(model_prefix=model_prefix, price_input_per_1k=price_input_per_1k, price_output_per_1k=price_output_per_1k)
        .on_conflict_do_update(
            index_elements=["model_prefix"],
            set_={"price_input_per_1k": price_input_per_1k, "price_output_per_1k": price_output_per_1k, "updated_at": text("NOW()")},
        )
    )
    await session.execute(stmt)
    await audit.record(session, request, "upsert_pricing", "model_pricing",
                       details={"model_prefix": model_prefix, "input": price_input_per_1k, "output": price_output_per_1k})
    await session.commit()
    return RedirectResponse("/ui/pricing", status_code=303)


@router.post("/ui/pricing/{model_prefix}/delete")
async def delete_pricing_ui(model_prefix: str, request: Request, session: AsyncSession = Depends(get_session)):
    row = await session.get(ModelPricing, model_prefix)
    if row:
        await audit.record(session, request, "delete_pricing", "model_pricing", details={"model_prefix": model_prefix})
        await session.delete(row)
        await session.commit()
    return RedirectResponse("/ui/pricing", status_code=303)


# ── Model Registry ────────────────────────────────────────────────────────────

@router.get("/ui/models", response_class=HTMLResponse)
async def model_registry_page(request: Request, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(ModelRegistry).order_by(ModelRegistry.provider, ModelRegistry.name))
    return templates.TemplateResponse(request, "model_registry.html", {"models": result.scalars().all()})


@router.post("/ui/models")
async def create_model_ui(
    request: Request,
    name: str = Form(...),
    model_id: str = Form(...),
    provider: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    model = ModelRegistry(name=name, model_id=model_id, provider=provider, enabled=True)
    session.add(model)
    await session.flush()
    await audit.record(session, request, "create_model", "model_registry",
                       details={"model_id": model_id, "provider": provider})
    await session.commit()
    return RedirectResponse("/ui/models", status_code=303)


@router.post("/ui/models/{model_id}/toggle")
async def toggle_model_ui(model_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(ModelRegistry).where(ModelRegistry.model_id == model_id))
    model = result.scalar_one_or_none()
    if model:
        model.enabled = not model.enabled
        await audit.record(session, request, "toggle_model", "model_registry",
                           resource_id=model_id, details={"enabled": model.enabled})
        await session.commit()
    return RedirectResponse("/ui/models", status_code=303)


@router.post("/ui/models/{model_id}/delete")
async def delete_model_ui(model_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(ModelRegistry).where(ModelRegistry.model_id == model_id))
    model = result.scalar_one_or_none()
    if model:
        await audit.record(session, request, "delete_model", "model_registry", resource_id=model_id)
        await session.delete(model)
        await session.commit()
    return RedirectResponse("/ui/models", status_code=303)
