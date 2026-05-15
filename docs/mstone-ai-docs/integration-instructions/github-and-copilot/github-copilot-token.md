# GitHub Copilot Token


This token grants the platform read access to GitHub Copilot Business seat assignments and usage metrics.

## Before You Start

- Tokens are **tied to the user who generated them** and stop working if that user loses access. Use a dedicated bot or service account when feasible.
- Organizations may enforce policies on fine-grained PATs, including maximum lifetime requirements and mandatory admin approval.
- The default maximum lifetime is **366 days**.

## Step-by-Step: Create the Token

### 1. Access Fine-Grained Token Page

Navigate: **GitHub → Profile → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**

### 2. Token Naming

| Field | Value |
|---|---|
| Name | `Engineering Analytics Token (read-only)` |
| Description | `Token for platform integration to gather metadata and generate analytics` |

### 3. Set Expiration

Choose a **1-year** expiration period, or longer if org policy permits.

### 4. Select Resource Owner

Designate the **organization** as the resource owner to limit token access to organization-owned resources.

### 5. Repository Access Scope

Restrict access to **public repositories only**.

### 6. Organization Permissions (Read-only)

| Permission | Level |
|---|---|
| Members | Read |
| GitHub Copilot Business seats and metrics | Read |

### 7. Generate & Store

Click **Generate token** and securely store it on the deployment machine.
