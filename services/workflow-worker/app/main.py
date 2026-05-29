"""workflow-worker main loop.

Polls work_queue with FOR UPDATE SKIP LOCKED, spawns agent containers via
the DockerRuntime port, publishes lifecycle events to Redis pubsub, and
advances the DAG by enqueueing successor nodes when a node completes.

Concurrency is bounded by an asyncio.Semaphore (default 5). Stale claims
(worker crashed mid-execution) are recovered by a background sweeper that
resets expired claim_expires rows.
"""
from __future__ import annotations

import asyncio
import functools
import json
import logging
import signal
import uuid
from typing import Any

import asyncpg
import httpx
from redis.asyncio import Redis

from app.config import Settings
from app.dag import is_terminal, ready_successors, should_loop
from app.dag import node as dag_node
from app.events import node_finished, node_log, node_started, run_finished
from app.runtime import RunResult
from app.runtime.docker import DockerRuntime
from app.runtime.relay import RelayRuntime
from app.sanitizer import sanitize_inputs as _sanitize_inputs
from app.threat_detection import load_patterns_from_admin as _load_threat_patterns
from app.threat_detection import scan_outputs as _scan_outputs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
_log = logging.getLogger("workflow-worker")


# ---------------------------------------------------------------------------
# Queue operations
# ---------------------------------------------------------------------------

async def _claim_one(pool: asyncpg.Pool, worker_id: str, claim_ttl_s: int) -> dict | None:
    """Claim a single work item using SELECT ... FOR UPDATE SKIP LOCKED."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT id, run_id, node_id, iteration
                FROM work_queue
                WHERE claimed_by IS NULL AND available_at <= NOW()
                ORDER BY available_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
            )
            if row is None:
                return None
            await conn.execute(
                """
                UPDATE work_queue
                SET claimed_by = $1, claim_expires = NOW() + ($2 || ' seconds')::interval, attempts = attempts + 1
                WHERE id = $3
                """,
                worker_id, str(claim_ttl_s), row["id"],
            )
            return dict(row)


async def _finalize_node(pool: asyncpg.Pool, queue_id: int, run_id: uuid.UUID, node_id: str, iteration: int, status: str, outputs: dict | None, error: str | None) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                UPDATE run_nodes
                SET status = $4, outputs = $5::jsonb, error = $6, finished_at = NOW()
                WHERE run_id = $1 AND node_id = $2 AND iteration = $3
                """,
                run_id, node_id, iteration, status, json.dumps(outputs) if outputs is not None else None, error,
            )
            await conn.execute("DELETE FROM work_queue WHERE id = $1", queue_id)


async def _mark_node_running(pool: asyncpg.Pool, run_id: uuid.UUID, node_id: str, iteration: int, agent_id: uuid.UUID | None) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE run_nodes
            SET status = 'running', started_at = NOW(), agent_id = $4
            WHERE run_id = $1 AND node_id = $2 AND iteration = $3
            """,
            run_id, node_id, iteration, agent_id,
        )
        await conn.execute(
            "UPDATE workflow_runs SET status = 'running', started_at = COALESCE(started_at, NOW()) WHERE id = $1 AND status = 'pending'",
            run_id,
        )


async def _fetch_run_context(pool: asyncpg.Pool, run_id: uuid.UUID) -> dict | None:
    """Return the DAG + scoped API key + project/team for one run."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT wr.team_id, wr.project_id, wr.scoped_api_key_id, wr.status,
                   wv.dag,
                   ak.key_hash IS NOT NULL AS has_key
            FROM workflow_runs wr
            JOIN workflow_versions wv ON wv.workflow_id = wr.workflow_id AND wv.version = wr.version
            LEFT JOIN api_keys ak ON ak.id = wr.scoped_api_key_id AND ak.revoked_at IS NULL
            WHERE wr.id = $1
            """,
            run_id,
        )
        return dict(row) if row else None


async def _resolve_agent(pool: asyncpg.Pool, agent_slug: str) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, image, manifest FROM agents WHERE slug = $1 AND enabled = TRUE",
            agent_slug,
        )
        return dict(row) if row else None


async def _enqueue_successor(pool: asyncpg.Pool, run_id: uuid.UUID, node_id: str) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO run_nodes (run_id, node_id, iteration, status) VALUES ($1, $2, 0, 'pending') ON CONFLICT DO NOTHING",
                run_id, node_id,
            )
            await conn.execute(
                "INSERT INTO work_queue (run_id, node_id) VALUES ($1, $2)",
                run_id, node_id,
            )


async def _enqueue_loop_iteration(pool: asyncpg.Pool, run_id: uuid.UUID, node_id: str, iteration: int) -> None:
    """Re-enqueue the same node for the next loop iteration."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO run_nodes (run_id, node_id, iteration, status) VALUES ($1, $2, $3, 'pending') ON CONFLICT DO NOTHING",
                run_id, node_id, iteration,
            )
            await conn.execute(
                "INSERT INTO work_queue (run_id, node_id, iteration) VALUES ($1, $2, $3)",
                run_id, node_id, iteration,
            )


