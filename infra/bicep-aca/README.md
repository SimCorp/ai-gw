# ACA Bicep Infrastructure (Archived)

This directory contains the Bicep IaC that deployed the AI Gateway to Azure Container Apps.

It has been superseded by `infra/docker-compose.yml` which deploys all services as Docker
containers on a Linux VM in the same spoke VNet (PlatformAITooling Dev, Sweden Central).

The ACA deployment was non-functional due to `internal: true` ACA environment + all apps
having `external: false`, making them unreachable from clients outside the environment
(see issue #55). Rather than pursue a policy exemption from the SCLZ platform team,
the deployment was simplified to Docker Compose on `vm-aigw-dev-sdc`.
