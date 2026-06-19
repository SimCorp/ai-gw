// infra/bicep/environments/test/main.bicepparam
// Committed to git — contains NO secrets.
using '../dev/main.bicep'

param location = 'swedencentral'
param env = 'test'
param vnetResourceGroup = 'rg-spoke-platformaitooling-test-sdc-001'
param vnetName = 'vnet-spoke-platformaitooling-test-sdc-001'
param acaInfraSubnetId = '/subscriptions/<TEST_SUBSCRIPTION_ID>/resourceGroups/rg-spoke-platformaitooling-test-sdc-001/providers/Microsoft.Network/virtualNetworks/vnet-spoke-platformaitooling-test-sdc-001/subnets/snet-aca-infra'
param peSubnetPrefix = '<TEST_PE_SUBNET_CIDR>'
param deployingPrincipalId = '<TEST_DEPLOYING_PRINCIPAL_ID>'
param imageTag = 'sha-<placeholder>'  // MUST override at deploy time: sha-XXXXXXX or v1.2.3

// postgresAdminPassword, tlsCertBase64, tlsCertPassword are passed at deploy time
// via --parameters on the az CLI command — never committed to this file.

// ── Pending platform-team inputs (fill before first main.bicep deploy) ─────────
// <TEST_SUBSCRIPTION_ID>       — PlatformAITooling Test subscription ID
// <TEST_PE_SUBNET_CIDR>        — available CIDR in test VNet for snet-pe-aigw-test (e.g. 10.x.x.64/26)
// <TEST_DEPLOYING_PRINCIPAL_ID> — object ID of ai-gw-github-actions-test SP in test tenant
//
// See docs/access/2026-06-18-test-environment-access-request.md for all IT requests.

// ── Post-deploy outputs (fill after first main.bicep deploy to test) ─────────
// acaStaticIp:       <fill after deploy>
// acaDefaultDomain:  <fill after deploy>
// acrLoginServer:    acraigwtestsdc.azurecr.io
//
// DNS: private zone aigw-test.lab.cloud.scdom.net → <acaStaticIp> to be created in
//   rg-spoke-platformaitooling-test-sdc-001, linked to spoke VNet.
//
// ── Pending platform-team requests ─────────────────────────────────────────────
// 1. Hub DNS conditional forwarder: aigw-test.lab.cloud.scdom.net → 168.63.129.16
//
// 2. ACR private DNS A records (required when switching from GHCR to ACR):
//    a) Zone: privatelink.azurecr.io
//       A record: acraigwtestsdc → <assigned PE IP>
//    b) Zone: swedencentral.data.privatelink.azurecr.io
//       A record: acraigwtestsdc → <assigned data-plane PE IP>
//    Both zones must be linked to vnet-spoke-platformaitooling-test-sdc-001.
//
// 3. Entra App Registration "ai-gw-github-actions-test":
//    Federated credentials:
//      repo=SimCorp/ai-gw, subject=repo:SimCorp/ai-gw:ref:refs/tags/v*
//      repo=SimCorp/ai-gw, subject=repo:SimCorp/ai-gw:ref:refs/heads/master
//    Assign: Contributor on rg-aigw-test-sdc
//    Then add GitHub repo secrets: AZURE_CLIENT_ID_TEST, AZURE_SUBSCRIPTION_ID_TEST
//    (AZURE_TENANT_ID=aa81b43f-3969-4fd4-80c9-84c411508d82 — same as dev)
