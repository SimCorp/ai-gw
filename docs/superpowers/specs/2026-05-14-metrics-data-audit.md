# Metrics Data Audit & Algorithm Definitions

**Date:** 2026-05-14
**Status:** Authoritative reference — update when data collection changes

---

## 1. What the gateway currently captures

### 1a. AI Gateway events (`cost_records`, `sessions`, `developer_activity_log`)

Every request through the gateway produces a `GatewayEvent`. The observability service writes to three tables:

| Table | Granularity | Key columns |
|---|---|---|
| `cost_records` | Per request | `developer_id`, `team_id`, `model`, `tokens_in/out`, `cost_usd`, `cache_hit`, `latency_ms`, `tool_invocation_count`, `retry_count`, `request_error_type`, `repo`, `session_trace_id` |
| `sessions` | Per session (upserted) | `developer_id`, `team_id`, `turn_count`, `quality_score` (1–5), `avg_inter_request_s`, `retry_count`, `error_count`, `tool_invocations`, `produced_commit`, `dominant_intent`, `repo`, `session_type` |
| `developer_activity_log` | Per developer per day | `developer_id`, `date`, `request_count`, `tokens_in/out`, `cost_usd`, `cache_hits`, `tool_invocations`, `error_count` |

### 1b. GitHub webhooks (`developer_output_events`)

The observability service receives GitHub webhook events at `POST /webhooks/github`. Three event types are handled:

| Event | Stored as `event_type` | Columns populated |
|---|---|---|
| `push` | `push` | `developer_id`, `repo`, `commit_count`, `lines_added`, `lines_removed`, `occurred_at` |
| `pull_request` opened | `pr_opened` | `developer_id`, `repo`, `pr_number`, `lines_added`, `lines_removed`, `occurred_at` |
| `pull_request` merged | `pr_merged` | `developer_id`, `repo`, `pr_number`, `lines_added`, `lines_removed`, `occurred_at` |
| `pull_request_review` submitted | `review` | `developer_id`, `repo`, `pr_number`, `occurred_at`, `raw→state` |

### 1c. What is NOT currently collected

| Data needed | Why it's missing | Collection method required |
|---|---|---|
| PR opened/merged timestamps as typed columns | `raw` JSONB only stores metadata, `occurred_at` is insert time not event time | Store `pr_created_at`, `pr_merged_at` from webhook payload |
| PR review comment count | Only review submissions captured, not individual comments | Add `pull_request_review_comment` webhook handler |
| GitHub API data (Copilot seats, acceptance rates) | Requires PAT + polling — not a webhook | New scheduled GitHub API collector |
| Deployment events | Not subscribed to `deployment_status` webhook | Add `deployment_status` webhook handler |
| Jira/PM data (issues, estimates, sprints, bugs) | No integration built | New Jira webhook or API poller |
| Code longevity (git blame) | Requires periodic repo scanning | New git analysis background job |
| Copilot/Qodo tool-specific metrics | Separate vendor APIs | New vendor API collector |

---

## 2. Performance Monitoring — algorithm definitions

### Metrics computable NOW from existing data

---

#### PR Size
**Source:** `developer_output_events`
**Algorithm:**
```sql
SELECT
    team_id,
    AVG(lines_added + lines_removed) AS avg_pr_size_loc,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lines_added + lines_removed) AS median_pr_size
FROM developer_output_events doe
JOIN developers d ON d.id = doe.developer_id
WHERE event_type = 'pr_merged'
  AND occurred_at >= NOW() - INTERVAL '{period}'
GROUP BY team_id
```
**Actionable threshold:** Flag PRs > 400 LOC. Target median < 200 LOC.

---

#### Code Changes (rate of changes)
**Source:** `developer_output_events`
**Algorithm:**
```sql
SELECT
    d.team_id,
    DATE_TRUNC('week', doe.occurred_at) AS week,
    SUM(doe.commit_count) AS commits,
    SUM(doe.lines_added + doe.lines_removed) AS loc_changed
FROM developer_output_events doe
JOIN developers d ON d.id = doe.developer_id
WHERE event_type = 'push'
  AND occurred_at >= NOW() - INTERVAL '{period}'
GROUP BY d.team_id, week
```

