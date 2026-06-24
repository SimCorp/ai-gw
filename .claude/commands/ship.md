---
description: Drive the current branch's PR to green & merged autonomously, working with Copilot's review, then sync + clean up.
argument-hint: "[pr-number]   (optional; otherwise uses the PR for the current branch)"
allowed-tools: Bash, Read, Edit, Write, Task, ScheduleWakeup, PushNotification
---

You are running `/ship`. Goal: take the current branch's PR all the way to **merged**, working
*with* Copilot's automated review, with **no manual step** from the user in the happy path. Run
**detached**: do one pass, and whenever you must wait, re-arm via `ScheduleWakeup` and end the
turn so the user can walk away. Notify (`PushNotification`) only on **merge** or **escalation**.

## The `master` merge gate (ai-gw, verified)

Source of truth: `gh api repos/{owner}/{repo}/rules/branches/master`. Currently:
- `required_approving_review_count: 0` — **no human approval needed**.
- `required_review_thread_resolution: true` — **all** review threads must be resolved (every
  thread blocks, not only Copilot's).
- `copilot_code_review.review_on_push: true` — Copilot re-reviews on every push.
- `dismiss_stale_reviews_on_push: false` — pushes don't wipe prior state.
- 4 required status checks: **`Lint (Python)`, `Lint + build (frontend)`, `Unit tests (frontend)`,
  `Security scan`** (`strict: false` → the branch need not be current with master to merge).

Re-read the gate at runtime; don't trust this snapshot if it looks stale.

## State

Persist `{pr, branch, worktree, round}` in `~/.claude/state/ship-<pr>.json` so the round counter
survives wakeups. Read it at the top of each pass; create it on the first pass.

## One pass

1. **Resolve the PR.** Use `$ARGUMENTS` if given, else `gh pr view --json number,headRefName,state`
   for the current branch. If no PR exists, `gh pr create --fill`. Record `worktree` = current
   worktree path. If repo auto-merge is enabled
   (`gh api repos/{owner}/{repo} --jq .allow_auto_merge`), also set
   `gh pr merge <pr> --auto --squash` as a backstop (harmless if it later merges manually).

2. **Read status.**
   - `gh pr view <pr> --json state,mergeable,mergeStateStatus,statusCheckRollup,headRefOid`
   - Review threads via GraphQL:
     ```
     gh api graphql -f query='query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){pullRequest(number:$n){reviewThreads(first:100){nodes{id isResolved comments(first:20){nodes{author{login} body path}}}}}}}' -f o=<owner> -f r=<repo> -F n=<pr>
     ```

3. **Merged?** (`state == MERGED`) → **leave the worktree first**: relocate to the primary
   checkout (`ExitWorktree`, or just call the script which uses `git -C <primary>`), then run
   `~/.claude/scripts/git-sync-main.sh "<worktree>" "<branch>"`. `PushNotification` "PR #<pr>
   merged & synced". Delete the state file. **Stop the loop** (do not re-arm).

4. **A required check FAILED?**
   - Clearly ours and fixable (lint/format/unit failure from this change) → fix in the worktree,
     commit, push (this re-triggers Copilot + CI). `round++`. Re-arm (step 7).
   - Infra/flaky/ambiguous, or a real failure needing a decision → **escalate**: `PushNotification`
     with a one-line summary + the failing check, and **stop**.

5. **Checks still pending, or Copilot has not yet re-reviewed `headRefOid`** → nothing to do yet.
   Re-arm (step 7).

6. **Checks green but unresolved threads exist** → for each unresolved thread:
   - Address it in the worktree (fix the code), or reply with reasoning if it's a genuine
     non-issue, then **resolve** it:
     ```
     gh api graphql -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{isResolved}}}' -f id=<threadId>
     ```
   - **Never resolve a thread you haven't actually addressed.** Anything that reads as a real
     security or correctness concern you're not sure about → **escalate**, don't auto-resolve.
   - Commit + push the fixes. `round++`. Re-arm (step 7).

   If checks are **green and no unresolved threads remain**: **if the diff touches
   `services/auth`, `services/cache`, or `services/admin`** (per repo `CLAUDE.md`), dispatch the
   `security-reviewer` agent over the diff first — clean → proceed, any finding → **escalate**.
   Then merge: `gh pr merge <pr> --squash --delete-branch` (or let auto-merge fire) → go to step 3.

7. **Re-arm / convergence guard.**
   - If `round > 3` and still not merged → **escalate** (stop + notify with a summary of what's
     blocking). No infinite nit-loops.
   - Otherwise `ScheduleWakeup` (~270s while CI/Copilot is mid-flight to stay in cache; longer if
     you know it'll be minutes) with this same `/ship <pr>` prompt, then **end the turn**.

## Principles

- **Integrity over green.** The aim is a genuinely good merge, not a gamed gate. Resolve only
  what's addressed; surface doubt, don't bury it.
- **Always re-confirm Copilot reviewed the current `headRefOid`** before declaring "no unresolved
  threads" — never merge ahead of the latest review.
- **The worktree stays alive** for the whole loop (fixes are pushed from it). Only step 3 removes
  it, after merge.
