# GIT request package — ai-gw internal access via Zscaler ZPA

**Requestor:** bntp@simcorp.com · **Date:** 2026-06-17 · **Environment:** dev (Sweden Central)
**Goal:** internal-only access to the ai-gw developer platform from corp workstations over
Zscaler ZPA, on a clean trusted hostname **`dev.aigw.scdom.net`** (wildcard cert
`*.aigw.scdom.net` so test/prod can follow).

> The service is already deployed, healthy, and working internally (app-to-app). The only
> gap is reaching it from a developer's machine with a trusted name. The requests below are
> the minimum needed. Nothing here exposes the service to the public internet.

## Key coordinates (for every request below)

| Item | Value |
|---|---|
| Hostname (dev) | `dev.aigw.scdom.net` |
| Wildcard cert subject | `*.aigw.scdom.net` |
| Target IP (ACA env load balancer) | **`10.179.231.6`** |
| Port | **TCP 443 only** (TLS mandatory; plain HTTP is policy-denied) |
| Spoke VNet | `vnet-spoke-platformaitooling-dev-sdc-001` — `10.179.231.0/25`, Sweden Central |
| ACA subnet of the LB | `snet-aca-infra` — `10.179.231.0/27` |
| Subscription | `8fc66d8e-c80e-454e-9248-b67af047c2c2` (PlatformAITooling Dev) |
| Resource group | `rg-aigw-dev-sdc` |

## Access chain

```
developer browser/agent
  → Zscaler Client Connector
  → ZPA App Connector ──(TCP 443, TLS passthrough, no inspection)──▶ 10.179.231.6 (ACA env LB)
                                                                       envoy serves *.aigw.scdom.net (SNI)
                                                                       → ca-gateway-dev-sdc (path-routes to services)
DNS  dev.aigw.scdom.net      A   → 10.179.231.6   (internal / split-horizon)
     asuid.dev.aigw.scdom.net TXT → <verification id>  (public — ownership proof only)
```

---

## R1 — Public DNS: domain-ownership TXT (one record)

- **Zone:** `aigw.scdom.net` (or `scdom.net`), **public** authoritative DNS.
- **Record:** `asuid.dev.aigw.scdom.net`  **TXT** = `<customDomainVerificationId>`
- Value supplied by us at submission time (obtained from Azure; stable per app). It contains
  **no IP and no service data** — it only proves we own the name so Azure will issue/bind the
  TLS cert for the hostname. Can be removed after binding; keeping it simplifies future rebinds.

## R2 — Internal DNS: A record (split-horizon, not public)

- **Resolver:** corporate **internal** DNS view used by ZPA App Connectors and corp clients.
- **Record:** `dev.aigw.scdom.net`  **A** = `10.179.231.6`
- Optional future-proofing: `*.aigw.scdom.net` A = `10.179.231.6` (only if subdomain-per-service
  routing is wanted later — not required today).

## R3 — Certificate: wildcard from SimCorp internal CA

- **Subject / SAN:** `*.aigw.scdom.net` (add SAN `aigw.scdom.net` if the apex will be used).
- **Issuer:** SimCorp **internal / enterprise CA** (trusted on corp-managed devices).
- **Deliver to us:** a **PFX (PKCS#12) with private key** + password, over a secure channel
  (Key Vault drop or `pass`). We import it to the ACA environment ourselves.
- **Constraints:** EKU Server Authentication; RSA ≥2048 or ECDSA P-256.

## R4 — Zscaler ZPA: application segment

- **Domain:** `dev.aigw.scdom.net` (or `*.aigw.scdom.net` to cover future hosts).
- **Port:** **TCP 443** only. No UDP. Do **not** include 53.
- **Destination:** resolves (via R2) to `10.179.231.6`; assign an **App Connector group** that
  routes into spoke VNet `10.179.231.0/25` (Sweden Central).
- **TLS inspection:** **bypass / disabled** for this segment — clients must complete TLS
  end-to-end with the backend so the `*.aigw.scdom.net` SNI cert is presented intact.
- **Access policy:** grant the relevant developer group(s).

## R5 — Firewall / NSG (only if a hub firewall sits between ZPA and the spoke)

- **Allow:** `TCP 443` from the ZPA App Connector source range → `10.179.231.6`. No other ports.
- If App Connectors already route freely into `10.179.231.0/25`, this is a no-op — please confirm.

## R6 — Azure Policy exemption (platform / Landing-Zone governance)

- **Need:** flip the gateway app `ca-gateway-dev-sdc` ingress to `external:true`. On this
  **internal** ACA environment that means **VNet-visible only — NOT internet-exposed** (the
  environment has no public IP). Without it, the env load balancer `.6` cannot route to the app.
- **Exemption:** category **Waiver**, scoped to the single resource
  `.../rg-aigw-dev-sdc/providers/Microsoft.App/containerApps/ca-gateway-dev-sdc`,
  targeting **only** reference id `Deny-ContainerApps-Public-Network-Access`
  (definition `783ea2a8-b8fd-46be-896a-9ae79643a0b1`, initiative `Deny-PublicPaaSEndpoints`,
  MG `mg-sclz-landingzones-corp`).
- All backend services (auth, cache, litellm, portal, …) stay `external:false`; the rest of the
  PaaS-deny initiative stays fully enforced.

---

## Open questions to resolve in the same ticket

1. New delegated public sub-zone `aigw.scdom.net`, or records directly under `scdom.net`?
   (Only R1's TXT is public; R2 is internal.)
2. Where do the ZPA App Connectors live, and do they already route to `10.179.231.0/25`?
   (Decides whether R5 is needed.)
3. Can the internal CA issue a **wildcard** SAN? If not, an explicit SAN list
   (`dev.`/`test.`/`prod.aigw.scdom.net`) is fine.

## What we do after fulfillment (no further GIT action)

Upload the R3 cert to the ACA environment, bind `dev.aigw.scdom.net` (validates once R1 is
live), flip ingress to external (succeeds once R6 is in place), and codify all three in Bicep
(`infra/bicep/modules/gateway.bicep`). Then verify: `https://dev.aigw.scdom.net/portal/` → 200
with the trusted cert, and `POST /v1/chat/completions` with an API key → 200.