---

#### Review Depth (reviews per PR)
**Source:** `developer_output_events`
**Algorithm:**
```sql
SELECT
    doe_pr.team_id,
    AVG(review_counts.review_count) AS avg_reviews_per_pr
FROM (
    SELECT developer_id, repo, pr_number, COUNT(*) AS review_count
    FROM developer_output_events
    WHERE event_type = 'review'
      AND occurred_at >= NOW() - INTERVAL '{period}'
    GROUP BY developer_id, repo, pr_number
) review_counts
JOIN developers d ON d.id = review_counts.developer_id
GROUP BY d.team_id
```
**Caveat:** This counts review submissions, not individual comments. One review submission = one row in the table. To get comment depth, individual review comment events must be captured (see gaps above).

---

#### Pickup Time (PR open → first review)
**Source:** `developer_output_events`
**Algorithm:**
```sql
WITH pr_opens AS (
    SELECT repo, pr_number, MIN(occurred_at) AS opened_at
    FROM developer_output_events
    WHERE event_type = 'pr_opened'
    GROUP BY repo, pr_number
),
first_reviews AS (
    SELECT repo, pr_number, MIN(occurred_at) AS first_review_at
    FROM developer_output_events
    WHERE event_type = 'review'
    GROUP BY repo, pr_number
)
SELECT
    d.team_id,
    AVG(EXTRACT(EPOCH FROM (fr.first_review_at - po.opened_at)) / 3600) AS avg_pickup_hours
FROM pr_opens po
JOIN first_reviews fr USING (repo, pr_number)
JOIN developer_output_events doe ON doe.repo = po.repo AND doe.pr_number = po.pr_number AND doe.event_type = 'pr_opened'
JOIN developers d ON d.id = doe.developer_id
WHERE po.opened_at >= NOW() - INTERVAL '{period}'
GROUP BY d.team_id
```

---

#### Review Time (first review → merge)
**Source:** `developer_output_events`
**Algorithm:**
```sql
WITH first_reviews AS (
    SELECT repo, pr_number, MIN(occurred_at) AS first_review_at
    FROM developer_output_events
    WHERE event_type = 'review'
    GROUP BY repo, pr_number
),
merges AS (
    SELECT repo, pr_number, MAX(occurred_at) AS merged_at
    FROM developer_output_events
    WHERE event_type = 'pr_merged'
    GROUP BY repo, pr_number
)
SELECT
    d.team_id,
    AVG(EXTRACT(EPOCH FROM (m.merged_at - fr.first_review_at)) / 3600) AS avg_review_hours
FROM first_reviews fr
JOIN merges m USING (repo, pr_number)
JOIN developer_output_events doe ON doe.repo = fr.repo AND doe.pr_number = fr.pr_number AND doe.event_type = 'pr_merged'
JOIN developers d ON d.id = doe.developer_id
WHERE fr.first_review_at >= NOW() - INTERVAL '{period}'
GROUP BY d.team_id
```

---

#### PR Cycle Time (open → merge)
**Source:** `developer_output_events`
**Algorithm:**
```sql
WITH pr_opens AS (
    SELECT repo, pr_number, developer_id, MIN(occurred_at) AS opened_at
    FROM developer_output_events WHERE event_type = 'pr_opened' GROUP BY repo, pr_number, developer_id
),
pr_merges AS (
    SELECT repo, pr_number, MAX(occurred_at) AS merged_at
    FROM developer_output_events WHERE event_type = 'pr_merged' GROUP BY repo, pr_number
)
SELECT
    d.team_id,
    AVG(EXTRACT(EPOCH FROM (pm.merged_at - po.opened_at)) / 3600) AS avg_cycle_time_hours,
    PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (pm.merged_at - po.opened_at)) / 3600
    ) AS p50_cycle_time_hours,
    PERCENTILE_CONT(0.9) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (pm.merged_at - po.opened_at)) / 3600
    ) AS p90_cycle_time_hours
FROM pr_opens po
JOIN pr_merges pm USING (repo, pr_number)
JOIN developers d ON d.id = po.developer_id
WHERE po.opened_at >= NOW() - INTERVAL '{period}'
GROUP BY d.team_id
```
**Note:** This is PR cycle time (code to merge), not full issue cycle time (which requires Jira/PM).

