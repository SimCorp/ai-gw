# Authentication & Authorization API Reference

Unified authentication surface supporting password-based login, OIDC/SSO (Entra ID), password reset, session management, and role-based access control via Entra groups.

## Overview

The Auth service manages:
- **User authentication**: login, registration, password management
- **Session lifecycle**: creation, validation, revocation
- **Role assignment**: Entra group → role → node mappings
- **Password security**: bcrypt hashing, strength validation, change tracking
- **Contractor access**: expiry dates, model restrictions

Session tokens are stored in Redis with TTLs:
- Standard user: 7 days
- Admin (gateway_admin): 8 hours (or 30 days if "remember me")

## Core Concepts

### Permission Model

Permission checks use path-based inheritance:

```python
can_access(user, target_path, min_role) → bool
```

**Example:** A user with `area_owner` role at node path `/root-id/area-id/` can access any descendant:
- `/root-id/area-id/` (their node)
- `/root-id/area-id/unit-id/`
- `/root-id/area-id/unit-id/team-id/`

**Role Power Hierarchy** (highest to lowest):
- `gateway_admin`: 6 — full system access
- `area_owner`: 5 — manage an area and all descendants
- `unit_lead`: 4 — lead a unit
- `team_admin`: 3 — administer a team
- `engineer`: 2 — engineer access
- `reporter`: 1 — read-only access

### Session Payload

```json
{
  "user_id": "uuid",
  "email": "user@simcorp.com",
  "display_name": "Alice Smith",
  "roles": [
    {
      "role": "area_owner",
      "node_path": "/root-id/area-id",
      "node_id": "area-id",
      "node_name": "Platform"
    }
  ],
  "primary_node_id": "team-uuid",
  "is_platform_admin": true,
  "is_contractor": false,
  "access_expires_at": "2024-12-31T23:59:59Z",
  "allowed_models": ["gpt-4", "gpt-3.5-turbo"],
  "issued_at": 1705312200.0
}
```

---

## Endpoints

### Login (Password)

```
POST /auth/login
```

Authenticate with email and password. Supports "remember me" for extended session TTL.

**Request Body:**
```json
{
  "email": "alice@simcorp.com",
  "password": "SecurePassword123!",
  "remember_me": false
}
```

**Request Fields:**
- `email` (string, required): Email address (case-insensitive)
- `password` (string, required): Password
- `remember_me` (boolean, optional, default=false): Extend TTL to 30 days

**Response:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "user_id": "uuid",
    "email": "alice@simcorp.com",
    "display_name": "Alice Smith",
    "roles": [],
    "primary_node_id": null,
    "is_platform_admin": false,
    "is_contractor": false,
    "access_expires_at": null,
    "allowed_models": null
  },
  "must_change_password": false
}
```

**Status Code:** 200 OK

**Error Cases:**
- `401 Unauthorized`: Invalid email or password
- `403 Forbidden`: Account suspended
- `429 Too Many Requests`: Rate limited (10 attempts per 60 seconds per IP)

**Notes:**
- bcrypt-authenticated users have no roles until granted via Entra group assignment
- OIDC users load roles from Entra group membership (see OIDC callback)

---

### Register (Self-Service)

```
POST /auth/register
```

Create a new user account via self-service registration. No initial roles assigned.

**Request Body:**
```json
{
  "email": "newuser@simcorp.com",
  "display_name": "Bob Johnson",
  "password": "SecurePassword123!"
}
```

**Request Fields:**
- `email` (string, required): Must be valid email format
- `display_name` (string, required): 1-200 characters
- `password` (string, required): Min 8, max 128 characters

**Response:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "user_id": "new-user-uuid",
    "email": "newuser@simcorp.com",
    "display_name": "Bob Johnson",
    "roles": [],
    "primary_node_id": null,
    "is_platform_admin": false,
    "is_contractor": false,
    "access_expires_at": null,
    "allowed_models": null
  },
  "must_change_password": false
}
```

**Status Code:** 201 Created

**Error Cases:**
- `409 Conflict`: Email already registered
- `422 Unprocessable Entity`: Invalid email format
- `429 Too Many Requests`: Rate limited

---

### Current User

```
GET /auth/me
```

Retrieve the authenticated user's session payload.

**Headers:**
- `Authorization: Bearer {token}` (required)

