# Enterprise Security & Compliance Reference

The Admin Portal provides enterprise-grade controls for identity management, access governance, budget enforcement, and audit logging. These features are designed for large organizations (~2000 engineers) with hierarchical governance, contractor onboarding, and regulatory compliance requirements.

**Access:** https://aigw-dev.lab.cloud.scdom.net/admin/ (over the corporate VPN, Entra ID SSO)

---

## Overview: User Types & Scopes

The platform distinguishes between three user categories, each with different control profiles:

| User Type | Contractor? | Access Expiry | Model Restrictions | Role Examples |
|-----------|-------------|---------------|--------------------|---|
| **Regular employee** | No | None | Team-scoped | developer, team_admin, area_owner, platform_admin |
| **Contractor** | Yes (`is_contractor=true`) | `access_expires_at` (datetime) | Explicit allow list (`allowed_models`) | developer (read-only) |
| **Service account** | No | None | Custom scopes | integration, bot |

---

## Authentication & Sessions

### Session Management (`/auth` endpoints)

**Session structure** (Redis key: `session:{token}`):
```json
{
  "user_id": "uuid",
  "email": "user@example.com",
  "display_name": "John Doe",
  "roles": [
    {
      "role": "team_admin",
      "node_path": "/org/area/unit/team",
      "expires_at": "2026-12-31T23:59:59Z"
    }
  ],
  "is_contractor": false,
  "access_expires_at": null,
  "allowed_models": null,
  "issued_at": 1705000000,
  "primary_node_id": "uuid"
}
```

### Login Flow
1. User submits email + password
2. Validate against `users.password_hash` (bcrypt or legacy pbkdf2)
3. Check `users.status` (must be "active", not "suspended")
4. Issue session token (8-hour TTL by default)
5. Store in Redis with expiry
6. Return token in Set-Cookie (httpOnly, secure)

**API Endpoint:**
- `POST /auth/login` — body: `{"email", "password", "remember_me"?}`
- `remember_me=true` extends TTL to 30 days

### Session Validation
- All authenticated endpoints call `get_current_user()` dependency
- Validates Bearer token exists and has not expired
- **Contractor check:** if `access_expires_at` is past (UTC now), reject with 401
- **Password invalidation (D3):** if user changed password after session issued, reject with 401 (flag set in Redis)
- **Node change detection:** if `user_node_changed:{user_id}` flag set, reload session payload from DB (allows live permission revocation)

**Endpoints:**
- `GET /auth/me` — return current session payload
- `POST /auth/logout` — delete session token
- `POST /auth/sessions/{session_id}/revoke` — revoke specific session (admin only)
- `POST /auth/sessions/revoke-all-others` — user revokes all other sessions (force re-login on other devices)

---

## Password Reset Flow

Two distinct flows: self-service (forgot password) and admin-initiated.

### Self-Service Forgot Password
1. User clicks "Forgot password?" on login page
2. Enters email
3. System checks if user exists and is active
4. Generates one-time token (UUID, stored in Redis with 15-minute TTL)
5. Sends email with reset link: `https://aigw-dev.lab.cloud.scdom.net/portal/reset?token=<uuid>`
6. User clicks link, enters new password
7. Validate password strength (12+ chars, uppercase, lowercase, digit, special char)
8. Update `users.password_hash`, set `must_change_password=false`
9. Clear all existing sessions (force re-login)
10. Mark timestamp in Redis: `pwd_changed:{user_id}` (used to invalidate old sessions)

**Endpoints:**
- `POST /auth/forgot-password` — body: `{"email"}` → sends email
- `POST /auth/reset-password` — body: `{"token", "new_password"}` → applies reset

### Admin-Forced Password Reset
1. Admin opens user detail page
2. Clicks "Force password change"
3. System sets `users.must_change_password=true`
4. On user's next login, check this flag:
   - If true, redirect to "Set password" form (before home page access)
   - User must set new password before continuing
5. Once set, clear flag and proceed normally

**Endpoints:**
- `POST /users/{user_id}/force-password-change` — admin only, sets flag

---

## Session Management Details

### View & Revoke Sessions
Admins can audit active sessions for a user:
- `GET /users/{user_id}/sessions` — list all active sessions with:
  - Token (masked to first/last 8 chars)
  - Issued timestamp
  - Last activity timestamp
  - IP address (if logged)
  - User agent (browser, OS)