async def _cleanup_run_key(redis: Redis, run_id: uuid.UUID) -> None:
    try:
        await redis.delete(f"workflow:scoped_key:{run_id}")
    except Exception:
        pass


async def _mark_run_finished(pool: asyncpg.Pool, run_id: uuid.UUID, status: str, outputs: dict | None = None, error: str | None = None) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE workflow_runs
            SET status = $2, finished_at = NOW(), outputs = $3::jsonb, error = $4
            WHERE id = $1
            """,
            run_id, status, json.dumps(outputs) if outputs is not None else None, error,
        )
        # Revoke the scoped key
        await conn.execute(
            """
            UPDATE api_keys SET revoked_at = NOW()
            WHERE id = (SELECT scoped_api_key_id FROM workflow_runs WHERE id = $1)
              AND revoked_at IS NULL
            """,
            run_id,
        )


async def _run_node_state(pool: asyncpg.Pool, run_id: uuid.UUID) -> dict[str, str]:
    """Snapshot run_nodes' statuses by node_id (iteration 0)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT node_id, status FROM run_nodes WHERE run_id = $1 AND iteration = 0",
            run_id,
        )
    return {r["node_id"]: r["status"] for r in rows}


# ---------------------------------------------------------------------------
# Sweeper — reclaim stale claims
# ---------------------------------------------------------------------------

async def _sweeper_loop(pool: asyncpg.Pool, interval_s: float, stop: asyncio.Event, redis: Redis | None = None) -> None:
    while not stop.is_set():
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    # Collect run_ids before resetting so we can purge their
                    # plaintext scoped keys from Redis — a crashed worker would
                    # otherwise leave those keys in Redis for up to 61 minutes.
                    stale_rows = await conn.fetch(
                        """
                        SELECT run_id FROM work_queue
                        WHERE claimed_by IS NOT NULL AND claim_expires < NOW()
                        """,
                    )
                    if stale_rows:
                        n = await conn.execute(
                            """
                            UPDATE work_queue
                            SET claimed_by = NULL, claim_expires = NULL
                            WHERE claimed_by IS NOT NULL AND claim_expires < NOW()
                            """,
                        )
                        _log.info("sweeper reclaimed: %s", n)
                        if redis is not None:
                            for row in stale_rows:
                                try:
                                    await redis.delete(f"workflow:scoped_key:{row['run_id']}")
                                except Exception as exc:
                                    _log.warning("sweeper redis cleanup error run_id=%s: %s", row["run_id"], exc)
        except Exception as exc:
            _log.warning("sweeper error: %s", exc)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_s)
        except asyncio.TimeoutError:
            pass


# ---------------------------------------------------------------------------
# Per-job handler
# ---------------------------------------------------------------------------

