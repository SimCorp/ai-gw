# Security Scanner API

The Security Scanner service provides automated vulnerability scanning for AI models, APIs, and network infrastructure. It uses industry-standard tools (Garak, Nuclei, Nmap, ZAP) to identify security issues in a multi-tenant environment with quota enforcement and approval workflows.

**Service URL**: https://dev.aigw.scdom.net/scanner/

---

## Overview

The scanner service runs on-demand security scans against registered targets (APIs, AI models, services). Scans are queued, executed by Docker-based workers, and results are stored with severity levels and remediation guidance.

### Scan Types

| Scan Type | Tool | Finds | Tiers |
|-----------|------|-------|-------|
| **ai** | Garak | Prompt injection, jailbreaks, PII leakage, toxicity, XSS | quick, standard, deep |
| **api** | Nuclei + ZAP | OWASP API top-10, misconfigurations, exposures, CVEs | quick, standard, deep |
| **network** | Nmap | Open ports, services, OS fingerprints | quick, standard, deep |

### Scan Tiers

- **quick** (5 min): Fast scan for critical issues — top 100 ports, basic API checks, prompt injection only
- **standard** (15 min): Balanced coverage — top 1000 ports, full API vulnerabilities, comprehensive AI probes
- **deep** (45 min): Exhaustive scan — all ports, deep API scanning with ZAP, all AI probes

---

## Target Registration

Before scanning, administrators must register and approve targets. Targets are scoped to teams (organization nodes) and support internal/external access control.

### POST /scanner/targets — Register a new target

**Request Body:**
```json
{
  "url": "https://api.example.com",
  "label": "Production API",
  "openapi_spec_url": "https://api.example.com/openapi.json",
  "requested_scan_types": ["ai", "api", "network"],
  "node_id": "550e8400-e29b-41d4-a716-446655440000",
  "created_by": "f47ac10b-58cc-4372-a567-0e02b2c3d479"
}
```

**Field Details:**
- `url` (string, required): Target URL (api.example.com, 10.0.1.5, etc.)
- `label` (string, required): Human-readable name for this target
- `openapi_spec_url` (string, optional): OpenAPI 3.0 spec URL for ZAP deep scans; only used if registered target approves `api` scan type and `deep` tier
- `requested_scan_types` (array, optional): Requested scan types; admin may approve a subset. Default: `["ai", "api", "network"]`
- `node_id` (string, UUID): Team/organization node UUID
- `created_by` (string, UUID): User ID of the requester

**Status Codes:**
- `201` — Target registered (pending admin approval)
- `403` — External URL not allowed for this team (check `allow_external_targets` quota)
- `400` — Invalid request

**Response:**
```json
{
  "id": "uuid",
  "url": "https://api.example.com",
  "label": "Production API",
  "openapi_spec_url": "https://api.example.com/openapi.json",
  "allowed_scan_types": ["ai", "api"],
  "status": "pending_approval",
  "node_id": "uuid",
  "created_by": "uuid",
  "created_at": "2026-05-28T10:30:00Z",
  "approved_by": null,
  "approved_at": null,
  "notes": null
}
```

### GET /scanner/targets — List all targets

**Query Parameters:**
- `node_id` (string, optional): Filter by team/org node
- `status` (string, optional): Filter by status: `pending_approval`, `approved`, `revoked`

**Response:**
```json
[
  {
    "id": "uuid",
    "url": "https://api.example.com",
    "label": "Production API",
    "status": "approved",
    "allowed_scan_types": ["ai", "api"],
    "node_id": "uuid",
    "created_at": "2026-05-28T10:30:00Z",
    "approved_at": "2026-05-28T11:00:00Z"
  }
]
```

### POST /scanner/targets/{target_id}/approve — Approve a target

Admins approve targets and specify which scan types are allowed.

**Request Body:**
```json
{
  "allowed_scan_types": ["ai", "api"],
  "notes": "Approved for tier=quick and tier=standard only",
  "approved_by": "e3f4a5b6-c7d8-4e9f-a0b1-c2d3e4f5a6b7"
}
```

**Field Details:**
- `allowed_scan_types` (array, required): Scan types approved for this target (subset of requested types)
- `notes` (string, optional): Admin approval notes/restrictions
- `approved_by` (string, optional): Approver user UUID

**Response:**
```json
{
  "status": "approved"
}
```

### POST /scanner/targets/{target_id}/revoke — Revoke a target

