# AI Gateway — Azure Testability & Mixed-Identity Design

**Date:** 2026-06-11
**Status:** Approved (decisions captured below)
**Related:** [Azure enterprise deployment](2026-06-08-azure-enterprise-deployment-design.md) · Azure-only transition plan (`frolicking-noodling-rain`)

## Goal

Make the deployed Azure gateway **testable end-to-end now**, without waiting on the
external platform-team blockers, by:
1. Supporting a **mix of managed (Entra SSO) and unmanaged (local-account) identities**, so login/admin/key-issuance work without the pending Entra app-registration.
2. Solving **E** (worker/scanner spawn) on Azure with **no new VNet subnet**.
3. Providing **VNet reachability** for tests against the `internal:true` gateway.

### Blocker reality (why this is enough)
- **Images:** deploy already pulls from **GHCR** — ACR (G) is not required to test.
- **Deploy auth:** GitHub→Azure OIDC deploy already works.
- **User login:** the only thing the pending Entra app-registration blocks; **local accounts remove that dependency**. Inference auth uses `sk-*` API keys (not Entra).
- **Reachability:** `internal:true` is the one genuinely external piece → solved with a **VNet jumpbox** we own.

### Decisions
| # | Decision |
|---|---|
| Scope | Everything, incl. portal UI |
| Local-account authorization | **Local groups + `role_assignments`** (permanent dual-auth; not the removed dev bypass) |
| Reachability | **VNet jumpbox/runner** added to our bicep |
| E spawn runtime | **Azure Container Apps Jobs** (pivot from ACI — no new subnet, no re-vend) |

---

## Component 1 — Unmanaged identities (local accounts)

Authorization is Entra-group-driven since migration 0025 (`role_assignments.entra_group_id TEXT` → `organization_nodes.node_id` → role; per-user `user_roles` dropped). We reuse that mechanism for local accounts instead of reverting it.

**Schema (new Alembic migration in `services/admin/migrations/versions/`):**
- `local_groups(id TEXT PK, name TEXT NOT NULL, created_at TIMESTAMPTZ)` — ids namespaced `lcl-<uuid>` so they never collide with Entra group GUIDs.
- `local_group_members(group_id TEXT REFERENCES local_groups(id) ON DELETE CASCADE, user_id UUID REFERENCES users(id) ON DELETE CASCADE, PRIMARY KEY(group_id,user_id))`.
- No change to `role_assignments` — a local group is bound to a node by inserting a row with `entra_group_id = '<lcl-...>'` (the column is a generic group key; add a clarifying comment).

**Login (`services/admin/app/routers/unified_auth.py`):** the bcrypt path currently sets `roles = []` (line ~555). Change it to load the user's local group ids from `local_group_members` and call the existing `_load_role_assignments(group_ids)`. Entra users are unchanged (groups from token claims). Same `role_assignments` table feeds both → true dual-auth.

**Bootstrap (`services/admin/scripts/create_local_account.py`):** CLI that (a) creates a `users` row (email, `_hash_bcrypt(password)`, `hash_type='bcrypt'`), (b) ensures a `local_groups` row, (c) adds membership, (d) ensures a `role_assignments` row binding that group → root node → a given role (default `platform_admin`). Idempotent. This is the "break-glass / first admin" + general local-account provisioning path. Runnable from the jumpbox via `az containerapp exec`.

**Not a dev bypass:** real bcrypt hashing, real role grants, no `ENVIRONMENT` gating. Coexists with Entra SSO; either can be disabled by simply not provisioning it.

---

## Component 2 — E: spawn via Azure Container Apps Jobs

Replace the Docker-socket spawn with **ACA Jobs** running inside the existing ACA
environment (`snet-aca-workload`) — reaches internal services over the env DNS,
pulls from GHCR/ACR, no new subnet.