async def _handle_job(
    *,
    job: dict,
    pool: asyncpg.Pool,
    redis: Redis,
    runtime: DockerRuntime,
    cache_base_url: str,
    relay_url: str,
    relay_secret: str,
    admin_url: str,
    admin_internal_token: str,
) -> None:
    run_id: uuid.UUID = job["run_id"]
    node_id: str = job["node_id"]
    iteration: int = job["iteration"]
    queue_id: int = job["id"]

    ctx = await _fetch_run_context(pool, run_id)
    if ctx is None or ctx["status"] == "cancelled":
        _log.info("skipping run=%s (cancelled or missing)", run_id)
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM work_queue WHERE id = $1", queue_id)
        return

    dag = ctx["dag"] if isinstance(ctx["dag"], dict) else json.loads(ctx["dag"])
    nspec = dag_node(dag, node_id)
    if nspec is None:
        await _finalize_node(pool, queue_id, run_id, node_id, iteration, "failed", None, f"node {node_id} not in DAG")
        await node_finished(redis, run_id, node_id, iteration, "failed", error=f"node {node_id} not in DAG")
        await _mark_run_finished(pool, run_id, "failed", error=f"node {node_id} not in DAG")
        await run_finished(redis, run_id, "failed")
        await _cleanup_run_key(redis, run_id)
        return

    agent_slug = nspec.get("agent_slug")
    agent = await _resolve_agent(pool, agent_slug) if agent_slug else None
    if agent is None:
        msg = f"agent {agent_slug!r} not found or disabled"
        await _finalize_node(pool, queue_id, run_id, node_id, iteration, "failed", None, msg)
        await node_finished(redis, run_id, node_id, iteration, "failed", error=msg)
        await _mark_run_finished(pool, run_id, "failed", error=msg)
        await run_finished(redis, run_id, "failed")
        await _cleanup_run_key(redis, run_id)
        return

    # Collect inputs: defaults from node, override with predecessor outputs and run inputs
    inputs: dict[str, Any] = dict(nspec.get("inputs") or {})
    # If this is the entry node, merge run-level inputs
    if node_id == dag.get("entry_node"):
        async with pool.acquire() as conn:
            run_inputs = await conn.fetchval("SELECT inputs FROM workflow_runs WHERE id = $1", run_id)
        if run_inputs:
            inputs.update(run_inputs if isinstance(run_inputs, dict) else json.loads(run_inputs))
    # Merge predecessor outputs (linear v0.1: one predecessor)
    pred_outputs: dict[str, Any] = {}
    async with pool.acquire() as conn:
        pred_rows = await conn.fetch(
            """
            SELECT node_id, outputs FROM run_nodes
            WHERE run_id = $1 AND node_id IN (
                SELECT 'x' FROM (SELECT 1) z WHERE FALSE  -- placeholder; filled below
            )
            """,
            run_id,
        )
    # Build the predecessor list from the DAG
    pred_ids = [e["from"] for e in dag.get("edges", []) if e.get("to") == node_id]
    if pred_ids:
        async with pool.acquire() as conn:
            pred_rows = await conn.fetch(
                "SELECT node_id, outputs FROM run_nodes WHERE run_id = $1 AND node_id = ANY($2)",
                run_id, pred_ids,
            )
        for pr in pred_rows:
            if pr["outputs"]:
                out = pr["outputs"] if isinstance(pr["outputs"], dict) else json.loads(pr["outputs"])
                pred_outputs[pr["node_id"]] = out
    if pred_outputs:
        inputs["_predecessors"] = pred_outputs

    # Sanitize inputs before writing inputs.json — strips @mentions, HTML tags,
    # enforces size/key-count limits, preventing prompt injection via DAG inputs.
    inputs = _sanitize_inputs(inputs)

    # Retrieve the plaintext scoped API key from Redis. Admin stored it there
    # during run submission (workflow:scoped_key:{run_id}) so the worker can
    # inject it into each agent container as AIGW_API_KEY.
    scoped_key = ""
    try:
        scoped_key = await redis.get(f"workflow:scoped_key:{run_id}") or ""
    except Exception as exc:
        _log.warning("could not read scoped key for run %s: %s", run_id, exc)

    env = {
        "AIGW_RUN_ID": str(run_id),
        "AIGW_NODE_ID": node_id,
        "AIGW_BASE_URL": cache_base_url,
        "AIGW_API_KEY": scoped_key,
    }

    # Mark running + publish event
    await _mark_node_running(pool, run_id, node_id, iteration, agent["id"])
    await node_started(redis, run_id, node_id, iteration, agent["id"])

    # Choose runtime: RelayRuntime for relay:// agents, DockerRuntime otherwise
    image: str = agent["image"]
    active_runtime: DockerRuntime | RelayRuntime = (
        RelayRuntime(relay_url, relay_secret=relay_secret) if image.startswith("relay://") else runtime
    )

    on_log = functools.partial(_forward_log, redis, run_id, node_id)
    try:
        result = await active_runtime.run(
            image=image,
            env=env,
            inputs=inputs,
            run_id=str(run_id),
            node_id=node_id,
            timeout_s=300.0,
            on_log=on_log,
        )
    except asyncio.TimeoutError:
        await _finalize_node(pool, queue_id, run_id, node_id, iteration, "failed", None, "timeout")
        await node_finished(redis, run_id, node_id, iteration, "failed", error="timeout")
        await _mark_run_finished(pool, run_id, "failed", error="timeout")
        await run_finished(redis, run_id, "failed")
        await _cleanup_run_key(redis, run_id)
        return
    except Exception as exc:
        msg = f"runtime error: {exc}"
        await _finalize_node(pool, queue_id, run_id, node_id, iteration, "failed", None, msg)
        await node_finished(redis, run_id, node_id, iteration, "failed", error=msg)
        await _mark_run_finished(pool, run_id, "failed", error=msg)
        await run_finished(redis, run_id, "failed")
        await _cleanup_run_key(redis, run_id)
        return

    if result.exit_code != 0:
        msg = f"exit code {result.exit_code}"
        await _finalize_node(pool, queue_id, run_id, node_id, iteration, "failed", None, msg)
        await node_finished(redis, run_id, node_id, iteration, "failed", error=msg)
        await _mark_run_finished(pool, run_id, "failed", error=msg)
        await run_finished(redis, run_id, "failed")
        await _cleanup_run_key(redis, run_id)
        return

    # Redact scoped API keys and known secrets from outputs before DB persistence.
    result = RunResult(
        exit_code=result.exit_code,
        outputs=_redact_outputs(result.outputs or {}),
        stdout_tail=result.stdout_tail,
    )

    # Threat detection on agent outputs — block propagation if threats found.
    clean, findings = _scan_outputs(result.outputs or {})
    if not clean:
        msg = f"threat-detection-blocked: {findings[0]}"
        await _finalize_node(pool, queue_id, run_id, node_id, iteration, "failed", None, msg)
        await node_finished(redis, run_id, node_id, iteration, "failed", error=msg)
        await _mark_run_finished(pool, run_id, "failed", error=msg)
        await run_finished(redis, run_id, "failed")
        await _cleanup_run_key(redis, run_id)
        return

    await _finalize_node(pool, queue_id, run_id, node_id, iteration, "succeeded", result.outputs, None)
    await node_finished(redis, run_id, node_id, iteration, "succeeded", outputs=result.outputs)

    outputs = result.outputs or {}

    # Autonomous agent: fire-and-forget sub-workflow spawn if _spawn key present
    spawn_payload = outputs.get("_spawn")
    if spawn_payload and isinstance(spawn_payload, dict):
        asyncio.create_task(_fire_spawn(admin_url, spawn_payload, ctx["team_id"], admin_internal_token))

    # Loop check: re-enqueue same node if loop condition met
    if should_loop(nspec, outputs, iteration):
        await _enqueue_loop_iteration(pool, run_id, node_id, iteration + 1)
        return

    # Advance DAG: enqueue successors whose predecessors are all succeeded
    # and whose edge conditions are satisfied by this node's outputs.
    state = await _run_node_state(pool, run_id)
    next_nodes = ready_successors(dag, node_id, state, outputs=outputs)
    if next_nodes:
        for nxt in next_nodes:
            await _enqueue_successor(pool, run_id, nxt)
    elif is_terminal(dag, node_id):
        # No successors: run is complete when all nodes have succeeded
        all_done = all(
            state.get(n["id"]) == "succeeded"
            for n in dag.get("nodes", [])
            if n.get("id") in state
        )
        if all_done:
            await _mark_run_finished(pool, run_id, "succeeded", outputs=result.outputs)
            await run_finished(redis, run_id, "succeeded")
            try:
                await redis.delete(f"workflow:scoped_key:{run_id}")
            except Exception:
                pass


