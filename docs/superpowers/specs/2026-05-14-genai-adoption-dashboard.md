# GenAI Adoption Dashboard — Feature Spec

**Date:** 2026-05-14
**Status:** Draft — pending approval
**Audience:** Engineering leadership, team leads, platform/DevOps, finance

---

## 1. Problem

SimCorp has deployed AI coding tools (Claude Code, GitHub Copilot, etc.) to ~2000 engineers through the AI Gateway. Usage data is already flowing through the observability pipeline and stored in Postgres, but there is no surface in the admin portal that shows _who_ is using AI tools, _how effectively_, or _what impact_ they are having on engineering output. Leadership cannot currently answer "is our GenAI investment paying off?"

---

## 2. Goal

Add a **"GenAI Adoption"** section to the admin portal that presents three sequential views:

| Tab | Question it answers |
|---|---|
| **1. Adoption** | Who is using AI tools, at what frequency, and which teams are lagging? |
| **2. Productivity** | Are AI users completing work faster and with fewer retries than non-users? |
| **3. Code Quality** | Are AI-assisted sessions producing more reliable, lower-error output? |

---

## 3. Data Available (no new ingestion required)

All metrics below are derivable from data already stored:

| Table | Relevant columns |
|---|---|
| `developer_activity_log` | `developer_id`, `date`, `request_count`, `cost_usd`, `cache_hits`, `tool_invocations`, `error_count` |
| `sessions` | `developer_id`, `team_id`, `turn_count`, `quality_score`, `retry_count`, `error_count`, `avg_inter_request_s`, `dominant_intent`, `repo` |
| `cost_records` | `model`, `tokens_input`, `tokens_output`, `cache_hit`, `latency_ms`, `session_trace_id` |
| `api_keys` | `developer_id`, `team_id` |

---

## 4. Backend — New API Endpoints

A new router is added to the **admin service** (`services/admin`) at the prefix `/genai-adoption`. All endpoints require admin JWT auth (same pattern as existing admin routes). All return JSON.

### 4.1 Adoption endpoints

```
GET /genai-adoption/adoption/summary
```
Returns org-level adoption rate, active user count (last 30 days), and usage frequency distribution.

Response shape:
```json
{
  "period_days": 30,
  "total_licensed_developers": 2000,
  "active_users": 1240,
  "adoption_rate_pct": 62.0,
  "frequency_buckets": {
    "rare": 310,
    "occasional": 480,
    "regular": 450
  }
}
```

Frequency buckets:
- **Rare** — 1–3 active days in period
- **Occasional** — 4–14 active days
- **Regular** — 15+ active days

```
GET /genai-adoption/adoption/by-team?period_days=30
```
Same metrics broken down per team. Used to populate the team-level table and identify low-adoption groups.

```
GET /genai-adoption/adoption/trend?period_days=90&granularity=week
```
Weekly active user count over the past 90 days. Used for the trend sparkline.

---

### 4.2 Productivity endpoints

```
GET /genai-adoption/productivity/summary?period_days=30
```
Compares avg session quality score and avg inter-request time between:
- **High-adoption** cohort (≥15 active days)
- **Low-adoption** cohort (<4 active days)

Response shape:
```json
{
  "high_adoption": {
    "avg_quality_score": 3.9,
    "avg_inter_request_s": 145,
    "avg_turn_count": 6.2,
    "avg_tool_invocations": 4.1,
    "session_count": 8420
  },
  "low_adoption": {
    "avg_quality_score": 2.8,
    "avg_inter_request_s": 62,
    "avg_turn_count": 4.1,
    "avg_tool_invocations": 1.2,
    "session_count": 3210
  }
}
```

```
GET /genai-adoption/productivity/by-team?period_days=30
```
Same breakdown per team — used to rank teams by productivity delta.

```
GET /genai-adoption/productivity/trend?period_days=90&granularity=week
```
Weekly avg quality score trend for the high-adoption cohort.

---

### 4.3 Code quality endpoints

```
GET /genai-adoption/quality/summary?period_days=30
```
Error and retry rates by adoption cohort:

```json
{
  "high_adoption": {
    "avg_error_rate_pct": 4.1,
    "avg_retry_rate_pct": 6.3,
    "cache_hit_rate_pct": 38.0
  },
  "low_adoption": {
    "avg_error_rate_pct": 9.8,
    "avg_retry_rate_pct": 14.2,
    "cache_hit_rate_pct": 12.0
  }
}
```

```
GET /genai-adoption/quality/by-team?period_days=30
```
Per-team error and retry rates. Used to surface teams with elevated error rates despite high adoption (potential quality risk).

