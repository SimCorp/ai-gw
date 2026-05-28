# Security Scanner — AI Gateway Developer Platform

**Date:** 2026-05-28
**Status:** Approved
**Scope:** Self-service security scanning for developers building on the AI Gateway (~2000 engineers)

---

## Overview

A developer self-service security scanning platform that lets SimCorp engineers test their AI-integrated applications for vulnerabilities before and during production. Developers register their application URLs, run scans from the developer portal or CI/CD pipelines, and receive structured findings across three dimensions: AI/LLM attack vectors, API/web vulnerabilities, and open network ports/services.

**Primary goals:**
- Give developers fast feedback on security posture without requiring a dedicated security team engagement
- Cover AI-specific threats (prompt injection, jailbreaks, PII extraction) alongside traditional API and network vulnerabilities
- Integrate into CI/CD pipelines so security gates can block deployments on critical findings
- Keep the platform safe through target registration approval, scan type restrictions, and per-team quotas

---

## Architecture

Two services collaborate. The **admin service** (existing, `:8005`) gains target registration management and quota administration, surfaced in both portals. The **scanner service** (new, `:8011`) is the execution plane: it owns the job queue, Docker socket access, scan container lifecycle, and raw result storage.

```
Developer Portal / CI Pipeline
        │
        ├── POST /admin/scanner/targets       → admin service  (register a target)
        ├── POST /scanner/jobs                → scanner service (submit a scan job)
        ├── GET  /scanner/jobs/{id}           → scanner service (poll status)
        └── GET  /scanner/jobs/{id}/results   → scanner service (fetch findings)

Admin Portal
        ├── GET/PATCH /admin/scanner/targets  → admin service  (approve/revoke targets)
        ├── GET/PATCH /admin/scanner/quotas   → admin service  (view/set team quotas)
        └── GET       /scanner/jobs           → scanner service (all jobs, admin view)

Scanner Service (internal only — not exposed via nginx to the internet)
        ├── Redis queue          ← jobs pushed here, worker polls
        ├── Docker socket        ← spins up ephemeral scanner containers
        └── Postgres             ← scan_targets, scan_jobs, scan_findings tables
```

The scanner service is exposed via nginx at `/scanner/` (same pattern as other gateway services). Nginx blocks any request path starting with `/scanner/internal/` — those endpoints are reachable only by the worker process running inside the scanner service container. The Docker socket is mounted into the scanner service container only.

---

## Scan Engines

| Engine | Category | License | Docker image |
|---|---|---|---|
| Garak (NVIDIA) | AI/LLM attacks | Apache 2.0 | Custom image built from `pip install garak` |
| Nuclei (ProjectDiscovery) | API/web vulnerabilities | MIT | `projectdiscovery/nuclei` |
| OWASP ZAP | API/web (deep, OpenAPI) | Apache 2.0 | `zaproxy/zap-stable` |
| Nmap | Port/network discovery | NPSL (internal use OK) | `instrumentisto/nmap` or alpine-built |
| RustScan | Port discovery front-end | GPL v3 (internal use OK) | Official RustScan Docker image |

**Garak** covers prompt injection, jailbreaks, PII extraction, data leakage, and toxicity using 50+ probe modules. No official Docker image — the scanner service maintains a custom image built from the pip package.

**Nuclei** runs template-based API and web vulnerability checks with low false positive rate. Templates used: `http/vulnerabilities`, `http/exposures`, `http/misconfiguration`, `http/technologies`, and a curated `api-security` subset.

**ZAP** runs only when a developer has registered an OpenAPI spec with their target. Covers OWASP API Top 10 logic-level vulnerabilities that template-based tools miss.

**Nmap + RustScan**: RustScan performs fast initial port discovery, then hands discovered ports to Nmap for service version detection and NSE script scanning. Output is Nmap XML, parsed into structured findings.

---

## Scan Tiers

| Tier | Nmap | Nuclei | ZAP | Garak probes | Target runtime |
|---|---|---|---|---|---|
| `quick` | Top 100 ports | `technologies` only | No | 5 probes | ~5 min |
| `standard` | Top 1000 ports | `vulnerabilities` + `api` | No | 15 probes | ~15 min |
| `deep` | Full port range | All templates | Yes (if OpenAPI spec registered) | Full suite | ~45 min |

Default team quota allows `quick` tier only. Admins unlock `standard` or `deep` per team.

Nmap and Nuclei run in parallel. Garak runs sequentially after Nmap (uses the open port/service list to focus probes). ZAP runs in parallel with Garak when enabled. Each scanner container has a hard 15-minute timeout; on timeout the container is killed and findings collected so far are saved.

---

## Data Model

### `scan_targets`
Registered application URLs that teams are permitted to scan.