async def _fire_spawn(admin_url: str, spawn_payload: dict, team_id: str, admin_internal_token: str) -> None:
    """Fire-and-forget: POST sub-workflow spawn to admin service.

    Restricts spawn_payload to only allowed fields (workflow_id, version, inputs)
    and injects the parent run's team_id. Sends Authorization header if configured.
    """
    # Strip any fields the agent should not be able to control — only allow
    # workflow_id, version, and inputs from the agent-supplied payload.
    _ALLOWED_SPAWN_FIELDS = {"workflow_id", "version", "inputs"}
    safe_payload = {k: v for k, v in spawn_payload.items() if k in _ALLOWED_SPAWN_FIELDS}
    # Inject authoritative values from the parent run so the agent cannot
    # escalate privileges by supplying team_id or triggered_by.
    safe_payload["team_id"] = str(team_id) if team_id is not None else None
    safe_payload["triggered_by"] = "workflow-worker-spawn"
    safe_payload["triggered_by_kind"] = "system"

    headers: dict[str, str] = {}
    if admin_internal_token:
        headers["Authorization"] = f"Bearer {admin_internal_token}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{admin_url.rstrip('/')}/runs",
                json=safe_payload,
                headers=headers,
                timeout=10.0,
            )
        if not resp.is_success:
            _log.warning("sub-workflow spawn failed (%s): %s", resp.status_code, resp.text[:200])
        else:
            _log.info("sub-workflow spawned: %s", safe_payload.get("workflow_id"))
    except Exception as exc:
        _log.warning("sub-workflow spawn error: %s", exc)


