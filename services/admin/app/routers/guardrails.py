import json as _json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter(prefix="/guardrails", tags=["guardrails"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GuardrailCreate(BaseModel):
    name: str
    description: str | None = None
    type: str
    applies_to: str  # input | output | both
    action: str       # block | flag | redact | rewrite | truncate | route
    severity: str = "high"
    priority: int = 100
    config: dict[str, Any] = {}
    team_id: str | None = None


class GuardrailUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    applies_to: str | None = None
    action: str | None = None
    severity: str | None = None
    priority: int | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None


class GuardrailHitCreate(BaseModel):
    guardrail_id: str
    guardrail_type: str
    team_id: str | None = None
    api_key_id: str | None = None
    request_id: str | None = None
    model: str | None = None
    input_or_output: str
    action_taken: str
    severity: str
    match_count: int = 1
    match_hash: str | None = None
    redacted_excerpt: str | None = None
    match_offsets: list[dict] | None = None


# ---------------------------------------------------------------------------
# List + stats
# ---------------------------------------------------------------------------

_LIST_QUERY_BASE = """
    SELECT
        g.id, g.name, g.description, g.type, g.applies_to, g.action,
        g.severity, g.priority, g.config, g.enabled, g.version,
        g.created_at, g.updated_at, g.created_by, g.updated_by,
        g.team_id,
        COUNT(h.id) FILTER (WHERE h.created_at >= NOW() - INTERVAL '24 hours') AS hits_24h,
        COUNT(h.id) FILTER (WHERE h.action_taken = 'block' AND h.created_at >= NOW() - INTERVAL '24 hours') AS blocks_24h
    FROM guardrails g
    LEFT JOIN guardrail_hits h ON h.guardrail_id = g.id
    {where}
    GROUP BY g.id
    ORDER BY g.priority ASC, g.created_at ASC
"""

_SUMMARY_QUERY = text("""
    SELECT
        COUNT(*) FILTER (WHERE enabled) AS active_count,
        COUNT(*) FILTER (WHERE enabled AND applies_to = 'input') AS input_count,
        COUNT(*) FILTER (WHERE enabled AND applies_to = 'output') AS output_count,
        COUNT(*) FILTER (WHERE enabled AND applies_to = 'both') AS both_count,
        (SELECT COUNT(*) FROM guardrail_hits WHERE created_at >= NOW() - INTERVAL '24 hours') AS hits_24h,
        (SELECT COUNT(*) FROM guardrail_hits WHERE action_taken = 'block' AND created_at >= NOW() - INTERVAL '24 hours') AS blocked_24h
    FROM guardrails
""")

_RECENT_HITS_BASE = """
    SELECT
        h.id, h.created_at, h.guardrail_type, h.input_or_output,
        h.action_taken, h.severity, h.match_count, h.redacted_excerpt,
        h.request_id, h.model,
        t.name AS team_name
    FROM guardrail_hits h
    LEFT JOIN teams t ON t.id = h.team_id
    {where}
    ORDER BY h.created_at DESC
    LIMIT :limit
"""


@router.get("")
async def list_guardrails(
    team_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    if team_id:
        where = "WHERE (g.team_id = CAST(:team_id AS uuid) OR g.team_id IS NULL)"
        params: dict = {"team_id": team_id}
    else:
        where = ""
        params = {}
    sql = text(_LIST_QUERY_BASE.format(where=where))
    rows = (await session.execute(sql, params)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/summary")
async def guardrails_summary(session: AsyncSession = Depends(get_session)):
    row = (await session.execute(_SUMMARY_QUERY)).mappings().first()
    return dict(row) if row else {}


@router.get("/hits")
async def recent_hits(
    guardrail_id: str | None = Query(default=None),
    limit: int = Query(default=20, le=200),
    session: AsyncSession = Depends(get_session),
):
    if guardrail_id:
        where = "WHERE h.guardrail_id = CAST(:guardrail_id AS uuid)"
        params: dict = {"guardrail_id": guardrail_id, "limit": limit}
    else:
        where = ""
        params = {"limit": limit}
    sql = text(_RECENT_HITS_BASE.format(where=where))
    rows = (await session.execute(sql, params)).mappings().all()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Redis sync helper
# ---------------------------------------------------------------------------

async def _sync_guardrails_to_redis(session: AsyncSession, redis, team_id: str | None) -> None:
    """Rebuild the guardrail cache key for the given team_id (or global) in Redis."""
    if team_id:
        rows = (await session.execute(
            text("""
                SELECT id, name, type, applies_to, action, severity, priority, config, enabled, team_id
                FROM guardrails
                WHERE team_id = CAST(:tid AS uuid)
                ORDER BY priority ASC
            """),
            {"tid": team_id},
        )).mappings().all()
        redis_key = f"guardrails:{team_id}"
    else:
        rows = (await session.execute(
            text("""
                SELECT id, name, type, applies_to, action, severity, priority, config, enabled, team_id
                FROM guardrails
                WHERE team_id IS NULL
                ORDER BY priority ASC
            """),
        )).mappings().all()
        redis_key = "guardrails:global"

    rules = [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "type": r["type"],
            "applies_to": r["applies_to"],
            "action": r["action"],
            "severity": r["severity"],
            "priority": r["priority"],
            "config": r["config"] if isinstance(r["config"], dict) else {},
            "enabled": r["enabled"],
        }
        for r in rows
    ]
    await redis.set(redis_key, _json.dumps(rules), ex=300)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.post("", status_code=201)
async def create_guardrail(
    body: GuardrailCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    import json
    result = await session.execute(
        text("""
            INSERT INTO guardrails
                (name, description, type, applies_to, action, severity, priority, config, team_id)
            VALUES
                (:name, :description, :type, :applies_to, :action, :severity, :priority, CAST(:config AS jsonb), :team_id)
            RETURNING *
        """),
        {
            "name": body.name,
            "description": body.description,
            "type": body.type,
            "applies_to": body.applies_to,
            "action": body.action,
            "severity": body.severity,
            "priority": body.priority,
            "config": json.dumps(body.config),
            "team_id": body.team_id,
        },
    )
    await session.commit()
    row = dict(result.mappings().first())
    await _sync_guardrails_to_redis(session, request.app.state.redis, body.team_id)
    return row


@router.patch("/{guardrail_id}")
async def update_guardrail(
    guardrail_id: str,
    body: GuardrailUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    import json
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    _ALLOWED_GUARDRAIL_FIELDS = {"name", "description", "type", "applies_to", "action", "severity", "priority", "enabled", "config"}
    for field in updates:
        if field not in _ALLOWED_GUARDRAIL_FIELDS:
            raise HTTPException(status_code=400, detail=f"Unknown field: {field}")

    set_clauses = []
    params: dict = {"id": guardrail_id}
    for field, value in updates.items():
        if field == "config":
            set_clauses.append(f"{field} = CAST(:{field} AS jsonb)")
            params[field] = json.dumps(value)
        else:
            set_clauses.append(f"{field} = :{field}")
            params[field] = value

    set_clauses.append("updated_at = NOW()")
    set_clauses.append("version = version + 1")

    sql = text(f"""
        UPDATE guardrails
        SET {', '.join(set_clauses)}
        WHERE id = CAST(:id AS uuid)
        RETURNING *
    """)
    result = await session.execute(sql, params)
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Guardrail not found")
    await session.commit()
    row_dict = dict(row)
    # team_id may be a UUID or None
    sync_team_id = str(row_dict["team_id"]) if row_dict.get("team_id") else None
    await _sync_guardrails_to_redis(session, request.app.state.redis, sync_team_id)
    return row_dict


@router.delete("/{guardrail_id}", status_code=204)
async def delete_guardrail(
    guardrail_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    # Fetch team_id before deleting so we know which Redis key to refresh
    pre = (await session.execute(
        text("SELECT team_id FROM guardrails WHERE id = CAST(:id AS uuid)"),
        {"id": guardrail_id},
    )).mappings().first()
    if not pre:
        raise HTTPException(status_code=404, detail="Guardrail not found")
    deleted_team_id = str(pre["team_id"]) if pre["team_id"] else None
    await session.execute(
        text("DELETE FROM guardrails WHERE id = CAST(:id AS uuid)"),
        {"id": guardrail_id},
    )
    await session.commit()
    await _sync_guardrails_to_redis(session, request.app.state.redis, deleted_team_id)


# ---------------------------------------------------------------------------
# Record hits (called by cache/proxy service)
# ---------------------------------------------------------------------------

@router.post("/hits", status_code=201)
async def record_hit(
    body: GuardrailHitCreate,
    session: AsyncSession = Depends(get_session),
):
    import json
    result = await session.execute(
        text("""
            INSERT INTO guardrail_hits
                (guardrail_id, guardrail_type, team_id, api_key_id, request_id, model,
                 input_or_output, action_taken, severity, match_count, match_hash,
                 redacted_excerpt, match_offsets,
                 guardrail_version)
            SELECT
                CAST(:guardrail_id AS uuid),
                :guardrail_type,
                :team_id,
                :api_key_id,
                :request_id,
                :model,
                :input_or_output,
                :action_taken,
                :severity,
                :match_count,
                :match_hash,
                :redacted_excerpt,
                CAST(:match_offsets AS jsonb),
                COALESCE((SELECT version FROM guardrails WHERE id = CAST(:guardrail_id AS uuid)), 1)
            RETURNING id
        """),
        {
            "guardrail_id": body.guardrail_id,
            "guardrail_type": body.guardrail_type,
            "team_id": body.team_id,
            "api_key_id": body.api_key_id,
            "request_id": body.request_id,
            "model": body.model,
            "input_or_output": body.input_or_output,
            "action_taken": body.action_taken,
            "severity": body.severity,
            "match_count": body.match_count,
            "match_hash": body.match_hash,
            "redacted_excerpt": body.redacted_excerpt,
            "match_offsets": json.dumps(body.match_offsets or []),
        },
    )
    await session.commit()
    return {"id": str(result.mappings().first()["id"])}
