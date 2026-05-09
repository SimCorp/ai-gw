"""
GitHub webhook receiver for developer output tracking.

Receives push/pull_request events from GitHub, correlates the github user
to a developer account, and writes to developer_output_events.

Register this URL (POST /webhooks/github) in your GitHub org/repo settings.
Set the GITHUB_WEBHOOK_SECRET env var to the same secret used in GitHub.
"""
import hashlib
import hmac
import logging
import os

from fastapi import APIRouter, Header, HTTPException, Request

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify_signature(payload: bytes, signature_header: str | None) -> bool:
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        return True  # Signature checking is optional when no secret is configured
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


@router.post("/github", status_code=202)
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
):
    body = await request.body()
    if not _verify_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    import json
    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = x_github_event or "unknown"
    pool = request.app.state.pg_pool

    try:
        if event_type == "push":
            await _handle_push(pool, payload)
        elif event_type == "pull_request":
            await _handle_pull_request(pool, payload)
        elif event_type == "pull_request_review":
            await _handle_review(pool, payload)
    except Exception as exc:
        _log.exception("GitHub webhook handler error: %s", exc)

    return {"accepted": True}


async def _resolve_developer(pool, github_user: str) -> str | None:
    """Try to match github username to a developer by email heuristic or exact match."""
    row = await pool.fetchrow(
        "SELECT id FROM developers WHERE email = $1 OR split_part(email, '@', 1) = $2",
        github_user, github_user,
    )
    return str(row["id"]) if row else None


async def _mark_recent_sessions_with_commit(pool, developer_id: str | None, repo: str) -> None:
    """Mark sessions for this developer that ended within the last 24h as produced_commit=true."""
    if not developer_id:
        return
    try:
        await pool.execute(
            """
            UPDATE sessions SET produced_commit = TRUE
            WHERE developer_id = $1
              AND (repo = $2 OR repo IS NULL)
              AND last_request_at >= NOW() - INTERVAL '24 hours'
              AND (produced_commit IS NULL OR produced_commit = FALSE)
            """,
            developer_id, repo,
        )
    except Exception:
        pass


async def _handle_push(pool, payload: dict) -> None:
    github_user = (payload.get("pusher") or {}).get("name", "unknown")
    repo = (payload.get("repository") or {}).get("full_name", "unknown")
    commits = payload.get("commits") or []
    commit_count = len(commits)
    lines_added = sum(len(c.get("added", [])) for c in commits)
    lines_removed = sum(len(c.get("removed", [])) for c in commits)

    developer_id = await _resolve_developer(pool, github_user)

    import json
    await pool.execute(
        """
        INSERT INTO developer_output_events
            (developer_id, repo, event_type, github_user,
             commit_count, lines_added, lines_removed, raw)
        VALUES ($1, $2, 'push', $3, $4, $5, $6, $7::jsonb)
        """,
        developer_id, repo, github_user,
        commit_count, lines_added, lines_removed,
        json.dumps({"ref": payload.get("ref"), "head_commit": payload.get("head_commit", {}).get("id")}),
    )
    await _mark_recent_sessions_with_commit(pool, developer_id, repo)


async def _handle_pull_request(pool, payload: dict) -> None:
    action = payload.get("action", "")
    if action not in ("opened", "closed"):
        return
    pr = payload.get("pull_request") or {}
    github_user = (pr.get("user") or {}).get("login", "unknown")
    repo = (payload.get("repository") or {}).get("full_name", "unknown")
    pr_number = pr.get("number")
    event_type = "pr_merged" if (action == "closed" and pr.get("merged")) else "pr_opened"
    additions = pr.get("additions", 0)
    deletions = pr.get("deletions", 0)

    developer_id = await _resolve_developer(pool, github_user)

    import json
    await pool.execute(
        """
        INSERT INTO developer_output_events
            (developer_id, repo, event_type, github_user,
             lines_added, lines_removed, pr_number, raw)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
        """,
        developer_id, repo, event_type, github_user,
        additions, deletions, pr_number,
        json.dumps({"title": pr.get("title"), "merged": pr.get("merged")}),
    )
    if pr.get("merged"):
        await _mark_recent_sessions_with_commit(pool, developer_id, repo)


async def _handle_review(pool, payload: dict) -> None:
    review = payload.get("review") or {}
    github_user = (review.get("user") or {}).get("login", "unknown")
    repo = (payload.get("repository") or {}).get("full_name", "unknown")
    pr_number = (payload.get("pull_request") or {}).get("number")

    developer_id = await _resolve_developer(pool, github_user)

    import json
    await pool.execute(
        """
        INSERT INTO developer_output_events
            (developer_id, repo, event_type, github_user, pr_number, raw)
        VALUES ($1, $2, 'review', $3, $4, $5::jsonb)
        """,
        developer_id, repo, github_user, pr_number,
        json.dumps({"state": review.get("state")}),
    )