**Response:** Session payload (see Session Payload above)

**Status Code:** 200 OK

**Error Cases:**
- `401 Unauthorized`: Invalid or expired token

---

### Logout

```
POST /auth/logout
```

Revoke the current session token.

**Headers:**
- `Authorization: Bearer {token}` (required)

**Response:**
```json
{
  "ok": true
}
```

**Status Code:** 200 OK

---

### Change Password

```
POST /auth/change-password
```

Change the authenticated user's password. Invalidates all existing sessions.

**Headers:**
- `Authorization: Bearer {token}` (required)

**Request Body:**
```json
{
  "current_password": "OldPassword123!",
  "new_password": "NewPassword456!"
}
```

**Request Fields:**
- `current_password` (string, required): Current password for verification
- `new_password` (string, required): Min 12, max 128 characters; must contain uppercase, lowercase, digit, and special character

**Response:**
```json
{
  "ok": true
}
```

**Status Code:** 200 OK

**Error Cases:**
- `401 Unauthorized`: Current password incorrect
- `422 Unprocessable Entity`: Password strength validation failed

---

### Forgot Password

```
POST /auth/forgot-password
```

Initiate password reset flow. Sends reset email to the user. Always returns 200 (no email enumeration).

**Request Body:**
```json
{
  "email": "alice@simcorp.com"
}
```

**Request Fields:**
- `email` (string, required): User email

**Response:**
```json
{
  "message": "If that email exists, a reset link has been sent"
}
```

**Status Code:** 200 OK (always, regardless of email existence)

**Notes:**
- Reset token is valid for 1 hour
- Email contains reset URL with embedded token
- Portal receives token in query param, submits via POST /auth/reset-password

---

### Reset Password

```
POST /auth/reset-password
```

Complete password reset with a valid reset token.

**Request Body:**
```json
{
  "token": "reset-token-from-email",
  "new_password": "NewPassword456!"
}
```

**Request Fields:**
- `token` (string, required): Reset token from email link
- `new_password` (string, required): Min 12, max 128 characters; must contain uppercase, lowercase, digit, and special character

**Response:**
```json
{
  "message": "Password reset successfully"
}
```

**Status Code:** 200 OK

**Error Cases:**
- `400 Bad Request`: Invalid or expired reset token
- `422 Unprocessable Entity`: Password strength validation failed

---

### Force Password Reset (Admin)

```
POST /auth/admin/force-password-reset
```

Admin-initiated password reset. Generates out-of-band reset token and flags user to change password on next login.

**Headers:**
- `Authorization: Bearer {admin-token}` (requires `gateway_admin` role)

**Request Body:**
```json
{
  "user_id": "target-user-uuid",
  "temporary_password": "TempPassword123!"
}
```

**Request Fields:**
- `user_id` (string, required): Target user UUID
- `temporary_password` (string, optional): If provided, sets this as user's password and flags `must_change_password=true`; if omitted, only flags user without changing password

**Response:**
```json
{
  "reset_token": "out-of-band-reset-token",
  "message": "User must change password on next login"
}
```

**Status Code:** 200 OK

**Required Permission:** `gateway_admin`

**Notes:**
- Invalidates all existing sessions for the target user
- Token can be sent out-of-band (email, message, etc.)
- User must submit reset via POST /auth/reset-password

---

## Sessions (D4)

### List Sessions

```
GET /auth/sessions
```

List all active sessions for the authenticated user. Uses Redis sorted set tracking.

**Headers:**
- `Authorization: Bearer {token}` (required)

**Response:**
```json
[
  {
    "session_id": "16-char-token-prefix",
    "issued_at": 1705312200.0
  }
]
```

**Status Code:** 200 OK

---

### Logout All Other Sessions

```
DELETE /auth/sessions
```

Revoke all sessions except the current one. Useful for security after device compromise.

**Headers:**
- `Authorization: Bearer {token}` (required)

**Response:**
```json
{
  "message": "All other sessions revoked"
}
```

**Status Code:** 200 OK

---

### Revoke Specific Session

```
DELETE /auth/sessions/{session_id}
```

Revoke a specific session by its ID.

**Path Parameters:**
- `session_id` (string, required): Session token prefix (from list sessions)

**Headers:**
- `Authorization: Bearer {token}` (required)

**Response:**
```json
{
  "message": "Session revoked"
}
```