Individual revocation:
- `DELETE /auth/sessions/{session_id}` — immediately invalidate token

Bulk revocation (user action):
- `POST /auth/sessions/revoke-all-others` — user revokes all sessions except current
  - Useful after password change to clean up stale sessions

**Security note:** Revoking a session is immediate (Redis key delete); existing bearer tokens become invalid within ~100ms.

---

## SCIM 2.0 Provisioning (Azure Entra ID)

Automatic user provisioning and deprovisioning from Azure Entra ID.

### Configuration
- **Endpoint:** `GET /scim/v2/Users` (and other standard SCIM endpoints)
- **Auth:** Bearer token via `SCIM_BEARER_TOKEN` environment variable (shared secret, not per-user)
- **Triggered by:** Entra ID lifecycle event (employee hired, transferred, or departed)

### Supported Operations

#### User Create
**Entra ID → SCIM POST /Users**
```
{
  "userName": "user@example.com",
  "name": { "formatted": "John Doe" },
  "externalId": "aad-12345",
  "active": true
}
```

**System action:**
1. Check if user already exists by email
2. If not, create new user record:
   - `email` = userName
   - `display_name` = formatted name
   - `status` = "active" (if active=true) or "suspended"
   - `scim_external_id` = externalId (for future updates)
   - `password_hash` = random bcrypt hash
   - `must_change_password` = true (force reset on first login)
3. Do NOT create team membership yet (admin assigns manually)

#### User Update
**Entra ID → SCIM PATCH /Users/{id}**
- `active: false` → set `status = "suspended"` (blocks login)
- `active: true` → set `status = "active"` (allows login)
- Name changes → update `display_name`

#### User Delete
**Entra ID → SCIM DELETE /Users/{id}**
- **Not implemented** — instead, Entra deprovisioning sets `active=false` (PATCH)
- To fully delete user data, use manual admin deletion (not SCIM)

#### User Query
**Entra ID → SCIM GET /Users**
- List all users with pagination (startIndex, count)
- Filter by email: `filter=userName eq "user@example.com"`
- Returns SCIM User schema with computed fields

### Workflow: Hire → Suspend → Offboard

1. **Hire (Day 1):**
   - HR adds employee to Entra ID
   - Entra ID pushes SCIM POST /Users
   - User created in gateway with `must_change_password=true`
   - User logs in, forced to set password
   - Admin assigns to team(s) via `/teams/{team_id}/members`

2. **Transfer (Mid-tenure):**
   - HR moves employee to different manager in Entra
   - Entra ID pushes SCIM PATCH (update meta, but name/email same)
   - Admin updates team assignments manually

3. **Offboard (Day of departure):**
   - HR marks employee as inactive in Entra ID
   - Entra ID pushes SCIM PATCH `active: false`
   - User status set to "suspended"
   - All existing sessions invalidated (next auth check fails)
   - API keys continue to work but rate-limit to 0 (optional enforcement)
   - (Optional) Send offboarding email with 48-hour grace period to export data

**Note:** SCIM deprovisioning does not delete team membership or data; it only suspends login. Permanent deletion is a separate admin action (data retention policy).

---

## Contractor Isolation

Contractors are employees, vendors, or temporary consultants with time-bounded access and model restrictions.

### Contractor Fields
```sql
CREATE TABLE users (
  id UUID PRIMARY KEY,
  email VARCHAR,
  is_contractor BOOLEAN DEFAULT false,
  access_expires_at TIMESTAMP NULL,  -- UTC, null = indefinite
  allowed_models TEXT NULL,  -- comma-separated list of model IDs
  ...
);
```

### Access Control Flow
1. **On login check:**
   - If `is_contractor=true` and `access_expires_at <= NOW()`, reject 401
   - Session payload includes `access_expires_at` (checked on every request)

2. **On API call (auth service):**
   - If `allowed_models` is set (non-null), whitelist specific model IDs
   - Reject calls to models not in the list with 403 "Model not authorized"
   - If `allowed_models` is null, all team models allowed (default for employees)

### Admin Setup
1. Create or import contractor user (SCIM or manual)
2. Set `is_contractor=true`
3. Set `access_expires_at` (e.g., "2026-06-30T23:59:59Z" for 3-month contract)
4. Set `allowed_models` (e.g., "claude-sonnet-4-6,gpt-4o" for specific model whitelist)
5. Add to team with "developer" role (read-only, cannot create keys)

