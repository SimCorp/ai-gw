"""Agentic workflow runs — read-only status surface.

Proxies the GitHub Actions API to list recent runs of this repo's gh-aw
agentic workflows (the `simcorp-*` workflows under `.github/workflows/`).
Powers the admin-portal "Agentic workflows" page. Read-only.

Requires a GitHub token with `actions:read` on the repo (settings.github_token);
without it the endpoint returns configured=false and an empty list rather than
erroring, so the page degrades gracefully.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Query

from app.config import settings

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/agentic-workflows", tags=["agentic-workflows"])

# gh-aw agentic workflows live in .github/workflows/ and are named simcorp-*.
_WORKFLOW_PATH_PREFIX = ".github/workflows/simcorp-"


def _trim_run(run: dict) -> dict:
    """Reduce a GitHub workflow-run object to the fields the page shows."""
    return {
        "id": run.get("id"),
        "name": run.get("name"),
        "title": run.get("display_title") or run.get("name"),
        "status": run.get("status"),  # queued | in_progress | completed
        "conclusion": run.get("conclusion"),  # success | failure | cancelled | skipped | ...
        "event": run.get("event"),
        "branch": run.get("head_branch"),
        "run_number": run.get("run_number"),
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
        "html_url": run.get("html_url"),
        "path": run.get("path"),
    }


@router.get("/runs")
async def list_runs(limit: int = Query(30, ge=1, le=100)) -> dict:
    """Recent GitHub Actions runs of the agentic (gh-aw) workflows."""
    if not settings.github_token:
        return {
            "configured": False,
            "repo": settings.github_repo,
            "runs": [],
            "summary": {"total": 0, "success": 0, "failure": 0, "other": 0},
            "detail": "Set GITHUB_TOKEN (actions:read) on the admin service to enable.",
        }

    url = f"https://api.github.com/repos/{settings.github_repo}/actions/runs"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {settings.github_token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    # Over-fetch a little, then filter to the agentic workflows by path.
    params = {"per_page": min(100, limit * 3)}
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=headers, params=params, timeout=20)
            r.raise_for_status()
            payload = r.json()
    except Exception as exc:
        _log.warning("agentic-workflows: GitHub API call failed: %s", exc)
        return {
            "configured": True,
            "repo": settings.github_repo,
            "runs": [],
            "summary": {"total": 0, "success": 0, "failure": 0, "other": 0},
            "detail": "Could not reach the GitHub Actions API.",
        }

    runs = [
        _trim_run(run)
        for run in payload.get("workflow_runs", [])
        if str(run.get("path", "")).startswith(_WORKFLOW_PATH_PREFIX)
    ][:limit]

    success = sum(1 for r in runs if r["conclusion"] == "success")
    failure = sum(1 for r in runs if r["conclusion"] in ("failure", "timed_out"))
    summary = {
        "total": len(runs),
        "success": success,
        "failure": failure,
        "other": len(runs) - success - failure,
    }
    return {"configured": True, "repo": settings.github_repo, "runs": runs, "summary": summary}
