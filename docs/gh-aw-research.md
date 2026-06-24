# GitHub Agentic Workflows (gh-aw) — Research Report

> **Superseded for the live setup — see [`docs/ops/agentic-workflows.md`](ops/agentic-workflows.md).**
> This report proposed routing inference through the AI Gateway (`codex` engine).
> The gateway is internal-only and unreachable from GitHub-hosted runners, so the
> active workflows now run on the **GitHub Copilot engine** with GitHub data only.
> This document is retained for the trigger/output/security-model reference and the
> (still-deferred) gateway-routed design.

> Source: https://github.github.com/gh-aw/  
> Researched: 2026-05-11  
> Context: AI Gateway integration opportunities for SimCorp

## What gh-aw Is

GitHub Agentic Workflows (gh-aw) is a GitHub Next / Microsoft Research project that runs AI agent execution natively inside GitHub Actions. Installed as a single GitHub CLI extension (`gh extension install github/gh-aw`), it lets you define AI-powered automation as **Markdown files with YAML frontmatter** in `.github/workflows/*.md`.

Key design principle: **read-agent-write-separate architecture** — the AI agent runs with read-only tokens, produces `agent_output.json`, and a completely separate job with scoped write permissions applies the output only after an AI-powered threat detection scan passes. The agent can never write directly to GitHub.

---

## BYO Model (Routing via the AI Gateway)

```yaml
engine:
  id: codex
  model: claude-sonnet-4-6
  env:
    OPENAI_BASE_URL: ${{ vars.AIGW_BASE_URL }}   # https://aigw.simcorp.internal/v1
    OPENAI_API_KEY:  ${{ secrets.AIGW_API_KEY }}

network:
  allowed:
    - defaults
    - aigw.simcorp.internal
```

All model calls flow through `cache:8002 → litellm:8003 → provider`, inheriting:
- Semantic caching (repeated queries cached)
- Cost attribution (billed to `github-automation` team)
- Guardrails (content filtering)
- Rate limiting (per-team quota)
- Audit trail (full observability)

---

## All Trigger Types

| Category | Triggers |
|---|---|
| PR events | `pull_request` (opened, synchronize, labeled, etc.) |
| Issues | `issues` (opened, labeled, edited, etc.) |
| Comments | `issue_comment`, `pull_request_review_comment` |
| Scheduled | `schedule` (daily/weekly, fuzzy or cron + timezone) |
| Manual | `workflow_dispatch` (typed inputs), `slash_command`, `label_command` |
| CI events | `workflow_run` (completed, with conclusion filters) |
| Discussions | `discussion`, `discussion_comment` |
| Push | `push` (branch + path filters) |
| Deployments | `deployment_status` |

Execution modifiers: `skip-if-match`, `skip-if-check-failing`, `roles`, `stop-after`, `manual-approval`.

---

## All Output Types (40+)

**Issues/Discussions:** create-issue, update-issue, close-issue, create-discussion  
**PRs:** create-pull-request, update-pull-request, submit-pull-request-review, push-to-pull-request-branch  
**Comments/Labels:** add-comment, add-labels, remove-labels, add-reviewer  
**Projects:** create-project, create-project-status-update (ON_TRACK/AT_RISK/OFF_TRACK)  
**Security:** create-code-scanning-alert (SARIF), autofix-code-scanning-alert  
**Orchestration:** dispatch-workflow, call-workflow, assign-to-agent (hand off to Copilot coding agent)

---

## 5-Layer Security Model

1. **Read-only agent token** — agent never receives write credentials
2. **Zero secrets in agent env** — write tokens only in separate safe-output jobs
3. **Network isolation** — Squid proxy enforces domain allowlist; unlisted domains blocked
4. **Safe output gating** — artifact buffering; separate job applies outputs
5. **AI threat detection** — scans for prompt injection, secret leaks, malicious patches before any write

---

## 8 Workflows for the AI Gateway

| ID | Name | Trigger | Gateway Services | Effort | Phase |
|---|---|---|---|---|---|
| W1 | PR Code Review + CodeMate | `pull_request` opened/sync | cache:8002, /mcp/codemate | Medium | 2 |
| W2 | Issue Triage + Librarian | `issues` opened | cache:8002, librarian:8008 | Medium | 3 |
| W3 | PR Description Generator | label_command `ai-describe` | cache:8002 | Low | 1 |
| W4 | Budget Alert Issues | daily schedule | /budget, cache:8002 | Low | 1 |
| W5 | Security Scan via Guardrails | `pull_request` opened | /guardrails, cache:8002 | Medium | 2 |
| W7 | Run Failure Diagnosis | `workflow_run` failure | /devops-agent, cache:8002 | Medium | 1 |
| W8 | Weekly Chargeback Report | weekly schedule | /budget, cache:8002 | Low | 1 |
| W6 | Documentation Auto-Update | `push` to main | librarian:8008, /mcp/codemate | High | 4 |

---

## Implementation Prerequisites

```bash
# GitHub Actions secrets/variables to create:
AIGW_API_KEY     # secret: service-account API key from Gateway admin panel
AIGW_BASE_URL    # variable: https://aigw.simcorp.internal/v1
```

Gateway setup:
1. Create a `github-automation` team in the admin portal
2. Create projects: `code-review`, `issue-triage`, `security-scan`, `ops-reports`
3. Issue a service-account API key per project for cost attribution

## Key Limitations

- macOS runners not supported — use `ubuntu-latest`
- Compiled lock files must be committed after frontmatter changes (`gh aw compile`)
- CodeMate requires SimCorp network — use self-hosted runners or VPN-connected runners
- Actions minutes billed separately from model inference
- PRs created by the default `GITHUB_TOKEN` don't trigger CI — use a PAT for W6
