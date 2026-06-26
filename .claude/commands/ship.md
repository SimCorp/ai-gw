---
description: Drive the current branch's PR to green & merged autonomously, working with Copilot's review, then sync + clean up.
argument-hint: "[pr-number]   (optional; otherwise uses the PR for the current branch)"
allowed-tools: Bash, Read, Edit, Write, Task, PushNotification
---

You are running `/ship`. Goal: take the current branch's PR all the way to **merged**, working
*with* Copilot's automated review, with **no manual step** from the user in the happy path.

**For detached "walk-away" operation, invoke as `/loop /ship <pr>`** (no interval → self-paced
dynamic mode). In that mode you do **one pass per iteration** and simply **end the turn** whenever
you must wait for CI/review; `/loop` automatically schedules the next iteration (it picks the
delay — short while CI is active, longer when idle). Do **not** call `ScheduleWakeup` yourself —
that is `/loop`'s internal mechanism, and calling it from an ordinary turn is a no-op that would
silently kill the loop. Run bare (`/ship <pr>`) and it just does a single pass.
Notify (`PushNotification`) only on **merge** or **escalation**.

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
survives across loop iterations. Read it at the top of each pass; create it on the first pass.

## One pass

1. **Resolve the PR.** Use `$ARGUMENTS` if given, else `gh pr view --json number,headRefName,state`
   for the current branch. If no PR exists, `gh pr create --fill`. Record `worktree` = current
   worktree path. If repo auto-merge is enabled
   (`gh api repos/{owner}/{repo} --jq .allow_auto_merge`), also set
   `gh pr merge <pr> --auto --squash` as a backstop (harmless if it later merges manually).

   **On every pass (including the first), immediately after resolving `<pr>`**: check
   `gh pr view <pr> --json state --jq .state`. If `MERGED` → go straight to step 3 cleanup. This
   short-circuits stale loop iterations where the PR merged between passes and the loop fired again
   before step 3 had a chance to run.

2. **Read status.**
   - `gh pr view <pr> --json state,mergeable,mergeStateStatus,statusCheckRollup,headRefOid`
   - Review threads via GraphQL. Paginate to be exhaustive — a PR can have >100 threads, and
     stopping at the first page would let `/ship` wrongly conclude "no unresolved threads" and
     burn rounds. `$after` is nullable: **omit `-f after` entirely on the first call** (it
     defaults to null), then pass `-f after="<endCursor>"` per page until `hasNextPage` is false:
     ```
     # first page (no after):
     gh api graphql -f query='query($o:String!,$r:String!,$n:Int!,$after:String){repository(owner:$o,name:$r){pullRequest(number:$n){reviewThreads(first:100,after:$after){pageInfo{hasNextPage endCursor} nodes{id isResolved comments(first:20){nodes{author{login} body path}}}}}}}' -f o=<owner> -f r=<repo> -F n=<pr>
     # subsequent pages: append  -f after="<endCursor>"
     ```

3. **Merged?** (`state == MERGED`) → run `~/.claude/scripts/git-sync-main.sh "<worktree>"
   "<branch>"`. The script targets the primary checkout via `git -C <primary>`, so it is safe to
   call from inside the worktree it removes — no need to relocate first. `PushNotification`
   "PR #<pr> merged & synced". Delete the state file. **Stop the loop** (do not re-arm). If the
   script exits non-zero (e.g. the default branch has diverged from origin and can't
   fast-forward), **escalate** with its message rather than retrying.

4. **A required check FAILED?**
   - Clearly ours and fixable (lint/format/unit failure from this change) → fix in the worktree.
     For Python lint (`Lint (Python)` check), **always try ruff auto-fix first**:
     ```
     ruff check --fix services/ && ruff format services/
     ```
     (install via `pip install ruff` if absent). If ruff leaves remaining errors, fix them
     manually. Then commit + push (re-triggers Copilot + CI).
     `round++`. Go to step 7 (wait).
   - Infra/flaky/ambiguous, or a real failure needing a decision → **escalate**: `PushNotification`
     with a one-line summary + the failing check, and **stop**.

5. **Checks still pending, or Copilot has not yet re-reviewed `headRefOid`** → nothing to do yet.
   Go to step 7 (wait).

6. **Checks green but unresolved threads exist** → for each unresolved thread:
   - Address it in the worktree (fix the code), or reply with reasoning if it's a genuine
     non-issue, then **resolve** it:
     ```
     gh api graphql -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{isResolved}}}' -f id=<threadId>
     ```
   - **Never resolve a thread you haven't actually addressed.** Anything that reads as a real
     security or correctness concern you're not sure about → **escalate**, don't auto-resolve.
   - Commit + push the fixes. `round++`. Go to step 7 (wait).

   If checks are **green and no unresolved threads remain**: **if the diff touches any
   auth-adjacent service — `services/auth`, `services/cache`, `services/admin`,
   `services/identity`, or `services/agent-relay`** (the `security-reviewer` agent covers auth,
   key handling, input validation, and access control) — dispatch `security-reviewer` over the
   diff first; clean → proceed, any finding → **escalate**. Then **re-check state** (`gh pr view
   <pr> --json state`): if a backstop auto-merge already fired (`state == MERGED`), skip the merge
   call and go straight to step 3 cleanup; otherwise merge:
   `gh pr merge <pr> --squash --delete-branch` → go to step 3.

7. **Wait / convergence guard.**
   - If `round > 3` and still not merged → **escalate**: post a PR comment AND a PushNotification
     so the contributor can see the blocker on the PR itself:
     ```
     gh pr comment <pr> --body "🚫 /ship escalated after <round> rounds without merging.
     Blocker: <one line per failing check or unresolved thread>.
     Manual intervention needed — fix the issue and re-invoke \`/loop /ship <pr>\`."
     ```
     Delete the state file (`~/.claude/state/ship-<pr>.json`). Then `PushNotification` with the
     same one-liner + stop. No infinite nit-loops.
   - Otherwise **just end the turn.** Under `/loop /ship <pr>` the next iteration is scheduled
     automatically (self-paced); the persisted state file carries `round` forward. Run bare
     (no `/loop`), ending the turn simply stops — re-invoke `/ship <pr>` manually to continue.

## Principles

- **"Escalate" means: `PushNotification` with a one-line summary of what's blocking, delete the
  state file (`~/.claude/state/ship-<pr>.json`), and stop the loop without re-arming.** Deleting
  the state file matters — a later `/ship` retry on the same PR (after you fix the blocker) must
  start from a clean `round` counter, not an inflated one that trips the convergence guard early.
- **Integrity over green.** The aim is a genuinely good merge, not a gamed gate. Resolve only
  what's addressed; surface doubt, don't bury it.
- **Always re-confirm Copilot reviewed the current `headRefOid`** before declaring "no unresolved
  threads" — never merge ahead of the latest review.
- **The worktree stays alive** for the whole loop (fixes are pushed from it). Only step 3 removes
  it, after merge.
