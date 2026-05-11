---
name: "Daily Budget Alerts"
description: >
  Checks AI Gateway team budgets daily and creates a GitHub issue if any team
  exceeds 80% of their monthly budget. Prevents duplicate alerts via
  skip-if-match. Routes through the AI Gateway.

on:
  schedule: daily around 08:00 UTC
skip-if-match: 'is:issue is:open label:budget-alert in:title "[Budget Alert]"'

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
  issues: read

safe-outputs:
  create-issue:
    title-prefix: "[Budget Alert] "
    labels: [budget-alert, cost-tracking]
    max: 1
  add-comment:
    max: 1

pre-agent-steps:
  - name: Fetch Gateway budget status
    id: budget
    run: |
      curl -sf \
        -H "Authorization: Bearer ${{ secrets.AIGW_API_KEY }}" \
        "${{ vars.AIGW_BASE_URL_ADMIN }}/budget/status" \
        -o /tmp/budget_status.json || echo '{}' > /tmp/budget_status.json
      echo "budget_data=$(cat /tmp/budget_status.json | base64 -w0)" >> "$GITHUB_OUTPUT"
  - name: Fetch Gateway org settings
    run: |
      curl -sf \
        -H "Authorization: Bearer ${{ secrets.AIGW_API_KEY }}" \
        "${{ vars.AIGW_BASE_URL_ADMIN }}/budget/forecast" \
        -o /tmp/budget_forecast.json || echo '{}' > /tmp/budget_forecast.json
---

# Budget Alert Agent

You are a cost governance agent for SimCorp's AI Gateway platform.

The AI Gateway serves ~2000 engineers across multiple teams. Each team has
a monthly budget cap. Your job is to produce a daily budget alert when
teams are approaching or exceeding their limits.

Budget data is available in /tmp/budget_status.json and
/tmp/budget_forecast.json. Read them to understand the current state.

Create a GitHub issue ONLY if:
- At least one team has consumed ≥ 80% of their monthly budget, OR
- The organisation's total spend is ≥ 75% of the org-level budget ceiling

The issue should contain:
1. **Alert summary** — which teams are over threshold
2. **Budget table** — all teams with name, spent, limit, percentage, status
3. **Cache savings** — how many tokens were served from cache (not billed)
4. **Projected month-end** — estimated total cost if current rate continues
5. **Recommended actions** — increase limit, restrict models, or notify team lead

Format all monetary values as USD. Use 🟢 / 🟡 / 🔴 emoji for
under 60% / 60-80% / over 80% respectively.

If no team is over threshold, respond with "noop" — do not create an issue.