---

#### Coding Time (proxy via gateway sessions)
**Source:** `sessions`
**Algorithm:**
```sql
-- AI-assisted coding time per developer per week
SELECT
    s.team_id,
    DATE_TRUNC('week', s.first_request_at) AS week,
    SUM(s.turn_count * COALESCE(s.avg_inter_request_s, 120)) / 3600.0 AS estimated_coding_hours
FROM sessions s
WHERE s.first_request_at >= NOW() - INTERVAL '{period}'
  AND s.dominant_intent IN ('code', 'debug', 'refactor', 'feature')
GROUP BY s.team_id, week
```
**Important caveat:** This measures AI-tool-assisted coding time only, not total time at keyboard. It is a leading indicator, not a complete coding time measurement. True coding time requires IDE plugin telemetry or git commit timestamp interval analysis.

---

#### Productiveness Score (proxy)
**Source:** `sessions`
**Algorithm:** The existing `quality_score` in `sessions` is a 1–5 score computed per session:
```
score = 3 (baseline)
  + 1 if retry_rate  < 10%   (smooth flow)
  - 1 if retry_rate  > 30%   (struggling)
  + 1 if error_rate  < 10%   (reliable)
  - 1 if error_rate  > 30%   (broken environment)
  ± 0 if turns 3–10          (focused session)
  - 1 if turns > 20          (possible struggle)
  - 1 if turns == 1          (likely abandoned)
  + 1 if avg_inter_s > 120   (applying output — positive signal)
  - 1 if avg_inter_s < 10 and turns > 3  (rapid-fire = stuck)
clamped to [1, 5]
```
Aggregate to team level: `ROUND(AVG(quality_score), 2)` per team per period.

---

### Metrics requiring additional data collection

| Metric | Gap | Required addition |
|---|---|---|
| **Issues/PR Cycle Time** (full, PM→deploy) | No Jira | Jira webhook: store `issue_created_at`, `in_progress_at` |
| **Lead Time** (PM) | No Jira | Jira webhook |
| **Completed Backlog Stories** | No Jira | Jira webhook |
| **CR Impact** (% code changed post-review) | No per-review-round commit data | Store PR commit events separately; compare lines_added before/after each review round |
| **Code Longevity** | No git history scan | Background job: `git log --follow` to compute average commit age in a repo |
| **Deployment Frequency** (DORA) | No deployment events | Add `deployment_status` webhook: store deploy timestamp, status, environment |
| **Lead Time for Changes** (DORA) | No deployment events | Same as above; compute from first commit to first successful deploy |
| **Change Failure Rate** (DORA) | No deployment failure events | `deployment_status` with `failure` state |
| **MTTR** (DORA) | No incident data | Deployment failure + recovery events or PagerDuty/incident webhook |
| **Bug Density** | No bug data | Jira: store bug issue count per repo per period |
| **Issues out of SLA** | No SLA/PM data | Jira: store issue created_at, resolved_at, priority-based SLA target |
| **Bugs per Repo / Priority** | No Jira | Jira webhook |
| **PR/Issue Test Coverage** | No CI data | GitHub Actions webhook: capture test coverage report on PR |
| **Coding Time vs. Estimated** | No estimates | Jira: store story point estimate per issue |

---

## 3. Engineering Investment — algorithm definitions

### Metrics computable NOW

---

