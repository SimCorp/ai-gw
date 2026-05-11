---
name: "Weekly AI Cost Chargeback Report"
description: >
  Produces a weekly cost report for all teams using the AI Gateway.
  Published as a GitHub Discussion (or issue) every Monday for finance
  visibility. Routes through the AI Gateway.

on:
  schedule: weekly on monday around 09:00 UTC

engine:
  id: codex
  model: claude-haiku-4-5
  env:
    OPENAI_BASE_URL: ${{ vars.AIGW_BASE_URL }}
    OPENAI_API_KEY: ${{ secrets.AIGW_API_KEY }}

network:
  allowed:
    - defaults
    - aigw.simcorp.internal

tools:
  github:
    toolsets:
      - context
    read-only: true

permissions:
  contents: read
  discussions: read

safe-outputs:
  create-issue:
    title-prefix: "[Weekly AI Cost Report] "
    labels: [cost-report, chargeback, automated]
    close-older-issues: true
    max: 1

pre-agent-steps:
  - name: Fetch weekly cost data
    run: |
      curl -sf \
        -H "Authorization: Bearer ${{ secrets.AIGW_API_KEY }}" \
        "${{ vars.AIGW_BASE_URL_ADMIN }}/reports/costs?period=7d" \
        -o /tmp/weekly_costs.json || echo '{}' > /tmp/weekly_costs.json
      curl -sf \
        -H "Authorization: Bearer ${{ secrets.AIGW_API_KEY }}" \
        "${{ vars.AIGW_BASE_URL_ADMIN }}/reports/costs?period=14d" \
        -o /tmp/prior_week_costs.json || echo '{}' > /tmp/prior_week_costs.json
      curl -sf \
        -H "Authorization: Bearer ${{ secrets.AIGW_API_KEY }}" \
        "${{ vars.AIGW_BASE_URL_ADMIN }}/dashboard/stats" \
        -o /tmp/dashboard_stats.json || echo '{}' > /tmp/dashboard_stats.json
---

# Weekly AI Cost Chargeback Report Agent

You are a cost analytics agent for SimCorp's AI Gateway platform.

Generate a comprehensive weekly cost report for the finance team and
engineering leadership. Cost data is in:
- /tmp/weekly_costs.json — this week's spend
- /tmp/prior_week_costs.json — last week's spend (for trend comparison)
- /tmp/dashboard_stats.json — cache hit rates and aggregate stats

Structure the report as follows:

## 📊 AI Gateway — Weekly Cost Report (Week of {{date}})

### Executive Summary
- Total spend this week: $X.XX
- Week-over-week change: ▲/▼ X% (+/-$X.XX)
- Total requests: X,XXX
- Cache hit rate: XX% (saving ~$X.XX in provider costs)

### Team Breakdown
| Team | Project | Requests | Input Tokens | Output Tokens | Cost | vs Last Week |
|------|---------|----------|-------------|--------------|------|-------------|
| ...  | ...     | ...      | ...         | ...          | $X   | ▲/▼ X%     |

### Model Usage
| Model | Requests | Cost | % of Total |
|-------|----------|------|-----------|
| ...   | ...      | $X   | XX%       |

### Cache Performance
- Exact cache hits: X (saving $X.XX)
- Semantic cache hits: X (saving $X.XX)
- Total savings via cache: $X.XX

### Month-to-Date
- MTD spend: $X.XX
- Monthly budget: $X.XX
- Remaining: $X.XX (XX% used, XX days remaining)
- Projected month-end: $X.XX

### Notes
Any unusual spikes, new teams, or notable changes this week.

Use real numbers from the data files. If data is unavailable for a section,
note "data unavailable" rather than omitting the section.
Format all costs to 2 decimal places.