```sql
CREATE TABLE scan_targets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id         UUID NOT NULL REFERENCES teams(id),
    url             TEXT NOT NULL,
    label           TEXT NOT NULL,
    openapi_spec_url TEXT,                         -- optional; enables ZAP deep scan
    allowed_scan_types TEXT[] NOT NULL DEFAULT '{"ai","api","network"}',
    status          TEXT NOT NULL DEFAULT 'pending_approval',
                    -- pending_approval | approved | revoked
    approved_by     UUID REFERENCES users(id),
    approved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      UUID NOT NULL REFERENCES users(id),
    notes           TEXT                           -- admin notes on approval/revocation
);
```

External targets (non-`*.simcorp.internal`, non-RFC-1918) are rejected at registration time unless the team's `scanner_quota.allow_external_targets` is `true`.

### `scan_jobs`
One row per scan execution.

```sql
CREATE TABLE scan_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id         UUID NOT NULL REFERENCES teams(id),
    target_id       UUID NOT NULL REFERENCES scan_targets(id),
    requested_by    UUID NOT NULL REFERENCES users(id),
    scan_types      TEXT[] NOT NULL,               -- subset of target's allowed_scan_types
    tier            TEXT NOT NULL,                 -- quick | standard | deep
    status          TEXT NOT NULL DEFAULT 'queued',
                    -- queued | running | completed | failed | cancelled
    trigger         TEXT NOT NULL DEFAULT 'manual',-- manual | scheduled | ci_pipeline
    ci_ref          TEXT,                          -- e.g. "main@abc123" from CI
    queued_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    error_message   TEXT,
    worker_id       TEXT                           -- which worker picked up the job
);
```

### `scan_findings`
One row per finding from any scanner.

```sql
CREATE TABLE scan_findings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID NOT NULL REFERENCES scan_jobs(id) ON DELETE CASCADE,
    scanner         TEXT NOT NULL,                 -- garak | nuclei | zap | nmap
    severity        TEXT NOT NULL,                 -- critical | high | medium | low | info
    category        TEXT NOT NULL,
                    -- prompt_injection | jailbreak | pii_extraction |
                    -- api_vuln | auth_bypass | open_port | service_exposure | ...
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    evidence        JSONB,                         -- raw scanner output, truncated to 10 KB
    remediation     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ON scan_findings(job_id);
CREATE INDEX ON scan_findings(severity);
```

### Team quota (added to existing `teams` table)
```sql
ALTER TABLE teams ADD COLUMN scanner_quota JSONB NOT NULL DEFAULT '{
    "daily_limit": 3,
    "allow_external_targets": false,
    "max_tier": "quick"
}'::jsonb;
```

---

## Scanner Service API

Authentication: Bearer token (team API key) validated against the existing auth service. Admin endpoints additionally require `admin` role claim.

### Job submission
```
POST /jobs
{
  "target_id": "uuid",
  "scan_types": ["ai", "api", "network"],  // optional, defaults to target's allowed types
  "tier": "quick",
  "trigger": "ci_pipeline",
  "ci_ref": "main@abc123"                  // optional
}

→ 202 Accepted
{
  "job_id": "uuid",
  "status": "queued",
  "estimated_duration_minutes": 5
}

→ 403  target not approved / scan type not allowed
→ 429  quota exceeded  { "daily_used": 3, "daily_limit": 3, "resets_at": "..." }
```

### Job status & results
```
GET  /jobs/{id}           → { status, progress_pct, findings_count, ... }
DELETE /jobs/{id}         → cancel queued or running job
GET  /jobs/{id}/results   → paginated findings
GET  /jobs/{id}/results?format=sarif  → SARIF 2.1 export
GET  /jobs                → list jobs (team-scoped; admin sees all teams)
```

### Internal worker endpoints (nginx-blocked, localhost only)
The scan worker authenticates to these endpoints using a shared secret (`SCANNER_WORKER_SECRET` env var), passed as `Authorization: Bearer <secret>`. These routes are unreachable from outside the scanner service container.

```
POST /internal/jobs/{id}/progress   → worker reports progress updates
POST /internal/jobs/{id}/findings   → worker bulk-inserts findings
POST /internal/jobs/{id}/complete   → worker marks job done
```

---

## Guardrail Enforcement

Three layers evaluated in order on every job submission:

**Layer 1 — Target registration**
The `target_id` must reference a `scan_targets` row with `status = approved`. Unregistered or revoked targets return `403`. External targets require `scanner_quota.allow_external_targets = true` on the team — enforced at registration approval, not at scan time.

**Layer 2 — Scan type restriction**
`scan_targets.allowed_scan_types` is set by the admin at approval time. A job requesting a scan type not in the target's allowed set returns `403` with which types are permitted.

