---
name: "Workflow Health Monitor"
description: >
  Meta-agent that monitors all AI Gateway workflow runs, identifies
  failure patterns, and produces a weekly health digest. Implements
  the meta-agent oversight pattern from Peli's Agent Factory.

on:
  schedule: weekly on monday around 07:00 UTC
  workflow_dispatch:
    inputs:
      lookback_days:
        description: "Days of history to analyze"
        type: string
        default: "7"

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
      - issues
    read-only: true

permissions:
  contents: read
  issues: read
  discussions: read

safe-outputs:
  create-issue:
    title-prefix: "[Workflow Health] "
    labels: [workflow-health, meta-agent, automated]
    close-older-issues: true
    max: 1
  create-discussion:
    max: 1

pre-agent-steps:
  - name: Fetch workflow run statistics
    run: |
      DAYS="${{ inputs.lookback_days || '7' }}"
      # Fetch failed runs
      curl -sf \
        -H "Authorization: Bearer ${{ secrets.AIGW_API_KEY }}" \
        "${{ vars.AIGW_BASE_URL_ADMIN }}/runs?status=failed&limit=50" \
        -o /tmp/failed_runs.json || echo '[]' > /tmp/failed_runs.json
      # Fetch succeeded runs
      curl -sf \
        -H "Authorization: Bearer ${{ secrets.AIGW_API_KEY }}" \
        "${{ vars.AIGW_BASE_URL_ADMIN }}/runs?status=succeeded&limit=50" \
        -o /tmp/succeeded_runs.json || echo '[]' > /tmp/succeeded_runs.json
      # Fetch all agents
      curl -sf \
        -H "Authorization: Bearer ${{ secrets.AIGW_API_KEY }}" \
        "${{ vars.AIGW_BASE_URL_ADMIN }}/agents" \
        -o /tmp/agents.json || echo '{"agents":[]}' > /tmp/agents.json
      # Gateway system health
      curl -sf \
        -H "Authorization: Bearer ${{ secrets.AIGW_API_KEY }}" \
        "${{ vars.AIGW_BASE_URL_ADMIN }}/system/health" \
        -o /tmp/system_health.json || echo '{}' > /tmp/system_health.json
---

# Workflow Health Monitor — Meta-Agent

You are a meta-agent that oversees all AI Gateway workflow executions.
Your role: identify patterns, diagnose systemic problems, and recommend
improvements to the workflow infrastructure.

## Data Sources

- /tmp/failed_runs.json — recent failed workflow runs
- /tmp/succeeded_runs.json — recent successful workflow runs
- /tmp/agents.json — registered agents
- /tmp/system_health.json — gateway system health

## Analysis

1. **Failure rate**: What percentage of runs failed? Is this trending up?

2. **Failure patterns**: Group failures by:
   - Agent slug (which agents fail most?)
   - Error type (timeout / threat-detection-blocked / runtime-error / dag-error)
   - Workflow ID (which workflows are most unreliable?)
   - Time of day (are there peak failure windows?)

3. **Agent health**: For each agent with > 3 failures:
   - What errors did it produce?
   - Is it consistently timing out? (possible performance regression)
   - Did it trigger threat-detection-blocked? (possible prompt injection / compromise)

4. **Infrastructure signals**: From system health:
   - Is Redis latency elevated? (may explain timeout patterns)
   - Are any services degraded?
   - Is the worker concurrency saturated?

5. **Recommendations**: Based on patterns, suggest:
   - Agents to investigate or disable
   - Workflows to simplify or split
   - Infra changes (increase worker concurrency, reduce timeouts)
   - Guardrail tuning (if too many false positives in threat-detection)

## Output Format

Create an issue with this structure:

## 🤖 AI Gateway Workflow Health Report (Week of {{date}})

### Summary
- Total runs: X (X succeeded, X failed — X% success rate)
- Week-over-week: ▲/▼ X%
- Most reliable agent: [slug] (X% success)
- Most problematic: [slug] (X% failure, X runs)

### Failure Analysis
[Grouped findings with counts]

### Threat Detection Events
[Any runs blocked by threat-detection — these need human review]

### Infrastructure Health
[Redis, worker, provider status summary]

### Recommended Actions
[Numbered list of specific actions]

---

**If runs data is empty or unavailable**, report that the monitoring
endpoint was unreachable and suggest checking the admin service health.
Do not guess — report facts only.
