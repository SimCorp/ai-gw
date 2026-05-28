import json
from datetime import datetime, timezone, timedelta
import time
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import get_identity
from app.config import settings
from app.db import get_session

router = APIRouter(prefix="/jobs", tags=["jobs"])

_TIER_ORDER = {"quick": 0, "standard": 1, "deep": 2}
_TIER_DURATIONS = {"quick": 5, "standard": 15, "deep": 45}


class JobCreate(BaseModel):
    target_id: str
    scan_types: list[str] | None = None
    tier: str = "quick"
    trigger: str = "manual"
    ci_ref: str | None = None


async def _check_kill_switch(redis) -> None:
    if await redis.get("scanner:disabled"):
        raise HTTPException(status_code=503, detail="Security scanning is temporarily disabled")


async def _load_target(session: AsyncSession, target_id: str, team_id: str) -> dict:
    row = (await session.execute(
        text("""
            SELECT id, team_id, url, status, allowed_scan_types, openapi_spec_url
            FROM scan_targets
            WHERE id = CAST(:id AS uuid) AND team_id = CAST(:team_id AS uuid) AND status = 'approved'
        """),
        {"id": target_id, "team_id": team_id},
    )).mappings().first()
    if not row:
        raise HTTPException(status_code=403, detail="Target not found or not approved for this team")
    return dict(row)


async def _check_quota(redis, session: AsyncSession, team_id: str, tier: str) -> None:
    quota_row = (await session.execute(
        text("SELECT scanner_quota FROM teams WHERE id = CAST(:id AS uuid)"),
        {"id": team_id},
    )).mappings().first()
    quota: dict = quota_row["scanner_quota"] if quota_row else {}
    daily_limit: int = quota.get("daily_limit", 3)
    max_tier: str = quota.get("max_tier", "quick")

    if _TIER_ORDER.get(tier, 0) > _TIER_ORDER.get(max_tier, 0):
        raise HTTPException(
            status_code=403,
            detail=f"Tier '{tier}' not allowed; team quota permits up to '{max_tier}'",
        )

    # Concurrent job limit: max 2 running jobs per team
    running = (await session.execute(
        text("SELECT COUNT(*) AS n FROM scan_jobs WHERE team_id = CAST(:tid AS uuid) AND status = 'running'"),
        {"tid": team_id},
    )).mappings().first()
    if running and running["n"] >= 2:
        raise HTTPException(status_code=429, detail="Concurrent job limit reached (max 2 running jobs per team)")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    counter_key = f"scanner:quota:{team_id}:{today}"
    current = await redis.incr(counter_key)
    if current == 1:
        tomorrow = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0) + timedelta(days=1)
        ttl = int(tomorrow.timestamp() - time.time())
        await redis.expire(counter_key, max(ttl, 1))

    if current > daily_limit:
        await redis.decr(counter_key)
        tomorrow_str = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
        raise HTTPException(
            status_code=429,
            headers={"X-Quota-Resets-At": tomorrow_str},
            detail={
                "error": "quota_exceeded",
                "daily_used": daily_limit,
                "daily_limit": daily_limit,
                "resets_at": tomorrow_str,
            },
        )


