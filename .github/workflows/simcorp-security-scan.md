---
name: "Security Scan"
description: >
  Runs TruffleHog (secret detection) and Semgrep (SAST) against every PR diff,
  then has the agent review the findings and the diff and produce code-scanning
  alerts. Runs on the GitHub Copilot engine. Org PRs only.

on:
  pull_request:
    types: [opened, synchronize]
    forks: ["SimCorp/*"]
  roles: [write, maintain, admin]

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
  security-events: read
  copilot-requests: write

safe-outputs:
  create-code-scanning-alert:
    max: 20
  add-labels:
    allowed: [security-reviewed, security-concern, secrets-detected]
    max: 2
  add-comment:
    max: 1

pre-agent-steps:
  - name: TruffleHog secret scan
    run: |
      mkdir -p /tmp/gh-aw/agent
      pipx run trufflehog3 --no-history --format json \
        --output /tmp/gh-aw/agent/trufflehog_output.json . \
        2>/dev/null || echo '[]' > /tmp/gh-aw/agent/trufflehog_output.json
      echo "TruffleHog findings written to /tmp/gh-aw/agent/trufflehog_output.json"
  - name: Semgrep SAST
    run: |
      mkdir -p /tmp/gh-aw/agent
      pipx run semgrep --config=p/security-audit --config=p/secrets \
        --json --output /tmp/gh-aw/agent/semgrep_output.json . \
        2>/dev/null || echo '{}' > /tmp/gh-aw/agent/semgrep_output.json
      echo "Semgrep findings written to /tmp/gh-aw/agent/semgrep_output.json"
---

# Security Scan Agent

You are a security-focused code review agent for SimCorp's AI Gateway.

## Data Sources

- /tmp/gh-aw/agent/trufflehog_output.json — TruffleHog secret detection results
- /tmp/gh-aw/agent/semgrep_output.json — Semgrep SAST findings

Use the GitHub tools to read the full PR diff and understand the context.

## Your Analysis

1. **Secrets detection** — Review TruffleHog output. Any verified finding
   is a CRITICAL issue that MUST block the PR.

2. **SAST findings** — Review Semgrep output. Focus on:
   - SQL injection (`python.lang.security.sqlalchemy-execute-raw-query`)
   - Command injection (`python.lang.security.audit.subprocess-shell-true`)
   - Hardcoded passwords (`python.lang.security.hardcoded-password`)
   - SSRF (`python.requests.security.ssrf`)

3. **AI Gateway-specific checks** — Read the diff for:
   - Missing `revoked_at` checks on API key lookups
   - Direct SQL strings in asyncpg calls (should use `$N` params)
   - `DEV_BYPASS_AUTH` checks outside of dev/test/ci environments
   - Agent image strings not validated against the registry pattern

## Output

For each finding, create a code scanning alert with:
- `rule-id`: e.g. `guardrail/pii-detector`, `semgrep/injection`, `secret/api-key`
- `severity`: critical | high | medium | low
- `location`: file path + line number
- `message`: what the issue is and how to fix it

Also add a summary comment to the PR with the total finding count and
whether the PR can proceed.

If no issues found, comment "✅ Security scan passed — no issues found" and
add the `security-reviewed` label.