### Before Expiry
- **30-day warning email** sent to contractor + team admin
- **7-day warning email** sent again
- **Expiry date:** access blocked, all sessions revoked

### Enforcement Points
| Component | Check | Action |
|-----------|-------|--------|
| Auth (login) | `access_expires_at` | Reject 401 if expired |
| Gateway (per-request) | session `access_expires_at` | Reject 401 if expired |
| Auth (model whitelist) | `allowed_models` list | Reject 403 if not in list |
| Cost tracking | `is_contractor` flag | Tag costs separately in billing |

---

## Role-Based Access Control (RBAC)

Permissions are tree-structured: roles grant power over organization nodes.

### Role Hierarchy
```
platform_admin (power=6)
  ├─ area_owner (power=5)
  │  └─ unit_lead (power=4)
  │     └─ team_admin (power=3)
  │        └─ developer (power=2)
  │           └─ viewer (power=1)
```

### Role Assignment Structure
```sql
CREATE TABLE role_assignments (
  id UUID PRIMARY KEY,
  user_id UUID,
  role VARCHAR,  -- 'developer', 'team_admin', 'area_owner', etc.
  organization_node_id UUID,  -- path: /org, /org/area, /org/area/unit, etc.
  expires_at TIMESTAMP NULL,  -- time-bounded role grant
  created_at TIMESTAMP
);
```

### Permission Check Algorithm
```python
def can_access(user, target_path, min_role):
    """Returns True if user has at least min_role power on target_path or above."""
    required = ROLE_POWER[min_role]  # e.g., 'team_admin' = 3
    for assignment in user.roles:
        node_path = assignment.node_path  # e.g., '/org/area/unit/team'
        if target_path.startswith(node_path):  # target is at or below this node
            if ROLE_POWER[assignment.role] >= required:  # e.g., 'area_owner' = 5 >= 3
                return True
    return False
```

**Example:** User with role `area_owner` at `/org/sales/`:
- Can access `/org/sales` ✓
- Can access `/org/sales/unit-a` ✓
- Can access `/org/sales/unit-a/team-1` ✓
- Cannot access `/org/eng` ✗ (different area)

### Time-Bounded Roles
A role assignment can have `expires_at` timestamp:
```python
# During session validation:
if assignment.expires_at and assignment.expires_at < datetime.now(UTC):
    # Role has expired — remove from session.roles list
    skip_assignment()
```

**Use cases:**
- Project lead for 6 months only
- Temporary admin access for vendor
- Intern mentor role expires after internship

**Enforcement:** Checked on every session validation (Redis can cache for 5 minutes, then re-check DB).

---

## Model Access Approval Workflow

Developers request access to gated models; team admins review and approve.

### Request Flow
1. **Developer initiates request:**
   - UI: "Request access" button on model detail page
   - `POST /access-requests` → body: `{"model_id": "uuid"}`
   - Stored in `access_requests` table with `status=pending`

2. **Admin notified:**
   - Email sent to team admins: "Developer John requested access to Claude Opus"
   - Link to approval dashboard

3. **Admin reviews:**
   - `GET /access-requests?status=pending` lists all pending requests
   - Shows developer name, requested model, reason (if provided), date
   - Two buttons: "Approve" / "Deny"

4. **If approved:**
   - `POST /access-requests/{req_id}/approve` (admin only)
   - Add model to developer's `allowed_models` list
   - Send email to developer: "Your request for Claude Opus has been approved"
   - Request marked `status=approved`, `reviewed_at=NOW()`, `reviewed_by=admin_id`

5. **If denied:**
   - `POST /access-requests/{req_id}/deny` — body: `{"reason": "Over quota"}`
   - Developer notified with reason
   - Request marked `status=denied`
   - Developer can re-request after cooldown (7 days)

### API Endpoints
- `POST /access-requests` — submit request (developer)
- `GET /access-requests` — list requests (admin, filters: status, model_id, developer_id)
- `POST /access-requests/{request_id}/approve` — approve (admin)
- `POST /access-requests/{request_id}/deny` — deny + reason (admin)
- `GET /access-requests/{request_id}` — view single request

### Audit Trail
- Access requests logged in `audit_log` (action: "request_model_access", "approve_access", "deny_access")
- Reason for denial retained for compliance

---

## Bulk User Import (CSV)

Onboard multiple users at once via CSV upload.

