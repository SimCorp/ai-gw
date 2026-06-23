# Agentic Workflows (gh-aw) — Operations Guide

This repo automates routine GitHub operations with [GitHub Agentic Workflows
(gh-aw)](https://github.github.com/gh-aw/) — Markdown specs in
`.github/workflows/*.md` compiled to hardened `*.lock.yml` GitHub Actions.

> Implements issue #108. The earlier design (`docs/gh-aw-research.md`) routed
> inference through the AI Gateway via the `codex` engine. That requires the
> gateway to be reachable from the runner, which GitHub-hosted runners are not
> (the gateway is internal-only — ZPA, no public IP). **The active workflows
> therefore run on the GitHub Copilot engine on `ubuntu-latest` and use GitHub
> data only.** Two cost workflows that need the gateway's admin API for data are
> deferred (see below).

## How it works

- **Engine:** `engine: copilot`. No external API key — the Copilot engine uses
  GitHub Actions token-based inference, enabled by `permissions.copilot-requests: write`.
- **Network:** `network: defaults` (GitHub + the engine's own endpoints). No
  internal SimCorp hosts.
- **Tools:** read-only GitHub toolsets only (`context`, `repos`, `issues`,
  `pull_requests`, `actions`). The agent never gets write credentials.
- **Writes:** every write (comment, label, issue, PR, review, SARIF alert) goes
  through gh-aw `safe-outputs`, applied by a separate, scoped, gated job after a
  threat-detection scan — the agent itself cannot write to the repo.

## Active workflows

| File | Trigger | What it does |
|---|---|---|
| `simcorp-pr-review.md` | PR opened/sync, `eyes` reaction | Security/correctness/quality review |
| `simcorp-pr-describe.md` | `ai-describe` label | Generates a structured PR description |
| `simcorp-dod-test-check.md` | PR opened/sync | Verifies new code has tests |
| `simcorp-pr-triage.md` | PR opened/sync | Labels PRs by area + size |
| `simcorp-security-scan.md` | PR opened/sync (org) | TruffleHog + Semgrep → code-scanning alerts |
| `simcorp-issue-triage.md` | Issue opened, `eyes` reaction | Classifies issues, suggests assignee |
| `simcorp-stale-nudge.md` | Weekly | Nudges + labels issues idle 30+ days |
| `simcorp-dependabot-triage.md` | PR opened/sync (Dependabot) | Summarises + labels dependency bumps |
| `simcorp-run-diagnosis.md` | CI `workflow_run` completed (master) | Diagnoses CI failures from Actions logs |
| `simcorp-continuous-docs-maintenance.md` | Push to master | Opens a draft PR fixing stale docs |
| `simcorp-pr-enhancement-radar.md` | Daily | Surfaces enhancement issues from recent PRs |
| `simcorp-daily-repo-status.md` | Daily | Rolling repo status issue (issues/PRs/CI) |
| `simcorp-workflow-health.md` | Weekly | Meta-agent: health of the agentic workflows |

## Deferred workflows

`.github/agentic-workflows/simcorp-budget-alerts.md` and
`.github/agentic-workflows/simcorp-chargeback-report.md` are **not active**.
They are kept as specs but **not** in `.github/workflows/` and **not compiled**,
because they need the gateway **admin `/budget` API for data** — unreachable from
public runners. To enable either one:

1. Register a `vnet-aigw-dev` self-hosted runner (in-VNet, can reach the gateway).
2. Set `runs-on: [self-hosted, vnet-aigw-dev]` and restore the gateway
   `engine`/`network`/`pre-agent-steps` config in the spec.
3. Create the GitHub secrets/vars: `AIGW_API_KEY`, `AIGW_BASE_URL_ADMIN`, and a
   `github-automation` gateway service key.
4. Move the file into `.github/workflows/` and run `gh aw compile`.

## Editing and compiling

```bash
gh extension install github/gh-aw   # once
gh aw compile                        # compile all .md → .lock.yml
gh aw compile <workflow-id>          # compile one
gh aw lint                           # actionlint the lock files
```

Commit the `.md` **and** the regenerated `.lock.yml` together — the lock file is
what GitHub Actions executes. Editing only the Markdown body needs no recompile;
frontmatter changes do.

> **Caveat:** the generated `agentics-maintenance.yml` is also gated on
> `vars.AGENTIC_WORKFLOWS_ENABLED` (its two scheduled cleanup jobs). `gh aw compile`
> **regenerates this file from the template and drops that guard**, so after a
> recompile re-add `vars.AGENTIC_WORKFLOWS_ENABLED == 'true' &&` to the `if:` of the
> `close-expired-entities` and `cleanup-cache-memory` jobs (or skip it once the
> workflows are enabled — then the guard is a no-op anyway).

## Activation — dormant by default

**All active workflows are gated** behind a repository variable and do nothing
until it is set:

```yaml
if: ${{ vars.AGENTIC_WORKFLOWS_ENABLED == 'true' }}
```

This mirrors the dormancy pattern used by `e2e-quality.yml`. Until the variable
is `true`, every agentic-workflow job is **skipped** (neutral check, never a
failure) — so merging this work to `master` is safe and the introducing PR does
not get red checks from the PR-triggered workflows.

## One-time setup (manual) — do these IN ORDER, before activating

These cannot be done from code. They are **prerequisites**: activate (step 3)
only after steps 1 and 2, or the workflows will fail/skip-write at runtime.

1. **Enable GitHub Copilot** for the repo/org (centralized Copilot billing) so
   `copilot-requests: write` token inference works. See
   <https://github.github.com/gh-aw/reference/billing/>. *Without this, runs fail.*
2. **Create the labels** the workflows apply:
   ```bash
   scripts/sync-labels.sh        # applies .github/labels.yml via gh
   ```
   *Without this, `add-labels` safe-outputs fail/skip — labels must pre-exist.*
3. **Activate** by setting the repo variable (only after 1 and 2):
   ```bash
   gh variable set AGENTIC_WORKFLOWS_ENABLED --body true
   ```
   To pause everything again, set it to `false` (or delete the variable).

## Debugging a run

```bash
gh aw logs <workflow-id>          # view recent run logs
gh aw audit <run-id-or-url>       # inspect a specific run
```
