// infra/bicep/environments/dev/main.bicepparam
// Committed to git — contains NO secrets.
using './main.bicep'

param location = 'swedencentral'
param env = 'dev'
param vnetResourceGroup = 'rg-spoke-platformaitooling-dev-sdc-001'
param vnetName = 'vnet-spoke-platformaitooling-dev-sdc-001'
param acaInfraSubnetId = '/subscriptions/8fc66d8e-c80e-454e-9248-b67af047c2c2/resourceGroups/rg-spoke-platformaitooling-dev-sdc-001/providers/Microsoft.Network/virtualNetworks/vnet-spoke-platformaitooling-dev-sdc-001/subnets/snet-aca-infra'
param deployingPrincipalId = '45674099-3cd8-404c-a6ad-871027c8a585'

// postgresAdminPassword, tlsCertBase64, tlsCertPassword are passed at deploy time
// via --parameters on the az CLI command — never committed to this file.

// ── Post-deploy outputs (aigw-phase1-202606091324, 2026-06-09) ───────────────
// acaStaticIp:       10.179.231.6
// acaDefaultDomain:  calmbush-e5f546e4.swedencentral.azurecontainerapps.io
// acrLoginServer:    acraigwdevsdc.azurecr.io
// tlsCertId:         .../managedEnvironments/cae-aigw-dev-sdc/certificates/tls-wildcard-lab
//
// DNS: private zone aigw-dev.lab.cloud.scdom.net → 10.179.231.6 created in
//   rg-spoke-platformaitooling-dev-sdc-001, linked to spoke VNet.
// Egress: snet-aca-infra has no UDR/NAT GW — Azure default SNAT provides outbound internet.
//
// ── Pending platform-team requests ───────────────────────────────────────────
// 1. Hub DNS conditional forwarder: aigw-dev.lab.cloud.scdom.net → 168.63.129.16
//    (lets VPN clients resolve the ACA ingress IP without a full zone delegation)
// 2. Entra App Registration "ai-gw-github-actions" + Federated Credential:
//    repo=SimCorp/ai-gw, subject=repo:SimCorp/ai-gw:ref:refs/heads/master
//    Assign: AcrPush on acraigwdevsdc, Contributor on rg-aigw-dev-sdc
//    Then add GitHub repo secrets: AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID
//    (AZURE_TENANT_ID=aa81b43f-3969-4fd4-80c9-84c411508d82,
//     AZURE_SUBSCRIPTION_ID=8fc66d8e-c80e-454e-9248-b67af047c2c2)
