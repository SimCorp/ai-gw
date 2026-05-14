# Metric Calculation Algorithms — Concrete Definitions

**Date:** 2026-05-14
**Scope:** Every metric computable from data the gateway collects today.

All queries parameterised on `{period}` (e.g. `INTERVAL '30 days'`).
Table aliases: `doe` = `developer_output_events`, `dal` = `developer_activity_log`, `s` = `sessions`, `d` = `developers`, `t` = `teams`.

---

## Data model cheat-sheet

```
developers (id UUID, email, display_name, team_id)
    └─ developer_activity_log (developer_id, date DATE, request_count, cache_hits,
                                tool_invocations, error_count, cost_usd)
    └─ sessions (session_trace_id, developer_id, team_id TEXT,
                 turn_count, retry_count, error_count, tool_invocations,
                 quality_score INT 1-5, avg_inter_request_s FLOAT,
                 produced_commit BOOL, dominant_intent TEXT, repo TEXT,
                 first_request_at, last_request_at, total_cost)
    └─ developer_output_events (id, developer_id, repo, event_type, pr_number,
                                 commit_count, lines_added, lines_removed,
                                 occurred_at, raw JSONB)
         event_type values: 'push' | 'pr_opened' | 'pr_merged' | 'review'

teams (id UUID, name, area_id)
cost_records (developer_id, team_id UUID, model, tokens_in/out, cost_usd,
              cache_hit, latency_ms, tool_invocation_count, retry_count,
              request_error_type, repo, session_trace_id, created_at)
```

---

## A. Performance Monitoring

### A1. PR Cycle Time
**Definition:** Time from PR opened to PR merged, in hours.
**Data:** `developer_output_events` — join `pr_opened` rows to `pr_merged` rows on `(repo, pr_number)`.

```sql
WITH opens AS (
    SELECT developer_id, repo, pr_number,
           MIN(occurred_at) AS opened_at
    FROM developer_output_events
    WHERE event_type = 'pr_opened'
      AND occurred_at >= NOW() - {period}
    GROUP BY developer_id, repo, pr_number
),
merges AS (
    SELECT repo, pr_number,
           MIN(occurred_at) AS merged_at
    FROM developer_output_events
    WHERE event_type = 'pr_merged'
      AND occurred_at >= NOW() - {period}
    GROUP BY repo, pr_number
),
cycles AS (
    SELECT o.developer_id,
           EXTRACT(EPOCH FROM (m.merged_at - o.opened_at)) / 3600.0 AS cycle_hours
    FROM opens o
    JOIN merges m USING (repo, pr_number)
    WHERE m.merged_at > o.opened_at
)
SELECT
    t.name                                                        AS team_name,
    ROUND(AVG(c.cycle_hours)::numeric, 1)                         AS avg_cycle_hours,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP
          (ORDER BY c.cycle_hours)::numeric, 1)                   AS p50_cycle_hours,
    ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP
          (ORDER BY c.cycle_hours)::numeric, 1)                   AS p90_cycle_hours,
    COUNT(*)                                                       AS pr_count
FROM cycles c
JOIN developers d ON d.id = c.developer_id
JOIN teams t ON t.id = d.team_id
GROUP BY t.name
ORDER BY avg_cycle_hours;
```

**Output:** avg, p50, p90 cycle time in hours per team.
**Action trigger:** p90 > 48h flags a bottleneck worth investigating.

---

### A2. Pickup Time
**Definition:** Time from PR opened to first review submitted, in hours.
**Data:** `developer_output_events` — match `pr_opened` with earliest `review` per `(repo, pr_number)`.

```sql
WITH opens AS (
    SELECT developer_id, repo, pr_number, MIN(occurred_at) AS opened_at
    FROM developer_output_events
    WHERE event_type = 'pr_opened' AND occurred_at >= NOW() - {period}
    GROUP BY developer_id, repo, pr_number
),
first_reviews AS (
    SELECT repo, pr_number, MIN(occurred_at) AS first_review_at
    FROM developer_output_events
    WHERE event_type = 'review' AND occurred_at >= NOW() - {period}
    GROUP BY repo, pr_number
)
SELECT
    t.name                                                              AS team_name,
    ROUND(AVG(
        EXTRACT(EPOCH FROM (fr.first_review_at - o.opened_at)) / 3600.0
    )::numeric, 1)                                                      AS avg_pickup_hours,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (fr.first_review_at - o.opened_at)) / 3600.0
    )::numeric, 1)                                                      AS p50_pickup_hours,
    COUNT(*)                                                             AS pr_count
FROM opens o
JOIN first_reviews fr USING (repo, pr_number)
JOIN developers d ON d.id = o.developer_id
JOIN teams t ON t.id = d.team_id
WHERE fr.first_review_at > o.opened_at
GROUP BY t.name
ORDER BY avg_pickup_hours;
```

