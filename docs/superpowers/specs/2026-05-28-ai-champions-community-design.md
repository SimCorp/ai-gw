# AI-Champions Community — Design

## Context

SimCorp has ~2000 engineers on the AI gateway. The existing Transformation feature *measures* AI adoption; leadership wants something that *accelerates* it. The idea: a curated **AI-Champions** community where leadership-nominated champions help teams unstick problems, take ideas to production, and share reusable knowledge — without it becoming a full-time content job for the champions.

Built as a thin orchestration + UX layer on top of capabilities the gateway already has (librarian for indexing/search, AI-League for points/badges, Transformation for individual scores, AiHelpWidget as the conversational front door).

## Decisions captured during brainstorming

| # | Question | Decision |
|---|---|---|
| 1 | How are champions identified? | Curated by leadership (admin-managed list) |
| 2 | How do teams ask for help? | All four flows: public help-board, directed (via profile), smart routing, office hours |
| 3 | Content types | Articles + walkthroughs (video) + reusable artifacts + curated external links |
| 4 | Content submission UX | URL-only and paste-text box. No in-platform rich editor. |
| 5 | AI does the curation | Auto-classify, summarise, tag, index every submission |
| 6 | Discovery surfaces | Hub + contextual surfacing + semantic search (all three) |
| 7 | Recognition | AI-League points + public profile + admin activity dashboard (all three) |
| 8 | Integration depth | Thin layer; reuse librarian + AI-League + Transformation |
| 9 | Notifications | In-portal only for V1; push (Teams/email) deferred |
| 10 | Champion capacity | Self-regulation, no system-enforced limits |
| 11 | Ask resolution | Champion marks resolved → asker confirmation prompt → auto-confirm after 7 days |
| 12 | AiHelpWidget integration | **Replace** — AiHelpWidget becomes the front door (chat to browse, search, ask) |
| 13 | Ask visibility | Always company-wide; no privacy toggle |
| 14 | Content moderation | Trust + flag-and-review; admin handles flagged items |

## Goals / Non-Goals

**Goals.** Discoverable, contactable champions through multiple flows. Zero-friction contribution (drop a link or paste text). Effortless consumption (chat-first, hub for browsing, contextual nudges). Visible reward (AI-League points, public profile, manager visibility).

**Non-goals.** Real-time messaging (defer to Teams/email). Anonymous Q&A. In-platform rich editor. System-enforced champion availability.

## Architecture — Thin Layer Across Existing Services

The feature spans three services:

- **services/admin** (:8005) — owns champion data, asks, bookings, AI metadata pipeline, admin UI APIs, and the AiHelpWidget endpoint.
- **services/librarian** (:8008) — ingests content with `topic='champions'`; powers semantic search. No code changes required.
- **services/league** (:8010) — receives point-grant calls for champion actions via a new minimal internal API.

Reuse:
- **Transformation** — champion profile links to the score; contextual surfacing matches user's weakest dimension to champion `focus_areas`.
- **litellm (:8003)** — one cheap call per content submission for classification (existing pattern, same model as `ai_help.py`).
- **AiHelpWidget** — `POST /ai-help/chat/portal` in `services/admin/app/routers/ai_help.py` repurposed as the conversational front door.

```
[Champion] POST /champions/content ──┐
                                      ├─→ litellm classify (one call)
                                      ├─→ librarian.ingest (topic='champions')
                                      ├─→ admin.champion_contributions row
                                      └─→ league points grant (HTTP)

[Team]  AiHelpWidget chat ─→ librarian.search(topic='champions')
                          └─→ low-confidence? "ask a champion" CTA
        GET /champions       directory + filters
        POST /champions/asks help-board entry (always company-wide)
        POST /champions/{id}/book office-hours request
```

## Cross-service points

AI-League lives at `services/league/` with its own DB and no public grant API.

**Decision: add a minimal internal grant API in `services/league/`** (preferred over direct Postgres writes, which would couple schemas).

- `POST /league/internal/points/grant` — accepts `{engineer_id, delta, reason, ref_id}`.
- Auth: existing `X-Admin-Token` mechanism. The admin service already holds the same `settings.admin_token` in its env.
- Reason codes constrained to a `champion_*` prefix and validated server-side.

This is a ~50-line addition to `services/league/app/routers/` and unlocks future cross-service grants. Fallback (if zero changes to the league service are required): direct INSERTs from admin into `league_points_ledger` via shared Postgres.

## Data Model (admin schema, migration `0025_champions.py`)

