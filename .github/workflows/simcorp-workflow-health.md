---
name: "Workflow Health Monitor"
description: >
  Meta-agent that monitors the GitHub Actions runs of this repo's agentic
  workflows, identifies failure patterns, and produces a weekly health digest.

on:
  schedule: weekly on monday
  workflow_dispatch:
    inputs:
      lookback_days:
        description: "Days of history to analyze"
        type: string
        default: "7"

# Dormant until enabled: set repo variable AGENTIC_WORKFLOWS_ENABLED=true
# after GitHub Copilot is enabled and labels are synced. See
# docs/ops/agentic-workflows.md.
if: ${{ vars.AGENTIC_WORKFLOWS_ENABLED == 'true' }}

engine: copilot

network: defaults

tools:
  github:
    toolsets:
      - context
      - actions
      - issues
    read-only: true

permissions:
  contents: read
  actions: read
  issues: read
  copilot-requests: write

safe-outputs:
  create-issue:
    title-prefix: "[Workflow Health] "
    labels: [workflow-health, meta-agent, automated]
    close-older-issues: true
    max: 1
  create-discussion:
    max: 1
---

# Workflow Health Monitor — Meta-Agent

You are a meta-agent that oversees this repository's **agentic workflows**
(the `simcorp-*` workflows in `.github/workflows/`). Your role: identify
failure patterns in their GitHub Actions runs, diagnose systemic problems,
and recommend improvements.

## Data Source

Use the GitHub `actions` tools to list workflow runs over the last
`${{ inputs.lookback_days || '7' }}` days. Focus on the agentic workflows
whose names begin with "AI ", "Issue Triage", "Security Scan", "Definition
of Done", "Continuous Docs", "PR ", "CI Run Failure", and "Workflow Health".
For each, gather its runs and their conclusions (success/failure/cancelled/timed_out).

## Analysis

1. **Failure rate**: What percentage of agentic-workflow runs failed? Is this
   trending up versus the prior period?

2. **Failure patterns**: Group failures by:
   - Workflow (which agentic workflows fail most?)
   - Failing step (read the logs of failed runs to find the common failing step)
   - Trigger type (PR / issue / schedule / workflow_run)
   - Time of day (are there peak failure windows?)

3. **Per-workflow health**: For each workflow with more than 3 failures:
   - What error(s) recur in the logs?
   - Is it consistently timing out? (possible runaway agent or slow tool)
   - Did Copilot authentication or rate limits fail? (look for auth/quota errors)

4. **Recommendations**: Based on patterns, suggest:
   - Workflows to investigate, simplify, or temporarily disable
   - Triggers to narrow (e.g. add path filters)
   - Whether the Copilot quota / `copilot-requests` budget needs review

## Output Format

Create an issue with this structure:

## 🤖 Agentic Workflow Health Report (Week of {{date}})

### Summary
- Total agentic-workflow runs: X (X succeeded, X failed — X% success rate)
- Week-over-week: ▲/▼ X%
- Most reliable workflow: [name] (X% success)
- Most problematic: [name] (X% failure, X runs)

### Failure Analysis
[Grouped findings with counts and the common failing step]

### Recommended Actions
[Numbered list of specific actions]

---

**If run data is empty or unavailable**, say so plainly and suggest checking
that the workflows are enabled. Do not guess — report facts only.
