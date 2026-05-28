# IT Tools Integration — Developer Portal

**Date:** 2026-05-28  
**Status:** Approved for implementation

## Context

SimCorp developers need a quick-access toolbox for everyday tasks: UUID generation, Base64 encoding, JWT decoding, JSON formatting, CRON expression parsing, regex testing, color conversion, and ~95 more utilities. Rather than building these from scratch or sending developers to external sites, we integrate the open-source [it-tools](https://github.com/CorentinTh/it-tools) project (~100 tools) directly into the developer portal.

The design priorities are:
- **Full catalog** — all ~100 tools available, not a curated subset
- **Admin control** — each tool can be enabled or disabled globally
- **Low upgrade cost** — bumping the it-tools version should require minimal changes

## Architecture Overview

```
Dev Portal  →  GET /admin/tools (enabled only)  →  Admin Service → Postgres
Dev Portal  →  /tools-app/{slug}  →  Nginx  →  it-tools container
Admin Portal →  GET/PATCH /admin/tools  →  Admin Service → Postgres
```

The it-tools app runs as a standalone Docker container. The dev portal provides a native catalog page (search, category filter, tool cards) that reflects which tools are enabled. Clicking a tool loads it via an iframe pointing to the nginx-proxied it-tools service. Admins control availability through a dedicated page in the admin portal.

## 1. Infrastructure

### Docker Compose (`infra/docker-compose.yml`)

Add an `it-tools` service:

```yaml
it-tools:
  image: ghcr.io/corentinth/it-tools:latest
  restart: unless-stopped
  # No published port — accessed only through nginx
```

Pin to a specific tag (e.g., `2023.12.21-7d90d6a`) rather than `latest` for reproducibility. Update the tag when upgrading.

### Nginx (`infra/nginx/`)

Add a location block proxying `/tools-app/` to the it-tools container:

```nginx
location /tools-app/ {
    proxy_pass http://it-tools:80/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

The it-tools SPA uses root-relative assets, so the sub-path proxy requires the `proxy_pass` trailing slash and may need a `sub_filter` rewrite for asset paths if it-tools doesn't support a base path. If rewriting is needed, add `sub_filter` rules or use the `ngx_http_sub_module`.

### Service Port Table Update (`CLAUDE.md`)

Add `it-tools` row (internal only, no direct port).

## 2. Catalog Data

**File:** `services/admin/tools_catalog.json`

A JSON array of all tools from it-tools, each with:

```json
{
  "id": "uuid-generator",
  "label": "UUID generator",
  "description": "Generate random UUIDs",
  "category": "Random",
  "path": "/uuid-generator"
}
```

This file is the single upgrade touchpoint. When bumping the it-tools image, check the it-tools changelog and add any new tools to this file. The migration seeds the `tool_config` table from this file on first run; subsequent runs upsert new rows (preserving existing `enabled` state).

**Category list** (from it-tools source):
Converter, Web, Images & Videos, Development, Network, Math, Measurement, Text, Crypto, Data, Time & Date, Docker, Random

## 3. Database

### Migration: `services/admin/migrations/versions/0025_tool_config.py`

```sql
CREATE TABLE tool_config (
    tool_id    TEXT PRIMARY KEY,
    enabled    BOOLEAN NOT NULL DEFAULT TRUE,
    label      TEXT NOT NULL,
    category   TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

The migration reads `tools_catalog.json` at `services/admin/tools_catalog.json` (two levels up from the migrations versions directory) and inserts all rows with `enabled = TRUE`. When new tools are added to the catalog in a future upgrade, a new migration upserts them (preserving existing `enabled` state via `ON CONFLICT (tool_id) DO NOTHING` for existing rows, `INSERT` for new ones).

## 4. Admin Service

**New router:** `services/admin/app/routers/tools.py`

### `GET /tools`

Returns the full catalog with enabled state. Accepts a `?enabled_only=true` query param (used by the dev portal).

Response:

```json
[
  {
    "id": "uuid-generator",
    "label": "UUID generator",
    "description": "...",
    "category": "Random",
    "path": "/uuid-generator",
    "enabled": true
  }
]
```

### `PATCH /tools/{tool_id}`

Body: `{ "enabled": true | false }`  
Admin-only (enforces existing admin auth middleware).  
Updates `tool_config.enabled` and `updated_at`.  
Returns the updated tool row.

**Registration:** Add the tools router to `services/admin/app/main.py`.

## 5. Dev Portal

### Nav item

Add "Tools" to the **Use** group in `apps/portal/app/portal/_components/PortalShell.tsx`:

```typescript
{ href: "/portal/tools", label: "Tools", icon: <WrenchIcon /> }
```

Use the existing lucide-react `Wrench` icon.

### `/portal/tools` — Catalog page

**File:** `apps/portal/app/portal/tools/page.tsx`

- Hero section: title "Developer Tools", subtitle, search input
- Category filter tabs (All + one per category from the catalog)
- Tool card grid: each card shows label, category pill, description; clicking navigates to `/portal/tools/[slug]`
- Fetches `GET /admin/tools?enabled_only=true` on mount using `useAuth()` token
- Search filters client-side (no additional API calls)
- Empty state when no tools match search/filter

Follows existing portal CSS patterns: `.pmain`, `.phero`, `.card`, `.btn`.

### `/portal/tools/[slug]` — Tool page

**File:** `apps/portal/app/portal/tools/[slug]/page.tsx`

- Receives `slug` from route params
- Fetches `GET /admin/tools?enabled_only=true` (same call as the catalog page) to look up metadata for the given slug
- Shows: breadcrumb ("Tools → {label}"), category pill, brief description
- Full-height iframe: `src="/tools-app/{slug}"`, `title={tool.label}`, no `sandbox` restrictions (it-tools needs JS)
- "Back to Tools" link

If the slug is not found in the catalog (tool disabled or unknown), shows a 404-style message with a link back to the catalog.

## 6. Admin Portal

### Nav item

Add "Tools" under the **Configure** section in `apps/admin/app/admin/layout.tsx`.

### `/admin/tools` — Tool catalog manager

**File:** `apps/admin/app/admin/tools/page.tsx`

- Page header: "Developer Tools", subtitle "Manage which tools are available in the developer portal"
- KPI strip: total tools count, enabled count
- Search bar + category filter tabs
- Scrollable list of tool rows (not a table — a styled list for easier toggle UX):
  - Tool icon (emoji from category), label, category pill, description
  - Toggle switch on the right (enabled/disabled)
- **Auto-save on toggle:** each toggle fires `PATCH /tools/{id}` immediately; optimistic UI update (no loading state for individual toggles), error toast on failure with revert
- Uses `apiFetch` from `apps/admin/lib/apiClient.ts` for auth

## 7. Verification

### Local smoke test

1. `docker compose up --build` — verify it-tools container starts, `curl http://localhost:8080/tools-app/` returns 200
2. Dev portal: navigate to `/portal/tools` — catalog loads, search works, clicking a tool loads it in iframe
3. Admin portal: navigate to `/admin/tools` — all tools listed with toggles
4. Disable a tool in admin portal → reload dev portal catalog → tool is gone
5. Re-enable → tool reappears

### Edge cases

- it-tools asset paths under `/tools-app/` sub-path — verify CSS/JS loads correctly in iframe; fix nginx `sub_filter` if needed
- Unknown slug in `/portal/tools/[slug]` → graceful 404 message
- All tools disabled → catalog shows empty state with message

## Upgrade Path

When a new it-tools version is released:

1. Update the image tag in `docker-compose.yml`
2. Diff the it-tools changelog for new tools
3. Add new tool entries to `tools_catalog.json`
4. Add a new Alembic migration that upserts the updated catalog (new rows inserted, existing rows left untouched); run `docker compose up --build`
5. New tools default to `enabled = TRUE`
