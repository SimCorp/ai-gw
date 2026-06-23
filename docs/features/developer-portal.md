# Developer Portal Feature Guide

The Developer Portal (Next.js app at `apps/portal/`) is the primary interface for developers to interact with the AI Gateway. It provides a unified dashboard for model access, API key management, agent registration, and team collaboration.

**Access:** https://dev.aigw.scdom.net/ (over the corporate VPN, Entra ID SSO)

---

## Home Dashboard

The home page (`/`) is the entry point for authenticated developers.

### Components
- **Welcome hero** — personalized greeting with team name and quick action buttons
- **Workspace context** — current team assignment, organizational hierarchy (area/unit/team), and co-memberships
- **AI Recommendations** — 5 most recent AI insights auto-generated every 6 hours (cache/model/budget/error/health/usage categories)
- **Statistics strip** — four key metrics for the current team:
  - Team spend MTD (vs. budget cap)
  - Requests in last 7 days
  - Cache hit rate (last 24h, team average)
  - Average latency + p99
- **Getting started checklist** — guides new developers through key onboarding steps (join team, create key, try playground)
- **Quick actions** — 3-card grid linking to Playground, Agent Builder, and Quickstart docs
- **API keys summary** — shows up to 6 active keys with rotation status
- **Playground session history** — placeholder for recent chat sessions (stored in Playground)

### Data Sources
- Team details: `GET /teams/{team_id}` (admin service)
- Statistics: `GET /dashboard/stats` (admin service)
- API keys: `GET /teams/{team_id}/keys` (admin service, portal-facing)
- AI insights: `GET /insights/developer/me` (admin service, token-authenticated)

### Team Selection
The sidebar component (`TeamSelector`) displays all team memberships. Developer can switch between teams; the home page updates to show stats for the selected team. Switching teams also filters API keys, budgets, and usage data.

---

## API Keys (`/keys`)

Manage scoped API keys for programmatic access to the gateway.

### Key Operations
- **List keys** — displays all team keys (active and revoked) in a table with:
  - Name
  - Key prefix (first 8 chars of hash for identification)
  - Monthly budget cap (if set; otherwise "unlimited")
  - Created date
  - Status (active/revoked)
  - Action: revoke button (confirmation required)

- **Create key** — prompt for name, generates `sk-*` token, returns raw key once (never shown again)
  - Scopes default to `DEFAULT_KEY_SCOPES` (defined in auth service)
  - Optional project_id for per-project tracking
  - Audited: logged in audit_log with developer_id

- **Revoke key** — marks revoked_at timestamp, takes effect within 30 seconds
  - Confirmation dialog shows key name
  - Revoked keys remain in history for audit trail