def _redact_outputs(outputs: dict) -> dict:
    """Redact any scoped API keys or known secrets from outputs before DB persistence."""
    import re
    SECRET_RE = re.compile(r'aigw_run_[A-Za-z0-9_\-]{20,}')

    def _redact_value(v):
        if isinstance(v, str):
            return SECRET_RE.sub('[REDACTED]', v)
        elif isinstance(v, dict):
            return {k: _redact_value(val) for k, val in v.items()}
        elif isinstance(v, list):
            return [_redact_value(item) for item in v]
        return v

    return _redact_value(outputs)


async def _forward_log(redis: Redis, run_id: uuid.UUID, node_id: str, line: str) -> None:
    # Sample log lines so we don't flood the bus
    try:
        await node_log(redis, run_id, node_id, line[:1000])
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def _main() -> None:
    cfg = Settings.from_env()
    _runtime_label = (
        cfg.agent_runtime if cfg.agent_runtime != "kubernetes" else "kubernetes (not yet configured)"
    )
    _log.info(
        "workflow-worker starting (id=%s concurrency=%d runtime=%s)",
        cfg.worker_id, cfg.concurrency, _runtime_label,
    )

    pool = await asyncpg.create_pool(cfg.database_url, min_size=2, max_size=10)
    redis = Redis.from_url(cfg.redis_url, decode_responses=True)
    runtime = DockerRuntime(
        host_runs_path=cfg.host_runs_path,
        worker_runs_path="/worker-runs",  # bind-mounted to host_runs_path
        container_network=cfg.container_network,
    )
    cache_base_url = "http://cache:8002"
    relay_url = cfg.relay_url
    relay_secret = cfg.relay_secret
    admin_url = cfg.admin_url
    admin_internal_token = cfg.admin_internal_token

    stop_event = asyncio.Event()
    sem = asyncio.Semaphore(cfg.concurrency)

    def _signal(_signo, _frame):
        _log.info("shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _signal)

    # Load threat-detection patterns from admin service on startup.
    # Fail-open: defaults are compiled inside load_patterns_from_admin even if
    # the admin service is unreachable.
    await _load_threat_patterns(admin_url)

    sweeper = asyncio.create_task(_sweeper_loop(pool, cfg.sweeper_interval_s, stop_event, redis))

    async def _worker_for(job: dict) -> None:
        async with sem:
            try:
                await _handle_job(
                    job=job,
                    pool=pool,
                    redis=redis,
                    runtime=runtime,
                    cache_base_url=cache_base_url,
                    relay_url=relay_url,
                    relay_secret=relay_secret,
                    admin_url=admin_url,
                    admin_internal_token=admin_internal_token,
                )
            except Exception as exc:
                _log.exception("unhandled error in job handler: %s", exc)

    in_flight: set[asyncio.Task] = set()
    try:
        while not stop_event.is_set():
            # Don't overflow concurrency
            if sem.locked():
                await asyncio.sleep(0.1)
                continue
            job = await _claim_one(pool, cfg.worker_id, cfg.claim_ttl_s)
            if job is None:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=cfg.poll_interval_s)
                except asyncio.TimeoutError:
                    pass
                continue
            t = asyncio.create_task(_worker_for(job))
            in_flight.add(t)
            t.add_done_callback(in_flight.discard)
    finally:
        _log.info("draining %d in-flight jobs", len(in_flight))
        if in_flight:
            await asyncio.gather(*in_flight, return_exceptions=True)
        sweeper.cancel()
        try:
            await sweeper
        except asyncio.CancelledError:
            pass
        await runtime.close()
        await redis.aclose()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(_main())
