"""
Background worker that detects cost spikes per organization node (team).
Compares today's spend against a rolling 7-day average.
Fires when today >= avg * multiplier AND today >= floor.
Results are written to audit_log as action='budget_spike_alert'.
Dedup: one alert per (node, calendar day) via Redis flag with 24h TTL.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import asyncpg

_log = logging.getLogger(__name__)

_FIRED_KEY_PREFIX = "cost_spike_sent:"  # {node_id}:{YYYY-MM-DD}
_FIRED_TTL = 3600 * 24  # 24-hour TTL

_CONFIG_KEY = "budget_alert_config"
_SPIKE_SQL = """
WITH daily AS (
  SELECT node_id, DATE(created_at) AS day, SUM(cost_usd) AS spend
  FROM cost_records
  WHERE created_at >= NOW() - INTERVAL '8 days'
  GROUP BY node_id, DATE(created_at)
),
agg AS (
  SELECT node_id,
         SUM(spend) FILTER (WHERE day = CURRENT_DATE) AS today_spend,
         AVG(spend) FILTER (WHERE day < CURRENT_DATE)  AS rolling_avg
  FROM daily GROUP BY node_id
)
SELECT a.node_id, n.name AS team_name, a.today_spend, a.rolling_avg
FROM agg a JOIN organization_nodes n ON n.id = a.node_id
WHERE a.today_spend IS NOT NULL AND a.rolling_avg IS NOT NULL
"""


@dataclass
class Spike:
    node_id: str
    team_name: str
    daily_spend: float
    rolling_avg: float
    multiplier: float  # round(today_spend / rolling_avg, 2)


def detect_spikes(rows: list[dict], multiplier: float, floor: float) -> list[Spike]:
    """Pure spike detection. Each row must have node_id, team_name, today_spend, rolling_avg."""
    spikes: list[Spike] = []
    for row in rows:
        avg = row["rolling_avg"]
        today = row["today_spend"]
        if not avg:  # None or 0
            continue
        if today >= avg * multiplier and today >= floor:
            spikes.append(
                Spike(
                    node_id=str(row["node_id"]),
                    team_name=row["team_name"],
                    daily_spend=float(today),
                    rolling_avg=float(avg),
                    multiplier=round(float(today) / float(avg), 2),
                )
            )
    return spikes


async def _check_once(
    pool: asyncpg.Pool,
    redis,
    multiplier_default: float = 3.0,
    floor_default: float = 1.0,
) -> None:
    try:
        # 1. Read config from org_settings (same pattern as budget_alert._get_webhook_url)
        multiplier = multiplier_default
        floor = floor_default
        try:
            cfg_rows = await pool.fetch(
                "SELECT value FROM org_settings WHERE key = $1", _CONFIG_KEY
            )
            if cfg_rows:
                cfg = json.loads(cfg_rows[0]["value"])
                multiplier = float(cfg.get("spike_multiplier", multiplier_default))
                floor = float(cfg.get("min_spend_floor_usd", floor_default))
        except Exception:
            pass  # fall back to defaults

        # 2. Run spike detection query
        rows = await pool.fetch(_SPIKE_SQL)

        # 3. Detect spikes (pure function)
        spikes = detect_spikes(rows, multiplier, floor)

        # 4. Dedup via Redis; insert audit_log for new spikes
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for spike in spikes:
            fired_key = f"{_FIRED_KEY_PREFIX}{spike.node_id}:{today_str}"
            already_sent = await redis.exists(fired_key)
            if already_sent:
                continue

            details = json.dumps(
                {
                    "team_name": spike.team_name,
                    "daily_spend": spike.daily_spend,
                    "rolling_avg": spike.rolling_avg,
                    "multiplier": spike.multiplier,
                }
            )
            await pool.execute(
                """
                INSERT INTO audit_log (actor, action, resource_type, resource_id, details)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                """,
                "cost-anomaly-worker",
                "budget_spike_alert",
                "team",
                spike.node_id,
                details,
            )
            await redis.setex(fired_key, _FIRED_TTL, "1")
            _log.warning(
                "Cost spike alert: node %s (%s) %.2fx rolling avg ($%.4f vs $%.4f avg)",
                spike.node_id,
                spike.team_name,
                spike.multiplier,
                spike.daily_spend,
                spike.rolling_avg,
            )
    except Exception as exc:
        _log.exception("Cost anomaly check failed: %s", exc)


async def run_cost_anomaly_loop(pool: asyncpg.Pool, redis, interval_seconds: int = 3600) -> None:
    """Run cost anomaly checks on a fixed interval. Designed for asyncio.create_task()."""
    while True:
        await _check_once(pool, redis)
        await asyncio.sleep(interval_seconds)
