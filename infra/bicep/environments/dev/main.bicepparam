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
// Pending SC Platform team:
//   DNS A record:  aigw-dev.lab.cloud.scdom.net → 10.179.231.6  (docker-host-dev NGINX retired)
//   Hub firewall:  allow ACA egress from 10.179.231.0/24 to internet (provider APIs)
