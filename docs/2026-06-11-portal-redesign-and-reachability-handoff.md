# Handoff: Circuit Duotone portal redesign + dev-env reachability

**Date:** 2026-06-11
**Branch of record:** `master` (all work merged)
**Status:** Redesign **done & deployed**. Live URL **not browsable** — blocked on Zscaler ZPA config (not an app/Azure problem).

This is a self-contained brief for an agent picking up where this left off. Read the
"Open blocker" and "Decisive next test" sections first if you only read two things.

---

## 1. What was delivered (complete)

A full UX redesign of both Next.js portals — design system **"Circuit Duotone"**.
Spec: `docs/superpowers/specs/2026-06-10-aigw-portal-redesign-design.md`. Design
decisions were user-validated via mockups — **do not relitigate them.**

- **Token system** in `packages/ui/src/styles/` (`primitives → theme → surface → base →
  components → shell → density → league`, imported by `packages/ui/src/globals.css`).
  Light + dark themes via `[data-theme]`; one brand, two accents via `[data-surface]`
  (admin = indigo, portal = fuchsia); brand gradient used only as a *trace* (1px borders,
  underlines, logo). Mono microlabels, tabular numerals.
- **Self-hosted Geist / Geist Mono** via the `geist` package; `next-themes` provider
  (default `system`). Google Fonts removed from CSP.
- **Shared shell** in `@aigw/ui`: icon rail + contextual page panel + breadcrumb topbar +
  **⌘K command palette** (`cmdk`). Circuit-node `BrandMark`, new `icon.svg`, titles
  `ai-gw /admin` and `ai-gw /dev`. Components: `RailShell`, `AppTopbar`, `CommandPalette`,
  `ThemeToggle`, `BrandMark`, `EmptyState`, `Skeleton` (old `Shell`/`Topbar` deleted).
- **Deep reworks:** admin dashboard (KPI hierarchy + sparklines), portal home (first-run
  "get to first request" checklist), API keys (one-time reveal), playground (real SSE
  streaming + model compare), and a game-like **AI-League** (quest board, client-side
  XP/levels from lifetime points, podium leaderboard, reward shop + confetti; sub-theme
  scoped to `[data-zone="league"]` in `league.css`).
- **Token sweep** across all ~75 pages; legacy `--sc-*` / `--side-*` aliases and the
  `compat.css` shim removed after migration.
- Merged via PRs **#45** (redesign) and follow-ups; dead `TeamSelector` removed.

### Conventions for future portal work
- **Do not** add Tailwind — it's installed but deliberately inert; the system is pure CSS
  tokens. Don't reintroduce hardcoded hex/rgba (breaks light mode). Use `var(--accent)`,
  `--good/--warn/--bad`, `--cat-*`, `--fg-1/2/3`, `--rule`, `.microlabel`, `.num`, and the
  `@aigw/ui` components.
- **Local visual check (no backend):** `NEXT_PUBLIC_USE_MOCKS=1 pnpm --filter @aigw/portal dev`
  (and `@aigw/admin`). MSW handlers with realistic sample data live in
  `apps/portal/app/portal/_mocks/handlers.ts` and `apps/admin/app/admin/_mocks/{handlers,browser}.ts`.
  URLs are basePath + segment: `/admin-portal/admin/...`, `/portal/portal/...`.

---

## 2. Azure deployment — DONE and verified healthy

Deployed to the dev environment (ACA, `rg-aigw-dev-sdc`, Sweden Central). The deploy
pipeline (`.github/workflows/deploy.yml`, triggered by `ci` on master push, also supports
`workflow_dispatch` with an `image_tag`) is green. All 15 container apps + the new
`ca-gateway-dev-sdc` are `Running` / `Succeeded` on the latest image.