#### Engineering Effort Overview (AI tool cost as effort proxy)
**Source:** `developer_activity_log`, `cost_records`
**Algorithm:**
```sql
SELECT
    d.team_id,
    DATE_TRUNC('month', dal.date::timestamptz) AS month,
    SUM(dal.cost_usd) AS ai_tool_spend_usd,
    SUM(dal.request_count) AS total_requests,
    COUNT(DISTINCT dal.developer_id) AS active_developers
FROM developer_activity_log dal
JOIN developers d ON d.id = dal.developer_id
WHERE dal.date >= CURRENT_DATE - INTERVAL '{period}'
GROUP BY d.team_id, month
```
**Limitation:** This measures AI tool spend, not total engineering effort. True effort = headcount × salary. AI spend is a cost-efficiency signal, not a complete effort measure.

---

#### Investment by Work Type (via intent classification)
**Source:** `sessions`
**Algorithm:**
```sql
SELECT
    team_id,
    COALESCE(dominant_intent, 'general') AS work_type,
    COUNT(*) AS session_count,
    SUM(total_cost) AS cost_usd,
    SUM(turn_count * COALESCE(avg_inter_request_s, 120)) / 3600.0 AS estimated_hours
FROM sessions
WHERE first_request_at >= NOW() - INTERVAL '{period}'
GROUP BY team_id, work_type
ORDER BY cost_usd DESC
```
**Intent values** (classified by `request_intent` in the observability service):
- `feature` — new feature development
- `bug` — bug fixing
- `refactor` — code improvement
- `debug` — debugging
- `docs` — documentation
- `test` — test writing
- `general` — unclassified

---

#### Wasted Spend / Non-Prod Work
**Source:** `sessions`, `developer_output_events`

Wasted work = AI sessions on repos that have had no `pr_merged` or `push` events in 90+ days:
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
        repo,
        SUM(total_cost) AS cost_usd,
        COUNT(*) AS sessions
    FROM sessions
    WHERE first_request_at >= NOW() - INTERVAL '{period}'
      AND repo IS NOT NULL
    GROUP BY repo
)
SELECT
    ss.repo,
    ss.cost_usd,
    ss.sessions,
    (ar.repo IS NULL) AS is_idle_repo
FROM session_spend ss
LEFT JOIN active_repos ar ON ar.repo = ss.repo
```
Aggregate: `SUM(cost_usd WHERE is_idle_repo) / SUM(cost_usd) * 100` = wasted spend %.

---

### Metrics requiring additional data collection

| Metric | Gap | Required addition |
|---|---|---|
| **True engineering effort ($ or hours)** | No headcount/salary data | HR system integration or manual headcount table |
| **Teams/Groups work time per category** (full) | PM work categories | Jira sprint/epic categorization |
| **Non-Prod Work Analysis** (per team) | Deployment tracking | `deployment_status` webhook to know what reached production |
| **Feature Spend by Issue Type** | No Jira issue linkage | Jira: link commit/PR to issue; store issue_type per PR |
| **Coding Time vs. Estimated** | No story point estimates | Jira: store estimate per issue, actual via PR cycle time |

---

## 4. GenAI Utilization & Impact — algorithm definitions

All metrics in this section are computable from existing gateway data **except** Copilot-specific and Qodo-specific metrics.

---

#### GenAI Adoption Rate
```sql
active / total_developers * 100
-- where active = COUNT(DISTINCT developer_id) FROM developer_activity_log
-- WHERE date >= CURRENT_DATE - 30 days
-- total_developers = COUNT(*) FROM developers
```

---

#### Active Users (weekly/monthly)
```sql
SELECT
    DATE_TRUNC('week', date::timestamptz) AS week,
    COUNT(DISTINCT developer_id) AS active_users