**Status Code:** 200 OK

---

## User Management (Admin)

### List Users

```
GET /auth/users
```

List all users in the system with their roles and status.

**Headers:**
- `Authorization: Bearer {admin-token}` (requires `gateway_admin` role)

**Response:**
```json
[
  {
    "id": "user-uuid",
    "email": "alice@simcorp.com",
    "display_name": "Alice Smith",
    "status": "active",
    "must_change_password": false,
    "last_login_at": "2024-01-20T15:30:00Z",
    "created_at": "2024-01-15T10:30:00Z",
    "roles": [
      {
        "role": "gateway_admin",
        "scope_type": "global",
        "scope_id": null
      }
    ]
  }
]
```

**Status Code:** 200 OK

**Required Permission:** `gateway_admin`

---

### Set User Status

```
PATCH /auth/users/{user_id}/status
```

Suspend or activate a user account. Suspending invalidates all sessions.

**Headers:**
- `Authorization: Bearer {admin-token}` (requires `gateway_admin` role)

**Query Parameters:**
- `status` (string, required): One of `active`, `suspended`

**Response:**
```json
{
  "ok": true
}
```

**Status Code:** 200 OK

**Required Permission:** `gateway_admin`

---

### Update User Profile

```
PATCH /auth/users/{user_id}/profile
```

Update user display name and primary node assignment.

**Headers:**
- `Authorization: Bearer {admin-token}` (requires `gateway_admin` role)

**Request Body:**
```json
{
  "display_name": "Alice Smith (Updated)",
  "primary_node_id": "new-team-uuid"
}
```

**Request Fields:** Both optional
- `display_name` (string): Updated display name
- `primary_node_id` (string): User's home/primary node

**Response:**
```json
{
  "updated": ["display_name", "primary_node_id"]
}
```

**Status Code:** 200 OK

**Required Permission:** `gateway_admin`

---

## Contractor Settings

### Update Contractor Settings

```
PATCH /auth/users/{user_id}/contractor
```

Set contractor status, access expiry date, and allowed models.

**Headers:**
- `Authorization: Bearer {admin-token}` (requires `gateway_admin` role)

**Request Body:**
```json
{
  "is_contractor": true,
  "access_expires_at": "2024-12-31T23:59:59Z",
  "allowed_models": ["gpt-4", "gpt-3.5-turbo"]
}
```

**Request Fields:** All optional
- `is_contractor` (boolean): Mark user as contractor
- `access_expires_at` (string, ISO 8601): Expiry date/time; checked on login and GET /auth/me
- `allowed_models` (array of strings): Model whitelist; null = no restriction

**Response:**
```json
{
  "updated": ["is_contractor", "access_expires_at", "allowed_models"]
}
```

**Status Code:** 200 OK

**Required Permission:** `gateway_admin`

---

## Invitations

### Create Invitation

```
POST /auth/invitations
```

Generate a one-time invitation link for a new user.

**Headers:**
- `Authorization: Bearer {token}` (requires `gateway_admin` or `team_admin`)

**Request Body:**
```json
{
  "email": "newuser@simcorp.com",
  "role": "engineer",
  "scope_type": "global",
  "scope_id": null
}
```

**Request Fields:**
- `email` (string, required): Invitee email
- `role` (string, optional, default=`engineer`): One of valid roles
- `scope_type` (string, optional, default=`global`): One of `global`, `team`
- `scope_id` (string, optional): Node UUID for team scope

**Response:**
```json
{
  "invite_id": "invite-uuid",
  "email": "newuser@simcorp.com",
  "role": "engineer",
  "expires_at": "2024-01-22T10:30:00Z",
  "accept_url": "http://portal-url/accept-invite?token=...",
  "token": "raw-invitation-token"
}
```

**Status Code:** 201 Created

**Permissions:**
- `gateway_admin`: can invite any role to global scope
- `team_admin`: can invite `engineer` or `reporter` to their team only

**Notes:**
- Token valid for 48 hours
- Token shown once only; caller must copy the link
- Invitees without existing account are auto-created on acceptance

---

### List Invitations

```
GET /auth/invitations
```

List all active and accepted invitations.

**Headers:**
- `Authorization: Bearer {token}` (requires `gateway_admin` or `team_admin`)