@router.post("", status_code=202)
async def submit_job(
    body: JobCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    identity = await get_identity(request)
    team_id: str = identity["team_id"]
    user_id: str = identity.get("user_id") or identity.get("sub") or "unknown"
    redis = request.app.state.redis

    await _check_kill_switch(redis)
    target = await _load_target(session, body.target_id, team_id)
    await _check_quota(redis, session, team_id, body.tier)

    scan_types = body.scan_types or list(target["allowed_scan_types"])
    disallowed = set(scan_types) - set(target["allowed_scan_types"])
    if disallowed:
        raise HTTPException(status_code=403, detail=f"Scan types not allowed for this target: {disallowed}")

    result = await session.execute(
        text("""
            INSERT INTO scan_jobs
                (team_id, target_id, requested_by, scan_types, tier, trigger, ci_ref)
            VALUES
                (CAST(:team_id AS uuid), CAST(:target_id AS uuid), CAST(:user_id AS uuid),
                 CAST(:scan_types AS text[]), :tier, :trigger, :ci_ref)
            RETURNING id
        """),
        {
            "team_id": team_id,
            "target_id": body.target_id,
            "user_id": user_id,
            "scan_types": "{" + ",".join(scan_types) + "}",
            "tier": body.tier,
            "trigger": body.trigger,
            "ci_ref": body.ci_ref,
        },
    )
    await session.commit()
    job_id = str(result.mappings().first()["id"])

    await redis.lpush(settings.scan_job_queue_key, json.dumps({
        "job_id": job_id,
        "target_url": target["url"],
        "openapi_spec_url": target.get("openapi_spec_url"),
        "scan_types": scan_types,
        "tier": body.tier,
        "team_id": team_id,
    }))

    return {
        "job_id": job_id,
        "status": "queued",
        "estimated_duration_minutes": _TIER_DURATIONS.get(body.tier, 5),
    }


@router.get("")
async def list_jobs(
    request: Request,
    team_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    session: AsyncSession = Depends(get_session),
):
    identity = await get_identity(request)
    effective_team_id = team_id or identity["team_id"]
    where_clauses = ["team_id = CAST(:team_id AS uuid)"]
    params: dict[str, Any] = {"team_id": effective_team_id, "limit": limit}
    if status:
        where_clauses.append("status = :status")
        params["status"] = status
    where = "WHERE " + " AND ".join(where_clauses)
    rows = (await session.execute(
        text(f"SELECT * FROM scan_jobs {where} ORDER BY queued_at DESC LIMIT :limit"),
        params,
    )).mappings().all()
    return [dict(r) for r in rows]


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    identity = await get_identity(request)
    row = (await session.execute(
        text("SELECT * FROM scan_jobs WHERE id = CAST(:id AS uuid) AND team_id = CAST(:team_id AS uuid)"),
        {"id": job_id, "team_id": identity["team_id"]},
    )).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return dict(row)


@router.delete("/{job_id}", status_code=204)
async def cancel_job(
    job_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    identity = await get_identity(request)
    result = await session.execute(
        text("""
            UPDATE scan_jobs SET status = 'cancelled', finished_at = NOW()
            WHERE id = CAST(:id AS uuid)
              AND team_id = CAST(:team_id AS uuid)
              AND status IN ('queued', 'running')
            RETURNING id
        """),
        {"id": job_id, "team_id": identity["team_id"]},
    )
    if not result.mappings().first():
        raise HTTPException(status_code=404, detail="Job not found or not cancellable")
    await session.commit()


_SARIF_LEVEL = {"critical": "error", "high": "error", "medium": "warning", "low": "note", "info": "none"}


def _to_sarif(job_id: str, findings: list[dict]) -> dict:
    rules: dict[str, dict] = {}
    results = []
    for f in findings:
        rule_id = f"{f['scanner']}/{f['category']}"
        rules[rule_id] = {
            "id": rule_id,
            "name": f["title"],
            "shortDescription": {"text": f["title"]},
            "fullDescription": {"text": f["description"]},
            "defaultConfiguration": {"level": _SARIF_LEVEL.get(f["severity"], "warning")},
        }
        results.append({
            "ruleId": rule_id,
            "level": _SARIF_LEVEL.get(f["severity"], "warning"),
            "message": {"text": f["description"]},
            "properties": {"severity": f["severity"], "scanner": f["scanner"]},
        })
    return {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [{
            "tool": {"driver": {"name": "ai-gw-scanner", "version": "1.0.0", "rules": list(rules.values())}},
            "results": results,
            "properties": {"jobId": job_id},
        }],
    }


@router.get("/{job_id}/results")
async def get_results(
    job_id: str,
    request: Request,
    severity: str | None = Query(default=None),
    format: str | None = Query(default=None),
    offset: int = Query(default=0),
    limit: int = Query(default=50, le=200),
    session: AsyncSession = Depends(get_session),
):
    identity = await get_identity(request)
    job_row = (await session.execute(
        text("SELECT id, status FROM scan_jobs WHERE id = CAST(:id AS uuid) AND team_id = CAST(:team_id AS uuid)"),
        {"id": job_id, "team_id": identity["team_id"]},
    )).mappings().first()
    if not job_row:
        raise HTTPException(status_code=404, detail="Job not found")

    where_clauses = ["job_id = CAST(:job_id AS uuid)"]
    params: dict[str, Any] = {"job_id": job_id, "limit": limit, "offset": offset}
    if severity:
        where_clauses.append("severity = :severity")
        params["severity"] = severity
    where = "WHERE " + " AND ".join(where_clauses)
    rows = (await session.execute(
        text(f"SELECT * FROM scan_findings {where} ORDER BY severity, created_at LIMIT :limit OFFSET :offset"),
        params,
    )).mappings().all()
    findings = [dict(r) for r in rows]

    if format == "sarif":
        return _to_sarif(job_id, findings)

    total_row = (await session.execute(
        text("SELECT COUNT(*) AS n FROM scan_findings WHERE job_id = CAST(:job_id AS uuid)"),
        {"job_id": job_id},
    )).mappings().first()
    return {"total": total_row["n"] if total_row else 0, "offset": offset, "findings": findings}