**Action trigger:** avg > 4h — set team SLA and monitor trend.

---

### A3. Review Time
**Definition:** Time from first review to PR merge, in hours.
**Data:** `developer_output_events` — earliest `review` to `pr_merged` per `(repo, pr_number)`.

```sql
WITH first_reviews AS (
    SELECT repo, pr_number, MIN(occurred_at) AS first_review_at
    FROM developer_output_events
    WHERE event_type = 'review' AND occurred_at >= NOW() - {period}
    GROUP BY repo, pr_number
),
merges AS (
    SELECT repo, pr_number, developer_id, MIN(occurred_at) AS merged_at
    FROM developer_output_events
    WHERE event_type = 'pr_merged' AND occurred_at >= NOW() - {period}
    GROUP BY repo, pr_number, developer_id
)
SELECT
    t.name                                                                  AS team_name,
    ROUND(AVG(
        EXTRACT(EPOCH FROM (m.merged_at - fr.first_review_at)) / 3600.0
    )::numeric, 1)                                                          AS avg_review_hours,
    COUNT(*)                                                                 AS pr_count
FROM first_reviews fr
JOIN merges m USING (repo, pr_number)
JOIN developers d ON d.id = m.developer_id
JOIN teams t ON t.id = d.team_id
WHERE m.merged_at > fr.first_review_at
GROUP BY t.name
ORDER BY avg_review_hours;
```

---

### A4. Review Depth
**Definition:** Number of review submissions per merged PR. (One row in `developer_output_events` per `pull_request_review` webhook — each submission = one review round by one reviewer.)

```sql
WITH merged_prs AS (
    SELECT DISTINCT repo, pr_number
    FROM developer_output_events
    WHERE event_type = 'pr_merged' AND occurred_at >= NOW() - {period}
),
review_counts AS (
    SELECT doe.repo, doe.pr_number, COUNT(*) AS review_submissions
    FROM developer_output_events doe
    JOIN merged_prs mp USING (repo, pr_number)
    WHERE doe.event_type = 'review'
    GROUP BY doe.repo, doe.pr_number
),
pr_owner AS (
    SELECT repo, pr_number, developer_id
    FROM developer_output_events
    WHERE event_type = 'pr_merged'
)
SELECT
    t.name                                          AS team_name,
    ROUND(AVG(rc.review_submissions)::numeric, 1)  AS avg_review_submissions_per_pr,
    COUNT(*)                                         AS pr_count
FROM review_counts rc
JOIN pr_owner po USING (repo, pr_number)
JOIN developers d ON d.id = po.developer_id
JOIN teams t ON t.id = d.team_id
GROUP BY t.name
ORDER BY avg_review_submissions_per_pr;
```

**Note:** This counts review rounds (approve / request changes), not individual inline comments. To count inline comments, `pull_request_review_comment` events need to be captured separately.

---

### A5. PR Size
**Definition:** Lines of code changed (added + removed) per merged PR.

```sql
SELECT
    t.name                                                             AS team_name,
    ROUND(AVG(doe.lines_added + doe.lines_removed)::numeric, 0)       AS avg_pr_size_loc,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY (doe.lines_added + doe.lines_removed)
    )::numeric, 0)                                                     AS p50_pr_size_loc,
    COUNT(*)                                                            AS pr_count,
    COUNT(CASE WHEN (doe.lines_added + doe.lines_removed) > 400
               THEN 1 END)                                             AS oversized_pr_count
FROM developer_output_events doe
JOIN developers d ON d.id = doe.developer_id
JOIN teams t ON t.id = d.team_id
WHERE doe.event_type = 'pr_merged'
  AND doe.occurred_at >= NOW() - {period}
GROUP BY t.name
ORDER BY avg_pr_size_loc DESC;
```

**Action trigger:** `oversized_pr_count / pr_count > 20%` — coaching opportunity on PR decomposition.

---