**Runtime (`services/workflow-worker/app/runtime/aca_job.py`):** `ACAJobRuntime`
implementing the existing runtime interface. Per agent run: start a manual execution
of a pre-declared job (`job-agent-runner-<env>-sdc`) via `azure-mgmt-appcontainers`
+ `DefaultAzureCredential` (worker MI), supplying a **per-execution template override**
(`JobExecutionTemplate`: the agent's image from the agents table, env with run inputs,
resources). I/O exchange via an **Azure Files** share mounted at `/run` (mirrors the
Docker bind-mount): worker writes `inputs.json` to the run dir, polls execution status,
reads `outputs.json`. Hardening: read-only where possible, no privilege, restart=Never.

**Fix the selector bug:** `services/workflow-worker/app/main.py` always instantiates
`DockerRuntime` and only logs `AGENT_CONTAINER_RUNTIME`. Wire it to select
`aca_job`/`docker`/`relay`. Remove the `kubernetes.py` stub (decision: ACA Jobs).

**Scanner (`services/scanner/app/worker/runner.py`):** port the sync Docker spawn to
the same ACA-Jobs mechanism (`job-scanner-runner-<env>-sdc`) for nmap/nuclei/ZAP/garak;
capture findings via the share / job logs.

**Bicep (`infra/bicep/modules/containerApps.bicep` + a storage module):**
- Declare `job-agent-runner-<env>-sdc` and `job-scanner-runner-<env>-sdc` (manual
  trigger, generic default image overridden per execution).
- Azure Files share + ACA environment storage mount.
- Worker/scanner managed identities get **Container Apps Jobs operator** (start/read
  executions) + **Storage File Data SMB Share Contributor** roles.

**Deps:** add `azure-mgmt-appcontainers`, `azure-identity`, `azure-storage-file-share`
to workflow-worker + scanner; drop `aiodocker`/`docker` from the Azure path.

Per-execution template override is the supported `Microsoft.App/jobs/.../start` body —
the same dynamic-image pattern the `db-migrate` job uses for a fixed image.

---

## Component 3 — VNet jumpbox (reachability)

A small VNet-internal toolbox so tests + the `deploy.yml` E2E job reach the
`internal:true` gateway without the pending firewall/DNS.

- Bicep: `ca-toolbox-<env>-sdc` — a minimal Container App (curl/python/az image,
  no ingress, scale-to-zero-ish min 1) in the ACA env. Tests run via
  `az containerapp exec -n ca-toolbox-... --command "<script>"` (control-plane reach,
  works from a GitHub-hosted runner). Optionally registered as a self-hosted runner later.

---

## Component 4 — Test enablement (end-to-end)

- **Seed:** post-deploy, run `create_local_account.py` (via the toolbox) to create a
  local `platform_admin` for the test run.
- **Enable `deploy.yml` `e2e-test`:** flip it on, executed through the toolbox:
  `/auth`, `/cache`, `/admin` health; then the functional path — log in with the local
  admin → register a team → issue an `sk-*` key → chat completion → assert cache hit on
  the 2nd identical call + a cost row in Postgres. Portal UI reachability: HTTP 200 on
  the admin-portal and portal roots via the toolbox.
- **Agentic/scanner smoke:** trigger one agent run (ACA-Jobs runtime) and one scan;
  assert completion + output recorded.

---

## Verification
- `pytest services/` green (new: local-account login/role tests; `ACAJobRuntime` unit tests with the Azure SDK mocked). `ruff` + `az bicep build` clean.
- A `master` deploy → toolbox seeds a local admin → `e2e-test` passes: health, login, key issuance, inference with cache hit + cost row, portal 200s, one agent run + one scan complete.

## Out of scope / follow-ups
- ACR switch (G) and the Entra app-registration (H.2) remain follow-ups; when Entra lands, restore admin `OIDC_CLIENT_SECRET` to its KV `secretRef` and local accounts become break-glass alongside SSO.
- Firewall/DNS (H.3/H.4) still wanted for direct VPN access; the jumpbox is the interim.
