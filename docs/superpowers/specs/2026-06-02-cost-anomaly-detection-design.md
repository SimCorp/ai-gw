# Cost Anomaly Detection

**Date:** 2026-06-02
**Status:** Approved (autonomous build under /goal) — feature #3 of the hardening sequence
**Spec + plan combined.**

## Problem & key finding

The admin alerting *surface* already exists but is **unpopulated**:
- `GET /budget/alerts` (`services/admin/app/routers/alerts.py`) returns rows from
  `audit_log WHERE action='budget_spike_alert'`.
- The admin `/admin/alerts` page already renders a "Cost spike alerts" table from that endpoint
  (Time / Team / Daily spend / vs Average).
- `budget_alert_config` in `org_settings` already carries a `spike_multiplier`.
- **Nothing writes those `budget_spike_alert` rows.** Detection is the missing piece.

So this feature is a **detection worker** that populates the spike alerts the UI already expects —
no new endpoint, no new admin UI, no new table (reuses `audit_log`).

## Design

New worker `services/observability/app/workers/cost_anomaly.py`, mirroring the existing
`budget_alert.py` worker (same `run_*_loop(pool, redis, interval_seconds)` shape, wired into
`services/observability/app/main.py` lifespan as an `asyncio.create_task`).

**Detection (per team / org node, daily):** compare the current day's spend against the rolling
average of the prior 7 complete days. Fire when:
`today_spend >= rolling_7d_avg * spike_multiplier` **and** `today_spend >= min_spend_floor`
(an absolute floor so trivial amounts like $0.10→$0.60 don't alert).

SQL (asyncpg, reuses the dashboard `node_id`/`created_at` pattern):
```sql
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
WHERE a.today_spend IS NOT NULL AND a.rolling_avg IS NOT NULL;
```
Decision logic lives in a **pure function** `detect_spikes(rows, multiplier, floor) -> list[Spike]`
(unit-testable without a DB).

**Alert write:** for each spike, insert into `audit_log`:
`action='budget_spike_alert'`, `actor='cost-anomaly-worker'`, `resource_type='team'`,
`resource_id=node_id`, `details={team_name, daily_spend, rolling_avg, multiplier}`.

**Dedup:** one alert per (node, day). Use a Redis flag `cost_spike_sent:{node_id}:{YYYY-MM-DD}`
(24h TTL) — same dedup idiom as `budget_alert.py`'s `budget_alert_sent:*`. Skip insert if flag set.

**Config:** read `spike_multiplier` (default 3.0) and an optional `min_spend_floor_usd` (default 1.0)
from `budget_alert_config` in `org_settings`; fall back to defaults if absent. Interval default 3600s.

## Out of scope
- Per-key / per-model anomaly granularity (the existing UI is team-level; YAGNI for now).
- New admin endpoint or UI (the surface already exists).
- Webhook/Slack delivery for spikes (budget_alert already owns webhooks; can extend later).

## Plan (TDD)
1. **Pure `detect_spikes`** + `Spike` dataclass in `cost_anomaly.py`. Unit tests
   (`services/observability/tests/test_cost_anomaly.py`): fires above multiplier+floor; not below
   multiplier; not below floor; handles `rolling_avg == 0`/None; multiple nodes. Implement. Commit.
2. **`_check_once(pool, redis, ...)`** — runs the query, calls `detect_spikes`, dedups via Redis,
   inserts audit_log rows. Test with an `AsyncMock`/fake pool returning canned rows + a mock redis,
   asserting correct inserts and that a set dedup flag suppresses re-insert. Implement. Commit.
3. **Wire into lifespan** (`run_cost_anomaly_loop`), mirroring `run_budget_alert_loop`. Commit.
4. `pytest services/observability` green; `ruff check`/`format` clean. PR.

## Success criteria
- A spike (today >= multiplier × prior-7-day avg, above floor) writes one `budget_spike_alert`
  audit row per team per day; the existing `/budget/alerts` endpoint + admin page then display it.
- Dedup prevents duplicate same-day alerts.
- Detection logic unit-tested; worker tested with mocked pool/redis. No new migration.
