---
description: Execute the current session's plan, create a PR, then ship it to merged. Run as `/loop /go` for full walk-away operation.
argument-hint: "[optional: plan file path override]"
allowed-tools: Bash, Read, Edit, Write, Task, Agent, Skill, PushNotification, EnterWorktree
---

You are running `/go`. Goal: take the plan in the current session's context all the way from **implementation → PR → merged**, with no manual steps from the user.

**Run as `/loop /go`** (self-paced dynamic mode). You do **one phase per loop iteration** and simply **end the turn** when the phase is done; `/loop` reschedules automatically. Do **not** call `ScheduleWakeup` — that is `/loop`'s internal mechanism. Run bare (`/go`) for a single pass only.

Notify (`PushNotification`) only on **merge** or **escalation**.

## State

Persist `{phase, pr, branch, worktree, round}` in `~/.claude/state/go.json`. Read it at the top of each pass; create on the first pass.

**At the top of every pass:** if `phase == "ship"` and `pr` is set, immediately check `gh pr view <pr> --json state --jq .state`. If `MERGED` → go straight to **Merged cleanup**.

---

## Phase: build

Execute this entire phase in a single loop iteration, then end the turn.

**1. Locate the plan.**
The plan file was written during this session's `/plan` invocation — its path is available in context (e.g. `~/.claude/plans/<slug>.md`). If `$ARGUMENTS` provides an explicit path, use that instead. Read the plan file.

**2. Ensure a worktree.**
Check: `git rev-parse --git-dir` vs `git rev-parse --git-common-dir`. If they differ, you're already in a worktree — continue. If on the default branch in the primary checkout, invoke the `superpowers:using-git-worktrees` skill to create a new worktree branching off master.

**3. Implement the plan.**
Invoke the `superpowers:subagent-driven-development` skill, giving it the plan content. This fans out independent tasks to parallel subagents and handles ordering for dependent tasks. Stay in the worktree throughout.

**4. Commit and push.**
Stage all changes. Write a commit message derived from the plan title. Push the branch to origin.

**5. Create the PR.**
```
gh pr create --fill
```
Capture the PR number from the output.

If auto-merge is enabled (`gh api repos/{owner}/{repo} --jq .allow_auto_merge` returns `true`):
```
gh pr merge <pr> --auto --squash
```

**6. Write state.**
Save `~/.claude/state/go.json`:
```json
{"phase": "ship", "pr": <N>, "branch": "<branch>", "worktree": "<path>", "round": 0}
```

**End the turn.** (Loop schedules the next iteration for the ship phase.)

---

## Phase: ship

Execute one ship pass, then end the turn. Read `pr`, `branch`, `worktree`, `round` from state.

**1. Read status.**
```
gh pr view <pr> --json state,mergeable,mergeStateStatus,statusCheckRollup,headRefOid
```
Review threads via GraphQL — paginate exhaustively (`hasNextPage` until false). Omit `-f after` on the first page; pass `-f after="<endCursor>"` for each subsequent page:
```
gh api graphql -f query='query($o:String!,$r:String!,$n:Int!,$after:String){repository(owner:$o,name:$r){pullRequest(number:$n){reviewThreads(first:100,after:$after){pageInfo{hasNextPage endCursor} nodes{id isResolved comments(first:20){nodes{author{login} body path}}}}}}}' -f o=<owner> -f r=<repo> -F n=<pr>
```

**2. Merged?** (`state == MERGED`) → go to **Merged cleanup**.

**3. A required check FAILED?**
- Fixable lint/format/unit failure from this change → fix in the worktree. For Python lint, try ruff first:
  ```
  ruff check --fix services/ && ruff format services/
  ```
  Commit + push. `round++`. Save state. End turn.
- Infra/flaky/ambiguous, or a real failure needing a decision → **escalate**.

**4. Checks pending or Copilot hasn't reviewed `headRefOid` yet** → end turn (wait).

**5. Checks green, unresolved threads exist** → address each thread:
- Fix the code or reply with reasoning, then resolve:
  ```
  gh api graphql -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{isResolved}}}' -f id=<threadId>
  ```
- Never resolve what you haven't actually addressed. Real security or correctness concern → **escalate**.
- Commit + push the fixes. `round++`. Save state. End turn.

**5a. Checks green + no unresolved threads:**
If the diff touches `services/auth`, `services/cache`, `services/admin`, `services/identity`, or `services/agent-relay` — dispatch `security-reviewer` over the diff; any finding → **escalate**.

Re-check state: if already `MERGED` (backstop auto-merge fired) → go to **Merged cleanup**. Otherwise:
```
gh pr merge <pr> --squash --delete-branch
```
→ go to **Merged cleanup**.

**6. Convergence guard.** If `round > 3` and still not merged → **escalate**:
```
gh pr comment <pr> --body "🚫 /go escalated after <round> rounds. Blocker: <one line per failing check or unresolved thread>. Fix the issue and re-invoke \`/loop /go\`."
```
`PushNotification` same one-liner. Delete state file. Stop.

Save updated `round` to state. End the turn.

---

## Merged cleanup

```
~/.claude/scripts/git-sync-main.sh "<worktree>" "<branch>"
```

If it exits non-zero → **escalate** with its output.

`PushNotification` "Plan implemented & merged: PR #<pr>."

Delete `~/.claude/state/go.json`. **Stop** (do not re-arm the loop).

---

## Escalate

`PushNotification` with a one-line summary of the blocker. Delete `~/.claude/state/go.json`. Stop the loop (do not re-arm).

---

## Principles

- **One phase per loop iteration.** Never attempt build and ship in the same pass.
- **Integrity over green.** Resolve only what's addressed; escalate doubt.
- **Always re-confirm Copilot reviewed `headRefOid`** before declaring "no unresolved threads."
- **The worktree stays alive** across the ship phase — only merged cleanup removes it.
- **Re-read the merge gate at runtime** (`gh api repos/{owner}/{repo}/rules/branches/master`); don't trust any hardcoded snapshot.
- **Re-read the state file at the start of each pass** — loop iterations are separate turns and in-memory state doesn't persist.
