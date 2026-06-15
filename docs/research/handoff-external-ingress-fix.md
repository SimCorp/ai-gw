# Handoff — make ai-gw reachable (gateway external ingress fix)

**Date:** 2026-06-15
**Goal:** Get ai-gw reachable (browser + agent) from the in-VNet host. Root cause is known; fix is mid-execution.

## Read first
Memory files in `~/.claude/projects/-home-bntp-repos-ai-gw/memory/`:
`aigw-rootcause-external-ingress`, `aigw-invnet-host-rbac`, `aigw-azure-env-facts`.

## Context (already established — don't re-investigate)
- Running on `AZWESU0005`, a Linux VM **inside the spoke VNet** (IP `10.179.231.74`), **no Zscaler in path**. Repo at `/home/bntp/repos/ai-gw`, branch `feature/multi-az-ha-hardening`.
- `az` installed (2.87.0 + containerapp ext). Auth = **managed identity only** (`az login --identity`; Conditional Access blocks device login). MI principalId `8fb81703-fb05-4ed7-9fb4-f09d19be482b` has **Reader + Resource Policy Contributor** on `rg-aigw-dev-sdc`. Shell quirk: `cat` is aliased to missing `bat` → use `/usr/bin/cat`.
- **ai-gw is fully healthy** — all 14 ACA apps Running. **The prior "Zscaler breaks TLS" theory was WRONG.** Real root cause: gateway `ca-gateway-dev-sdc` has ingress `external:false`, so the env LB (`10.179.231.6`) won't route it to VNet clients → "Container App does not exist". Env is `internal:true`; it serves a valid trusted Microsoft wildcard cert.
- Fix = set gateway to `external:true` (VNet-visible, **NOT public**), blocked by policy `Deny-Public-Endpoints` (MG `mg-sclz-landingzones-corp`, ref id `Deny-ContainerApps-Public-Network-Access`). Requires a scoped policy exemption.
- **The agent must NOT create the exemption or flip external itself** (safety classifier blocks weakening this guardrail). The user (BNTP, LZ owner) runs those security-sensitive commands; the agent does read-only verification.

## Pending — user runs these 3 from their authenticated workstation (in order; ~2 min between #2 and #3)

```sh
# 1 — self-grant exemption rights (Resource Policy Contributor; not ABAC-blocked)
az role assignment create --assignee-object-id 45674099-3cd8-404c-a6ad-871027c8a585 --assignee-principal-type User --role "Resource Policy Contributor" --scope /subscriptions/8fc66d8e-c80e-454e-9248-b67af047c2c2/resourceGroups/rg-aigw-dev-sdc

# 2 — scoped exemption: waives ONLY the ACA external-access rule on ONLY the gateway
az policy exemption create --name exempt-aca-external-gateway --policy-assignment "/providers/Microsoft.Management/managementGroups/mg-sclz-landingzones-corp/providers/Microsoft.Authorization/policyAssignments/Deny-Public-Endpoints" --exemption-category Waiver --policy-definition-reference-ids Deny-ContainerApps-Public-Network-Access --scope "/subscriptions/8fc66d8e-c80e-454e-9248-b67af047c2c2/resourceGroups/rg-aigw-dev-sdc/providers/Microsoft.App/containerApps/ca-gateway-dev-sdc" --description "Gateway must be external:true to be VNet-visible in internal-only ACA env; approved by LZ owner"

# 3 — flip the gateway to external (after #2 propagates)
az containerapp ingress update -n ca-gateway-dev-sdc -g rg-aigw-dev-sdc --type external
```

## Next action for the agent (after user confirms #3 succeeded)
Verify from this in-VNet host (env private DNS zone is NOT VNet-linked → NXDOMAIN, so use `--resolve`):

```sh
GW=ca-gateway-dev-sdc.internal.calmbush-e5f546e4.swedencentral.azurecontainerapps.io
# Browser path — expect 200
curl --resolve $GW:443:10.179.231.6 https://$GW/portal/
# Agent path — expect 200 (needs an sk- key; mint via auth/admin path)
curl --resolve $GW:443:10.179.231.6 https://$GW/v1/chat/completions -H "Authorization: Bearer sk-..." -H "Content-Type: application/json" -d '{"model":"claude-haiku-4-5","messages":[{"role":"user","content":"ping"}]}'
```

## Cleanup when done
Remove the MI's Resource Policy Contributor grant on `rg-aigw-dev-sdc` (left from this session):
```sh
az role assignment delete --assignee 8fb81703-fb05-4ed7-9fb4-f09d19be482b --role "Resource Policy Contributor" --scope /subscriptions/8fc66d8e-c80e-454e-9248-b67af047c2c2/resourceGroups/rg-aigw-dev-sdc
```