### CSV Format
```csv
email,display_name,team_name,role,is_contractor,access_expires_at,allowed_models
john.doe@company.com,John Doe,Engineering,developer,false,,
jane.smith@company.com,Jane Smith,Engineering,team_admin,false,,
vendor@contractor.io,Vendor Eng,Engineering,developer,true,2026-09-30,claude-sonnet-4-6
```

### Import Flow
1. **Admin uploads CSV** → `/bulk-import`
2. **Validation:**
   - Check email format (valid email regex)
   - Check team exists
   - Check role is valid
   - Check date format (ISO 8601)
   - Return errors for any invalid rows
3. **Dry-run preview:**
   - Show "Will create N new users" and "Will update M users"
   - Highlight any duplicates or skips
4. **Confirm & execute:**
   - Create users with `must_change_password=true`
   - Add to specified teams with role
   - Send "Welcome" email with password reset link
   - Return summary: "Created 50, Updated 3, Errors 1"

### Skip Logic
- **Duplicate email in CSV:** skip (show warning)
- **User already exists:** update `display_name` and `role`, skip password reset
- **Team doesn't exist:** skip row, add to error list
- **Invalid role:** skip row, add to error list

### Email Template
Subject: "Welcome to AI Gateway"
```
Hi John,

You've been added to the Engineering team in the AI Gateway.
Click here to set your password: https://aigw-dev.lab.cloud.scdom.net/portal/reset?token=xxx

This link expires in 15 minutes.

Thanks,
Platform Team
```

---

## Hierarchical Budgets

Budget caps cascade from organization → area → unit → team, with validation at each level.

### Budget Model
```sql
CREATE TABLE organization_nodes (
  id UUID PRIMARY KEY,
  name VARCHAR,
  path VARCHAR,  -- '/org', '/org/area1', '/org/area1/unit1', etc.
  monthly_budget_usd DECIMAL(10, 2) NULL,  -- null = unlimited
  budget_alert_pct FLOAT DEFAULT 0.8,  -- alert at 80% of cap
  budget_action VARCHAR DEFAULT 'alert'  -- 'alert' or 'block'
);

CREATE TABLE cost_records (
  id UUID PRIMARY KEY,
  team_id UUID,
  api_key_id UUID,
  cost_usd DECIMAL(10, 2),
  created_at TIMESTAMP
);
```

### Budget Hierarchy
```
Organization: €100k/month
├─ Area (Sales): €40k/month
│  ├─ Unit (Inside Sales): €20k/month
│  │  ├─ Team (EMEA): €10k/month
│  │  └─ Team (APAC): €10k/month
│  └─ Unit (Sales Ops): €20k/month
└─ Area (Engineering): €60k/month
   ├─ Unit (Platform): €25k/month
   │  ├─ Team (Infra): €12k/month
   │  └─ Team (API): €13k/month
   └─ Unit (Apps): €35k/month
```

### Enforcement Flow

**During API request** (auth service checks Redis cache):
```python
# Get team budget from Redis (synced by admin service every 5 min)
budget_limit = redis.get(f"budget_limit:team:{team_id}")  # {"limit": 10000, "action": "block"}
if budget_limit:
    monthly_spend = get_spend_from_cache(team_id)
    if monthly_spend >= budget_limit['limit'] and budget_limit['action'] == 'block':
        return 402 Payment Required  # Block the request
```

### Alert Behavior
- **action='alert':** allow request, trigger async alert email
  - Email to team admin + area owner
  - Subject: "Team Spend Alert — 85% of monthly budget"
  - Includes: current spend, cap, days left in month, projected spend
- **action='block':** deny request with 402 status
  - Error message: "Monthly budget exhausted"
  - Only team/area admin can approve exception or increase cap

### Parent Constraint Validation
When setting a child budget, system validates:
```python
# Cannot exceed parent cap
child_budget = 10000
parent_budget = 8000
if child_budget > parent_budget:
    raise ValueError("Team budget cannot exceed area cap")

# Siblings cannot exceed parent sum
siblings_sum = 25000
parent_cap = 20000
if siblings_sum > parent_cap:
    raise ValueError("Sum of team budgets exceeds area cap")
```

### Admin API for Budgets
- `GET /organizations/{org_id}/budget-tree` — view full hierarchy with current spend
- `PUT /organization-nodes/{node_id}/budget` — set budget + alert threshold
  - Body: `{"monthly_budget_usd": 10000, "budget_alert_pct": 0.8, "budget_action": "block"}`
  - Returns validation errors if constraints violated