- **Key best practices** — sidebar card with recommendations:
  - Use one key per service (don't share prod/dev)
  - Set narrowest scope needed
  - Store in Azure Key Vault, not in code
  - Auto-expiry at 90 days — rotate before expiration
  - Compromised: revoke within 30s

### Key Tester
Verify a key before deployment:
- Input text field (supports `sk-*` format)
- **Run test** — sends sample request to `/v1/chat/completions` with `claude-haiku-4-5` model
- Success: shows "Key is valid · gateway responded in Xms" with model response
- Failure: shows HTTP status and error message
- Latency measured client-side (T0 to response arrival)

### Code Samples
Language-specific examples (curl, Python, TypeScript, Anthropic SDK):
- Base URL: `https://dev.aigw.scdom.net/v1` (OpenAI-compatible)
- Anthropic-shaped: `/anthropic` path
- All samples assume key in `$AIGW_KEY` environment variable
- Copyable code blocks with single-click copy to clipboard

### API Contract
- `GET /teams/{team_id}/keys` — list active keys (Bearer token required)
- `POST /teams/{team_id}/keys` — create key (Bearer token + name in body)
- `DELETE /teams/{team_id}/keys/{key_id}` — revoke key (Bearer token)

Authentication: developer session token (stored in Redis as `dev_session:{token}`)

---

## Playground (`/playground`)

Interactive chat interface for testing models before integration.

### Features
- **Model picker** — dropdown fetches from `GET /v1/models` (LiteLLM service)
  - Falls back to static list if gateway unreachable
  - Model list scoped to developer's allowed models
- **System prompt** — customizable (default: "You are a helpful assistant.")
- **Parameter panel** — three tabs:
  - **Params:** temperature (0–1), top_p (0–1), max_tokens (1–8192)
  - **Tools:** attach MCP servers or custom tools (UI placeholder in current version)
  - **Context:** upload files, add retrieval sources (UI placeholder)
- **Cache toggle** — use prompt caching for long contexts (OpenAI/Anthropic feature)
- **API key input** — auto-loads first active team key; can override with manual key
- **Chat thread** — message history with:
  - Role labels (user/assistant)
  - Token counts (in/out)
  - Latency + p99 where available
  - Streaming indicator
  - Error state if request fails
- **Export** — copy conversation as JSON or markdown (future feature)

### Data Flow
1. User types message
2. Playground sends to `/v1/chat/completions` (cache service) with:
   - Selected model
   - System prompt
   - Full message history
   - Tuned parameters
3. Gateway routes via LiteLLM to provider
4. Streaming response rendered line-by-line in thread

### Related Content
`RelatedChampionContent` component suggests Champions (community experts) articles related to the current model or topic.

---

## Models (`/models`)

Unified model catalogue showing all available LLMs and their providers.

### Display
- Grid of model cards, grouped by provider (Anthropic, OpenAI, Google, Azure, GitHub, self-hosted)
- For each model:
  - Display name (e.g., "Claude 3.5 Sonnet")
  - Provider badge (colored logo + text)
  - "In LiteLLM" indicator (checkmark = routed via gateway, × = admin registry only)
  - Metadata (description, context window if available)

### Provider Detection
Logic in `detectProvider()` maps model IDs to upstream services:
- `claude*` → Anthropic
- `gpt*`, `o1*`, `o3*` → OpenAI
- `gemini*` → Google
- `azure-*` or Phi/DeepSeek/Cohere/Mistral/Llama → Azure AI Foundry
- `copilot-*` → GitHub Copilot
- `github-*` → GitHub Models

### Data Sources
- LiteLLM `/v1/models` — live available models (requires admin key `sk-litellm-local-dev`)
- Admin `/models?enabled_only=true` — curated registry with display names and descriptions

---

## Agents (`/agents`)

Agent registry and discovery interface.

### Agent List
- Fetches from `GET /agents` (admin service)
- Grid of agent cards with:
  - Custom image (if provided)
  - Agent name
  - Category (utility, llm, integration, data) with color coding
  - Short description
  - "Managed" badge (system agent vs. user-registered)

### Identity Search
- Search field with 500ms debounce
- Resolves agent DNS-style via identity service: `/resolve?slug=<query>`
- Results show:
  - Agent name, slug, category
  - Capabilities (list of MCP tools/resources)
  - Endpoint URL
  - Team ownership
  - Online/offline indicator (green/gray dot)
  - Registration timestamp + last heartbeat

### Create Agent
Button links to agent builder or creation form (UI structure TBD).

### Online Status
- Agents heartbeat to identity service; last_seen timestamp refreshes
- Offline = no heartbeat in TTL window (default: 30 seconds)

---

## Workflows (`/workflows`)

Workflow designer and execution interface (placeholder in current version).

### Planned Features
- Visual builder (drag-and-drop nodes)
- Trigger setup (manual, schedule, webhook)
- Step composition (agents, conditions, loops)
- Execution history and logs
- Alerting on failure

---

## Usage & Spend (`/usage`)

Consumption tracking and cost attribution.

### Dashboard
- Period selector (MTD, custom range)
- Cost breakdown:
  - By model (Claude vs. GPT vs. Gemini)
  - By team member (if data available)
  - By project (if keys tagged with project_id)
- Per-request history (when implemented)
- Export as CSV

### Budget Alerts
- Visual warning if team has exceeded alert threshold (default: 80% of cap)
- Notification sent to team admin via email (SMTP)

---

## Prompts (`/prompts`)

Prompt library and version control.

### Features (Planned)
- List saved prompts
- Fork and edit
- Share with team (RBAC)
- Version history
- Tag/search by category
- Export as markdown or JSON

---

## Tools / MCP Servers (`/tools` and `/mcp`)

Tool and Model Context Protocol (MCP) server management.

### Tools Page
- List available MCP servers
- For each:
  - Name and icon
  - Supported tools (resources/functions)
  - Status (ready/initializing/error)
  - Scopes (read/write/execute if restricted)
  - Link to docs

### MCP Page
- Configuration guide for local server setup
- List of public servers (Anthropic registry, community contributed)
- Installation instructions (Docker, pip, npm)
- CLI commands for listing tools

---

## Plugins & Skills (`/plugins` and `/skills`)

Extension ecosystem for custom integrations.

### Plugins
- Pre-built integrations (e.g., Slack, Jira, GitHub, Datadog)
- Installation flow with OAuth/API key setup
- Permissions requested (scope labels)
- Activity logs (when plugin is invoked)

### Skills
- Developer-authored functions (similar to plugins but lower-level)
- Searchable registry
- Versioning and rollback
- Community ratings

---

## Security Scanner (`/security`)

Developer-side security scanning and compliance features.

### Capabilities (Planned)
- API key strength check
- Prompts scan for PII leakage
- Model access audit (which models used, by whom)
- Suspicious request detection (anomaly alerts)
- Compliance reporting (SOC 2, GDPR)

---

## AI Transformation (`/transformation`)

Personal transformation tracking and gamification.

### Dashboard
- AI skills improvement over time (inferred from prompt quality + model usage)
- Badges earned (e.g., "First Agent", "Cached 100 Requests")
- Leaderboard rank (team and org-wide)
- Learning path suggestions (recommended skills to improve)
- Time spent in portal / calls made (productivity insights)

---

## League (`/league`)

Gamified challenge platform and community engagement.

### Features
- **Challenges** — coding contests, creative tasks (e.g., "build an agent that summarizes financial reports in <30ms")
- **Submissions** — code upload, automated evaluation
- **Leaderboard** — global and team rankings by score, speed, creativity
- **Prizes** — store with point redemption (team swag, extra quota, recognition)
- **Live events** — seasonal competitions, sponsor showcases

---

## Champions (`/champions`)

Community expert network and knowledge sharing.

### Pages
- **Champions grid** (`/champions`) — list of recognized experts with:
  - Bio and specialties
  - Articles/guides authored
  - Response time SLA
  - Contact info (Slack handle, calendar link)

- **Champion details** (`/champions/[id]`) — individual expert profile with:
  - Bio and background
  - Published articles
  - Ask form (submit questions for office hours)
  - Rating/review history

- **Ask hub** (`/champions/asks`) — community Q&A:
  - Submit question
  - Filter by topic (prompting, agents, optimization, security)
  - View responses from Champions
  - Rate answer helpfulness

### Related Content
`RelatedChampionContent` component (rendered on Playground) shows relevant Champion articles based on current model/topic.

---

## Settings (`/settings`)

Account and workspace configuration.

### Tabs (Planned)
- **Profile** — name, avatar, timezone, language
- **Notifications** — email preferences, alert channels
- **Keys** — link to key management page
- **Team settings** — if user is team admin (invite members, set budgets, configure integrations)

---

## Navigation & Shell

### PortalShell Component
- Top navigation bar with:
  - Portal logo / home link
  - Team selector (dropdown with all memberships)
  - Search / command palette
  - User profile menu (logout, settings)
- Left sidebar with sections:
  - **Home** → home page
  - **Build** → playground, agents, workflows, prompts
  - **Tools** → models, MCP servers, tools, skills
  - **Insights** → usage, transformation, league, champions
  - **Admin** → (team admins only) settings, audit log, budget config

### Auth Context
`AuthContext` provides:
- `developer` object (id, email, display_name, team_id, roles)
- `memberships` array (all team assignments with role per team)
- `token` (session token for Bearer auth)
- Sign out function

### Team Context
`TeamContext` provides:
- Current `teamId` and `teamName`
- Team switch handler

---

## Authentication & Authorization

### Session Token
- Issued by auth service (`/auth/login`)
- Stored in Redux as `dev_session:{token}`
- 8-hour TTL (7 days if "remember me" checked)
- Passed in `Authorization: Bearer <token>` header to all portal-facing endpoints

### Team Membership Check
- Portal endpoints verify developer is a member of `{team_id}`
- Membership from `team_members` table
- If membership removed or user promoted to gateway_admin, session remains valid but API calls fail with 403

### Developer Role
- Developers have limited scope (read own profile, create/revoke own keys)
- Team admins can manage team members, budgets, integrations
- Platform admins can manage org-wide settings, audit log, contractors

---

## Accessibility & Theming

- Dark mode via CSS variables (`--fg-1`, `--bg`, `--rule`, etc.)
- Keyboard navigation for all interactive elements
- WCAG 2.1 AA compliance target
- Custom CSS at `_styles/portal.css`

---

## Error States

- **No team assigned** — home page shows prompt to contact admin
- **Key tester fails** — displays HTTP status + error message from gateway
- **Model list unreachable** — falls back to static fallback list
- **Session expired** — 401 redirects to login page
- **Insufficient permissions** — 403 shows "Not a member of this team" message

---

## Future Roadmap

- Real-time request history and per-user analytics
- Prompt injection detection and sanitization
- Cost forecasting (ML model predicting end-of-month spend)
- OAuth2 integration with GitHub/GitLab for OIDC
- API docs auto-generation from schema
- Agent marketplace (publish/discover community agents)
- Workflow builder visual editor
- Multi-language support
