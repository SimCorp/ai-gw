# IT Tools Developer Toolbox

IT Tools is an integrated developer utility portal providing quick access to utility applications for common development tasks — encoding, conversion, network testing, time/date calculations, cryptography, and more.

## Overview

The IT Tools integration provides:
- **Single-page toolbox**: Browsable catalog of 50+ utility tools
- **Dynamic category filtering**: Organize tools by type (Crypto, Converter, Web, Images, Development, Network, Math, etc.)
- **Search capability**: Full-text search across tool names and categories
- **Admin configuration**: Enable/disable tools on a per-instance basis
- **Direct iframe embedding**: Tools rendered in a secure sandbox with no OS access

## Architecture

### Service Configuration

IT Tools runs the upstream `ghcr.io/corentinth/it-tools` image as its own Container App (`ca-it-tools-dev-sdc`) behind the gateway in Azure Container Apps.

**Deployment:**
The it-tools image (pinned to a specific SHA256 digest) and its version are managed through the Bicep Container App definition and deployed via the normal pipeline. The Container App is internal-only and exposes no public ingress — it is reachable solely through the gateway.

**Gateway Routing:**
```
GET /tools-app/* → it-tools Container App
```

The service runs in a WASM sandbox with no access to the host OS, file system, or network beyond the container environment.

### Portal Integration

The developer portal (`apps/portal`) surfaces IT Tools through:

1. **Toolbox listing page**: `/portal/tools`
2. **Individual tool viewer**: `/portal/tools/{tool_id}`
3. **Search and category filtering**
4. **Direct iframe linking**: Each tool is embedded as `<iframe src="/tools-app/#{tool_id}">`

## Developer Portal UI

### Tools Index Page

**Location:** `/apps/portal/app/portal/tools/page.tsx`

The tools page displays:
- **Search input** for filtering by tool name or category
- **Category tabs** (All, Crypto, Converter, Web, Images, Development, Network, Math, Measurement, Text, Data, Time & Date, Random)
- **Tool cards** with icon, name, and category (each icon is category emoji: 🔐, 🔄, 🌐, etc.)
- **Grid layout** responsive to viewport (3+ columns on desktop, 1-2 on mobile)
- **Pagination**: Loads up to 50 enabled tools

### Tool Viewer Page

**Location:** `/apps/portal/app/portal/tools/{slug}/page.tsx`

Individual tool page with:
- **Iframe container**: Embeds the tool directly via `/tools-app/#{tool_id}`
- **Fallback messaging** if tool fails to load
- **Breadcrumb navigation** back to tools list

## API

### List Tools

`GET /tools`

Retrieve the catalog of configured tools. Developers can call this to power search, filtering, or custom integrations.

**Query Parameters:**
- `enabled_only` (optional, default=false): Return only active tools

**Response:**
```json
[
  {
    "tool_id": "json-formatter",
    "label": "JSON Formatter",
    "category": "Data",
    "enabled": true,
    "updated_at": "2026-05-28T10:30:00Z"
  },
  {
    "tool_id": "base64-encode",
    "label": "Base64 Encoder/Decoder",
    "category": "Crypto",
    "enabled": true,
    "updated_at": "2026-05-28T10:30:00Z"
  },
  {
    "tool_id": "uuid-generator",
    "label": "UUID Generator",
    "category": "Random",
    "enabled": false,
    "updated_at": "2026-05-01T15:00:00Z"
  }
]
```

**Typical Tools Available:**
- **Crypto**: Base64, SHA256, MD5, JWT, RSA
- **Converter**: JSON ↔ YAML, XML ↔ JSON, hex/binary, units
- **Web**: URL encoding, HTML entity encoding, QR codes
- **Images & Videos**: Image minifier, color picker, SVG viewer
- **Development**: diff viewer, regex tester, SQL formatter, YAML validator
- **Network**: IP calculator, port scanner, DNS lookup
- **Math**: Calculator, unit converter, number base conversion
- **Measurement**: Height/weight converter, temperature conversion
- **Text**: Text counter, case converter, slug generator
- **Data**: CSV validator, JSON path tester, datetime converter
- **Time & Date**: Epoch converter, timezone calculator, date math
- **Random**: Password generator, UUID/GUID generator, random data

### Toggle Tool (Admin)

`PATCH /tools/{tool_id}`

Enable or disable a tool in the catalog. Disabled tools do not appear in the developer portal.

**Request:**
```json
{
  "enabled": false
}
```

**Response:**
```json
{
  "tool_id": "uuid-generator",
  "label": "UUID Generator",
  "category": "Random",
  "enabled": false,
  "updated_at": "2026-05-28T14:30:00Z"
}
```