### A6. Code Changes (commit velocity)
**Definition:** Total commits and LOC changed per week per team, split push vs. PR.

```sql
SELECT
    t.name                                                  AS team_name,
    DATE_TRUNC('week', doe.occurred_at)                     AS week,
    SUM(doe.commit_count)                                   AS commits,
    SUM(doe.lines_added)                                    AS lines_added,
    SUM(doe.lines_removed)                                  AS lines_removed,
    SUM(doe.lines_added + doe.lines_removed)                AS total_loc_changed
FROM developer_output_events doe
JOIN developers d ON d.id = doe.developer_id
JOIN teams t ON t.id = d.team_id
WHERE doe.event_type = 'push'
  AND doe.occurred_at >= NOW() - {period}
GROUP BY t.name, week
ORDER BY t.name, week;
```

---

### A7. Coding Time (AI-assisted proxy)
**Definition:** Estimated hours a developer spent in active AI-assisted coding sessions.

**Formula per session:**
```
session_active_minutes = turn_count × avg_inter_request_s / 60
```
This works because `avg_inter_request_s` is the average time between requests — a developer who takes 2 minutes between turns is thinking and applying output. A session with 8 turns × 120s inter-request = ~16 minutes of active coding time.

```sql
SELECT
    d.team_id,
    t.name                                                              AS team_name,
    DATE_TRUNC('week', s.first_request_at)                             AS week,
    COUNT(s.session_trace_id)                                           AS sessions,
    ROUND(SUM(
        s.turn_count * COALESCE(s.avg_inter_request_s, 120) / 3600.0
    )::numeric, 1)                                                      AS estimated_coding_hours,
    ROUND(AVG(
        s.turn_count * COALESCE(s.avg_inter_request_s, 120) / 3600.0
    )::numeric, 2)                                                      AS avg_session_hours
FROM sessions s
JOIN developers d ON d.id = s.developer_id
JOIN teams t ON t.id = d.team_id
WHERE s.first_request_at >= NOW() - {period}
  AND s.dominant_intent IN ('code', 'debug', 'refactor', 'feature', 'test')
GROUP BY d.team_id, t.name, week
ORDER BY t.name, week;
```

**Caveat:** Measures AI-tool-active time only — not total keyboard time.

---

### A8. Productiveness Score
**Definition:** 1–5 session quality score, aggregated per team.

The score is computed per session in the observability service (`_session_quality_score`):

| Signal | Score change |
|---|---|
| retry_rate < 10% | +1 |
| retry_rate > 30% | -1 |
| error_rate < 10% | +1 |
| error_rate > 30% | -1 |
| turns 3–10 (focused) | 0 |
| turns > 20 (struggle signal) | -1 |
| turns == 1 (abandoned) | -1 |
| avg_inter_request_s > 120s (applying output) | +1 |
| avg_inter_request_s < 10s AND turns > 3 (rapid-fire) | -1 |

Aggregate:
```sql
SELECT
    t.name                                              AS team_name,
    ROUND(AVG(s.quality_score)::numeric, 2)            AS avg_quality_score,
    ROUND(STDDEV(s.quality_score)::numeric, 2)         AS score_stddev,
    COUNT(s.session_trace_id)                           AS session_count,
    COUNT(CASE WHEN s.quality_score >= 4 THEN 1 END)   AS high_quality_sessions,
    COUNT(CASE WHEN s.quality_score <= 2 THEN 1 END)   AS low_quality_sessions
FROM sessions s
JOIN developers d ON d.id = s.developer_id
JOIN teams t ON t.id = d.team_id
WHERE s.first_request_at >= NOW() - {period}
GROUP BY t.name
ORDER BY avg_quality_score DESC;
```

---

## B. Engineering Investment

### B1. Engineering Effort Overview (AI tool cost)
**Definition:** Total AI gateway spend in USD per team per month — a proxy for AI-assisted engineering effort.

```sql
SELECT
    t.name                                                  AS team_name,
    DATE_TRUNC('month', dal.date::timestamptz)             AS month,
    ROUND(SUM(dal.cost_usd)::numeric, 2)                   AS ai_spend_usd,
    SUM(dal.request_count)                                  AS total_requests,
    COUNT(DISTINCT dal.developer_id)                        AS active_developers,
    ROUND(SUM(dal.cost_usd)::numeric / COUNT(DISTINCT dal.developer_id), 2)
                                                            AS spend_per_developer
FROM developer_activity_log dal
JOIN developers d ON d.id = dal.developer_id
JOIN teams t ON t.id = d.team_id
WHERE dal.date >= CURRENT_DATE - {period}
GROUP BY t.name, month
ORDER BY t.name, month;
```

