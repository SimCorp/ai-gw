"""
Background task that finalizes stale sessions.

Two actions:
1. Sessions idle for >30 min — recompute final quality score with full inter-request timing.
2. Sessions >24 h old with produced_commit still NULL — definitively mark as abandoned (FALSE).

This means session analytics eventually converge to complete data even without real-time GitHub events.
"""
import asyncio
import logging

import asyncpg

_log = logging.getLogger(__name__)
_IDLE_THRESHOLD_MINUTES = 30
_ABANDON_THRESHOLD_HOURS = 24


async def _finalize_stale_sessions(pool: asyncpg.Pool) -> None:
    try:
        # Mark sessions older than 24h with no produced_commit as definitively abandoned
        abandoned = await pool.execute(
            """
            UPDATE sessions
            SET produced_commit = FALSE
            WHERE produced_commit IS NULL
              AND first_request_at < NOW() - INTERVAL '24 hours'
            """
        )
        if abandoned and abandoned != "UPDATE 0":
            _log.info("Session cleanup: marked abandoned sessions — %s", abandoned)

        # Recompute quality score for recently-idle sessions (last_request > 30 min ago
        # but quality might have been computed with incomplete timing data)
        await pool.execute(
            """
            UPDATE sessions
            SET quality_score = GREATEST(1, LEAST(5,
                3
                + CASE WHEN retry_count::float / GREATEST(turn_count, 1) < 0.1 THEN 1
                       WHEN retry_count::float / GREATEST(turn_count, 1) > 0.3 THEN -1
                       ELSE 0 END
                + CASE WHEN error_count::float  / GREATEST(turn_count, 1) < 0.1 THEN 1
                       WHEN error_count::float  / GREATEST(turn_count, 1) > 0.3 THEN -1
                       ELSE 0 END
                + CASE WHEN turn_count > 20 THEN -1
                       WHEN turn_count = 1  THEN -1
                       ELSE 0 END
                + CASE WHEN COALESCE(avg_inter_request_s, 0) > 120 THEN 1
                       WHEN COALESCE(avg_inter_request_s, 0) < 10 AND turn_count > 3 THEN -1
                       ELSE 0 END
            )),
            updated_at = NOW()
            WHERE last_request_at < NOW() - INTERVAL '30 minutes'
              AND last_request_at > NOW() - INTERVAL '7 days'
              AND quality_score IS NOT NULL
            """
        )
    except Exception as exc:
        _log.exception("Session cleanup error: %s", exc)


async def run_session_cleanup_loop(pool: asyncpg.Pool, interval_seconds: int = 300) -> None:
    """Run session finalization on a fixed interval. Designed for asyncio.create_task()."""
    while True:
        await _finalize_stale_sessions(pool)
        await asyncio.sleep(interval_seconds)
