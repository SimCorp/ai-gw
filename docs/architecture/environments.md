# Environments (deferred V2 / ACA)

> **Status: future target, not currently running.** This document describes the **Azure Container
> Apps (ACA)** deployment — the deferred V2/prod target. The AI Gateway currently runs as a
> single-host Docker Compose stack on a VM; see [`dev-environment.md`](dev-environment.md) for the
> live deployment. The ACA Bicep IaC below is in-repo and ready for promotion, and its CI/CD
> workflows are archived in `.github/workflows/_archived/`.

The V2 target runs the AI Gateway in two Azure Container Apps environments in the SimCorp Landing
Zone (Sweden Central).

## Environment comparison

| | Dev | Test |
|---|---|---|
| **Purpose** | Active development | Release validation |
| **Promoted by** | Every `master` push | `git tag v1.2.3` |
| **Subscription** | PlatformAITooling Dev | PlatformAITooling Test |
| **Subscription ID** | `8fc66d8e-c80e-454e-9248-b67af047c2c2` | `<TEST_SUBSCRIPTION_ID>` |
| **Resource group** | `rg-aigw-dev-sdc` | `rg-aigw-test-sdc` |
| **ACA environment** | `cae-aigw-dev-sdc` | `cae-aigw-test-sdc` |
| **Key Vault** | `kv-aigw-dev-sdc` | `kv-aigw-test-sdc` |
| **ACR** | `acraigwdevsdc.azurecr.io` | `acraigwtestsdc.azurecr.io` |
| **Gateway FQDN** | `aigw-dev.lab.cloud.scdom.net` | `aigw-test.lab.cloud.scdom.net` |
| **Spoke VNet** | `vnet-spoke-platformaitooling-dev-sdc-001` | `vnet-spoke-platformaitooling-test-sdc-001` |
| **Bicep params** | `infra/bicep/environments/dev/main.bicepparam` | `infra/bicep/environments/test/main.bicepparam` |

Container Apps follow the pattern `ca-<service>-{dev|test}-sdc` in each environment.

## Promotion flow

```
master push
  → CI (lint, test, security, build all images + portal-dev)
  → deploy.yml (dev)
    → deploys containerApps.bicep to rg-aigw-dev-sdc
    → runs DB migrations
    → smoke test (control plane)

git tag v1.2.3
  → CI (same as above, also builds portal-test images)
  → deploy-test.yml (test)
    → deploys containerApps.bicep to rg-aigw-test-sdc
    → runs DB migrations
    → smoke test (control plane)
```

CI only deploys `containerApps.bicep` (the 14 container apps). PostgreSQL, Redis, Key Vault, ACA environment, and networking are deployed once via `main.bicep` (manual, one-time per environment).

## Releasing to test

```bash
# Tag a release
git tag v1.2.3 -m "Release 1.2.3 — <summary of changes>"
git push origin v1.2.3
```

GitHub Actions will:
1. Run full CI (lint → tests → security → build all images including portal-test variants)
2. On CI success, `deploy-test` fires automatically (detects `head_branch` starts with `v`)
3. Smoke test verifies all 14 `ca-*-test-sdc` apps are Running

## Hotfix flow

```bash
git checkout -b hotfix/v1.2.4
# apply fix, open PR → master
# master push validates the fix in dev
git tag v1.2.4 -m "Hotfix 1.2.4 — <description>"
git push origin v1.2.4
```

## First-time environment provisioning

CI/CD only manages the container apps. Full environment provisioning (PostgreSQL, Redis, Key Vault, ACA environment, networking) is a one-time manual step:

```bash
az deployment group create \
  --resource-group rg-aigw-{dev|test}-sdc \
  --template-file infra/bicep/environments/{dev|test}/main.bicep \
  --parameters infra/bicep/environments/{dev|test}/main.bicepparam \
  --parameters imageTag=sha-<git-sha> \
               postgresAdminPassword=<pwd> \
               tlsCertBase64=<cert> \
               tlsCertPassword=<pass> \
               ghcrPat=<pat> \
               ghcrUsername=<user>
```

Fill placeholder values in `infra/bicep/environments/test/main.bicepparam` before running this for test. See `docs/access/2026-06-18-test-environment-access-request.md` for the required platform-team inputs.

## Portal images

Next.js portal images have `NEXT_PUBLIC_*` API endpoints baked in at build time. Two variants are built:

| Image | Built when | Gateway FQDN |
|---|---|---|
| `admin-portal` / `portal` | Every master push | `aigw-dev.lab.cloud.scdom.net` |
| `admin-portal-test` / `portal-test` | Version tag push only | `aigw-test.lab.cloud.scdom.net` |

Python/worker service images are environment-agnostic — the same `sha-{sha}` image deploys to both environments.

## GitHub Actions secrets

| Secret | Scope | Purpose |
|---|---|---|
| `AZURE_CLIENT_ID` | Repo | Dev Entra SP client ID |
| `AZURE_SUBSCRIPTION_ID` | Repo | Dev subscription ID |
| `AZURE_TENANT_ID` | Repo | Shared tenant (`aa81b43f-...`) |
| `AZURE_CLIENT_ID_TEST` | Repo | Test Entra SP client ID |
| `AZURE_SUBSCRIPTION_ID_TEST` | Repo | Test subscription ID |
| `GHCR_PAT` | Repo | GitHub Container Registry PAT (shared) |
| `AIGW_E2E_ADMIN_PASSWORD` | Repo | Required before enabling e2e-test job |
| `AIGW_TEST_API_KEY` | Repo | Optional — used by e2e-test for inference validation |