---

### B2. Investment by Work Type
**Definition:** Breakdown of AI gateway sessions by intent classification — a proxy for how engineering effort is allocated across work types.

```sql
SELECT
    t.name                                              AS team_name,
    COALESCE(s.dominant_intent, 'general')              AS work_type,
    COUNT(s.session_trace_id)                           AS sessions,
    ROUND(SUM(s.total_cost)::numeric, 4)                AS cost_usd,
    ROUND(SUM(s.total_cost) * 100.0
          / SUM(SUM(s.total_cost)) OVER (PARTITION BY t.name), 1)
                                                        AS pct_of_team_spend,
    ROUND(SUM(
        s.turn_count * COALESCE(s.avg_inter_request_s, 120) / 3600.0
    )::numeric, 1)                                      AS estimated_hours
FROM sessions s
JOIN developers d ON d.id = s.developer_id
JOIN teams t ON t.id = d.team_id
WHERE s.first_request_at >= NOW() - {period}
GROUP BY t.name, work_type
ORDER BY t.name, cost_usd DESC;
```

**Work type values** from `dominant_intent`: `feature`, `bug`, `refactor`, `debug`, `test`, `docs`, `general`.

---

### B3. Wasted Spend / Non-Prod Work
**Definition:** % of AI session spend on repos with no git push or PR merge in the last 90 days — signals effort on idle/abandoned code.

```sql
WITH active_repos AS (
    SELECT DISTINCT repo
    FROM developer_output_events
    WHERE event_type IN ('push', 'pr_merged')
      AND occurred_at >= NOW() - INTERVAL '90 days'
      AND repo IS NOT NULL
),
session_spend AS (
    SELECT
        s.repo,
        t.name                          AS team_name,
        ROUND(SUM(s.total_cost)::numeric, 4) AS cost_usd,
        COUNT(s.session_trace_id)       AS sessions
    FROM sessions s
    JOIN developers d ON d.id = s.developer_id
    JOIN teams t ON t.id = d.team_id
    WHERE s.first_request_at >= NOW() - {period}
      AND s.repo IS NOT NULL
    GROUP BY s.repo, t.name
)
SELECT
    ss.team_name,
    SUM(ss.cost_usd)                                                       AS total_spend_usd,
    SUM(CASE WHEN ar.repo IS NULL THEN ss.cost_usd ELSE 0 END)            AS idle_repo_spend_usd,
    ROUND(
        SUM(CASE WHEN ar.repo IS NULL THEN ss.cost_usd ELSE 0 END) * 100.0
        / NULLIF(SUM(ss.cost_usd), 0), 1
    )                                                                       AS wasted_spend_pct
FROM session_spend ss
LEFT JOIN active_repos ar ON ar.repo = ss.repo
GROUP BY ss.team_name
ORDER BY wasted_spend_pct DESC;
```

**Action trigger:** `wasted_spend_pct > 15%` — review idle repos, archive or schedule cleanup sprints.

---

## C. GenAI Utilization & Impact

### C1. GenAI Adoption Rate
**Definition:** % of all developers who made at least one gateway request in the period.

```sql
WITH active AS (
    SELECT COUNT(DISTINCT developer_id) AS active_users
    FROM developer_activity_log
    WHERE date >= CURRENT_DATE - {period_days}
)
SELECT
    (SELECT COUNT(*) FROM developers)           AS total_developers,
    active.active_users,
    ROUND(active.active_users * 100.0
          / NULLIF((SELECT COUNT(*) FROM developers), 0), 1) AS adoption_rate_pct
FROM active;
```

---

### C2. Active Users (weekly trend)

```sql
SELECT
    DATE_TRUNC('week', date::timestamptz)   AS week,
    COUNT(DISTINCT developer_id)             AS active_users
FROM developer_activity_log
WHERE date >= CURRENT_DATE - {period_days}
GROUP BY week
ORDER BY week;
```

---

### C3. Usage Distribution (Rare / Occasional / Regular)

