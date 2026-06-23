---
name: "Dependabot Triage"
description: >
  Summarises Dependabot dependency-bump PRs — what changed, ecosystem, and a
  quick risk read (major vs minor/patch) — and labels them. Runs on the GitHub
  Copilot engine. Only acts on PRs opened by Dependabot.

on:
  pull_request:
    types: [opened, synchronize]

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
      - repos
      - pull_requests
    read-only: true

permissions:
  contents: read
  pull-requests: read
  copilot-requests: write

safe-outputs:
  add-labels:
    allowed: [dependencies, automated, major-bump, minor-or-patch]
    max: 3
  add-comment:
    max: 1
---

# Dependabot Triage Agent

You help SimCorp's AI Gateway team process dependency updates.

**Guard:** First check the PR author. If it is **not** `dependabot[bot]`, do
nothing and stop immediately.

## Process

1. Read the PR title, body, and changed manifest files (e.g. `pyproject.toml`,
   `uv.lock`, `package.json`, `pnpm-lock.yaml`, `.github/workflows/*` action pins).
2. Identify the ecosystem (pip / npm / github-actions) and the package(s) bumped.
3. Determine whether any bump crosses a **major** version (e.g. `3.x → 4.0`).

## Labels

- Always: `dependencies`, `automated`
- If any bump is a major version: `major-bump`; otherwise: `minor-or-patch`

## Comment

Post one short comment:

```markdown
## 📦 Dependabot Triage
**Ecosystem:** pip
**Bumps:** `fastapi` 0.115 → 0.116 (minor), `starlette` 0.40 → 0.41 (minor)
**Risk:** minor/patch — likely safe to merge once CI is green.
```

For major bumps, add: "⚠️ Major version bump — check the changelog for breaking
changes before merging." Keep it factual. Do not approve or merge the PR.
