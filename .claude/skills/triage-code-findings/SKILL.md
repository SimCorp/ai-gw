---
name: triage-code-findings
description: >-
  Triage GitHub security/code-quality findings and create handoff issues. Use
  when asked to triage, review, or hand off code scanning / CodeQL findings,
  secret scanning alerts, or Dependabot alerts — pulls open findings from a
  repo, groups them by severity and rule, and opens one GitHub issue per source
  (code scanning, secret scanning, Dependabot) for another agent to fix.
disable-model-invocation: true
---

# triage-code-findings

Turns a repo's open GitHub security findings into actionable **handoff issues** — one
per Security-tab section: **Code scanning (CodeQL)**, **Secret scanning**, **Dependabot**.
Each issue is triaged (grouped by severity → rule, deduped, linked to the alert) and ends
with a handoff section telling the implementing agent how to fix/dismiss and verify.

The whole thing is one driver: **`.claude/skills/triage-code-findings/driver.mjs`** (Node,
shells out to `gh`). Paths below are relative to the repo root.

## Prerequisites

- **Node 18+** and the **GitHub CLI** (`gh`), authenticated as a user with admin/maintainer
  on the target repo (reading code-scanning/secret-scanning alerts needs `security_events`
  read). Verify:
  ```bash
  gh auth status
  node --version
  ```
- No npm install — the driver uses only Node built-ins + `gh`.

## Run (agent path)

**Always dry-run first** (prints each issue body, creates nothing):
```bash
node .claude/skills/triage-code-findings/driver.mjs
```
It targets the current directory's repo, all three sources. A source that's disabled,
has no analysis yet, has 0 findings, or that you can't read is **skipped with a note** —
never a crash, never an empty issue.

**Create the issues** once the dry-run looks right:
```bash
node .claude/skills/triage-code-findings/driver.mjs --create
```
Prints the URL of each created issue. Labels (`security` + a per-source label like
`code-scanning`) are created idempotently first, so `--create` can't fail on a missing label.

### Flags (all verified)
| Flag | Effect |
|---|---|
| `--repo owner/name` | Target another repo (default: current repo via `gh repo view`). |
| `--include code,secret,dependabot` | Which sources → which issues (default: all three). |
| `--severity high` | Minimum severity for code + Dependabot (`critical\|high\|medium\|low`). |
| `--assignee @me` | Assign every created issue. |
| `--label team:platform` | Extra label(s) added to every issue. |
| `--create` | Actually open the issues (omit = dry-run to stdout). |

Examples that work:
```bash
# Only the secret-scanning issue
node .claude/skills/triage-code-findings/driver.mjs --include secret

# Only high+critical CodeQL findings
node .claude/skills/triage-code-findings/driver.mjs --include code --severity high

# Another repo (skips sources you can't read, e.g. no admin)
node .claude/skills/triage-code-findings/driver.mjs --repo cli/cli --include code
```

## What it produces

One issue per source with findings, e.g. (real run on `SimCorp/ai-gw`):
- `🔎 Code scanning triage: 39 CodeQL finding(s) (23 high, 16 medium) — <date>` → labels `security, code-scanning`
- `🔐 Secret scanning triage: 2 secret alert(s) — <date>` → labels `security, secret-scanning`
- (`📦 Dependabot triage: …` → labels `security, dependencies` — skipped when 0)

Each body: severity sections → collapsible per-rule groups → a checklist of
`[ ] #<alert> — path:line` linking the alert → a **Handoff** section (fix-or-dismiss steps,
PR-only reminder, how to verify the alert closes).

## Gotchas

- **`gh` token scope:** reading alerts needs admin/maintainer + `security_events`. On a repo
  where you lack it, `gh` returns **403** (the message asks for `admin:repo_hook` scope) — the
  driver treats 403 like "off" and **skips that source** so the others still run. If *every*
  source 403s, you'll see "Nothing to triage" — that's a permissions problem, not an empty repo.
- **Code scanning 404 = "no analysis found":** CodeQL must have run at least once. Right after
  enabling default setup, wait for the first scan before expecting findings.
- **Dependency between dedupe and severity:** a CodeQL *quality* rule has no
  `security_severity_level`; the driver falls back to the rule's `severity` (`warning`/`note`)
  so those still sort and group, just below the security tiers.
- **Re-running `--create` makes new issues** (no dedupe against existing issues). Close/replace
  the old triage issue first, or this is the periodic-snapshot behavior you want.
- **Secret alerts are listed but never printed in clear** — only type + validity + link. The
  driver never fetches the raw secret.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Nothing to triage.` | All sources empty/disabled/unreadable. Check `gh auth status` and that scanning is on. |
| `note: code not enabled / no analysis for <repo> — skipped` | CodeQL hasn't run yet, or no read access. Trigger a scan / use an admin token. |
| `--create` errors on `--assignee` | Assignee must be a collaborator; drop the flag or use `@me`. |
| Issue body shows `location unavailable` | Alert had no location instance (rare); the link still points at the alert. |