- `GET /organizations/budget-status` — snapshot: all nodes + current spend + utilization %
  - JSON export for BI/reporting

---

## Audit Logging

All sensitive operations are logged for compliance and forensics.

### Audit Schema
```sql
CREATE TABLE audit_log (
  id UUID PRIMARY KEY,
  timestamp TIMESTAMP DEFAULT NOW(),
  actor VARCHAR,  -- user_id or "system"
  action VARCHAR,  -- 'login', 'create_api_key', 'revoke_key', 'approve_access', etc.
  resource_type VARCHAR,  -- 'user', 'api_key', 'access_request', 'role_assignment', etc.
  resource_id VARCHAR,
  status VARCHAR,  -- 'success', 'failure'
  details TEXT,  -- JSON: extra context like old vs. new value
  ip_address VARCHAR,
  user_agent VARCHAR
);
```

### Logged Events

| Event | Resource | Details |
|-------|----------|---------|
| User login | user | email, ip, success/failure reason |
| User logout | session | token_prefix (last 8 chars) |
| Create API key | api_key | name, team_id, scopes |
| Revoke API key | api_key | name, team_id, developer_id |
| Force password reset | user | user_id, initiated_by |
| Change password | user | user_id |
| Create/update role | role_assignment | user_id, role, node_path, expires_at, old_value |
| Remove role | role_assignment | user_id, role, node_path |
| Request model access | access_request | developer_id, model_id |
| Approve/deny access | access_request | request_id, developer_id, model_id, reason |
| Create user | user | email, display_name, source (manual/scim/csv) |
| Suspend user | user | user_id, reason |
| Update budget | organization_node | node_id, old_budget, new_budget |
| SCIM provision | user | email, scim_external_id, method (create/update) |

### Querying Audit Log
- `GET /audit?resource_type=api_key&resource_id=<key_id>&since=<date>` — activity on a specific key
- `GET /audit?actor=<user_id>&since=<date>` — all actions by a user
- `GET /audit?action=login&since=<date>` — all login attempts (success + failures)
- **Export:** CSV download of audit log (for external auditors, up to 1M rows)

### Retention
- Keep audit logs for **7 years** (regulatory requirement for financial institutions)
- Archive to cold storage (S3 Glacier) after 1 year
- Immutable write-once design (cannot edit/delete logs)

---

## Email Notifications

SMTP-based notifications for key events. Configurable templates.

### SMTP Configuration
```bash
# .env
SMTP_HOST=smtp.company.com
SMTP_PORT=587
SMTP_USER=noreply@company.com
SMTP_PASSWORD=<secret>
SMTP_FROM=AI Gateway <noreply@company.com>
SMTP_TLS=true
```

### Notification Types

#### Password Reset
- **Trigger:** user clicks "Forgot password"
- **To:** user email
- **Subject:** "Reset your AI Gateway password"
- **Template:** reset_password.html
  - Reset link (15-min valid)
  - Fallback instructions if link doesn't work
  - "If you didn't request this, ignore this email"

#### Invitation (Bulk Import or Manual)
- **Trigger:** admin uploads CSV or manually adds user
- **To:** new user email
- **Subject:** "Welcome to AI Gateway — set your password"
- **Template:** welcome.html
  - Team name and role
  - Password reset link
  - Link to documentation
  - Support contact

#### Team Assignment
- **Trigger:** admin assigns user to team
- **To:** user email
- **Subject:** "You've been added to Engineering team"
- **Template:** team_assignment.html
  - Team name, admin contact
  - Link to team dashboard
  - Quick-start guide

#### Budget Alert
- **Trigger:** team spend crosses alert threshold
- **To:** team admin, area owner
- **Subject:** "Spending Alert — Engineering team at 82% of €10k budget"
- **Template:** budget_alert.html
  - Current spend vs. cap
  - Days left in month
  - Projected month-end spend
  - Link to budget dashboard
  - Request approval for exception

#### Access Request Approval
- **Trigger:** admin approves model access request
- **To:** developer
- **Subject:** "Your request for Claude Opus has been approved"
- **Template:** access_approved.html
  - Model name
  - Can now use via Playground or API
  - Link to model docs