**Request Body:**
```json
{
  "notes": "API deprecated; no longer needed"
}
```

**Response:**
```json
{
  "status": "revoked"
}
```

---

## Job Submission & Status

Once a target is approved, teams submit scan jobs. The service enforces per-team quotas (daily limit, max tier, concurrent jobs).

### POST /jobs — Submit a scan job

**Request Body:**
```json
{
  "target_id": "550e8400-e29b-41d4-a716-446655440000",
  "scan_types": ["ai", "api"],
  "tier": "standard",
  "trigger": "manual",
  "ci_ref": "main/abc123def456"
}
```

**Field Details:**
- `target_id` (string, UUID, required): Approved target UUID
- `scan_types` (array, optional): Requested scan types (must be subset of `allowed_scan_types` on target); default: all allowed types
- `tier` (string, optional): Scan intensity — `quick`, `standard`, or `deep`. Default: `quick`
- `trigger` (string, optional): Scan trigger source — `manual`, `ci`, or `scheduled`. Default: `manual`
- `ci_ref` (string, optional): CI reference (branch/commit) if triggered by CI/CD

**Status Codes:**
- `202` — Job queued (async processing)
- `403` — Target not approved, scan type not allowed, or tier exceeds quota
- `429` — Daily quota exceeded or concurrent job limit reached (max 2 running per team)
- `503` — Scanning temporarily disabled (kill switch)

**Response:**
```json
{
  "job_id": "uuid",
  "status": "queued",
  "estimated_duration_minutes": 15
}
```

**Quota Rules:**
- Teams have a `daily_limit` (default: 3 jobs/day)
- Teams have a `max_tier` quota (default: `quick`). Requesting a higher tier is rejected.
- Max 2 concurrent running jobs per team
- If quota exceeded, response includes `X-Quota-Resets-At` header with UTC timestamp

### GET /jobs — List jobs for team

**Query Parameters:**
- `status` (string, optional): Filter by status — `queued`, `running`, `completed`, `failed`, `cancelled`
- `limit` (integer, optional): Max results, default 20, max 100

**Response:**
```json
[
  {
    "id": "uuid",
    "node_id": "team-uuid",
    "target_id": "target-uuid",
    "requested_by": "user-uuid or null (API key callers)",
    "scan_types": ["ai", "api"],
    "tier": "standard",
    "status": "completed",
    "trigger": "manual",
    "ci_ref": null,
    "queued_at": "2026-05-28T10:30:00Z",
    "started_at": "2026-05-28T10:31:00Z",
    "finished_at": "2026-05-28T10:46:00Z",
    "error_message": null,
    "worker_id": "scanner-pod-01-12345",
    "partial_results": false
  }
]
```

### GET /jobs/{job_id} — Get job details

**Response:**
```json
{
  "id": "uuid",
  "node_id": "team-uuid",
  "target_id": "target-uuid",
  "requested_by": "user-uuid or null (API key callers)",
  "scan_types": ["ai", "api"],
  "tier": "standard",
  "status": "completed",
  "trigger": "manual",
  "queued_at": "2026-05-28T10:30:00Z",
  "started_at": "2026-05-28T10:31:00Z",
  "finished_at": "2026-05-28T10:46:00Z",
  "error_message": null,
  "worker_id": "scanner-pod-01-12345",
  "partial_results": false
}
```

**Job Status Workflow:**
- `queued` → `running` → `completed`/`failed`/`cancelled`
- `partial_results=true`: Some scanners timed out; results are incomplete but non-critical

### DELETE /jobs/{job_id} — Cancel a job

Only cancels jobs in `queued` or `running` status.

**Status Codes:**
- `204` — Cancelled
- `404` — Job not found or already finished

---

## Results & Findings

### GET /jobs/{job_id}/results — Fetch findings for a job

**Query Parameters:**
- `severity` (string, optional): Filter by severity — `critical`, `high`, `medium`, `low`, `info`
- `format` (string, optional): Return format — `json` (default) or `sarif` (SARIF 2.1.0 format for CI integration)
- `offset` (integer, optional): Pagination offset, default 0
- `limit` (integer, optional): Max results, default 50, max 200

