---
name: "Security Scan via AI Guardrails"
description: >
  Runs the AI Gateway's guardrails service against every PR diff to detect
  security issues. Produces SARIF findings for GitHub's Security tab.
  Only triggers for PRs from within the SimCorp org.

on:
  pull_request:
    types: [opened, synchronize]
    forks: ["SimCorp/*"]
  roles: [write, maintain, admin]
  skip-if-check-failing: false

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
      - repos
      - pull_requests
    read-only: true

permissions:
  contents: read
  pull-requests: read
  security-events: read

safe-outputs:
  create-code-scanning-alert:
    max: 20
  add-labels:
    allowed: [security-reviewed, security-concern, secrets-detected]
    max: 2
  add-comment:
    max: 1

threat-detection:
  post-steps:
    - name: TruffleHog secret scan
      run: |
        trufflehog git file://. --since-commit HEAD~1 --only-verified \
          --json > /tmp/trufflehog_output.json 2>/dev/null || true
    - name: Semgrep SAST
      run: |
        semgrep --config=p/security-audit --config=p/secrets \
          --json --output /tmp/semgrep_output.json . 2>/dev/null || true

pre-agent-steps:
  - name: Fetch active guardrails config
    run: |
      curl -sf \
        -H "Authorization: Bearer ${{ secrets.AIGW_API_KEY }}" \
        "${{ vars.AIGW_BASE_URL_ADMIN }}/guardrails?enabled=true" \
        -o /tmp/guardrails_config.json || echo '[]' > /tmp/guardrails_config.json
  - name: Run guardrails scan on diff
    run: |
      # Fetch the PR diff and send it through the guardrails endpoint
      curl -sf \
        -H "Authorization: Bearer ${{ secrets.AIGW_API_KEY }}" \
        -H "Content-Type: application/json" \
        -d "{\"input\": \"$(git diff HEAD~1 HEAD | base64 -w0)\"}" \
        "${{ vars.AIGW_BASE_URL_ADMIN }}/guardrails/scan" \
        -o /tmp/guardrail_hits.json 2>/dev/null || echo '[]' > /tmp/guardrail_hits.json
---

# Security Scan Agent

You are a security-focused code review agent for SimCorp's AI Gateway.

## Data Sources

- /tmp/guardrails_config.json — the active guardrail rules for this repo
- /tmp/guardrail_hits.json — results from the Gateway's guardrail scan on the diff
- /tmp/trufflehog_output.json — TruffleHog secret detection results
- /tmp/semgrep_output.json — Semgrep SAST findings

Use the GitHub tools to read the full PR diff and understand the context.

## Your Analysis

1. **Secrets detection** — Review TruffleHog output. Any verified finding
   is a CRITICAL issue that MUST block the PR.

2. **Guardrail violations** — Review the Gateway guardrail hits. Each hit
   represents a pattern the SimCorp security team has flagged as dangerous.
   Classify by severity (critical/high/medium/low from the guardrail config).

3. **SAST findings** — Review Semgrep output. Focus on:
   - SQL injection (`python.lang.security.sqlalchemy-execute-raw-query`)
   - Command injection (`python.lang.security.audit.subprocess-shell-true`)
   - Hardcoded passwords (`python.lang.security.hardcoded-password`)
   - SSRF (`python.requests.security.ssrf`)

4. **AI Gateway-specific checks** — Read the diff for:
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