FROM developer_activity_log
WHERE date >= CURRENT_DATE - INTERVAL '{period}'
GROUP BY week
```

---

#### Usage Distribution (Rare / Occasional / Regular)
```sql
WITH active_days AS (
    SELECT developer_id, COUNT(DISTINCT date) AS days_active
    FROM developer_activity_log
    WHERE date >= CURRENT_DATE - INTERVAL '{period}'
    GROUP BY developer_id
)
SELECT
    CASE
        WHEN days_active BETWEEN 1 AND 3  THEN 'Rare'
        WHEN days_active BETWEEN 4 AND 14 THEN 'Occasional'
        WHEN days_active >= 15            THEN 'Regular'
    END AS frequency_tier,
    COUNT(*) AS developer_count
FROM active_days
GROUP BY frequency_tier
```

---

#### Engagement Patterns (by model / intent)
```sql
SELECT
    COALESCE(cr.model, 'unknown') AS model,
    COALESCE(s.dominant_intent, 'general') AS intent,
    COUNT(DISTINCT s.developer_id) AS developers,
    COUNT(s.session_trace_id) AS sessions,
    SUM(s.total_cost) AS cost_usd
FROM sessions s
JOIN cost_records cr ON cr.session_trace_id = s.session_trace_id
WHERE s.first_request_at >= NOW() - INTERVAL '{period}'
GROUP BY model, intent
ORDER BY sessions DESC
```

---

#### Commits Impacted by GenAI
**Source:** `sessions` with `produced_commit = TRUE` linked to `developer_output_events`
```sql
WITH ai_commits AS (
    -- sessions that resulted in a commit
    SELECT DISTINCT developer_id, DATE_TRUNC('week', last_request_at) AS week
    FROM sessions
    WHERE produced_commit = TRUE
      AND first_request_at >= NOW() - INTERVAL '{period}'
),
total_commits AS (
    SELECT developer_id, DATE_TRUNC('week', occurred_at) AS week, SUM(commit_count) AS commits
    FROM developer_output_events
    WHERE event_type = 'push'
      AND occurred_at >= NOW() - INTERVAL '{period}'
    GROUP BY developer_id, week
)
SELECT
    tc.week,
    SUM(tc.commits) AS total_commits,
    COUNT(DISTINCT ac.developer_id) AS developers_with_ai_commits,
    -- commits from developers who used AI that week (proxy for AI-impacted commits)
    SUM(CASE WHEN ac.developer_id IS NOT NULL THEN tc.commits ELSE 0 END) AS ai_impacted_commits
FROM total_commits tc
LEFT JOIN ai_commits ac ON ac.developer_id = tc.developer_id AND ac.week = tc.week
GROUP BY tc.week
```

---

#### Activities Impacted by GenAI (PRs, sessions with commit output)
```sql
SELECT
    DATE_TRUNC('week', s.first_request_at) AS week,
    COUNT(CASE WHEN s.produced_commit THEN 1 END) AS sessions_with_commit,
    COUNT(*) AS total_sessions,
    ROUND(COUNT(CASE WHEN s.produced_commit THEN 1 END) * 100.0 / COUNT(*), 1) AS commit_conversion_pct
FROM sessions s
WHERE s.first_request_at >= NOW() - INTERVAL '{period}'
GROUP BY week
```

---

#### Productivity Impact (cohort comparison)
**Algorithm:** compare high-adoption vs low-adoption cohorts on PR cycle time and session quality:
```sql
WITH cohorts AS (
    SELECT developer_id,
           CASE WHEN COUNT(DISTINCT date) >= 15 THEN 'high' ELSE 'low' END AS adoption
    FROM developer_activity_log
    WHERE date >= CURRENT_DATE - INTERVAL '{period}'
    GROUP BY developer_id
),
cycle_times AS (
    SELECT po.developer_id,
           AVG(EXTRACT(EPOCH FROM (pm.occurred_at - po.occurred_at)) / 3600) AS avg_cycle_h
    FROM developer_output_events po
    JOIN developer_output_events pm ON pm.repo = po.repo AND pm.pr_number = po.pr_number
                                    AND pm.event_type = 'pr_merged'
    WHERE po.event_type = 'pr_opened'
      AND po.occurred_at >= NOW() - INTERVAL '{period}'
    GROUP BY po.developer_id
)
SELECT
    c.adoption,
    AVG(ct.avg_cycle_h) AS avg_pr_cycle_hours,
    AVG(s.quality_score) AS avg_session_quality,
    AVG(s.avg_inter_request_s) AS avg_thinking_time_s
