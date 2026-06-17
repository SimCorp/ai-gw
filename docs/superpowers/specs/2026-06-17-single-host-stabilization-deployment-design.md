# Single-host stabilization deployment — design

**Date:** 2026-06-17 · **Status:** approved design, ready for implementation planning
**Owner:** bntp@simcorp.com

## Context

The ai-gw platform is deployed to Azure Container Apps (ACA), but reaching it from a
developer workstation has been blocked by two pieces of ACA-specific friction, both
documented in the prior access work:

- An internal ACA environment will not route to an app unless that app is `external:true`,
  which Landing-Zone Azure Policy (`Deny-ContainerApps-Public-Network-Access`) denies —
  requiring a scoped governance exemption.
- ACA will not bind a custom domain (`dev.aigw.scdom.net`) without a **public** `asuid` TXT
  ownership record, which we cannot write into `scdom.net` ourselves.

Both problems exist only because of ACA. They are not inherent to the goal, which is simply:
**run the gateway somewhere internal, reachable over Zscaler ZPA on a trusted hostname, so
the system can be stabilized.** A plain Linux VM running the stack as containers behind a
TLS-terminating Caddy has neither problem — it is just a VNet IP, and Caddy presents the
wildcard certificate directly with no validation handshake and no policy waiver.

This design therefore **sets ACA aside for now** and runs the full stack as Docker Compose
on a dedicated VM in the dev Landing Zone. Once the system is stable, Phase 2 carries the
lessons back to an enterprise ACA deployment. This is a deliberate, temporary simplification
for stabilization — not the permanent target.

The access edge is the same internal-only design captured in
[`docs/access/2026-06-17-git-network-access-request.md`](../../access/2026-06-17-git-network-access-request.md);
the broader system is described in
[`docs/architecture/ai-gw-architecture.md`](../../architecture/ai-gw-architecture.md).

## Goals / non-goals

**Goals**
- One self-contained host running the whole gateway, reachable internally via ZPA on
  `https://dev.aigw.scdom.net` with a trusted certificate.
- Zero dependency on ACA, Key Vault, managed identity, ACR, private endpoints, or Azure
  Policy.
- Collapse the access asks to exactly the three SimCorp IT Service Desk forms (cert, DNS,
  ZPA) — no public DNS record, no policy exemption.

**Non-goals (explicitly out of scope for this phase)**
- High availability / multi-AZ (single VM is acceptable for stabilization).
- CI/CD to the VM (manual `docker compose` is fine).
- Migrating existing managed-PostgreSQL data (fresh containerized data; mint a new key).
- Production hardening of the VM beyond NSG + no-public-IP + file permissions.

## Architecture

A single Linux VM in the dev spoke VNet runs everything as one Compose project. Only Caddy
is exposed (TCP 443); every other container is reachable only on the Compose network.

```
ZPA ──443──▶ [ VM  dev.aigw.scdom.net · private IP only · NSG: 443 in (ZPA), 22 in (mgmt) ]
                 │
                 ▼  docker compose
            caddy  :443  — terminates TLS with *.aigw.scdom.net, path-routes to:
              ├─ cache:8002   /v1/*           (inference entry; orchestrates auth+litellm)
              ├─ portal:3002  /portal*
              ├─ admin-portal:3001  /admin-portal*
              ├─ admin:8005   /admin/*, /auth/*
              ├─ litellm:8003 /litellm/*
              ├─ identity:8006 /identity/*    librarian:8008 /librarian/*
              ├─ memory:8009 /memory/*        league:8010 /league/*
              ├─ observability:8004 /observability/*   agent-relay:8007 /agent-relay/*
              └─ /  → redirect /portal/        /healthz → 200
            supporting: auth:8001 · scanner · workflow-worker
            data: postgres (pgvector) · redis (redis-stack) · dex   — local Docker volumes
```

### Components and responsibilities

| Unit | What it is | Notes for this deployment |
|---|---|---|
| **VM** | Ubuntu 24.04 LTS, ~`D4as_v5`, **no public IP**, dev spoke VNet | NSG inbound: `443` from ZPA connector range, `22` from mgmt. Created by the user (`az vm create` is classifier-blocked for the agent). |
| **Caddy** | New front-door container, replaces the old `infra/nginx/default.conf` | Listens `:443`, `tls /etc/caddy/cert.pem /etc/caddy/key.pem`. Routes mirror `infra/bicep/modules/gateway.bicep`'s Caddyfile, but target Compose service names and **omit the `header_up Host` rewrites** (those existed only because ACA's envoy routes by Host — plain containers don't need it). |
| **Services** | The 14 FastAPI / Next.js services | FastAPI services build from `services/*/Dockerfile`; the Next.js apps use `Dockerfile.portal` / `Dockerfile.admin` (root) — or the restored compose's `node:20-alpine` dev-server pattern. Implementation chooses; both are in the repo. |
| **postgres** | `pgvector/pgvector:pg16` | Local volume. `init-litellm.sql` creates the separate `litellm` DB. Schema applied by the `db-migrate` (Alembic) one-shot service. |
| **redis** | `redis/redis-stack:7.2.0-v14` | Local volume. Exact/semantic cache + rate-limit counters. |
| **dex** | `dexidp/dex` | Local OIDC for portal auth in dev. |