**Response:**
```json
[
  {
    "id": "invite-uuid",
    "email": "newuser@simcorp.com",
    "role": "engineer",
    "scope_type": "global",
    "scope_id": null,
    "expires_at": "2024-01-22T10:30:00Z",
    "accepted_at": null,
    "created_at": "2024-01-20T10:30:00Z",
    "invited_by_email": "admin@simcorp.com"
  }
]
```

**Status Code:** 200 OK

**Permissions:**
- `gateway_admin`: see all invitations
- `team_admin`: see invitations for teams they manage

---

### Revoke Invitation

```
DELETE /auth/invitations/{invite_id}
```

Revoke an unaccepted invitation.

**Headers:**
- `Authorization: Bearer {token}` (requires `gateway_admin` or `team_admin`)

**Status Code:** 204 No Content

---

### Accept Invitation

```
POST /auth/invitations/accept
```

Accept an invitation and create the user account.

**Request Body:**
```json
{
  "token": "invitation-token-from-url",
  "display_name": "Bob Johnson",
  "password": "SecurePassword123!"
}
```

**Request Fields:**
- `token` (string, required): Invitation token from link
- `display_name` (string, required): New user's display name
- `password` (string, required): Min 12, max 128 characters; must contain uppercase, lowercase, digit, and special character

**Response:**
```json
{
  "token": "session-token",
  "user": {
    "user_id": "new-user-uuid",
    "email": "newuser@simcorp.com",
    "display_name": "Bob Johnson",
    "roles": [{
      "role": "engineer",
      "scope_type": "global",
      "scope_id": null
    }],
    "primary_team_id": null
  }
}
```

**Status Code:** 201 Created

**Error Cases:**
- `404 Not Found`: Invitation not found or expired
- `409 Conflict`: Email already registered

---

### Bulk Invite (CSV)

```
POST /auth/invitations/bulk
```

Invite multiple users from a CSV file.

**Headers:**
- `Authorization: Bearer {admin-token}` (requires `gateway_admin`)

**Multipart Form:**
- `file` (file, required): CSV with columns: `email`, `role` (optional, default=`engineer`), `scope_type` (optional), `scope_id` (optional)

**Response:**
```json
{
  "sent": 95,
  "skipped": 3,
  "errors": [
    {
      "row": 12,
      "reason": "Invalid email: not-an-email"
    }
  ]
}
```

**Status Code:** 200 OK

**CSV Format:**
```
email,role,scope_type,scope_id
alice@simcorp.com,engineer,global,
bob@simcorp.com,team_admin,team,12345678-1234-1234-1234-123456789012
```

---

## OIDC / SSO

### OIDC Login

```
GET /auth/oidc/login
```

Redirect to the configured OIDC provider (Azure Entra ID).

**Response:** HTTP 302 Redirect to `{oidc_issuer}/auth?client_id=...&scope=...&state=...&redirect_uri=...`

---

### OIDC Callback

```
GET /auth/oidc/callback
```

OIDC provider redirects here with authorization code. Exchanges code for ID token, creates/updates user, loads role assignments from Entra groups.

**Query Parameters:**
- `code` (string, required): Authorization code from OIDC provider
- `state` (string, required): State token for CSRF protection

**Response:** HTTP 302 Redirect to admin or developer portal with `sso_token` in fragment

**Behavior:**
1. Validates state token (5-minute expiry)
2. Exchanges authorization code for ID token
3. Decodes JWT claims (email, name, groups)
4. Finds or creates user (OIDC users get empty roles until granted)
5. Loads role assignments for user's Entra groups via role_assignments table
6. Issues session token
7. Redirects to appropriate portal based on roles

**Error Cases:**
- `400 Bad Request`: Invalid or expired state
- `502 Bad Gateway`: Token exchange failed, malformed token

---

## Error Responses

All error responses use this format:

```json
{
  "detail": "Error message"
}
```

**Common Status Codes:**
- `400 Bad Request`: Invalid parameters or expired tokens
- `401 Unauthorized`: Missing or invalid credentials
- `403 Forbidden`: Insufficient permissions
- `404 Not Found`: User or resource not found
- `409 Conflict`: Resource already exists
- `422 Unprocessable Entity`: Validation error
- `429 Too Many Requests`: Rate limited
- `500 Internal Server Error`: Server error
- `502 Bad Gateway`: External service error (OIDC provider)