**Response (JSON):**
```json
{
  "total": 42,
  "offset": 0,
  "findings": [
    {
      "id": "uuid",
      "job_id": "job-uuid",
      "scanner": "garak",
      "severity": "high",
      "category": "prompt_injection",
      "title": "Garak probe failed: promptinjection.HijackHateHumans",
      "description": "The probe 'promptinjection.HijackHateHumans' triggered a failure. The model may be susceptible to prompt injection.",
      "evidence": {
        "probe": "promptinjection.HijackHateHumans",
        "passed": false,
        "notes": {"attempt_idx": 2},
        "attempt_idx": 2
      },
      "remediation": "Review the model's system prompt and add guardrail rules to block prompt injection patterns.",
      "created_at": "2026-05-28T10:45:00Z"
    },
    {
      "id": "uuid",
      "job_id": "job-uuid",
      "scanner": "nuclei",
      "severity": "medium",
      "category": "api_vuln",
      "title": "Missing CORS headers",
      "description": "The API does not set restrictive CORS headers, allowing cross-origin requests from any origin.",
      "evidence": {
        "template_id": "http/misconfiguration/cors",
        "matched_at": "https://api.example.com/health",
        "host": "api.example.com",
        "type": "http"
      },
      "remediation": "Set Access-Control-Allow-Origin to a whitelist of trusted origins.",
      "created_at": "2026-05-28T10:45:30Z"
    },
    {
      "id": "uuid",
      "job_id": "job-uuid",
      "scanner": "nmap",
      "severity": "info",
      "category": "network_service",
      "title": "SSH service detected",
      "description": "SSH is open on port 22.",
      "evidence": {
        "port": 22,
        "state": "open",
        "service": "ssh",
        "product": "OpenSSH",
        "version": "8.2p1"
      },
      "remediation": "Ensure SSH access is restricted to internal networks only.",
      "created_at": "2026-05-28T10:45:45Z"
    }
  ]
}
```

**Response (SARIF):**
```json
{
  "version": "2.1.0",
  "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
  "runs": [
    {
      "tool": {
        "driver": {
          "name": "ai-gw-scanner",
          "version": "1.0.0",
          "rules": [
            {
              "id": "garak/prompt_injection",
              "name": "Garak probe failed: promptinjection.HijackHateHumans",
              "shortDescription": {"text": "Garak probe failed: promptinjection.HijackHateHumans"},
              "fullDescription": {"text": "The probe..."},
              "defaultConfiguration": {"level": "error"}
            },
            {
              "id": "nuclei/api_vuln",
              "name": "Missing CORS headers",
              "shortDescription": {"text": "Missing CORS headers"},
              "fullDescription": {"text": "The API does not set..."},
              "defaultConfiguration": {"level": "warning"}
            }
          ]
        }
      },
      "results": [
        {
          "ruleId": "garak/prompt_injection",
          "level": "error",
          "message": {"text": "The probe..."},
          "properties": {"severity": "high", "scanner": "garak"}
        }
      ],
      "properties": {"jobId": "job-uuid"}
    }
  ]
}
```

### Severity Levels

| Level | SARIF Level | Use Case |
|-------|-------------|----------|
| **critical** | error | Immediate threat (RCE, auth bypass, PII leak) |
| **high** | error | Significant risk (XSS, SQLi, prompt injection) |
| **medium** | warning | Moderate impact (missing headers, weak crypto) |
| **low** | note | Minor issue (info disclosure, best practice) |
| **info** | note | Informational only (service found, version detected) |

---

## Admin Endpoints

Admins manage targets, quotas, and system-wide settings.

### GET /scanner/targets — List all targets (admin view)

**Query Parameters:**
- `node_id` (string, optional): Filter by team
- `status` (string, optional): Filter by status

**Response:** Same as team endpoint (see Target Registration)

### GET /scanner/quotas — List all team quotas

**Response:**
```json
[
  {
    "id": "org-node-uuid",
    "name": "Platform Team",
    "scanner_quota": {
      "daily_limit": 10,
      "max_tier": "deep",
      "allow_external_targets": true
    }
  },
  {
    "id": "org-node-uuid",
    "name": "Mobile Team",
    "scanner_quota": {
      "daily_limit": 3,
      "max_tier": "quick",
      "allow_external_targets": false
    }
  }
]
```

### PATCH /scanner/quotas/{node_id} — Update team quota

**Request Body:**
```json
{
  "daily_limit": 5,
  "max_tier": "standard",
  "allow_external_targets": true
}
```

**Field Details:**
- `daily_limit` (integer, optional): Max jobs per day
- `max_tier` (string, optional): Max tier allowed — `quick`, `standard`, or `deep`
- `allow_external_targets` (boolean, optional): Allow scanning external/public URLs

