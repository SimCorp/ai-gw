"""Workflow Designer v0.1 admin routes.

Three groups under one module for v0.1 simplicity (each can split later):
- /agents          T5  registry of agent images
- /workflows       T5  workflow definitions and versioned DAGs
- /runs            T6  submit / fetch / cancel runs (rate-limited per team)
- /runs/{id}/stream T7  SSE firehose of workflow events for a single run
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_auth
from app.db import get_session
from app.api_keys import delete_scoped_key_from_redis, issue_scoped_key, revoke_key
from app.events import workflow as wf_events

_log = logging.getLogger(__name__)
router = APIRouter(tags=["workflow-designer"])


# =============================================================================
# /agents — T5
# =============================================================================

class AgentCreateBody(BaseModel):
    slug: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str
    description: str | None = None
    image: str
    manifest: dict[str, Any] = Field(default_factory=dict)
    category: str | None = None
    managed: bool = False
    owner_team_id: str | None = None
    owner_project_id: str | None = None


@router.get("/agents")
async def list_agents(
    category: str | None = None,
    session: AsyncSession = Depends(get_session),
    _auth: dict = Depends(require_admin_auth),
) -> dict:
    query = "SELECT id, slug, name, description, image, manifest, category, managed, enabled FROM agents WHERE enabled = TRUE"
    params: dict[str, Any] = {}
    if category:
        query += " AND category = :category"
        params["category"] = category
    query += " ORDER BY name"
    rows = (await session.execute(text(query), params)).mappings().all()
    return {"agents": [dict(r) | {"id": str(r["id"])} for r in rows]}


@router.post("/agents", status_code=201)
async def create_agent(
    body: AgentCreateBody,
    session: AsyncSession = Depends(get_session),
    _auth: dict = Depends(require_admin_auth),
) -> dict:
    row = (await session.execute(
        text(
            """
            INSERT INTO agents (slug, name, description, image, manifest, category, managed,
                                owner_team_id, owner_project_id)
            VALUES (:slug, :name, :description, :image, CAST(:manifest AS jsonb), :category, :managed,
                    :owner_team_id, :owner_project_id)
            ON CONFLICT (slug) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                image = EXCLUDED.image,
                manifest = EXCLUDED.manifest,
                category = EXCLUDED.category,
                managed = EXCLUDED.managed,
                updated_at = NOW()
            RETURNING id
            """
        ),
        {
            "slug": body.slug,
            "name": body.name,
            "description": body.description,
            "image": body.image,
            "manifest": json.dumps(body.manifest),
            "category": body.category,
            "managed": body.managed,
            "owner_team_id": body.owner_team_id,
            "owner_project_id": body.owner_project_id,
        },
    )).first()
    await session.commit()
    return {"id": str(row[0]), "slug": body.slug}


# =============================================================================
# /workflows — T5
# =============================================================================

class WorkflowCreateBody(BaseModel):
    slug: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str
    description: str | None = None
    team_id: str
    project_id: str | None = None


class WorkflowVersionBody(BaseModel):
    dag: dict[str, Any]
    created_by: str  # user/api-key UUID for audit


@router.get("/workflows")
async def list_workflows(
    team_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    _auth: dict = Depends(require_admin_auth),
) -> dict:
    query = "SELECT id, slug, team_id, project_id, name, description, latest_version, created_at FROM workflows"
    params: dict[str, Any] = {}
    if team_id:
        query += " WHERE team_id = :team_id"
        params["team_id"] = team_id
    query += " ORDER BY created_at DESC"
    rows = (await session.execute(text(query), params)).mappings().all()
    return {
        "workflows": [
            {
                **dict(r),
                "id": str(r["id"]),
                "team_id": str(r["team_id"]),
                "project_id": str(r["project_id"]) if r["project_id"] else None,
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]
    }


@router.post("/workflows", status_code=201)
async def create_workflow(
    body: WorkflowCreateBody,
    session: AsyncSession = Depends(get_session),
    _auth: dict = Depends(require_admin_auth),
) -> dict:
    row = (await session.execute(
        text(
            """
            INSERT INTO workflows (slug, team_id, project_id, name, description)
            VALUES (:slug, :team_id, :project_id, :name, :description)
            RETURNING id
            """
        ),
        body.model_dump(),
    )).first()
    await session.commit()
    return {"id": str(row[0]), "slug": body.slug}


@router.post("/workflows/{workflow_id}/versions", status_code=201)
async def create_workflow_version(
    workflow_id: str,
    body: WorkflowVersionBody,
    session: AsyncSession = Depends(get_session),
    _auth: dict = Depends(require_admin_auth),
) -> dict:
    # Validate DAG basics: nodes is a list, edges is a list, entry_node is set
    dag = body.dag
    if not isinstance(dag.get("nodes"), list) or not dag["nodes"]:
        raise HTTPException(422, "DAG must have a non-empty 'nodes' list")
    if not isinstance(dag.get("edges"), list):
        raise HTTPException(422, "DAG must have an 'edges' list (may be empty)")
    if "entry_node" not in dag:
        raise HTTPException(422, "DAG must declare 'entry_node'")
    node_ids = {n.get("id") for n in dag["nodes"] if isinstance(n, dict)}
    if dag["entry_node"] not in node_ids:
        raise HTTPException(422, "entry_node not found in nodes")

    # Append new version; bump latest_version atomically
    new_version = (await session.execute(
        text(
            """
            UPDATE workflows
            SET latest_version = latest_version + 1
            WHERE id = :wid
            RETURNING latest_version
            """
        ),
        {"wid": workflow_id},
    )).scalar_one_or_none()
    if new_version is None:
        raise HTTPException(404, "workflow not found")

    await session.execute(
        text(
            """
            INSERT INTO workflow_versions (workflow_id, version, dag, created_by)
            VALUES (:wid, :v, CAST(:dag AS jsonb), :created_by)
            """
        ),
        {
            "wid": workflow_id,
            "v": new_version,
            "dag": json.dumps(dag),
            "created_by": body.created_by,
        },
    )
    await session.commit()
    return {"workflow_id": workflow_id, "version": new_version}


@router.get("/workflows/{workflow_id}/versions/{version}")
async def get_workflow_version(
    workflow_id: str,
    version: int,
    session: AsyncSession = Depends(get_session),
    _auth: dict = Depends(require_admin_auth),
) -> dict:
    row = (await session.execute(
        text("SELECT dag, created_by, created_at FROM workflow_versions WHERE workflow_id = :wid AND version = :v"),
        {"wid": workflow_id, "v": version},
    )).first()
    if row is None:
        raise HTTPException(404, "workflow version not found")
    return {
        "workflow_id": workflow_id,
        "version": version,
        "dag": row[0],
        "created_by": str(row[1]),
        "created_at": row[2].isoformat() if row[2] else None,
    }


# =============================================================================
# /runs — T6
# =============================================================================

class RunSubmitBody(BaseModel):
    workflow_id: str
    version: int | None = None  # default: latest
    inputs: dict[str, Any] = Field(default_factory=dict)
    # v0.1: caller specifies these explicitly. Future iteration derives from auth context.
    team_id: str
    project_id: str | None = None
    triggered_by: str  # uuid of user or api_key
    triggered_by_kind: str = Field(default="user", pattern=r"^(user|api_key)$")


async def _check_run_rate_limit(redis, team_id: str, limit: int = 100, window_s: int = 3600) -> None:
    """Redis-counter rate limit: N runs per team per window. Fail open on Redis errors."""
    if redis is None:
        return
    key = f"workflow_runs:rate:{team_id}"
    try:
        async with redis.pipeline(transaction=True) as pipe:
            await pipe.watch(key)
            pipe.multi()
            pipe.incr(key)
            pipe.expire(key, window_s, nx=True)
            results = await pipe.execute()
        count = results[0]
        if count > limit:
            raise HTTPException(
                status_code=429,
                detail="Run rate limit exceeded for this team",
                headers={"Retry-After": str(window_s)},
            )
    except HTTPException:
        raise
    except Exception as exc:
        _log.warning("run rate limiter Redis error (fail-open): %s", exc)


@router.post("/runs", status_code=201)
async def submit_run(
    body: RunSubmitBody,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _auth: dict = Depends(require_admin_auth),
) -> dict:
    redis = getattr(request.app.state, "redis", None)
    await _check_run_rate_limit(redis, body.team_id)

    # Resolve workflow + version
    if body.version is None:
        wf = (await session.execute(
            text("SELECT latest_version FROM workflows WHERE id = :wid"),
            {"wid": body.workflow_id},
        )).scalar_one_or_none()
        if wf is None:
            raise HTTPException(404, "workflow not found")
        version = wf
    else:
        version = body.version

    dag_row = (await session.execute(
        text("SELECT dag FROM workflow_versions WHERE workflow_id = :wid AND version = :v"),
        {"wid": body.workflow_id, "v": version},
    )).scalar_one_or_none()
    if dag_row is None:
        raise HTTPException(404, "workflow version not found")
    dag = dag_row

    # Pre-generate run_id so we can tie the scoped key to it in Redis
    run_id_val = uuid.uuid4()

    # Issue a scoped API key; plaintext stored in Redis so the worker can
    # inject it as AIGW_API_KEY when launching agent containers.
    plaintext_key, key_id = await issue_scoped_key(
        session,
        team_id=uuid.UUID(body.team_id),
        project_id=uuid.UUID(body.project_id) if body.project_id else None,
        name=f"workflow-run:{body.workflow_id}",
        ttl_seconds=3600,
        run_id=run_id_val,
        redis=redis,
    )

    # Insert the run row using the pre-generated id
    run_id = (await session.execute(
        text(
            """
            INSERT INTO workflow_runs (id, workflow_id, version, status, inputs, triggered_by, triggered_by_kind,
                                       team_id, project_id, scoped_api_key_id)
            VALUES (:id, :wid, :v, 'pending', CAST(:inputs AS jsonb), :tb, :tbk, :team, :project, :key_id)
            RETURNING id
            """
        ),
        {
            "id": run_id_val,
            "wid": body.workflow_id,
            "v": version,
            "inputs": json.dumps(body.inputs),
            "tb": body.triggered_by,
            "tbk": body.triggered_by_kind,
            "team": body.team_id,
            "project": body.project_id,
            "key_id": key_id,
        },
    )).scalar_one()

    # Enqueue the entry node
    entry_node = dag.get("entry_node")
    await session.execute(
        text(
            """
            INSERT INTO work_queue (run_id, node_id)
            VALUES (:rid, :nid)
            """
        ),
        {"rid": run_id, "nid": entry_node},
    )
    await session.execute(
        text(
            """
            INSERT INTO run_nodes (run_id, node_id, iteration, status)
            VALUES (:rid, :nid, 0, 'pending')
            """
        ),
        {"rid": run_id, "nid": entry_node},
    )
    await session.commit()

    # Publish run.started — best-effort
    if redis is not None:
        try:
            await wf_events.run_started(redis, run_id, uuid.UUID(body.workflow_id), version,
                                        uuid.UUID(body.team_id),
                                        uuid.UUID(body.project_id) if body.project_id else None)
        except Exception as exc:
            _log.warning("run.started publish failed: %s", exc)

    return {
        "id": str(run_id),
        "scoped_api_key": plaintext_key,  # returned once; persisted only as hash
    }


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    _auth: dict = Depends(require_admin_auth),
) -> dict:
    run = (await session.execute(
        text(
            """
            SELECT id, workflow_id, version, status, inputs, outputs, error,
                   triggered_by, triggered_by_kind, team_id, project_id,
                   started_at, finished_at, created_at
            FROM workflow_runs WHERE id = :rid
            """
        ),
        {"rid": run_id},
    )).mappings().first()
    if run is None:
        raise HTTPException(404, "run not found")

    nodes = (await session.execute(
        text(
            """
            SELECT node_id, iteration, status, agent_id, inputs, outputs, error,
                   started_at, finished_at
            FROM run_nodes WHERE run_id = :rid
            ORDER BY started_at NULLS LAST, node_id
            """
        ),
        {"rid": run_id},
    )).mappings().all()

    def _stringify(row: dict) -> dict:
        out = dict(row)
        for k in ("id", "workflow_id", "team_id", "project_id", "triggered_by", "agent_id"):
            if k in out and out[k] is not None:
                out[k] = str(out[k])
        for k in ("started_at", "finished_at", "created_at"):
            if k in out and out[k] is not None:
                out[k] = out[k].isoformat()
        return out

    return {
        "run": _stringify(dict(run)),
        "nodes": [_stringify(dict(n)) for n in nodes],
    }


@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    request: Request = None,
    _auth: dict = Depends(require_admin_auth),
) -> dict:
    # Set status to cancelled and revoke the scoped key
    row = (await session.execute(
        text(
            """
            UPDATE workflow_runs
            SET status = 'cancelled', finished_at = NOW()
            WHERE id = :rid AND status IN ('pending', 'running')
            RETURNING scoped_api_key_id
            """
        ),
        {"rid": run_id},
    )).first()
    if row is None:
        raise HTTPException(409, "run is not cancellable (already finished or not found)")
    if row[0]:
        await revoke_key(session, row[0])
    await session.commit()

    redis = getattr(request.app.state, "redis", None) if request else None
    if redis is not None:
        try:
            await wf_events.run_finished(redis, uuid.UUID(run_id), "cancelled")
        except Exception:
            pass
        await delete_scoped_key_from_redis(redis, uuid.UUID(run_id))
    return {"status": "cancelled"}


# =============================================================================
# /runs/{id}/stream — T7 (SSE)
# =============================================================================

@router.get("/runs/{run_id}/stream")
async def stream_run_events(
    run_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _auth: dict = Depends(require_admin_auth),
):
    """SSE firehose for one run.

    Sends an initial 'snapshot' event from the database, then live events from
    Redis pubsub. Heartbeats every 15s to keep proxies happy.
    """
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(503, "Redis unavailable; SSE disabled")

    try:
        rid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(422, "invalid run_id")

    # Initial snapshot
    run = (await session.execute(
        text("SELECT status FROM workflow_runs WHERE id = :rid"),
        {"rid": run_id},
    )).first()
    if run is None:
        raise HTTPException(404, "run not found")

    async def _generator():
        # Backfill: current run state + nodes
        nodes = (await session.execute(
            text("SELECT node_id, iteration, status FROM run_nodes WHERE run_id = :rid"),
            {"rid": run_id},
        )).mappings().all()
        snap = {
            "kind": "snapshot",
            "ts": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "run_id": run_id,
                "status": run[0],
                "nodes": [dict(n) for n in nodes],
            },
        }
        yield f"event: snapshot\ndata: {json.dumps(snap)}\n\n"

        # Live events + heartbeats
        last_heartbeat = asyncio.get_event_loop().time()
        async for envelope in wf_events.subscribe(redis, rid):
            kind = envelope.get("kind", "message")
            yield f"event: {kind}\ndata: {json.dumps(envelope)}\n\n"
            # Stop if we just saw run.finished
            if kind == "workflow.run.finished":
                break
            now = asyncio.get_event_loop().time()
            if now - last_heartbeat > 15:
                yield ": heartbeat\n\n"
                last_heartbeat = now

    return StreamingResponse(_generator(), media_type="text/event-stream")
