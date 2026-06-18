# Test Environment Access Requests

Date: 2026-06-18  
Environment: PlatformAITooling Test (Sweden Central)  
Contact: AI Gateway team

These requests mirror the dev environment setup. Submit to the SimCorp IT Service Desk and Platform Engineering team.

---

## Required before first `main.bicep` deploy to test

### 1. PE subnet address prefix

Provide an available CIDR block in the test VNet (`vnet-spoke-platformaitooling-test-sdc-001`) for the private endpoint subnet `snet-pe-aigw-test`. In dev this is `10.179.231.64/26`.

Fill the value into `infra/bicep/environments/test/main.bicepparam` as `param peSubnetPrefix`.

---

### 2. Entra App Registration — `ai-gw-github-actions-test`

Create an Entra App Registration for GitHub Actions OIDC-based deploys to the test environment.

**Federated credentials** (two required):
| Subject | Used for |
|---|---|
| `repo:SimCorp/ai-gw:ref:refs/tags/v*` | Automatic deploys on version tag push |
| `repo:SimCorp/ai-gw:ref:refs/heads/master` | Manual `workflow_dispatch` deploys |

**Role assignments** (test subscription only, not subscription-wide):
| Role | Scope |
|---|---|
| `Contributor` | `rg-aigw-test-sdc` resource group |
| `AcrPush` | `acraigwtestsdc` container registry (when switching from GHCR) |

**Outputs needed** → add to GitHub repo secrets:
| Secret name | Value |
|---|---|
| `AZURE_CLIENT_ID_TEST` | Client ID of the new App Registration |
| `AZURE_SUBSCRIPTION_ID_TEST` | PlatformAITooling Test subscription ID |

Note: `AZURE_TENANT_ID` is the same as dev (`aa81b43f-3969-4fd4-80c9-84c411508d82`) — no new secret needed.

Also fill `<TEST_DEPLOYING_PRINCIPAL_ID>` in `infra/bicep/environments/test/main.bicepparam` with the service principal's object ID.

---

### 3. Hub DNS conditional forwarder

Forward `aigw-test.lab.cloud.scdom.net` to `168.63.129.16` (Azure DNS resolver in test VNet). This enables VPN client resolution of the test ACA ingress IP without a full zone delegation.

*Same pattern as dev: `aigw-dev.lab.cloud.scdom.net → 168.63.129.16`.*

---

### 4. TLS certificate

**No new certificate is needed.** The wildcard `*.lab.cloud.scdom.net` already covers `aigw-test.lab.cloud.scdom.net`.

Provision the **same PFX** into `kv-aigw-test-sdc` as secret `tls-wildcard-lab` at first deploy time (same secret name as dev — used by both environments).

---

## Required after first `main.bicep` deploy to test

After the first deploy, update `infra/bicep/environments/test/main.bicepparam` with the post-deploy outputs (ACA static IP, default domain).

### 5. Private DNS zone for ACA ingress

Create a private DNS A record resolving `aigw-test.lab.cloud.scdom.net` to the test ACA static IP (output of first `main.bicep` deploy), in `rg-spoke-platformaitooling-test-sdc-001`, linked to `vnet-spoke-platformaitooling-test-sdc-001`.

*Same pattern as dev.*

---

## Required when switching from GHCR to ACR

Currently images are pulled from GHCR (PAT auth). When ACR private endpoint DNS is ready:

### 6. ACR private DNS A records

After the PE IPs are assigned (output of `main.bicep` deploy):

| DNS zone | A record name | IP |
|---|---|---|
| `privatelink.azurecr.io` | `acraigwtestsdc` | PE IP (registry) |
| `swedencentral.data.privatelink.azurecr.io` | `acraigwtestsdc` | PE IP (data plane) |

Both zones must be linked to `vnet-spoke-platformaitooling-test-sdc-001`.

---

## Optional: ZPA app segment for portal access

To access the test portals (`aigw-test.lab.cloud.scdom.net`) from the corporate network via Zscaler ZPA, request a new app segment:

- Protocol: TCP 443 (and 80 for redirect)
- Destination: test ACA static IP (from post-deploy outputs)
- TLS: passthrough (not inspection)

*Same pattern as dev ZPA segment.*