**Response:**
```json
{
  "scanner_quota": {
    "daily_limit": 5,
    "max_tier": "standard",
    "allow_external_targets": true
  }
}
```

### POST /scanner/kill-switch — Toggle scanning on/off

**Query Parameters:**
- `enabled` (boolean, optional): Default `true`

**Response:**
```json
{
  "scanner_disabled": true
}
```

Used during maintenance or security incidents to pause all scanning across all teams.

---

## Worker Protocol (Internal)

Scan workers communicate with the scanner service via internal endpoints. These are protected by `Bearer {scanner_worker_secret}` token.

### POST /internal/jobs/{job_id}/progress

Workers report that they have picked up a job.

**Request Body:**
```json
{
  "worker_id": "scanner-pod-01-12345"
}
```

**Response:**
```json
{
  "ok": true
}
```

### POST /internal/jobs/{job_id}/findings

Workers submit findings as they complete individual scanners.

**Request Body:**
```json
{
  "findings": [
    {
      "scanner": "garak",
      "severity": "high",
      "category": "prompt_injection",
      "title": "Prompt injection detected",
      "description": "Model is susceptible to prompt injection attacks.",
      "evidence": {
        "probe": "promptinjection.HijackHateHumans",
        "passed": false,
        "attempt_idx": 2
      },
      "remediation": "Add guardrails to block prompt injection patterns."
    },
    {
      "scanner": "nuclei",
      "severity": "medium",
      "category": "api_vuln",
      "title": "Missing CORS headers",
      "description": "No restrictive CORS headers detected.",
      "evidence": {
        "template_id": "http/misconfiguration/cors",
        "matched_at": "https://api.example.com/health"
      },
      "remediation": "Set Access-Control-Allow-Origin to a whitelist."
    }
  ]
}
```

**Response:**
```json
{
  "inserted": 2
}
```

### POST /internal/jobs/{job_id}/complete

Workers mark a job as complete (success, failure, partial results).

**Request Body:**
```json
{
  "status": "completed",
  "error_message": null,
  "partial_results": false
}
```

**Field Details:**
- `status` (string, required): `completed`, `failed`, or `cancelled`
- `error_message` (string, optional): Error details if failed
- `partial_results` (boolean, optional): `true` if some scanners timed out but some results were collected

**Response:**
```json
{
  "ok": true
}
```

---

## Data Model

### scan_targets table

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default `gen_random_uuid()` | Target ID |
| `node_id` | UUID | FK→organization_nodes, nullable | Team/org node |
| `url` | TEXT | NOT NULL | Target URL (api.example.com, 10.0.1.5, etc.) |
| `label` | TEXT | NOT NULL | Human-readable name |
| `openapi_spec_url` | TEXT | nullable | OpenAPI 3.0 spec URL for deep scans |
| `allowed_scan_types` | TEXT[] | default `['ai','api','network']` | Approved scan types |
| `status` | TEXT | default `'pending_approval'` | `pending_approval`, `approved`, `revoked` |
| `approved_by` | UUID | FK→users, nullable | Approver user ID |
| `approved_at` | TIMESTAMPTZ | nullable | Approval timestamp |
| `created_at` | TIMESTAMPTZ | default NOW() | Creation timestamp |
| `created_by` | UUID | FK→users, NOT NULL | Requester user ID |
| `notes` | TEXT | nullable | Admin notes/restrictions |

**Indexes:**
- PRIMARY KEY (id)
- FOREIGN KEY (node_id) → organization_nodes(id)
- FOREIGN KEY (created_by, approved_by) → users(id)

### scan_jobs table

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default `gen_random_uuid()` | Job ID |
| `node_id` | UUID | FK→organization_nodes, nullable | Team/org node |
| `target_id` | UUID | FK→scan_targets(id) | Target being scanned |
| `requested_by` | UUID | FK→users, nullable | User who submitted job (null for API key callers) |
| `scan_types` | TEXT[] | NOT NULL | Scan types to run (ai, api, network) |
| `tier` | TEXT | NOT NULL | Scan intensity (quick, standard, deep) |
| `status` | TEXT | default `'queued'` | `queued`, `running`, `completed`, `failed`, `cancelled` |
| `trigger` | TEXT | default `'manual'` | Job trigger (manual, ci, scheduled) |
| `ci_ref` | TEXT | nullable | CI reference (branch/commit) |
| `queued_at` | TIMESTAMPTZ | default NOW() | Queue timestamp |
| `started_at` | TIMESTAMPTZ | nullable | Start timestamp |
| `finished_at` | TIMESTAMPTZ | nullable | Completion timestamp |
| `error_message` | TEXT | nullable | Error details if failed |
| `worker_id` | TEXT | nullable | Worker ID that executed job |
| `partial_results` | BOOLEAN | default false | True if some scanners timed out |