```
GET /genai-adoption/quality/trend?period_days=90&granularity=week
```
Weekly error rate trend, split by cohort.

---

## 5. Frontend — Admin Portal Pages

### Navigation

Add a new **"Measure"** section to the sidebar in `apps/admin/app/admin/layout.tsx`, between "Operate" and the sign-out button:

```
Measure
  └─ GenAI Adoption ✦
```

Route: `/admin/genai-adoption`

### Page structure

`apps/admin/app/admin/genai-adoption/page.tsx` — parent page with three tabs.

```
/admin/genai-adoption               → defaults to tab 1 (Adoption)
/admin/genai-adoption?tab=productivity
/admin/genai-adoption?tab=quality
```

Each tab renders its own component:

| File | Tab |
|---|---|
| `_components/AdoptionTab.tsx` | Adoption |
| `_components/ProductivityTab.tsx` | Productivity |
| `_components/QualityTab.tsx` | Code Quality |

### 5.1 Adoption Tab

- **Headline KPIs** (3 stat cards): Active users / Total licensed, Adoption rate %, Regular users %
- **Trend chart**: Weekly active users over 90 days (line chart)
- **Frequency donut**: Rare / Occasional / Regular breakdown
- **Team table**: Team name, Active users, Adoption %, Frequency distribution bar, delta vs. last period

### 5.2 Productivity Tab

- **Cohort comparison cards**: High-adoption vs. low-adoption side-by-side for quality score, avg inter-request time, avg turns per session
- **Interpretation callout**: e.g. "High-adoption developers spend 2.3× longer applying AI output between requests — a signal of effective usage"
- **Team table**: Team name, Avg quality score, Avg inter-request time, Avg turns — sortable

### 5.3 Code Quality Tab

- **Headline KPIs**: Error rate delta (high vs. low adoption), Retry rate delta, Cache hit rate delta
- **Trend chart**: Weekly error rate for high-adoption vs. low-adoption cohorts (dual-line)
- **Team table**: Team name, Error rate %, Retry rate %, Cache hit %, flag icon if error rate > 10%

### Period selector

Global dropdown at top-right of the page: **Last 7 days / 30 days / 90 days**. Updates all three tabs simultaneously via query param.

---

## 6. Data / Query Notes

- **Active developer count denominator**: query `api_keys` table for distinct `developer_id` values with `is_active = true`. This is the "licensed" base.
- **Cohort assignment**: done at query time by counting active days in `developer_activity_log` for the selected period. Not materialized — recomputed per request (fast at current data volume).
- **No new Postgres tables required** for MVP.
- **Caching**: responses cached in Redis with a 15-minute TTL using the same pattern as other admin endpoints. Key format: `genai-adoption:{endpoint}:{period_days}`.

---

## 7. Access Control

| Role | Access |
|---|---|
| Admin | Full access — all three tabs, all teams |
| Group Manager | Scoped to their groups only |
| Team Lead | Scoped to their teams only |
| Viewer | Read-only, same scoping as Team Lead |

Scoping is enforced server-side in the API endpoints using the existing JWT claims pattern.

---

## 8. Implementation Phases

| Phase | Scope | Estimated effort |
|---|---|---|
| **1 — Backend** | 9 new endpoints in admin service, Redis caching, SQL queries | ~1 day |
| **2 — Frontend shell** | Page, tab routing, period selector, shared layout | ~0.5 day |
| **3 — Adoption tab** | KPI cards, trend chart, frequency donut, team table | ~0.5 day |
| **4 — Productivity tab** | Cohort comparison cards, team table | ~0.5 day |
| **5 — Quality tab** | KPI cards, dual-line trend, team table with error flags | ~0.5 day |
| **6 — Tests** | Backend unit tests for SQL queries + API responses; frontend smoke tests | ~0.5 day |

---

## 9. Out of Scope (for this iteration)

- GitHub Copilot API integration (acceptance rate, suggestions shown) — requires external token; tracked separately
- Qodo Gen metrics — not yet connected to the gateway
- PDF/CSV export — follow-on feature
- Individual developer drill-down — privacy consideration; defer pending policy decision
- Historical comparison to pre-AI-gateway baseline — no data before gateway deployment

---

## 10. Open Questions

1. Should adoption rate denominator be total headcount (from HR list) or active API key holders? → Recommend active key holders for MVP; add HR list join in v2.
2. Do we gate individual developer views behind an additional role check, or exclude entirely for v1?
3. 15-minute Redis cache TTL acceptable for leadership dashboards, or do we need near-real-time?
