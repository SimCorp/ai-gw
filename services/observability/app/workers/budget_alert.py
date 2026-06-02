"""
Background task that checks if any team has consumed >80% of their monthly budget.
Runs every 5 minutes; results are written to Redis so the admin portal can surface them.
When a webhook URL is configured in org_settings, an HTTP POST is fired on each alert.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

import asyncpg
import httpx

_log = logging.getLogger(__name__)
_ALERT_KEY_PREFIX = "budget_alert:team:"
_ALERT_TTL = 3600 * 2  # 2-hour TTL — refreshed each check cycle
_FIRED_KEY_PREFIX = "budget_alert_sent:team:"  # prevents duplicate webhook posts within TTL


async def _get_webhook_url(pool: asyncpg.Pool) -> str | None:
    """Fetch notification webhook URL from org_settings. Returns None if not configured."""
    try:
        row = await pool.fetchrow(
            "SELECT value FROM org_settings WHERE key = 'notification_webhook_url'"
        )
        url = row["value"].strip() if row else ""
        return url if url else None
    except Exception:
        return None


async def _post_webhook(webhook_url: str, payload: dict) -> None:
    """Fire a Slack-compatible webhook POST. Fail silently."""
    try:
        text = (
            f":rotating_light: *Budget Alert — {payload['team_name']}*\n"
            f"Spent *${payload['spent_usd']:.2f}* of *${payload['budget_usd']:.2f}* "
            f"({payload['pct']:.1f}%) this month.\n"
            f"Action: `{payload['action']}`"
        )
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(webhook_url, json={"text": text})
            resp.raise_for_status()
    except Exception as exc:
        _log.warning("Budget alert webhook failed for team %s: %s", payload.get("team_id"), exc)


async def _check_once(pool: asyncpg.Pool, redis) -> None:
    try:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        rows = await pool.fetch(
            """
            SELECT t.id, t.name, t.monthly_budget_usd, t.budget_alert_pct, t.budget_action
            FROM teams t
            WHERE t.monthly_budget_usd IS NOT NULL AND t.monthly_budget_usd > 0
            """
        )
        webhook_url = await _get_webhook_url(pool)

        for row in rows:
            team_id = str(row["id"])
            budget = float(row["monthly_budget_usd"])
            threshold = float(row["budget_alert_pct"])

            spent_raw = await redis.get(f"budget:team:{team_id}:{month}")
            spent = float(spent_raw) if spent_raw else 0.0
            pct = spent / budget if budget > 0 else 0.0

            alert_key = f"{_ALERT_KEY_PREFIX}{team_id}"
            fired_key = f"{_FIRED_KEY_PREFIX}{team_id}:{month}"

            if pct >= threshold:
                payload = {
                    "team_id": team_id,
                    "team_name": row["name"],
                    "spent_usd": round(spent, 4),
                    "budget_usd": round(budget, 4),
                    "pct": round(pct * 100, 1),
                    "action": row["budget_action"],
                    "month": month,
                    "alerted_at": datetime.now(timezone.utc).isoformat(),
                }
                await redis.setex(alert_key, _ALERT_TTL, json.dumps(payload))
                _log.warning(
                    "Budget alert: team %s (%s) at %.1f%% of monthly budget",
                    team_id,
                    row["name"],
                    pct * 100,
                )

                if webhook_url:
                    already_sent = await redis.exists(fired_key)
                    if not already_sent:
                        await _post_webhook(webhook_url, payload)
                        # Mark as sent for the remainder of this month's alert window
                        await redis.setex(fired_key, _ALERT_TTL, "1")
            else:
                await redis.delete(alert_key)
                await redis.delete(fired_key)
    except Exception as exc:
        _log.exception("Budget alert check failed: %s", exc)


async def run_budget_alert_loop(pool: asyncpg.Pool, redis, interval_seconds: int = 300) -> None:
    """Run budget alert checks on a fixed interval. Designed for asyncio.create_task()."""
    while True:
        await _check_once(pool, redis)
        await asyncio.sleep(interval_seconds)
