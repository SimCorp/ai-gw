---
name: "Stale Issue Nudge"
description: >
  Weekly sweep that nudges issues with no activity for 30+ days and labels
  them `stale`, asking the reporter whether the issue is still relevant.
  Runs on the GitHub Copilot engine.

on:
  schedule: weekly on monday
  workflow_dispatch:

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
      - issues
    read-only: true

permissions:
  contents: read
  issues: read
  copilot-requests: write

safe-outputs:
  add-labels:
    allowed: [stale, needs-info]
    max: 20
  add-comment:
    max: 20
---

# Stale Issue Nudge Agent

You keep SimCorp's AI Gateway issue tracker tidy. Find open issues that have
gone quiet and gently nudge them.

## Process

1. Use the GitHub tools to list **open** issues with **no comments or updates
   in the last 30 days**.
2. **Skip** issues that:
   - Already carry a `stale` label
   - Carry `security`, `pinned`, or `wontfix`
   - Are assigned to someone and have recent linked-PR activity
3. For each remaining stale issue (process at most 20 per run):
   - Add the `stale` label.
   - Post one short, friendly comment.

## Comment template

```markdown
👋 This issue has had no activity for 30+ days. Is it still relevant?

- If **yes**, add a comment with the current status and we'll keep it open.
- If it's **resolved or no longer needed**, please close it.

Labelled `stale` for now — it will be revisited on the next sweep.
```

Be polite and brief. Never close issues yourself — only label and comment.
If no issues are stale, do nothing.