#### Contractor Expiry Warning
- **Trigger:** 30 days, then 7 days before contractor access expires
- **To:** contractor, team admin, area owner
- **Subject:** "Contractor access expires in 30 days"
- **Template:** contractor_expiring.html
  - Contractor name
  - Expiry date
  - Renewal request instructions
  - Known activity (last login, usage stats)

---

## Security Best Practices

### For Admins
1. **Audit regularly:** Check audit log for suspicious login patterns, bulk role changes
2. **Contractor onboarding:** Always set `access_expires_at`; don't forget to revoke
3. **Role delegation:** Avoid granting `platform_admin` to multiple people; use `area_owner` instead
4. **Session revocation:** If account compromised, immediately revoke all sessions
5. **SCIM token rotation:** Change `SCIM_BEARER_TOKEN` quarterly

### For Developers
1. **API keys:** Rotate before 90-day auto-expiry; store in Key Vault, not code
2. **Session timeout:** Portal logs out after 8 hours of inactivity
3. **Model access:** Request only needed models; assume least privilege
4. **Contractor accounts:** Do not share keys with contractors; they must use separate account

### For Compliance
1. **Audit log archival:** Export quarterly for external auditors (e.g., SOC 2)
2. **User offboarding checklist:**
   - Revoke all sessions
   - Mark user as suspended
   - Audit API key usage in last 30 days
   - Notify team of any key exports
3. **Contractor agreements:** Include clause that access expires automatically (no manual revocation needed)
4. **Data retention:** Keep audit logs 7 years; delete user PII after 1 year (unless contractor agreement says otherwise)

---

## API Reference

### Core Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/auth/login` | Authenticate user |
| `POST` | `/auth/logout` | Invalidate session |
| `POST` | `/auth/forgot-password` | Start self-service reset |
| `POST` | `/auth/reset-password` | Apply password reset |
| `GET` | `/auth/me` | Get current user + roles |
| `GET` | `/users/{user_id}` | Get user details |
| `GET` | `/users/{user_id}/sessions` | List active sessions |
| `DELETE` | `/auth/sessions/{session_id}` | Revoke session |
| `POST` | `/users/{user_id}/force-password-change` | Admin: force reset |
| `POST` | `/role-assignments` | Grant role |
| `DELETE` | `/role-assignments/{assignment_id}` | Revoke role |
| `GET` | `/access-requests` | List requests |
| `POST` | `/access-requests/{id}/approve` | Approve model access |
| `POST` | `/access-requests/{id}/deny` | Deny model access |
| `GET` | `/audit` | Query audit log |
| `GET` | `/organizations/budget-status` | View all budgets + spend |
| `PUT` | `/organization-nodes/{node_id}/budget` | Set budget |
| `POST` | `/bulk-import` | Upload CSV users |
| `GET` | `/scim/v2/Users` | SCIM: list users |
| `POST` | `/scim/v2/Users` | SCIM: create user |
| `PATCH` | `/scim/v2/Users/{id}` | SCIM: update user |

---

## Troubleshooting

### User Can't Log In
1. Check `users.status` is "active" (not "suspended")
2. If contractor, verify `access_expires_at` hasn't passed
3. Check `must_change_password=true` (force them to reset)
4. Look in `audit_log` for login attempts + failure reasons

### Sessions Getting Invalidated Unexpectedly
1. Check if password was changed (invalidates old sessions intentionally)
2. Check if user's roles were modified (flag `user_node_changed` triggers reload)
3. Check session TTL (default 8 hours; extend with "remember me")

### Model Access Denied
1. Verify user's `allowed_models` list includes that model
2. Check if access request is pending (not yet approved)
3. Verify role has `developer` power or higher
4. Check budget: if team capped out with `action=block`, all models denied

### Contractor Still Has Access After Expiry
1. Check `access_expires_at` timestamp (UTC timezone)
2. Force logout: `POST /auth/sessions/revoke-all-others` for that user
3. Check if `is_contractor=false` (if so, they're treated as regular employee)
4. Verify cache was invalidated: clear Redis `session:{token}` keys

---

## Future Enhancements

- **OAuth2/OIDC:** Let developers use GitHub/Google login
- **MFA:** Enforce 2FA for admins, optional for developers
- **API token permissions:** Fine-grained scopes (read-only vs. write)
- **Webhook audit events:** Push audit log changes to external SIEM
- **ML-based anomaly detection:** Flag unusual API usage or role changes
- **Compliance reports:** Auto-generate SOC 2, GDPR, FedRAMP attestations