### Latent deploy blockers fixed along the way (all merged)
These were pre-existing issues from other in-flight PRs (#42–#44) that this redesign's
deploy was first to actually exercise:
- **PR #46** — `deploy.yml` never provisioned the `staigwruns${env}sdc` storage that
  `containerApps.bicep` (from #44) references as `existing`; added a `storage.bicep` step.
- **PR #47/#48** — SCLZ `Enforce-Guardrails-Storage` policy denied that account; made it
  compliant. **Consequence (open, Workstream H):** the LZ denies `allowSharedKeyAccess`,
  so **#44's ACA-Jobs Azure Files mount cannot authenticate with account keys** — needs
  identity-based file access + a private endpoint before the agent/scanner spawn feature
  can run. Not relevant to the portals.
- **PR #49** — the `job-db-migrate` job failed `Settings` validation after Workstream C
  removed config defaults; alembic only needs `DATABASE_URL`, so the other required fields
  are stubbed on the job env.
- Transient CI flakes (Docker Hub / PyPI timeouts) — `ci.yml` now retries buildx 3×;
  reruns were used as needed.

### The front door (gateway) — built and bound
The single FQDN `aigw-dev.lab.cloud.scdom.net` had **never been servable**: the wildcard
cert `tls-wildcard-lab` sat on the ACA env bound to nothing, and no component path-routed
the FQDN that the portals' baked `NEXT_PUBLIC_*` URLs assume.

- **PR #51** — new `services/gateway`: an nginx reverse proxy. `/admin-portal` + `/portal`
  pass straight through (Next basePath); `/auth /cache /litellm /admin /identity /librarian
  /memory /league /observability /agent-relay` strip-and-proxy. Request-time DNS via the env
  resolver, SSE-safe (no buffering), WS upgrade headers. Built into the CI image matrix.
- **PR #52** — gateway ingress `external` defaults **false** behind a `gatewayExternal`
  param: the SCLZ policy `Deny-ContainerApps-Public-Network-Access` denies
  `ingress.external=true` even on an `internal:true` env.
- **PR #53** — bind the FQDN + wildcard cert (SNI) on the gateway's **internal** ingress
  (no `external` needed; the env is internal so the binding is served on the VNet LB).

**Verified live (control plane):** `ca-gateway-dev-sdc` provisioning `Succeeded`,
`customDomains` = `aigw-dev.lab.cloud.scdom.net` SNI-bound to `tls-wildcard-lab`
(thumbprint `20F68F96D2B6F951FA0EC8FEE0E77917B9D828FA`, valid → 2028, has private key),
revision Healthy. Env static IP `10.179.231.6`, default domain
`calmbush-e5f546e4.swedencentral.azurecontainerapps.io`, `internal: true`, infra subnet
has **no NSG block**. **Every Azure-side condition to serve TLS on 443 is satisfied.**

---

## 3. Open blocker: not browsable — it's Zscaler ZPA, not Azure

`https://aigw-dev.lab.cloud.scdom.net/portal/portal` fails for the user's real
Edge/Chrome/Firefox with `ERR_CONNECTION_RESET` ("Secure Connection Failed — authenticity
of the received data could not be verified", **no "Advanced/Accept risk" button** → the
handshake is reset *before* a cert is presented, i.e. a protocol-level reset, not a
cert-trust mismatch).

Key facts:
- The site is a **Zscaler Private Access (ZPA)** app. `aigw-dev.lab.cloud.scdom.net`
  resolves to **`100.64.1.30`**, a synthetic CGNAT IP handed out by the ZCC client.
- **Client-side probes are meaningless.** ZCC accepts the TCP SYN locally for any port in
  the app segment and resets later when brokering to the App Connector — so `:80`/`:443`
  always look "open" then reset, regardless of backend state. WSL probes are doubly
  useless: ZCC does **not** steer WSL2-originated traffic at all.
- The ACA env LB serves **only TCP 80/443** (80 = HTTP→HTTPS redirect). All app
  `targetPort`s (8001–8010, 3001, 3002, 8080) are **internal-only behind the env LB** — they
  must **not** be in the ZPA segment.

### Most likely root cause
The ZPA **application segment** for `*.lab.cloud.scdom.net` either does not include
**TCP 443** in its port range, or the user/group isn't authorized on it, or the App
Connector is unhealthy. Any of these resets all clients identically. (The user recalled
being asked "which ingress ports to open" — if the segment was built from the app port
numbers instead of 443, that is the bug.)

---

## 4. Decisive next test (settles ACA vs ZPA in one command)

Run from a terminal where `az` is logged in **with rights on the RG** (the prior agent
lacked `Microsoft.App/containerApps/getAuthToken` on the jumpbox, and its WSL sandbox
cannot reach the VNet — so the *user* or a properly-scoped principal must run this):

```
az containerapp exec -n ca-toolbox-dev-sdc -g rg-aigw-dev-sdc \
  --command "curl -sko /dev/null -w '%{http_code}\n' https://ca-gateway-dev-sdc.internal.calmbush-e5f546e4.swedencentral.azurecontainerapps.io/healthz"
```
This runs **inside the VNet**, bypassing ZPA.
- **`200`** → ACA serves fine; the problem is 100% ZPA config (go to §5).
- **reset / hang** → something subtler in the ACA internal ingress; dig there
  (the prior analysis believed this unlikely — cert/binding/health all check out — but it
  was never confirmed from inside the VNet).

---

## 5. Action items by owner

**Platform / Zscaler IT (the actual blocker):**
1. ZPA app segment `*.lab.cloud.scdom.net`: ensure **TCP 443** is in the port range and the
   user/group is authorized; confirm the App Connector serving it is healthy.
2. Confirm `100.64.1.30` (ZPA synthetic) → App Connector → ACA env LB `10.179.231.6:443`.
3. **Longer-term, the real blocker for coding agents:** ZCC does not steer WSL2-originated
   traffic, so CLI tools/agents in WSL cannot reach *any* ZPA app even when the Windows
   browser can. Need ZCC WSL coverage or an exception.

**Workaround an agent CAN build once the Windows browser works** (tracked, not started):
a small forward proxy on Windows (reachable from WSL via the already-enabled mirrored
loopback) relaying `*.lab.cloud.scdom.net` through the Windows/ZCC-steered stack; point
WSL `HTTPS_PROXY` at it for that host, and install the corp root CA into the WSL trust
store so cert validation passes.

**Azure side:** believed complete. Only revisit if §4 returns a non-200.

---

## 6. Pointers
- Redesign spec: `docs/superpowers/specs/2026-06-10-aigw-portal-redesign-design.md`
- Azure deploy design: `docs/superpowers/specs/2026-06-08-azure-enterprise-deployment-design.md`
- Gateway: `services/gateway/` (nginx.conf.template, entrypoint.sh, Dockerfile)
- Gateway app + binding: `infra/bicep/modules/containerApps.bicep` (`caGateway`, params
  `gatewayHostname`, `tlsCertName`, `gatewayExternal`)
- Deploy pipeline: `.github/workflows/deploy.yml` (supports `workflow_dispatch` + `image_tag`)
- Known CI quirk: `Validate Bicep (dev)` can't pass on PRs (federated cred has no
  `pull_request` subject) — merges used admin override after real checks were green.
