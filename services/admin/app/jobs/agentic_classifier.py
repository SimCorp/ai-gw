"""
Nightly agentic transformation classifier.

Classifies sessions into interactive / agentic / autonomous and awards
developer achievements based on existing session + cost_record data.
Can be run on demand or on a cron schedule.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Session classification
# ---------------------------------------------------------------------------

_CLASSIFY_SQL = """
UPDATE sessions
SET session_type = CASE
    WHEN turn_count > 15
         AND avg_inter_request_s < 8
         AND tool_invocations::float / GREATEST(turn_count, 1) > 0.8
        THEN 'autonomous'::session_type_enum
    WHEN tool_invocations::float / GREATEST(turn_count, 1) > 0.3
         OR (turn_count > 8 AND avg_inter_request_s < 20)
        THEN 'agentic'::session_type_enum
    ELSE 'interactive'::session_type_enum
END
WHERE session_type IS NULL
  AND last_request_at < NOW() - INTERVAL '5 minutes'
"""


async def classify_sessions(session: AsyncSession) -> int:
    result = await session.execute(text(_CLASSIFY_SQL))
    await session.commit()
    rows = result.rowcount
    log.info("Classified %d sessions", rows)
    return rows


# ---------------------------------------------------------------------------
# Achievement engine
# ---------------------------------------------------------------------------

_ACHIEVEMENTS = [
    # (achievement_name, SQL that returns developer_id rows deserving the badge)
    (
        "first_step",
        """
        SELECT DISTINCT d.id AS developer_id
        FROM developers d
        JOIN cost_records cr ON cr.developer_id = d.id
        WHERE NOT EXISTS (
            SELECT 1 FROM developer_achievements da
            WHERE da.developer_id = d.id AND da.achievement = 'first_step'
        )
        """,
    ),
    (
        "tool_user",
        """
        SELECT DISTINCT s.developer_id
        FROM sessions s
        WHERE s.tool_invocations > 0
          AND s.developer_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM developer_achievements da
              WHERE da.developer_id = s.developer_id AND da.achievement = 'tool_user'
          )
        """,
    ),
    (
        "going_agentic",
        """
        SELECT DISTINCT s.developer_id
        FROM sessions s
        WHERE s.session_type = 'agentic'
          AND s.developer_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM developer_achievements da
              WHERE da.developer_id = s.developer_id AND da.achievement = 'going_agentic'
          )
        """,
    ),
    (
        "autonomous",
        """
        SELECT DISTINCT s.developer_id
        FROM sessions s
        WHERE s.session_type = 'autonomous'
          AND s.developer_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM developer_achievements da
              WHERE da.developer_id = s.developer_id AND da.achievement = 'autonomous'
          )
        """,
    ),
    (
        "agentic_majority",
        # >50% of last 7 days cost in agentic/autonomous sessions
        """
        SELECT developer_id FROM (
            SELECT
                cr.developer_id,
                SUM(CASE WHEN s.session_type IN ('agentic','autonomous') THEN cr.cost_usd ELSE 0 END)
                    / NULLIF(SUM(cr.cost_usd), 0) AS agentic_cost_ratio
            FROM cost_records cr
            LEFT JOIN sessions s ON s.session_trace_id = cr.session_trace_id
            WHERE cr.developer_id IS NOT NULL
              AND cr.created_at >= NOW() - INTERVAL '7 days'
            GROUP BY cr.developer_id
            HAVING SUM(cr.cost_usd) > 0
        ) t
        WHERE agentic_cost_ratio > 0.5
          AND NOT EXISTS (
              SELECT 1 FROM developer_achievements da
              WHERE da.developer_id = t.developer_id AND da.achievement = 'agentic_majority'
          )
        """,
    ),
    (
        "ten_agent_commits",
        """
        SELECT developer_id FROM (
            SELECT developer_id, COUNT(*) AS commit_sessions
            FROM sessions
            WHERE produced_commit = TRUE
              AND session_type IN ('agentic','autonomous')
              AND developer_id IS NOT NULL
            GROUP BY developer_id
            HAVING COUNT(*) >= 10
        ) t
        WHERE NOT EXISTS (
            SELECT 1 FROM developer_achievements da
            WHERE da.developer_id = t.developer_id AND da.achievement = 'ten_agent_commits'
        )
        """,
    ),
    (
        "deep_thinker",
        # Single session with >100 tool invocations
        """
        SELECT DISTINCT developer_id
        FROM sessions
        WHERE tool_invocations > 100
          AND developer_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM developer_achievements da
              WHERE da.developer_id = sessions.developer_id AND da.achievement = 'deep_thinker'
          )
        """,
    ),
    (
        "consistent",
        # 5 consecutive calendar days with at least one agentic/autonomous session
        """
        SELECT developer_id FROM (
            SELECT
                developer_id,
                date_trunc('day', first_request_at)::date AS day
            FROM sessions
            WHERE session_type IN ('agentic','autonomous')
              AND developer_id IS NOT NULL
            GROUP BY developer_id, date_trunc('day', first_request_at)::date
        ) days
        GROUP BY developer_id
        HAVING MAX(day) - MIN(day) >= 4
           AND COUNT(DISTINCT day) >= 5
           AND NOT EXISTS (
               SELECT 1 FROM developer_achievements da
               WHERE da.developer_id = days.developer_id AND da.achievement = 'consistent'
           )
        """,
    ),
]


async def award_achievements(session: AsyncSession) -> dict[str, int]:
    awarded: dict[str, int] = {}
    now = datetime.now(timezone.utc)

    for achievement, sql in _ACHIEVEMENTS:
        rows = (await session.execute(text(sql))).mappings().all()
        count = 0
        for row in rows:
            await session.execute(
                text("""
                    INSERT INTO developer_achievements (developer_id, achievement, earned_at)
                    VALUES (CAST(:dev_id AS uuid), :ach, :now)
                    ON CONFLICT DO NOTHING
                """),
                {"dev_id": str(row["developer_id"]), "ach": achievement, "now": now},
            )
            count += 1
        if count:
            awarded[achievement] = count

    await session.commit()
    if awarded:
        log.info("Awarded achievements: %s", awarded)
    return awarded


async def run_classifier(session: AsyncSession) -> dict:
    classified = await classify_sessions(session)
    awarded = await award_achievements(session)
    return {"sessions_classified": classified, "achievements_awarded": awarded}