- `champions` — `developer_id` PK, `bio`, `focus_areas[]`, `office_hours_text` (free-form), `active`, `nominated_at`, `nominated_by`.
- `champion_contributions` — `id`, `champion_id`, `type` (`article|link|video|artifact`), `librarian_item_id`, `submitted_at`, `views`, `upvotes`, `flag_count`, `auto_metadata` JSON.
- `champion_asks` — `id`, `created_by`, `team_id`, `title`, `description`, `status` (`open|claimed|resolved_pending|resolved|closed`), `claimed_by`, `resolved_at`, `confirmed_at`, `auto_confirm_at`, `created_at`, `routed_to[]`, `tags[]`. Always company-wide visible.
- `champion_bookings` — `id`, `champion_id`, `team_id`, `requested_by`, `slot_text`, `topic`, `status`.
- `champion_upvotes` — `(developer_id, contribution_id)` PK.
- `champion_flags` — `id`, `contribution_id`, `flagged_by`, `reason`, `status` (`open|dismissed|removed`), `created_at`.

## API Surface

### services/admin

| Method | Path | Purpose |
|---|---|---|
| GET | `/champions` | Directory (filter by `focus_area`, name) |
| GET | `/champions/{id}` | Profile |
| POST | `/champions/content` | Submit URL or text → AI classify → librarian ingest → league grant |
| GET | `/champions/content` | Feed |
| POST | `/champions/content/{id}/upvote` | Toggle upvote |
| POST | `/champions/content/{id}/flag` | Flag (any developer) |
| GET | `/champions/search?q=` | Semantic via librarian + champion match |
| POST | `/champions/asks` | Create help request |
| GET | `/champions/asks` | List asks |
| POST | `/champions/asks/{id}/claim` | Champion claims |
| POST | `/champions/asks/{id}/route` | Smart-route |
| POST | `/champions/asks/{id}/resolve` | Champion marks resolved → triggers asker prompt |
| POST | `/champions/asks/{id}/confirm` | Asker confirms (or nightly cron auto-confirms) |
| POST | `/champions/{id}/book` | Request office-hours slot |
| POST | `/admin/champions` | Nominate |
| DELETE | `/admin/champions/{id}` | Retire (`active=false`) |
| GET | `/admin/champions/activity` | Per-champion + org-wide impact |
| GET | `/admin/champions/flags` | Moderation queue |
| POST | `/admin/champions/flags/{id}/resolve` | Dismiss or remove |

### services/league (new)

| Method | Path | Purpose |
|---|---|---|
| POST | `/league/internal/points/grant` | Cross-service point grant (X-Admin-Token) |

## AI Auto-Metadata Pipeline (`POST /champions/content`)

1. Champion submits `{url?, text?, type, optional_title}`.
2. If URL: fetch + extract main content (trafilatura; fall back to URL only on failure).
3. Single litellm call (`claude-haiku-4-5`): returns `{title, summary ≤200 chars, focus_areas[], tags[], difficulty}` as structured JSON.
4. Insert into librarian via `POST /ingest` with `topic='champions'`.
5. Insert `champion_contributions` row referencing the librarian item id.
6. Call `POST /league/internal/points/grant` (+50, `reason='champion_content'`).

Champion can edit auto-generated metadata afterwards.

## Resolution flow

```
champion clicks "resolved" → ask.status = resolved_pending
                           → ask.auto_confirm_at = now + 7d
                           → in-portal badge to asker

asker clicks "confirm"      → ask.status = resolved
                            → league grant (+200, champion_ask_resolved)

nightly cron picks up rows where auto_confirm_at < now and status = resolved_pending
                            → ask.status = resolved
                            → league grant (+200, champion_ask_resolved_auto)
```

## Discovery — AiHelpWidget as Front Door

Today (`apps/portal/app/portal/_components/AiHelpWidget.tsx`) the widget calls `POST /ai-help/chat/portal` in `services/admin/app/routers/ai_help.py`, which sends `messages` + a hardcoded `_SYSTEM_PORTAL` prompt to litellm. No RAG, no tools.

Plan changes to `ai_help.py`:

1. Add a librarian retrieval step before the litellm call: query `topic='champions'` (and `topic='docs'` if present) with the user's last message, take top-k chunks above similarity threshold.
2. Augment the system prompt with the retrieved chunks (cited with champion attribution).
3. If no chunk above threshold, return a structured response shape that lets the widget render an "Ask a champion?" CTA pre-filled with the user's last message.
4. Recognise browse intents (small regex-or-classifier layer): "show me champions", "find content on X", "book Y" — return structured card payloads.

Widget changes (`AiHelpWidget.tsx`): render structured card payloads (champion cards, content cards, ask-CTA) when the response signals them; otherwise fall back to current text rendering.

The hub page at `/portal/champions` remains for browsing, but most entry will come through the widget.

## Contextual Surfacing

- **`/portal/transformation`** — "Champions for your weakest dimension" widget mapping lowest sub-score → `focus_areas`.
- **`/portal/playground`, `/portal/agents`, `/portal/workflows`** — inline "Related champion content" rail driven by page tags.

## Recognition