```sql
WITH active_days AS (
    SELECT developer_id, COUNT(DISTINCT date) AS days_active
    FROM developer_activity_log
    WHERE date >= CURRENT_DATE - {period_days}
    GROUP BY developer_id
)
SELECT
    CASE
        WHEN days_active BETWEEN 1  AND 3  THEN 'Rare'        -- 1-3 days
        WHEN days_active BETWEEN 4  AND 14 THEN 'Occasional'  -- 4-14 days
        WHEN days_active >= 15             THEN 'Regular'     -- 15+ days
    END                         AS frequency_tier,
    COUNT(*)                    AS developer_count,
    ROUND(COUNT(*) * 100.0
          / SUM(COUNT(*)) OVER (), 1) AS pct
FROM active_days
GROUP BY frequency_tier
ORDER BY MIN(days_active);
```

---

### C4. Engagement Patterns (by model and intent)

```sql
SELECT
    cr.model,
    COALESCE(s.dominant_intent, 'general')          AS intent,
    COUNT(DISTINCT s.developer_id)                  AS developers,
    COUNT(DISTINCT s.session_trace_id)              AS sessions,
    ROUND(SUM(s.total_cost)::numeric, 4)            AS cost_usd,
    ROUND(AVG(s.quality_score)::numeric, 2)         AS avg_quality
FROM sessions s
JOIN cost_records cr ON cr.session_trace_id = s.session_trace_id
WHERE s.first_request_at >= NOW() - {period}
GROUP BY cr.model, intent
ORDER BY sessions DESC;
```

---

### C5. Adoption by Team (Developers per Product)

```sql
SELECT
    t.name                                          AS team_name,
    COUNT(DISTINCT dal.developer_id)                AS active_users,
    COUNT(DISTINCT d.id)                            AS total_developers,
    ROUND(COUNT(DISTINCT dal.developer_id) * 100.0
          / NULLIF(COUNT(DISTINCT d.id), 0), 1)    AS adoption_rate_pct
FROM teams t
LEFT JOIN developers d ON d.team_id = t.id
LEFT JOIN developer_activity_log dal ON dal.developer_id = d.id
  AND dal.date >= CURRENT_DATE - {period_days}
GROUP BY t.name
ORDER BY adoption_rate_pct DESC;
```

---

### C6. Commits Impacted by GenAI
**Definition:** Developers who had an AI session in the same week as a git push — treated as AI-impacted commits.

```sql
WITH ai_weeks AS (
    -- developers active in the gateway per week
    SELECT DISTINCT developer_id,
           DATE_TRUNC('week', date::timestamptz) AS week
    FROM developer_activity_log
    WHERE date >= CURRENT_DATE - {period_days}
),
commit_weeks AS (
    SELECT developer_id,
           DATE_TRUNC('week', occurred_at) AS week,
           SUM(commit_count) AS commits
    FROM developer_output_events
    WHERE event_type = 'push'
      AND occurred_at >= NOW() - {period}
    GROUP BY developer_id, week
)
SELECT
    cw.week,
    SUM(cw.commits)                                                          AS total_commits,
    SUM(CASE WHEN aw.developer_id IS NOT NULL THEN cw.commits ELSE 0 END)   AS ai_impacted_commits,
    ROUND(
        SUM(CASE WHEN aw.developer_id IS NOT NULL THEN cw.commits ELSE 0 END) * 100.0
        / NULLIF(SUM(cw.commits), 0), 1
    )                                                                        AS ai_impact_pct
FROM commit_weeks cw
LEFT JOIN ai_weeks aw ON aw.developer_id = cw.developer_id AND aw.week = cw.week
GROUP BY cw.week
ORDER BY cw.week;
```

---

### C7. Activities Impacted (sessions → commits)
**Definition:** % of AI sessions that produced a git commit (via `produced_commit = TRUE`, set when a push webhook fires within 24h of a session on the same repo).

```sql
SELECT
    t.name                                                              AS team_name,
    COUNT(s.session_trace_id)                                           AS total_sessions,
    COUNT(CASE WHEN s.produced_commit THEN 1 END)                      AS sessions_with_commit,
    ROUND(
        COUNT(CASE WHEN s.produced_commit THEN 1 END) * 100.0
        / NULLIF(COUNT(s.session_trace_id), 0), 1
    )                                                                   AS commit_conversion_pct
FROM sessions s
JOIN developers d ON d.id = s.developer_id
JOIN teams t ON t.id = d.team_id
WHERE s.first_request_at >= NOW() - {period}
GROUP BY t.name
ORDER BY commit_conversion_pct DESC;
```