**Notes:**
- Requires any authenticated user (developer or admin)
- Tool enable/disable changes are reflected immediately in the portal

## Database Schema

### tool_config Table

Configuration table for available tools:

| Column | Type | Notes |
|--------|------|-------|
| tool_id | VARCHAR(100) | Primary key, lowercase slug (e.g. `base64-encode`) |
| label | VARCHAR(255) | Display name in portal |
| category | VARCHAR(100) | Category tag for filtering (e.g. `Crypto`, `Data`) |
| enabled | BOOLEAN | Whether tool is visible to developers |
| updated_at | TIMESTAMP | Last modified timestamp |

## Admin Configuration

### Tools Admin Page

**Location:** `/apps/admin/app/admin/tools/...` (if exists)

The admin portal may provide a tools management interface to:
- View all available tools
- Toggle enable/disable per tool
- Organize tools by category
- Search for specific tools

The admin interface calls `GET /tools?enabled_only=false` and `PATCH /tools/{tool_id}` endpoints.

## Example Usage

### From the Developer Portal

1. Developer navigates to `/portal/tools`
2. Portal calls `GET /tools?enabled_only=true`
3. Developer enters search term or clicks a category filter
4. Portal filters locally (client-side)
5. Developer clicks on a tool (e.g. JSON Formatter)
6. Browser navigates to `/portal/tools/json-formatter`
7. Page renders iframe: `<iframe src="/tools-app/#/json-formatter">`
8. It-Tools service loads the tool in the browser

### From Custom Scripts or Integrations

An external tool could list all available tools:

```bash
curl -H "Authorization: Bearer <token>" \
  "https://aigw-dev.lab.cloud.scdom.net/admin/tools?enabled_only=true"
```

Then link engineers to specific tools:

```
https://aigw-dev.lab.cloud.scdom.net/tools/base64-encode
```

## Security

- **Iframe Sandbox**: Tools run in WASM containers with no OS or network access
- **No File System**: Tools cannot read/write local files or access node filesystem
- **No Network**: Tools cannot make outbound HTTP requests
- **Authentication**: Portal auth required to view tool list (enforced by the gateway via Entra ID SSO)
- **Data Isolation**: Each tool session is sandboxed; no cross-tool data sharing

## Limitations

- **No Persistence**: Tool state is not saved between sessions (by design)
- **No File I/O**: Tools cannot upload/download files to the file system
- **No External APIs**: Tools cannot call external APIs or cloud services
- **Stateless**: Each tool invocation is independent; no session cookies or auth tokens passed

## Migration & Uptime

As a Container App, the it-tools service is automatically restarted and recovered by the Azure Container Apps platform on failure. The container image is pinned to a specific SHA256 digest for consistency:

```
ghcr.io/corentinth/it-tools@sha256:8b8128748339583ca951af03dfe02a9a4d7363f61a216226fc28030731a5a61f
```

To update to a newer version:
1. Determine the digest of the desired upstream image tag
2. Update the pinned image digest in the it-tools Bicep Container App definition
3. Deploy through the normal pipeline; Azure Container Apps rolls out the new revision

## Error Handling

### Tool Not Found

If a developer requests `/portal/tools/nonexistent`:
- Page component tries to load the iframe
- It-Tools service responds with 404
- Fallback message displayed in portal

### API Failures

If `/tools` endpoint is unavailable:
- Portal cannot fetch tool list
- Shows "Loading tools…" or "No tools available" message
- Developer can still navigate to known tool URLs directly

### Network Timeouts

If iframe fails to load within timeout:
- Browser console shows CORS or timeout errors
- Tool card shows placeholder or error state
- User can try again or use another tool

## Extensibility

New tools can be added by:
1. Contributing to the upstream `it-tools` project (or forking)
2. Rebuilding the container image
3. Updating the pinned image digest in the it-tools Bicep Container App definition and deploying through the pipeline
4. No code changes needed in the gateway or portal — tools are auto-discovered

If custom tools are needed beyond the community catalog, consider:
- Forking `corentinth/it-tools` and adding custom tools
- Using the same WASM sandbox architecture for consistency
- Publishing a custom image to your container registry
- Pinning to the custom image digest

## Base URLs

**Developer Portal:** `https://aigw-dev.lab.cloud.scdom.net/tools/`

**Direct Tool Access:** `https://aigw-dev.lab.cloud.scdom.net/tools-app/#/{tool_id}`

**API Endpoint:** `https://aigw-dev.lab.cloud.scdom.net/admin/tools`
