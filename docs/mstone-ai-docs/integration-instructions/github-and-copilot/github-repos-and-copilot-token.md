# GitHub Repos & Copilot Token


This token grants the platform read access to your GitHub repositories and organization membership.

## Before You Start

- Tokens are **tied to the user who generated them** and stop working if that user loses access. Use a dedicated bot or service account when feasible.
- Organizations may enforce policies on fine-grained PATs, including maximum lifetime requirements and mandatory admin approval.
- The default maximum lifetime is **366 days**; "no expiration" may be available depending on your org policy.

## Step-by-Step: Create the Token

### 1. Open the Fine-Grained Token Page

Navigate: **GitHub → Your profile (top-right) → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**

### 2. Name & Description

| Field | Value |
|---|---|
| Token name | `Engineering Analytics Token (read-only)` |
| Description | `Token to be used by the platform integration to gather metadata and generate analytics` |

### 3. Expiration

- **Recommended:** 1 year
- **Alternative:** No expiration (if org policy permits)
- Coordinate with org owners if policies enforce shorter maximum lifetimes.

### 4. Resource Owner

Select your **organization** as the resource owner. The token will only access resources owned by that organization.

> If your organization does not appear, it may have blocked fine-grained PATs — contact an org owner to enable them.

### 5. Repository Access

Choose **All repositories** for that organization, or select specific repositories individually.

### 6. Repository Permissions (Read-only)

| Permission | Level |
|---|---|
| Contents | Read |
| Metadata | Read |
| Pull requests | Read |

### 7. Organization Permissions (Read-only)

| Permission | Level |
|---|---|
| Members | Read |

> This allows the platform to access the organization's members list.

### 8. Generate

Click **Generate token** and store it securely where the platform services will be configured.

> Tokens requiring organizational approval will remain pending until authorized by an org owner.