---

### C8. Productivity Impact (cohort comparison — the ROI signal)
**Definition:** Compare PR cycle time and session quality between high-adoption developers (≥15 active days/month) and low-adoption developers (<4 active days/month).

```sql
WITH cohorts AS (
    SELECT developer_id,
           CASE WHEN COUNT(DISTINCT date) >= 15 THEN 'high'
                WHEN COUNT(DISTINCT date) <  4  THEN 'low'
                ELSE NULL END AS adoption_cohort
    FROM developer_activity_log
    WHERE date >= CURRENT_DATE - {period_days}
    GROUP BY developer_id
    HAVING COUNT(DISTINCT date) >= 15 OR COUNT(DISTINCT date) < 4
),
pr_cycles AS (
    SELECT o.developer_id,
           AVG(EXTRACT(EPOCH FROM (m.occurred_at - o.occurred_at)) / 3600.0) AS avg_cycle_h
    FROM developer_output_events o
    JOIN developer_output_events m ON m.repo = o.repo AND m.pr_number = o.pr_number
      AND m.event_type = 'pr_merged'
    WHERE o.event_type = 'pr_opened'
      AND o.occurred_at >= NOW() - {period}
      AND m.occurred_at > o.occurred_at
    GROUP BY o.developer_id
),
session_quality AS (
    SELECT developer_id,
           AVG(quality_score)       AS avg_quality,
           AVG(avg_inter_request_s) AS avg_thinking_s,
           COUNT(*)                  AS sessions
    FROM sessions
    WHERE first_request_at >= NOW() - {period}
    GROUP BY developer_id
)
SELECT
    c.adoption_cohort,
    COUNT(DISTINCT c.developer_id)              AS developer_count,
    ROUND(AVG(pc.avg_cycle_h)::numeric, 1)     AS avg_pr_cycle_hours,
    ROUND(AVG(sq.avg_quality)::numeric, 2)     AS avg_session_quality,
    ROUND(AVG(sq.avg_thinking_s)::numeric, 0)  AS avg_inter_request_s,
    SUM(sq.sessions)                            AS total_sessions
FROM cohorts c
LEFT JOIN pr_cycles pc ON pc.developer_id = c.developer_id
JOIN session_quality sq ON sq.developer_id = c.developer_id
GROUP BY c.adoption_cohort;
```

**How to read the output:**
- `high` cohort with lower `avg_pr_cycle_hours` → AI use correlates with faster delivery
- `high` cohort with higher `avg_session_quality` + `avg_inter_request_s` → developers are applying output thoughtfully
- Delta between cohorts is the productivity impact signal

---

## Summary table

| Metric | Tables used | Computed via |
|---|---|---|
| PR Cycle Time | `developer_output_events` | `pr_opened` → `pr_merged` delta |
| Pickup Time | `developer_output_events` | `pr_opened` → first `review` delta |
| Review Time | `developer_output_events` | first `review` → `pr_merged` delta |
| Review Depth | `developer_output_events` | COUNT `review` rows per `pr_number` |
| PR Size | `developer_output_events` | `lines_added + lines_removed` on `pr_merged` |
| Code Changes | `developer_output_events` | SUM `commit_count`, SUM LOC on `push` |
| Coding Time | `sessions` | `turn_count × avg_inter_request_s` |
| Productiveness Score | `sessions` | AVG `quality_score` |
| Engineering Effort | `developer_activity_log` | SUM `cost_usd` per team |
| Investment by Work Type | `sessions` | GROUP BY `dominant_intent` |
| Wasted Spend | `sessions` + `developer_output_events` | sessions on repos with no recent push/merge |
| GenAI Adoption Rate | `developer_activity_log` + `developers` | active / total |
| Active Users Trend | `developer_activity_log` | COUNT DISTINCT weekly |
| Usage Distribution | `developer_activity_log` | COUNT active days → bucket |
| Engagement Patterns | `sessions` + `cost_records` | GROUP BY model + intent |
| Adoption by Team | `developer_activity_log` + `developers` + `teams` | active / total per team |
| Commits Impacted by GenAI | `developer_activity_log` + `developer_output_events` | co-occurrence by developer-week |
| Commit Conversion Rate | `sessions` | `produced_commit = TRUE` / total sessions |
| Productivity Impact (ROI) | `sessions` + `developer_output_events` | cohort comparison high vs. low adoption |
