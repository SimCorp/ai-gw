// infra/bicep/modules/gateway.bicep
// Front-door reverse proxy for the AI Gateway.
//
// Owns the single public hostname (aigw-${env}.lab.cloud.scdom.net) (the one entry
// point brokered to clients via Zscaler ZPA) and path-routes it to the internal
// services over the ACA environment's DNS. This replaces the ad-hoc local-dev
// nginx container that had leaked into Azure: it is version-controlled IaC built
// from a stock Caddy image with the Caddyfile delivered as a mounted secret —
// no custom image, no CI build step.
//
// TLS: ACA's envoy edge terminates TLS for the custom domain using the env
// wildcard cert (SNI binding). Caddy itself listens plain HTTP on :8080.
//
// Host rewrite: ACA internal ingress routes by the HTTP Host header, so each
// reverse_proxy rewrites Host to the target service's name (otherwise envoy
// returns "Container App does not exist").
//
// Deploy standalone (no GHCR PAT needed — caddy is a public image):
//   az deployment group create -g rg-aigw-dev-sdc \
//     --template-file infra/bicep/modules/gateway.bicep \
//     --parameters env=dev location=swedencentral \
//       acaEnvId=$(az containerapp env show -n cae-aigw-dev-sdc -g rg-aigw-dev-sdc --query id -o tsv)

param env string
param location string
param acaEnvId string
param tags object = {}
param customDomain string  // required — passed from containerApps.bicep via gatewayHostname
param certificateName string = 'tls-wildcard-lab'

// NOTE: Bicep multi-line strings ('''...''') are RAW — they do NOT interpolate
// ${...}. Caddy also treats {...} as its own placeholder syntax. So the env is
// templated with the sentinel __ENV__ and substituted via replace() below; this
// keeps the Caddyfile free of ${} (which Caddy would reject next to a scheme).
var caddyfileTemplate = '''
{
	admin off
	auto_https off
}

:8080 {
	encode gzip

	# Agent inference (OpenAI-compatible). Agents set
	# base_url = https://<gatewayHostname>/v1
	# cache serves /v1/chat/completions (validates the sk-* key, then auth -> litellm).
	handle /v1/* {
		reverse_proxy http://ca-cache-__ENV__-sdc:80 {
			header_up Host ca-cache-__ENV__-sdc
		}
	}

	# Admin portal (Next.js basePath /admin - keep the prefix).
	handle /admin* {
		reverse_proxy http://ca-admin-portal-__ENV__-sdc:80 {
			header_up Host ca-admin-portal-__ENV__-sdc
		}
	}

	# API services (strip the /prefix/ -> service root).
	handle_path /api/admin/* {
		reverse_proxy http://ca-admin-__ENV__-sdc:80 {
			header_up Host ca-admin-__ENV__-sdc
		}
	}
	handle_path /api/cache/* {
		reverse_proxy http://ca-cache-__ENV__-sdc:80 {
			header_up Host ca-cache-__ENV__-sdc
		}
	}
	handle_path /api/litellm/* {
		reverse_proxy http://ca-litellm-__ENV__-sdc:80 {
			header_up Host ca-litellm-__ENV__-sdc
		}
	}
	handle_path /api/identity/* {
		reverse_proxy http://ca-identity-__ENV__-sdc:80 {
			header_up Host ca-identity-__ENV__-sdc
		}
	}
	handle_path /api/librarian/* {
		reverse_proxy http://ca-librarian-__ENV__-sdc:80 {
			header_up Host ca-librarian-__ENV__-sdc
		}
	}
	handle_path /api/memory/* {
		reverse_proxy http://ca-memory-__ENV__-sdc:80 {
			header_up Host ca-memory-__ENV__-sdc
		}
	}
	handle_path /api/league/* {
		reverse_proxy http://ca-league-__ENV__-sdc:80 {
			header_up Host ca-league-__ENV__-sdc
		}
	}
	handle_path /api/observability/* {
		reverse_proxy http://ca-observability-__ENV__-sdc:80 {
			header_up Host ca-observability-__ENV__-sdc
		}
	}

	# WebSocket relay bus for agentic workflows.
	handle /agent-relay/* {
		reverse_proxy http://ca-agent-relay-__ENV__-sdc:80 {
			header_up Host ca-agent-relay-__ENV__-sdc
		}
	}

	# Direct login convenience - the admin service serves /auth/* at its root.
	handle /auth/* {
		reverse_proxy http://ca-admin-__ENV__-sdc:80 {
			header_up Host ca-admin-__ENV__-sdc
		}
	}

	# Front-door liveness (also the ACA ingress probe target).
	handle /health {
		respond "ok" 200
	}

	# Dev portal at the root - catch-all for everything not matched above
	# (Next.js app with no basePath: /, /keys, /docs, /_next/*, assets, ...).
	handle {
		reverse_proxy http://ca-portal-__ENV__-sdc:80 {
			header_up Host ca-portal-__ENV__-sdc
		}
	}
}
'''

var caddyfile = replace(caddyfileTemplate, '__ENV__', env)

resource caGateway 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-gateway-${env}-sdc'
  location: location
  tags: tags
  properties: {
    managedEnvironmentId: acaEnvId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false
        targetPort: 8080
        transport: 'Http'
        customDomains: [
          {
            name: customDomain
            bindingType: 'SniEnabled'
            certificateId: '${acaEnvId}/certificates/${certificateName}'
          }
        ]
      }
      secrets: [
        // The Caddyfile is configuration, not a credential — it's delivered as an
        // ACA secret only because that's how a Secret volume is sourced.
        #disable-next-line use-secure-value-for-secure-inputs
        { name: 'caddyfile', value: caddyfile }
      ]
    }
    template: {
      containers: [
        {
          name: 'gateway'
          image: 'docker.io/library/caddy:2.8-alpine'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          volumeMounts: [
            { volumeName: 'caddy-config', mountPath: '/etc/caddy' }
          ]
        }
      ]
      volumes: [
        {
          name: 'caddy-config'
          storageType: 'Secret'
          secrets: [
            { secretRef: 'caddyfile', path: 'Caddyfile' }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 2
      }
    }
  }
}

output fqdn string = caGateway.properties.configuration.ingress.fqdn
