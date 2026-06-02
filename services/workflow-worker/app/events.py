"""Workflow event publisher (worker side) — Redis pubsub.

Mirrors the schema in services/admin/app/events/workflow.py. Worker only
publishes (node.*); the admin service publishes run.* events.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis

_log = logging.getLogger(__name__)


def _channel(run_id: uuid.UUID | str) -> str:
    return f"workflow:events:{run_id}"


async def _publish(redis: Redis, run_id: uuid.UUID, kind: str, payload: dict[str, Any]) -> None:
    envelope = {
        "kind": kind,
        "ts": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    try:
        await redis.publish(_channel(run_id), json.dumps(envelope))
    except Exception as exc:
        _log.warning("publish %s failed: %s", kind, exc)


async def node_started(
    redis: Redis, run_id: uuid.UUID, node_id: str, iteration: int, agent_id: uuid.UUID | None
) -> None:
    await _publish(
        redis,
        run_id,
        "workflow.node.started",
        {
            "run_id": str(run_id),
            "node_id": node_id,
            "iteration": iteration,
            "agent_id": str(agent_id) if agent_id else None,
        },
    )


async def node_log(redis: Redis, run_id: uuid.UUID, node_id: str, line: str) -> None:
    await _publish(
        redis,
        run_id,
        "workflow.node.log",
        {
            "run_id": str(run_id),
            "node_id": node_id,
            "line": line,
        },
    )


async def node_finished(
    redis: Redis,
    run_id: uuid.UUID,
    node_id: str,
    iteration: int,
    status: str,
    outputs: dict | None = None,
    error: str | None = None,
) -> None:
    await _publish(
        redis,
        run_id,
        "workflow.node.finished",
        {
            "run_id": str(run_id),
            "node_id": node_id,
            "iteration": iteration,
            "status": status,
            "outputs": outputs,
            "error": error,
        },
    )


async def run_finished(redis: Redis, run_id: uuid.UUID, status: str) -> None:
    await _publish(
        redis,
        run_id,
        "workflow.run.finished",
        {
            "run_id": str(run_id),
            "status": status,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        },
    )