- **AI-League integration** (via new internal grant API, all reason codes prefixed `champion_*`):
  - Content submission: +50 — `champion_content`
  - Ask confirmed: +200 — `champion_ask_resolved`
  - Ask auto-confirmed: +200 — `champion_ask_resolved_auto`
  - Office-hours session marked done: +150 — `champion_office_hours`
  - Upvote received: +5, daily cap 50 — `champion_upvote`
- **Public profile** — `/portal/champions/{id}`: contributions, asks resolved, hours hosted, league rank.
- **Admin visibility** — `/admin/champions/activity`: per-champion 30/90-day deltas, org-wide adoption-impact view.

## Portal & Admin UI

- **Developer portal** (`apps/portal/app/portal/champions/`):
  - `page.tsx` — hub (directory + content feed + open asks)
  - `[id]/page.tsx` — profile
  - `asks/page.tsx` — full board
  - `new-content/page.tsx` — URL or paste-text submission
  - `new-ask/page.tsx` — create ask (reachable from widget CTA)
- **AiHelpWidget rewrite** in `apps/portal/app/portal/_components/AiHelpWidget.tsx` (and admin equivalent) — structured-card rendering, ask-CTA fallback.
- **Admin portal** (`apps/admin/app/admin/champions/`):
  - `page.tsx` — nominate / retire
  - `activity/page.tsx` — impact dashboard
  - `flags/page.tsx` — moderation queue
- Sidebar entries in `PortalShell` and the admin sidebar.
- Reuse `authContext.tsx` for developer auth and `getAdminToken()` for admin auth.

## Phasing (one spec, three shippable waves)

- **Wave 1 — Foundations.** Migration 0025 + admin nominate flow + directory page + content submission + AI metadata pipeline + content feed + league grant API + first grant (`champion_content`).
- **Wave 2 — Interactions.** Ask board + resolution flow + nightly auto-confirm cron + upvotes + flagging + admin moderation queue + AiHelpWidget RAG over champion content.
- **Wave 3 — Rich flows.** Smart routing, office-hours bookings, contextual surfacing widgets, AiHelpWidget intent classification for browse/book, admin activity dashboard.

## Critical files

**services/admin**
- `services/admin/migrations/versions/0025_champions.py` (new — six tables)
- `services/admin/app/routers/champions.py` (new — developer-facing endpoints)
- `services/admin/app/routers/admin_champions.py` (new — admin endpoints)
- `services/admin/app/main.py` (register routers)
- `services/admin/app/routers/ai_help.py` (extend with RAG + structured intents)
- `services/admin/app/llm/champion_metadata.py` (new — classification helper)
- `services/admin/app/jobs/auto_confirm_asks.py` (new — nightly cron)
- `services/admin/app/league_client.py` (new — thin HTTP client to league grant API)

**services/league**
- `services/league/app/routers/internal_points.py` (new — grant API)
- `services/league/app/main.py` (register router)

**services/librarian**
- No code changes; `topic='champions'` is honoured by existing ingest/search.

**apps/portal**
- `apps/portal/app/portal/champions/page.tsx` and subpages (new)
- `apps/portal/app/portal/_components/AiHelpWidget.tsx` (structured-card rendering)
- `apps/portal/app/portal/transformation/page.tsx` (champions widget)
- `apps/portal/app/portal/_lib/PortalShell.tsx` (sidebar entry)

**apps/admin**
- `apps/admin/app/admin/champions/...` (new pages)
- Admin sidebar component (add entry)

## Verification

- **Unit.** pytest suites under `services/admin/tests/` per new router; mock librarian + litellm + league client. New pytest suite under `services/league/tests/` for the internal grant endpoint.
- **Integration.** `docker compose -f infra/docker-compose.yml up`, run scenario:
  1. Admin nominates a champion.
  2. Champion submits a URL → librarian item appears with AI-generated tags + a `+50` row lands in `league_points_ledger` with `reason='champion_content'`.
  3. Developer asks a question in AiHelpWidget → answer cites the new content.
  4. Developer creates an ask → champion claims → marks resolved → asker confirms → `+200` row appears.
  5. Advance time / trigger cron → unconfirmed `resolved_pending` ask auto-confirms; points awarded with `_auto` reason.
  6. Developer flags content → appears in `/admin/champions/flags`; admin removes → content delisted.
- **UI.** Hit `localhost:3002/portal/champions` and `localhost:3001/admin/champions`; exercise widget chat flow end-to-end.
- **Linting.** `ruff check services/admin/ services/league/ && ruff format services/admin/ services/league/`.

## Open questions (settle during implementation)

- Smart-routing model: heuristic (focus_area overlap × recency) only, or add an LLM tiebreak call?
- Office-hours format: free-text decided for V1; revisit if traffic warrants structured slots.
- Multi-language content: does the AI metadata pass need language detection + per-language indexes? Probably defer.
- Champion onboarding: welcome email with how-to-contribute guidance and example submissions?
- Impact metric beyond raw counts: attributing team adoption gains to specific champions is hard — leave for post-V1.
