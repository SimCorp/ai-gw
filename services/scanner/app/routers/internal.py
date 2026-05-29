import json as _json

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_worker_auth
from app.db import get_session

router = APIRouter(prefix="/internal/jobs", tags=["internal"])


class FindingsBatch(BaseModel):
    findings: list[dict]


class CompletePayload(BaseModel):
    status: str
    error_message: str | None = None
    partial_results: bool = False


@router.post("/{job_id}/progress")
async def report_progress(
    job_id: str,
    payload: dict,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    require_worker_auth(request)
    await session.execute(
        text("UPDATE scan_jobs SET worker_id = :worker_id WHERE id = CAST(:id AS uuid)"),
        {"id": job_id, "worker_id": payload.get("worker_id")},
    )
    await session.commit()
    return {"ok": True}


@router.post("/{job_id}/findings")
async def bulk_insert_findings(
    job_id: str,
    payload: FindingsBatch,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    require_worker_auth(request)
    for f in payload.findings:
        evidence = f.get("evidence")
        await session.execute(
            text("""
                INSERT INTO scan_findings
                    (job_id, scanner, severity, category, title, description, evidence, remediation)
                VALUES
                    (CAST(:job_id AS uuid), :scanner, :severity, :category,
                     :title, :description, CAST(:evidence AS jsonb), :remediation)
            """),
            {
                "job_id": job_id,
                "scanner": f["scanner"],
                "severity": f["severity"],
                "category": f["category"],
                "title": f["title"],
                "description": f["description"],
                "evidence": _json.dumps(evidence) if evidence else None,
                "remediation": f.get("remediation"),
            },
        )
    await session.commit()
    return {"inserted": len(payload.findings)}


@router.post("/{job_id}/complete")
async def complete_job(
    job_id: str,
    payload: CompletePayload,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    require_worker_auth(request)
    await session.execute(
        text("""
            UPDATE scan_jobs
            SET status = :status,
                finished_at = NOW(),
                error_message = :error_message,
                partial_results = :partial_results
            WHERE id = CAST(:id AS uuid)
        """),
        {
            "id": job_id,
            "status": payload.status,
            "error_message": payload.error_message,
            "partial_results": payload.partial_results,
        },
    )
    await session.commit()
    return {"ok": True}
