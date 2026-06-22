"""Build worker — runs as its own container (`python -m app.worker`).

Isolated from the API so a heavy extraction (large repo / Whisper) that pressures
memory is OOM-killed in its own cgroup without taking the query API down. Polls
Postgres for queued builds, runs them serially (concurrency 1 in V1), and records
the outcome.
"""

from __future__ import annotations

import asyncio
import logging

from app import builder, db
from app.config import settings
from app.logging_config import init_logging

_log = logging.getLogger(__name__)


async def _process_one(pool) -> bool:
    """Claim and run one build. Returns True if a build was processed."""
    job = await db.claim_next_build(pool, settings.worker_id)
    if job is None:
        return False

    _log.info("Claimed build id=%s repo=%s", job["id"], job["repo_name"])
    try:
        result = await builder.run_build(job["repo_name"], job["github_url"], job["ref"])
    except Exception as exc:
        _log.exception("Build crashed repo=%s", job["repo_name"])
        result = {
            "succeeded": False,
            "log_tail": "",
            "error": f"worker exception: {exc}",
            "nodes": None,
            "edges": None,
            "last_commit": None,
        }

    await db.finish_build(
        pool,
        build_id=job["id"],
        repo_id=job["repo_id"],
        succeeded=result["succeeded"],
        log_tail=result["log_tail"],
        error=result["error"],
        nodes=result["nodes"],
        edges=result["edges"],
        last_commit=result["last_commit"],
    )
    return True


async def main() -> None:
    init_logging("graphify-worker")
    pool = await db.create_pool()
    await db.bootstrap_schema(pool)
    _log.info("graphify worker %s started", settings.worker_id)

    try:
        while True:
            try:
                processed = await _process_one(pool)
            except Exception:
                _log.exception("Build loop iteration failed")
                processed = False
            # Back off only when idle; if we just built, immediately check for more.
            if not processed:
                await asyncio.sleep(settings.build_poll_interval_seconds)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