### What we restore vs. write

- **Restore from commit `4d4410c~1`** (deleted by the Azure-only transition, PR #43):
  `infra/docker-compose.yml`, `infra/postgres/init-litellm.sql`, `infra/dex/config.yaml`.
- **Do NOT restore:** `infra/nginx/default.conf`, `infra/html/index.html` (replaced by Caddy);
  `infra/postgres/init.sql` (superseded by the Alembic baseline run by `db-migrate`).
- **Write new:** `infra/Caddyfile` (TLS front-door, derived from `gateway.bicep`) and a small
  Compose override or edit that (a) adds the `caddy` service, (b) removes the `127.0.0.1:<port>`
  host port bindings from internal services so only Caddy:443 is exposed.

### Configuration & secrets

- A **gitignored `.env`** on the VM (mode `0600`), populated from `pass` — at minimum
  `ANTHROPIC_API_KEY`, `INTERNAL_API_KEY`, and any service env the restored compose references
  via `env_file: ../.env`. DB/Redis creds can stay the compose dev defaults since both are
  container-local and never exposed off-box.
- The **wildcard cert** (`*.aigw.scdom.net`) PEM + private key at `/etc/caddy/` mode `0600`.
  This private key on the VM is the single most sensitive artifact — protected by no-public-IP
  + NSG + file permissions. No secret values are ever committed.

## The access edge — three SimCorp IT Service Desk requests

Sequencing: cert is IP-independent (request first/parallel); DNS + ZPA need the VM IP, so
create the VM, note its private IP, then submit those two.

**① Order a Certificate (Internal/External)** — Request Type **New**, Environment Type
**Internal**, subject/SAN **`*.aigw.scdom.net`**, delivered as PFX or PEM+key.

**② DNS Request for scdom.net zone** — DNS Type **A Record**, Request Type **New**,
**Uncoordinated**, description: add `dev.aigw.scdom.net` A → `<VM_PRIVATE_IP>` to the
internal zone, internal resolution only.

**③ Request Zscaler Private Access** — **New** resource, Hostname/IP
`dev.aigw.scdom.net` / `<VM_PRIVATE_IP>`, authorized AAD group = dev team, Services
**HTTPS / TCP 443**, note: **TLS passthrough, do not TLS-inspect** this segment.

## Phasing

- **Phase 0 — Stand up.** User creates the VM + NSG and installs Docker. Agent restores and
  adapts the compose stack (Caddy TLS front-door, drop localhost port bindings, `.env` from
  `pass`), seeds Postgres, mints an `sk-` key. User submits cert ① then DNS ② + ZPA ③.
- **Phase 1 — Stabilize.** Bring the stack up; verify all flows on-box, then end-to-end via
  ZPA from a workstation; iterate on bugs. This is the purpose of the exercise.
- **Phase 2 — Enterprise deployment** (later, separate spec). Carry lessons back to ACA: the
  ACA-native edge (scoped policy exemption + bound wildcard cert), multi-AZ HA, managed PaaS,
  CI/CD. Keep the VM as a staging/fallback environment.

## Verification

- **On-box:** `docker compose ps` all healthy; `curl -k https://localhost/healthz` → 200;
  `curl -k https://localhost/portal/` → 200; `POST https://localhost/v1/chat/completions`
  with the minted `sk-` key → 200 (real model), repeat shows `x-cache: HIT`.
- **Cert:** `openssl s_client -connect localhost:443 -servername dev.aigw.scdom.net` shows the
  SimCorp-CA `*.aigw.scdom.net` cert.
- **End-to-end via ZPA:** from a corp workstation, `https://dev.aigw.scdom.net/portal/` → 200
  with a trusted cert (no warning); `POST /v1/chat/completions` → 200.
- **DNS:** `dig +short dev.aigw.scdom.net @<corp-resolver>` → `<VM_PRIVATE_IP>`.

## Risks & mitigations

- **Single point of failure** — accepted for stabilization; Phase 2 restores HA.
- **Cert private key on the VM** — mitigated by no public IP, NSG, `0600` perms; optionally
  back with Key Vault + VM managed identity later (not required now).
- **`az vm create` is classifier-blocked for the agent** — the user runs VM creation; the
  agent does everything from Docker install onward.
- **Compose drift since deletion** — service Dockerfiles and app code have moved on since
  PR #43; expect minor env/healthcheck fixes when bringing the restored stack up (this is
  Phase-1 stabilization work, not a blocker).