**Layer 3 — Rate limits and quotas**
Redis counter per team per calendar day (UTC):
```
Key:  scanner:quota:{team_id}:{YYYY-MM-DD}
TTL:  expires midnight UTC
```
- `daily_limit`: max jobs per team per day (default 3)
- `max_tier`: `quick` by default; admins unlock `standard` or `deep`
- Concurrent limit: max 2 running jobs per team at once

On quota breach: `429` with `X-Quota-Resets-At` header and `{ daily_used, daily_limit, resets_at }` body.

**Global kill switch**: a Redis flag `scanner:disabled` — when set, all job submissions return `503` immediately without touching the database. Admins toggle this from the admin portal.

---

## CI/CD Integration

Teams submit jobs using their existing gateway API key. Typical pipeline pattern:

```bash
# Submit scan
JOB=$(curl -sf -X POST $GATEWAY_URL/scanner/jobs \
  -H "Authorization: Bearer $TEAM_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"target_id\": \"$TARGET_ID\", \"tier\": \"quick\", \"trigger\": \"ci_pipeline\", \"ci_ref\": \"$CI_COMMIT_SHA\"}" \
  | jq -r .job_id)

# Poll until complete (max 10 minutes)
for i in $(seq 1 60); do
  STATUS=$(curl -sf $GATEWAY_URL/scanner/jobs/$JOB | jq -r .status)
  [ "$STATUS" = "completed" ] && break
  [ "$STATUS" = "failed" ] && exit 1
  sleep 10
done

# Fail build on any critical findings
CRITICALS=$(curl -sf "$GATEWAY_URL/scanner/jobs/$JOB/results?severity=critical" | jq '.total')
[ "$CRITICALS" -gt 0 ] && echo "CRITICAL findings found — blocking deployment" && exit 1
```

SARIF output integrates with GitHub Advanced Security and Azure DevOps security dashboards via the `?format=sarif` query parameter.

---

## Developer Portal UI

New **Security** section in the left navigation of the developer portal.

**Targets tab**
- Lists the team's registered targets with status badges (pending / approved / revoked)
- "Register target" button: form with URL, label, requested scan types, optional OpenAPI spec URL
- Approved targets show last scan date and finding counts

**Scans tab**
- "Run scan" button: pick approved target → choose tier (gated by team quota) → optional label → submit
- Jobs list with live status indicators (polling every 3 s while running)
- Clicking a completed job opens the results view

**Results view**
- Summary bar: `3 critical · 7 high · 12 medium · 4 low`
- Findings grouped by severity then by scanner
- Each finding: title, category, evidence excerpt, remediation guidance
- Critical and high findings visually highlighted
- "Download SARIF" button at the top of the results page

---

## Admin Portal UI

New **Scanner** section in the admin portal.

**Targets tab**
- Approval queue: pending registrations with team name, URL, requested scan types, requester, date
- Approve with scan type checkboxes (admin can restrict allowed types at approval time)
- Revoke existing approved targets with a reason note

**Jobs tab**
- All running and recent jobs across all teams: team, target, tier, status, duration
- Cancel any running job
- Filter by team, status, date range

**Quotas tab**
- Per-team quota table: inline-editable `daily_limit`, `max_tier` dropdown, `allow_external_targets` toggle
- Global kill switch toggle at the top of the page

---

## Error Handling

- **Scanner container fails to start**: job status → `failed`, error recorded, quota counter is not incremented (failed submissions don't count against the daily limit)
- **Scanner timeout (15 min)**: container killed, findings collected so far are saved, job status → `completed` with a `partial_results: true` flag
- **Garak probe failure**: individual probe failure is logged as a finding with `severity: info` and `category: scan_error`; remaining probes continue
- **Redis unavailable**: quota check fails open — job is accepted and a `quota_check_skipped: true` flag is recorded on the job row for audit purposes
- **Postgres unavailable**: job submission returns `503`; no partial state is written

---

## Testing

- **Unit tests**: quota enforcement logic, SARIF serialisation, finding severity normalisation per scanner
- **Integration tests**: full job lifecycle against a mock target (httpbin + a local LLM stub for Garak); assert findings are written and status transitions are correct
- **Contract tests**: scanner service internal worker endpoints — assert the worker protocol matches the service's expected schema
- No mocks for Postgres or Redis in integration tests (same policy as the rest of the gateway — real instances via Docker Compose)

---

## Out of Scope

- Scanning the AI gateway's own infrastructure (admin-initiated posture audits are a separate concern)
- Authenticated scanning (providing session cookies or JWT tokens for the target app) — deferred to v2
- Scheduled/recurring scans — deferred to v2 (the data model supports `trigger: scheduled` but the scheduling UI and cron worker are not in scope for v1)
- Dependency/SBOM scanning (Trivy, Grype) — different threat model, deferred