**Indexes:**
- PRIMARY KEY (id)
- `ix_scan_jobs_node_id` (node_id) — for quota checks and listing

### scan_findings table

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default `gen_random_uuid()` | Finding ID |
| `job_id` | UUID | FK→scan_jobs(id), NOT NULL | Parent job (CASCADE on delete) |
| `scanner` | TEXT | NOT NULL | Scanner name (garak, nuclei, nmap, zap) |
| `severity` | TEXT | NOT NULL | Severity level (critical, high, medium, low, info) |
| `category` | TEXT | NOT NULL | Category (prompt_injection, api_vuln, network_service, etc.) |
| `title` | TEXT | NOT NULL | Short title/name |
| `description` | TEXT | NOT NULL | Full description |
| `evidence` | JSONB | nullable | Scanner-specific evidence (probe details, port info, etc.) |
| `remediation` | TEXT | nullable | Remediation steps |
| `created_at` | TIMESTAMPTZ | default NOW() | Finding timestamp |

**Indexes:**
- PRIMARY KEY (id)
- `ix_scan_findings_job_id` (job_id) — for result queries
- `ix_scan_findings_severity` (severity) — for filtering by severity

---

## Quota System

Teams are assigned quotas stored as JSONB in `organization_nodes.scanner_quota`:

```json
{
  "daily_limit": 3,
  "max_tier": "quick",
  "allow_external_targets": false
}
```

### Default Quotas

| Setting | Default | Meaning |
|---------|---------|---------|
| `daily_limit` | 3 | Max jobs per day (resets at UTC midnight) |
| `max_tier` | `quick` | Maximum allowed tier (quick ≤ standard ≤ deep) |
| `allow_external_targets` | false | Allow scanning external/public URLs (true = only internal) |

### Enforcement

1. **Tier enforcement** (checked first): If `tier > max_tier`, reject with 403
2. **Concurrent limit**: If team already has 2 running jobs, reject with 429
3. **Daily limit** (checked last): Increment Redis counter `scanner:quota:{node_id}:{YYYY-MM-DD}`. If exceeds limit, reject with 429 and include `X-Quota-Resets-At` header

---

## Example Workflows

### Scan an API for OWASP top-10 vulnerabilities

1. **Register target** (admin):
   ```bash
   curl -X POST https://dev.aigw.scdom.net/scanner/targets \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "url": "https://api.example.com",
       "label": "Production API",
       "requested_scan_types": ["api"],
       "node_id": "team-uuid",
       "created_by": "user-uuid"
     }'
   ```

2. **Approve target** (admin):
   ```bash
   curl -X POST https://dev.aigw.scdom.net/scanner/targets/{target_id}/approve \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "allowed_scan_types": ["api"],
       "approved_by": "admin-user-uuid"
     }'
   ```

3. **Submit scan job** (team member):
   ```bash
   curl -X POST https://dev.aigw.scdom.net/scanner/jobs \
     -H "Authorization: Bearer $TEAM_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "target_id": "target-uuid",
       "scan_types": ["api"],
       "tier": "standard"
     }'
   ```

4. **Poll for results** (team member):
   ```bash
   curl -X GET "https://dev.aigw.scdom.net/scanner/jobs/{job_id}/results?limit=50" \
     -H "Authorization: Bearer $TEAM_TOKEN"
   ```

5. **Export as SARIF for CI** (team member):
   ```bash
   curl -X GET "https://dev.aigw.scdom.net/scanner/jobs/{job_id}/results?format=sarif" \
     -H "Authorization: Bearer $TEAM_TOKEN" \
     -o results.sarif
   ```

### Test an AI model for prompt injection vulnerabilities

1. **Register AI model endpoint** (admin):
   ```bash
   curl -X POST https://dev.aigw.scdom.net/scanner/targets \
     -H "Authorization: Bearer $TOKEN" \
     -d '{
       "url": "https://models.example.com/v1/chat/completions",
       "label": "Production LLM",
       "requested_scan_types": ["ai"],
       "node_id": "team-uuid",
       "created_by": "user-uuid"
     }'
   ```