FROM cohorts c
JOIN sessions s ON s.developer_id = c.developer_id
    AND s.first_request_at >= NOW() - INTERVAL '{period}'
LEFT JOIN cycle_times ct ON ct.developer_id = c.developer_id
GROUP BY c.adoption
```

---

### GenAI metrics requiring external APIs

| Metric | API needed | Data to collect |
|---|---|---|
| **Accepted Code Completion Suggestions** | GitHub Copilot API (`/copilot/usage`) | `acceptances_count`, `suggestions_count` per user per day |
| **Developers per Product (Copilot vs. Claude vs. other)** | Gateway covers Claude; Copilot needs its own API | Poll GitHub Copilot Business seats endpoint |
| **Qodo Gen: Impacted PRs** | Qodo webhook/API | Qodo review events per PR |
| **Qodo Gen: Impacted LOCs** | Qodo API | LOC attribution from Qodo |

For Copilot specifically: the integration token was defined in `docs/mstone-ai-docs/integration-instructions/github-and-copilot/github-copilot-token.md`. A scheduled poller calling `GET /orgs/{org}/copilot/usage` would fill the gap and store results in a new `copilot_usage_log` table.

---

## 5. Implementation priority

### Phase 1 — no new data collection (computable now)
| Metric | Status |
|---|---|
| PR Size | ✅ |
| Code Changes volume | ✅ |
| Review Depth (submissions only) | ✅ |
| Pickup Time | ✅ |
| Review Time | ✅ |
| PR Cycle Time | ✅ |
| Coding Time (AI proxy) | ✅ |
| Productiveness Score (session quality) | ✅ |
| All GenAI Adoption metrics | ✅ |
| Commits Impacted by GenAI | ✅ |
| Productivity Impact (cohort comparison) | ✅ |
| Investment by Work Type (intent-based) | ✅ |
| Engineering Effort Overview (AI cost proxy) | ✅ |
| Wasted Spend (idle repos) | ✅ |

### Phase 2 — store PR timestamps properly
**Change needed:** In `github_webhook.py`, extract and store `pr.created_at` and `pr.merged_at` from the webhook payload as typed columns. Add to `developer_output_events`:
```sql
ALTER TABLE developer_output_events
  ADD COLUMN IF NOT EXISTS event_at TIMESTAMPTZ;  -- actual GitHub event time
```
Use `event_at` instead of `occurred_at` (insert time) for cycle time calculations.

### Phase 3 — add deployment webhook
Subscribe to `deployment_status` GitHub webhook. Store in a new `deployment_events` table:
```sql
CREATE TABLE deployment_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo TEXT NOT NULL,
    environment TEXT NOT NULL,
    state TEXT NOT NULL,       -- 'success', 'failure', 'error'
    sha TEXT,                  -- commit SHA being deployed
    developer_id UUID REFERENCES developers(id),
    deployed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```
Unlocks: Deployment Frequency, Lead Time for Changes, Change Failure Rate, MTTR.

### Phase 4 — Jira webhook
Store in new `pm_events` table: issue created/started/resolved, story points, issue type, linked PRs.
Unlocks: Lead Time (PM→deploy), Completed Backlog Stories, Bug Density, Issues out of SLA, Coding Time vs. Estimated.

### Phase 5 — GitHub Copilot API poller
Scheduled job calling the Copilot Business usage API. Store per-user daily: suggestions shown, accepted, active users.
Unlocks: Accepted Code Completion Suggestions, Developers per Product (Copilot).
