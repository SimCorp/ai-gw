# Single-Host Stabilization Deployment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the full ai-gw stack as Docker Compose on one dedicated Linux VM in the dev LZ, reachable internally via Zscaler ZPA at `https://dev.aigw.scdom.net`, behind a TLS-terminating Caddy using the `*.aigw.scdom.net` wildcard cert.

**Architecture:** Restore the Compose stack deleted in PR #43 (`4d4410c`), replace its nginx `hub` front-door with a Caddy container that terminates TLS and path-routes to the service containers (routing copied from `infra/bicep/modules/gateway.bicep`). Data (Postgres+Redis) runs in local volumes. No ACA, Key Vault, managed identity, ACR, or Azure Policy involved.

**Tech Stack:** Docker Compose, Caddy 2, FastAPI services (existing `services/*/Dockerfile`), Next.js apps, `pgvector/pgvector:pg16`, `redis/redis-stack`, Dex.

**Spec:** [`docs/superpowers/specs/2026-06-17-single-host-stabilization-deployment-design.md`](../specs/2026-06-17-single-host-stabilization-deployment-design.md)
**Access edge:** [`docs/access/2026-06-17-git-network-access-request.md`](../../access/2026-06-17-git-network-access-request.md)

> **Verification model:** this is infrastructure, not unit-testable code. Each task's "verify" steps run real commands (`docker compose`, `curl`, `openssl`) and state the expected output. Treat a mismatch exactly like a failing test: stop and fix before moving on.

---

## Prerequisite (USER — not the implementing agent)

The agent cannot create the VM (`az vm create` is blocked by the safety classifier). The user provisions this first, then hands the agent an SSH session on the VM with the repo cloned:

- VM: Ubuntu 24.04 LTS, ~`Standard_D4as_v5`, **no public IP**, in the dev spoke VNet.
- **Static private IP** on the VM NIC (set the NIC's IP allocation to `Static`) so the DNS A
  record and ZPA segment stay valid across reboots/redeploys. Record this IP — it is the
  `<VM_PRIVATE_IP>` used in Task 11.
- NSG inbound: `TCP 443` + `TCP 80` from the ZPA App Connector range; `TCP 22` from the ZPA/mgmt range (SSH for ongoing host config). Deny all other inbound. (Port 80 = HTTP→HTTPS redirect + headroom for future config such as ACME.)
- Install Docker Engine + compose plugin; add the working user to the `docker` group.
- `git clone` the repo to `~/ai-gw` (the agent works from there).
- Record the VM's **private IP** — needed for the DNS and ZPA forms in Task 11.

All tasks below run **on the VM**, in the repo root (`~/ai-gw`), unless noted.

---

## Task 1: Restore the Compose stack from history and prune the old front-door

**Files:**
- Restore: `infra/docker-compose.yml`, `infra/postgres/init-litellm.sql`, `infra/dex/config.yaml`
- Modify: `infra/docker-compose.yml` (remove `hub` and `it-tools` services)

- [ ] **Step 1: Restore the three files from the pre-deletion commit**

```bash
cd ~/ai-gw
git checkout 4d4410c~1 -- infra/docker-compose.yml infra/postgres/init-litellm.sql infra/dex/config.yaml
ls -l infra/docker-compose.yml infra/postgres/init-litellm.sql infra/dex/config.yaml
```
Expected: all three files present.

- [ ] **Step 2: Remove the nginx `hub` and `it-tools` services**

These are the old front-door (replaced by Caddy in Task 3) and a tool it served. Open `infra/docker-compose.yml` and delete the entire `hub:` service block (image `nginx:alpine`, mounts `./html/` and `./nginx/`) and the entire `it-tools:` service block. Leave everything else — `claude-sandbox` (profile `sandbox`), the `redis-sentinel-*` group (profile `sentinel`), and `ollama` (profile `ollama`) are profile-gated and will not start by default.

- [ ] **Step 3: Validate the compose file parses with the prune applied**

```bash
docker compose -f infra/docker-compose.yml config -q && echo "COMPOSE_OK"
```
Expected: `COMPOSE_OK`, no `hub`/`it-tools` errors. (Warnings about unset `.env` vars are fine — fixed in Task 4.)

- [ ] **Step 4: Commit**

```bash
git add infra/docker-compose.yml infra/postgres/init-litellm.sql infra/dex/config.yaml
git commit -m "chore(host): restore compose stack, drop nginx hub front-door"
```

---

## Task 2: Write the Caddy front-door config

**Files:**
- Create: `infra/Caddyfile`

- [ ] **Step 1: Create `infra/Caddyfile`**

Routing mirrors `infra/bicep/modules/gateway.bicep`, but targets Compose service names + their real ports, drops the `header_up Host` rewrites (only ACA's envoy needs them), and terminates TLS here. Site address `:443` serves the cert for any SNI, which keeps on-box testing simple.

```
{
	admin off
	auto_https off
}

# Plain HTTP -> redirect to HTTPS (port 80 is open for this + future config needs).
:80 {
	redir https://{host}{uri} permanent
}

:443 {
	encode gzip
	tls /etc/caddy/cert.pem /etc/caddy/key.pem

	# Agent inference (OpenAI-compatible): cache validates the sk- key, then auth -> litellm.
	handle /v1/* {
		reverse_proxy cache:8002
	}

	# Browser apps (Next.js basePath — keep the prefix).
	handle /portal* {
		reverse_proxy portal:3002
	}
	handle /admin-portal* {
		reverse_proxy admin-portal:3001
	}

	# API services (strip the /prefix/ -> service root).
	handle_path /admin/* {
		reverse_proxy admin:8005
	}
	handle_path /cache/* {
		reverse_proxy cache:8002
	}
	handle_path /litellm/* {
		reverse_proxy litellm:8003
	}
	handle_path /identity/* {
		reverse_proxy identity:8006
	}
	handle_path /librarian/* {
		reverse_proxy librarian:8008
	}
	handle_path /memory/* {
		reverse_proxy memory:8009
	}
	handle_path /league/* {
		reverse_proxy league:8010
	}
	handle_path /observability/* {
		reverse_proxy observability:8004
	}

	# WebSocket relay bus for agentic workflows.
	handle /agent-relay/* {
		reverse_proxy agent-relay:8007
	}

	# Direct login convenience — admin serves /auth/* at its root.
	handle /auth/* {
		reverse_proxy admin:8005
	}

	handle / {
		redir /portal/ 302
	}
	handle /healthz {
		respond "ok" 200
	}
}
```

- [ ] **Step 2: Commit**

```bash
git add infra/Caddyfile
git commit -m "feat(host): add Caddy TLS front-door config"
```

---

## Task 3: Add the Caddy service via a host override

**Files:**
- Create: `infra/docker-compose.host.yml`

- [ ] **Step 1: Create `infra/docker-compose.host.yml`**

A small override (kept separate from the restored base file) that adds the only externally-published container. Caddy resolves upstreams lazily and returns 502 until they're up, so no strict `depends_on` is required.

```yaml
name: ai-gateway

services:
  caddy:
    image: caddy:2.8-alpine
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - ./certs/cert.pem:/etc/caddy/cert.pem:ro
      - ./certs/key.pem:/etc/caddy/key.pem:ro
    depends_on:
      cache:
        condition: service_started
      admin:
        condition: service_started
    restart: unless-stopped
```

- [ ] **Step 2: Create the certs directory placeholder (cert lands in Task 5)**

```bash
mkdir -p infra/certs
echo "infra/certs/" >> .gitignore
```

- [ ] **Step 3: Validate the merged compose parses**

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.host.yml config -q && echo "MERGE_OK"
```
Expected: `MERGE_OK`.

- [ ] **Step 4: Commit**

```bash
git add infra/docker-compose.host.yml .gitignore
git commit -m "feat(host): add Caddy service override + gitignore certs"
```

---

## Task 4: Build the `.env` from `pass` (no secrets committed)

**Files:**
- Create (on VM only, gitignored): `.env`

- [ ] **Step 1: Seed from the repo template and inspect required keys**

```bash
cd ~/ai-gw
cp .env.example .env
grep -vE '^\s*#|^\s*$' .env.example   # the authoritative list of keys to fill
```
`.env.example` is the source of truth for which variables exist. Most runtime URLs (`DATABASE_URL`, `REDIS_URL`, `LITELLM_URL`, `AUTH_URL`) are set inline per-service in the compose file; `.env` mainly supplies secrets and shared config.

- [ ] **Step 2: Fill the real secrets from `pass`**

At minimum set these (names per `.env.example` — adjust if the template differs):

```bash
# Anthropic provider key (litellm). pass is the credential store on the user's machine;
# on the VM, the user pastes the value or scp's it — never commit it.
# ANTHROPIC_API_KEY=<from: pass show anthropic/api-key>
# INTERNAL_API_KEY=<generate: openssl rand -hex 24>
# SCANNER_WORKER_SECRET=<generate: openssl rand -hex 24>
# LITELLM_MASTER_KEY=<generate: sk-<openssl rand -hex 24>>  (if referenced by .env.example)
chmod 600 .env
```
Generate the non-provider secrets in place:
```bash
printf 'INTERNAL_API_KEY=%s\n' "$(openssl rand -hex 24)" >> .env
printf 'SCANNER_WORKER_SECRET=%s\n' "$(openssl rand -hex 24)" >> .env
```
Set `ANTHROPIC_API_KEY` (and `LITELLM_MASTER_KEY` if present in the template) by editing `.env` directly with the real values. DB/Redis creds can stay the compose dev defaults (`aigateway:aigateway`) — both are container-local and never exposed off-box.

- [ ] **Step 3: Verify no placeholder secrets remain and perms are tight**

```bash
grep -nE 'change-me|REPLACE|<.*>' .env || echo "NO_PLACEHOLDERS"
stat -c '%a %n' .env
```
Expected: `NO_PLACEHOLDERS` and `600 .env`.

---

## Task 5: Place the wildcard certificate

**Files:**
- Create (on VM only, gitignored): `infra/certs/cert.pem`, `infra/certs/key.pem`

> Depends on the cert form (Task 11 ①) being fulfilled. If the cert isn't issued yet, do Tasks 6–9 first using a self-signed stand-in (Step 1b) so the stack can be validated, then swap in the real cert here.

- [ ] **Step 1a: Install the issued cert**

The SimCorp internal CA delivers a PFX or PEM. Convert/place as PEM:
```bash
# From PFX:
openssl pkcs12 -in wildcard.pfx -clcerts -nokeys -out infra/certs/cert.pem -passin pass:'<pfx-pw>'
openssl pkcs12 -in wildcard.pfx -nocerts -nodes  -out infra/certs/key.pem  -passin pass:'<pfx-pw>'
# (Append the CA chain to cert.pem if the issuer provides intermediates.)
chmod 600 infra/certs/key.pem infra/certs/cert.pem
```

- [ ] **Step 1b: (only if real cert not yet issued) self-signed stand-in**

```bash
openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
  -keyout infra/certs/key.pem -out infra/certs/cert.pem \
  -subj "/CN=*.aigw.scdom.net" -addext "subjectAltName=DNS:*.aigw.scdom.net,DNS:dev.aigw.scdom.net"
chmod 600 infra/certs/key.pem infra/certs/cert.pem
```

- [ ] **Step 2: Verify the cert/key load**

```bash
openssl x509 -in infra/certs/cert.pem -noout -subject -enddate
```
Expected: subject shows `*.aigw.scdom.net`, a future expiry date.

---

## Task 6: Bring up data tier and run migrations

- [ ] **Step 1: Start Postgres, Redis, Dex; run the Alembic migration job**

```bash
cd ~/ai-gw/infra
docker compose up -d postgres redis dex
docker compose up db-migrate    # one-shot; runs Alembic to head
```

- [ ] **Step 2: Verify data tier healthy and migrations applied**

```bash
docker compose ps postgres redis
docker compose exec -T postgres psql -U aigateway -d aigateway -c '\dt' | head
docker compose exec -T postgres psql -U aigateway -d aigateway -c "select count(*) from alembic_version;"
```
Expected: postgres+redis `healthy`; tables listed; `alembic_version` has 1 row. The separate `litellm` DB exists (created by `init-litellm.sql`):
```bash
docker compose exec -T postgres psql -U aigateway -d litellm -c 'select 1;'
```
Expected: returns `1`.

---

## Task 7: Bring up the FastAPI services

- [ ] **Step 1: Build + start the request-path and worker services**

```bash
cd ~/ai-gw/infra
docker compose up -d --build litellm auth cache observability admin identity librarian memory league agent-relay workflow-worker scanner
```

- [ ] **Step 2: Verify all are healthy (allow ~2 min for litellm start_period)**

```bash
docker compose ps
docker compose exec -T auth  python3 -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8001/ready').status)"
docker compose exec -T cache python3 -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8002/ready').status)"
```
Expected: `docker compose ps` shows every service `Up (healthy)`; both readiness probes print `200`. If a service crash-loops, check `docker compose logs <svc>` — the known DB-URL gotchas (Prisma needs `postgresql://`, asyncpg dialect rejects `sslmode`) do not apply here because the compose uses clean container DSNs, so a failure is most likely a missing `.env` key (Task 4) or app drift since PR #43 (expected Phase-1 work).

---

## Task 8: Bring up Caddy and verify TLS + routing on-box

- [ ] **Step 1: Start Caddy with both compose files**

```bash
cd ~/ai-gw/infra
docker compose -f docker-compose.yml -f docker-compose.host.yml up -d caddy
docker compose -f docker-compose.yml -f docker-compose.host.yml ps caddy
```
Expected: `caddy` is `Up`.

- [ ] **Step 2: Verify TLS handshake and front-door liveness**

```bash
curl -sk https://localhost/healthz ; echo
openssl s_client -connect localhost:443 -servername dev.aigw.scdom.net </dev/null 2>/dev/null | openssl x509 -noout -subject
```
Expected: `ok`; subject `*.aigw.scdom.net` (or the self-signed stand-in until the real cert is installed).

- [ ] **Step 3: Verify path routing to a couple of services**

```bash
curl -sk -o /dev/null -w "litellm:%{http_code}\n" https://localhost/litellm/health/liveliness
curl -sk -o /dev/null -w "root:%{http_code}\n" https://localhost/
curl -s  -o /dev/null -w "http80:%{http_code} -> %{redirect_url}\n" http://localhost/healthz
```
Expected: `litellm:200`; `root:302` (redirect to `/portal/`); `http80:301 -> https://localhost/healthz` (port-80 redirect working).

---

## Task 9: Mint an inference key and verify the end-to-end inference path on-box

- [ ] **Step 1: Inspect the admin scripts for exact usage, then mint a key**

The admin image ships its `scripts/` (account/key creation + an internal-access verifier). Read them for exact flags, then run:
```bash
cd ~/ai-gw/infra
docker compose exec admin ls scripts/
docker compose exec admin python scripts/create_local_account.py --help   # confirm flags
```
Create an account + `sk-` key per the script's flags (it writes to the `api_keys` table; auth validates by `sha256(raw key)` with `revoked_at IS NULL`). Capture the printed `sk-...` value.

- [ ] **Step 2: Verify the inference path through the gateway (cache MISS then HIT)**

```bash
SK="sk-...."   # the minted key
curl -sk https://localhost/v1/chat/completions \
  -H "Authorization: Bearer $SK" -H "Content-Type: application/json" \
  -d '{"model":"claude-haiku-4-5","messages":[{"role":"user","content":"say hi"}]}' \
  -D - -o /dev/null | grep -iE 'HTTP/|x-cache'
# repeat the identical request:
curl -sk https://localhost/v1/chat/completions \
  -H "Authorization: Bearer $SK" -H "Content-Type: application/json" \
  -d '{"model":"claude-haiku-4-5","messages":[{"role":"user","content":"say hi"}]}' \
  -D - -o /dev/null | grep -iE 'HTTP/|x-cache'
```
Expected: first call `HTTP/.. 200` with `x-cache: MISS`; second call `200` with `x-cache: HIT`. (Requires a valid `ANTHROPIC_API_KEY` in `.env`.)

- [ ] **Step 3: (optional) run the repo's internal-access verifier**

If `scripts/verify_internal_access.py` is present in the admin image, run it for a fuller browser+agent check:
```bash
docker compose exec admin python scripts/verify_internal_access.py --base-url http://cache:8002 || true
```
Expected: its own PASS output (inspect the script for required args).

---

## Task 10: Wire up the web portals (after the core path works)

**Files:**
- Modify: `infra/docker-compose.yml` (the `portal` and `admin-portal` service blocks)

The restored `portal`/`admin-portal` run `node:20-alpine` dev servers pointed at the old hub (`NEXT_PUBLIC_ADMIN_API: http://localhost:8080/admin`). Two viable approaches — pick **A** unless dev hot-reload is wanted:

- [ ] **Step 1A (recommended): build the production images and point them at the gateway**

The repo has root `Dockerfile.portal` and `Dockerfile.admin`. Inspect each app's env usage to get the exact public-base var names:
```bash
grep -rnE 'NEXT_PUBLIC_[A-Z_]+' apps/ | sort -u
```
Replace the `portal` / `admin-portal` service definitions to `build:` from those Dockerfiles and set the discovered `NEXT_PUBLIC_*` vars to the gateway origin (e.g. `https://dev.aigw.scdom.net` and `https://dev.aigw.scdom.net/admin`). Keep their container ports `3002` / `3001` (matches the Caddyfile).

- [ ] **Step 1B (alt): keep dev servers, fix the API base**

Leave `node:20-alpine` + `npm run dev`, but change `NEXT_PUBLIC_*` to the gateway origin and ensure deps install (the monorepo uses pnpm — `command` must `corepack enable && pnpm install && pnpm --filter <app> dev`). Heavier; only if hot-reload matters.

- [ ] **Step 2: Restart the portals and verify**

```bash
cd ~/ai-gw/infra
docker compose up -d --build portal admin-portal
curl -sk -o /dev/null -w "portal:%{http_code}\n" https://localhost/portal/
```
Expected: `portal:200`.

- [ ] **Step 3: Commit**

```bash
cd ~/ai-gw
git add infra/docker-compose.yml
git commit -m "feat(host): wire portals to the Caddy gateway origin"
```

---

## Task 11: Submit the three access requests and verify via ZPA

> This is the external dependency. The form values below are self-contained and correct for
> the **VM path** — target the VM's private IP, no public `asuid` TXT, no policy exemption.
> (The earlier [`docs/access/2026-06-17-git-network-access-request.md`](../../access/2026-06-17-git-network-access-request.md)
> describes the *ACA-native* alternative — it targets the ACA LB `10.179.231.6` and adds a public
> TXT + policy waiver; **do not use those values for this VM deployment**.)

- [ ] **Step 1: Submit cert form ①** — New / Internal / SAN `*.aigw.scdom.net`. (Can be submitted first; feeds Task 5.)

- [ ] **Step 2: Submit DNS form ②** — A Record / New / Uncoordinated: `dev.aigw.scdom.net` → A → `<VM_PRIVATE_IP>` in the internal zone.

- [ ] **Step 3: Submit ZPA form ③** — New resource; Hostname/IP `dev.aigw.scdom.net` / `<VM_PRIVATE_IP>`; authorized AAD group = dev team; Services **HTTPS / TCP 443**, **HTTP / TCP 80**, and **SSH / TCP 22** (22 for host administration); note "TLS passthrough, do not inspect".

- [ ] **Step 4: Verify end-to-end from a corp workstation (after all three fulfilled)**

```bash
# DNS resolves internally:
dig +short dev.aigw.scdom.net           # expect <VM_PRIVATE_IP>
# Browser: https://dev.aigw.scdom.net/portal/  -> 200, trusted cert, no warning
curl -s -o /dev/null -w "%{http_code}\n" https://dev.aigw.scdom.net/healthz   # expect 200
# Agent path:
curl -s https://dev.aigw.scdom.net/v1/chat/completions \
  -H "Authorization: Bearer $SK" -H "Content-Type: application/json" \
  -d '{"model":"claude-haiku-4-5","messages":[{"role":"user","content":"ping"}]}' \
  -o /dev/null -w "%{http_code}\n"       # expect 200
```
Expected: DNS returns the VM IP; all HTTPS calls succeed with the trusted `*.aigw.scdom.net` cert (no `-k` needed). This is the definition of done for Phase 0/1.

---

## Task 12: Clean up the Landing Zone (stale artifacts from abandoned approaches)

> Needs Azure access (the agent's MI login no longer works — run as the user / with creds).
> **Each item is verify-then-delete:** confirm the resource exists AND is unused before removing
> it. These were all staged for paths we abandoned (the VM TLS-proxy and the 1sh.sh browser
> route); none are used by the VM-on-host deployment. RG is `rg-aigw-dev-sdc` unless noted.

- [ ] **Step 1: Inventory what's actually there**

```bash
az login   # or the user's normal auth
RG=rg-aigw-dev-sdc
az network nsg list -g $RG --query "[].name" -o tsv
az keyvault secret list --vault-name <kv-name> --query "[].name" -o tsv
az containerapp env certificate list -n cae-aigw-dev-sdc -g $RG --query "[].name" -o tsv
az containerapp hostname list -n ca-gateway-dev-sdc -g $RG -o table
```

- [ ] **Step 2: Delete the abandoned VM-TLS-proxy artifacts (if present)**

```bash
az network nsg delete -g $RG -n nsg-aigw-tlsproxy-dev          # staged for the never-built proxy VM
az keyvault secret delete --vault-name <kv-name> -n aigw-tlsproxy-pem   # wildcard cert+key staged for it
```

- [ ] **Step 3: Remove leftover 1sh.sh browser-route artifacts (if present)**

```bash
# gateway hostname binding + env cert from the weekend 1sh.sh experiment:
az containerapp hostname delete -n ca-gateway-dev-sdc -g $RG --hostname aigw.1sh.sh
az containerapp env certificate delete -n cae-aigw-dev-sdc -g $RG --certificate aigw-1sh-sh
# Cloudflare (user's own 1sh.sh zone) — optional: remove A aigw.1sh.sh and TXT asuid.aigw.1sh.sh.
```

- [ ] **Step 4: Revoke the temporary elevated RBAC grant**

The AZWESU0005 managed identity was granted **Resource Policy Contributor** on `rg-aigw-dev-sdc`
solely for the ACA policy-exemption path, which the VM deployment does not use. Remove it:
```bash
az role assignment list --assignee <AZWESU0005-MI-principalId> --scope /subscriptions/<sub>/resourceGroups/$RG -o table
az role assignment delete --assignee <AZWESU0005-MI-principalId> --role "Resource Policy Contributor" --scope /subscriptions/<sub>/resourceGroups/$RG
```
(Leave its **Reader** grant. The MI principalId is in [[aigw-invnet-host-rbac]] / decode via IMDS.)

- [ ] **Step 5: (decision, not automatic) ACA cost**

The ACA deployment is now redundant for stabilization. To stop paying for it without deleting,
scale the apps to zero (`az containerapp update -n <app> -g $RG --min-replicas 0`) — or leave it
running if you want it as a comparison. **Do not delete the ACA env or shared PaaS** (Postgres/
Redis/KV) — Phase 2 reuses them. Decide explicitly; don't tear down by reflex.

- [ ] **Step 6: Note what was removed in the issue/PR** so the cleanup is auditable.

---

## Done criteria

- `docker compose ... ps` shows all non-profiled services `healthy`.
- On-box: `/healthz` 200, `/portal/` 200, inference 200 with `x-cache` MISS→HIT.
- Via ZPA from a workstation: `https://dev.aigw.scdom.net/portal/` and `/v1/chat/completions` both 200 with the trusted cert.

Phase 2 (enterprise ACA migration) is a separate spec — not in this plan.