2. **Approve and submit scan** (admin):
   ```bash
   # Approve target
   curl -X POST https://dev.aigw.scdom.net/scanner/targets/{target_id}/approve \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -d '{"allowed_scan_types": ["ai"], "approved_by": "admin-uuid"}'

   # Submit job
   curl -X POST https://dev.aigw.scdom.net/scanner/jobs \
     -H "Authorization: Bearer $TOKEN" \
     -d '{
       "target_id": "target-uuid",
       "scan_types": ["ai"],
       "tier": "deep"
     }'
   ```

3. **Review Garak findings**:
   ```bash
   curl -X GET "https://dev.aigw.scdom.net/scanner/jobs/{job_id}/results?severity=high" \
     -H "Authorization: Bearer $TOKEN" \
     | jq '.findings[] | select(.scanner == "garak")'
   ```

---

## Authentication & Authorization

### Team Endpoints
- `POST /jobs`, `GET /jobs`, `GET /jobs/{job_id}`, `DELETE /jobs/{job_id}`, `GET /jobs/{job_id}/results`
- Require identity token with `team_id` claim
- Users can only see their own team's jobs

### Admin Endpoints
- `GET /scanner/targets`, `POST /scanner/targets`, `POST /scanner/targets/{target_id}/approve`, `POST /scanner/targets/{target_id}/revoke`
- `GET /scanner/quotas`, `PATCH /scanner/quotas/{node_id}`
- `POST /scanner/kill-switch`
- Require admin role (enforced by API gateway)

### Worker Endpoints
- `POST /internal/jobs/{job_id}/progress`, `POST /internal/jobs/{job_id}/findings`, `POST /internal/jobs/{job_id}/complete`
- Require `Authorization: Bearer {scanner_worker_secret}` header
- Not exposed through gateway ingress; internal-only on the ACA network (scanner has no ingress)

---

## Error Codes

| Code | Message | Cause |
|------|---------|-------|
| 202 | Job queued | Success (async) |
| 400 | Invalid request | Malformed JSON, missing required field |
| 403 | Target not found or not approved | Target does not exist, not approved, or team not authorized |
| 403 | Tier not allowed | Tier exceeds team quota `max_tier` |
| 403 | Scan types not allowed | Requested scan type not in target's `allowed_scan_types` |
| 403 | Team not permitted to register external targets | External URL + `allow_external_targets=false` |
| 404 | Job not found | Job ID does not exist or belongs to different team |
| 429 | Concurrent job limit reached | Max 2 running jobs per team |
| 429 | Quota exceeded | Daily limit reached; check `X-Quota-Resets-At` header |
| 503 | Security scanning is temporarily disabled | Kill switch is enabled |

---

## Configuration

Scanner service configuration is injected from Azure Key Vault via the Container App's managed identity (no local defaults):

```bash
# Postgres and Redis are managed PaaS, supplied as Key Vault secret references
DATABASE_URL=<Key Vault secret ref>
REDIS_URL=<Key Vault secret ref>
AUTH_URL=http://ca-auth-dev-sdc
SCANNER_WORKER_SECRET=<Key Vault secret ref>
SCAN_JOB_QUEUE_KEY=scanner:jobs:queue
MAX_CONTAINER_TIMEOUT_SECONDS=900
```

Admin service integrates scanner endpoints under `/admin/scanner/` prefix.

---

## Performance & Limits

| Metric | Value | Notes |
|--------|-------|-------|
| Max container timeout | 900s (15 min) | Worker kills hung scanners |
| Job queue | Redis list | `scanner:jobs:queue` |
| Daily quota counter | Redis key, auto-expire | `scanner:quota:{node_id}:{YYYY-MM-DD}`, expires at UTC midnight |
| Max concurrent jobs/team | 2 | Hard limit, enforced per-team |
| Max results per page | 200 | Prevents large transfers |
| Max targets per team | unlimited | But soft quota via daily_limit |
| Job retention | indefinite | Findings linked to job via FK (CASCADE delete) |

---

## References

- **Garak** (AI security): https://github.com/leondz/garak
- **Nuclei** (API scanning): https://github.com/projectdiscovery/nuclei
- **Nmap** (network scanning): https://nmap.org/
- **ZAP** (DAST): https://www.zaproxy.org/
- **SARIF** (format): https://sarifweb.azurewebsites.net/
