"""Workflow event publisher and subscriber, backed by Redis pubsub.

Cross-process: admin publishes run.started/finished, workflow-worker publishes
node.* events, and the SSE handler in admin subscribes for live observability.
The wire taxonomy follows the parent spec:

- workflow.run.started      {run_id, workflow_id, version, team_id, project_id}
- workflow.run.finished     {run_id, status, finished_at}
- workflow.node.started     {run_id, node_id, iteration, agent_id}
- workflow.node.log         {run_id, node_id, line}
- workflow.node.finished    {run_id, node_id, iteration, status, outputs|error}
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


async def publish(redis: Redis, event_kind: str, payload: dict[str, Any]) -> None:
    """Publish to the workflow:events:{run_id} channel.

    Fails silent — observability events must never block the producer.
    """
    rid = payload.get("run_id")
    if not rid:
        _log.warning("workflow event missing run_id: kind=%s", event_kind)
        return
    envelope = {
        "kind": event_kind,
        "ts": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    try:
        await redis.publish(_channel(rid), json.dumps(envelope))
    except Exception as exc:
        _log.warning("workflow event publish failed (%s): %s", event_kind, exc)


async def subscribe(redis: Redis, run_id: uuid.UUID):
    """Async generator yielding event envelopes for one run.

    Caller is responsible for awaiting the generator's aclose() to unsubscribe.
    Usage:
        async for env in subscribe(redis, rid):
            ...
    """
    pubsub = redis.pubsub()
    await pubsub.subscribe(_channel(run_id))
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            data = message.get("data")
            if not data:
                continue
            try:
                yield json.loads(data)
            except json.JSONDecodeError:
                _log.warning("malformed workflow event payload on run %s", run_id)
    finally:
        try:
            await pubsub.unsubscribe(_channel(run_id))
            await pubsub.close()
        except Exception:
            pass


# Convenience wrappers ---------------------------------------------------------

async def run_started(redis: Redis, run_id: uuid.UUID, workflow_id: uuid.UUID, version: int, team_id: uuid.UUID, project_id: uuid.UUID | None) -> None:
    await publish(redis, "workflow.run.started", {
        "run_id": str(run_id),
        "workflow_id": str(workflow_id),
        "version": version,
        "team_id": str(team_id),
        "project_id": str(project_id) if project_id else None,
    })


async def run_finished(redis: Redis, run_id: uuid.UUID, status: str) -> None:
    await publish(redis, "workflow.run.finished", {
        "run_id": str(run_id),
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    })


async def node_started(redis: Redis, run_id: uuid.UUID, node_id: str, iteration: int, agent_id: uuid.UUID | None) -> None:
    await publish(redis, "workflow.node.started", {
        "run_id": str(run_id),
        "node_id": node_id,
        "iteration": iteration,
        "agent_id": str(agent_id) if agent_id else None,
    })


async def node_log(redis: Redis, run_id: uuid.UUID, node_id: str, line: str) -> None:
    await publish(redis, "workflow.node.log", {
        "run_id": str(run_id),
        "node_id": node_id,
        "line": line,
    })


async def node_finished(redis: Redis, run_id: uuid.UUID, node_id: str, iteration: int, status: str, outputs: dict | None = None, error: str | None = None) -> None:
    await publish(redis, "workflow.node.finished", {
        "run_id": str(run_id),
        "node_id": node_id,
        "iteration": iteration,
        "status": status,
        "outputs": outputs,
        "error": error,
    })
