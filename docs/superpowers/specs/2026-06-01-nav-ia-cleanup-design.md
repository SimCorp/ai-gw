# Design Spec: Sidebar Navigation IA Cleanup (Portal + Admin)
**Date:** 2026-06-01
**Status:** Approved for implementation

---

## Context

Both Next.js front-ends have accreted pages faster than their sidebars were re-grouped, so navigation reads as "scattered":

- **Portal** (`apps/portal`) — the sidebar's `Use` group is a flat list of **13 items**, mixing build tools, credentials, catalog, and security with no sub-structure. The `Account` group is a grab-bag (usage, transformation, champions, bookings, settings).
- **Admin** (`apps/admin`) — **8 groups**, but the entire **Scanner subsystem** (`/admin/security/*`, 4 pages backing the `scanner` service) is **not linked from the sidebar at all**, and **Champions** is listed three times as flat siblings (`Champions`, `Champions · Activity`, `Champions · Flags`).

This spec covers **navigation information architecture only** — regrouping the sidebars so items live where they logically belong, and homing the orphaned pages. Each app gets its **own** scheme (they serve different audiences); no cross-app symmetry is forced.

**Out of scope / separate spec:** within-page element layout across the ~70 pages. That is sub-project B — to be scoped from an audit *after* this reorg lands, against the new structure (see [§7 Future work](#7-future-work)).

---

## Decisions

| # | Question | Decision |
|---|----------|----------|
| 1 | Surface | Both apps (portal + admin), each with its own scheme |
| 2 | Scope of this spec | Sidebar IA only — no page content, route, or behaviour changes |
| 3 | Approach | Per-app task-oriented regroup ("Approach B"); fix defects along the way |
| 4 | Admin Scanner orphans | Home them in a new top-level **Security** group |
| 5 | Admin Champions triplicate | Collapse to one `Champions` entry; `Activity` & `Flags` become indented sub-items |
| 6 | Admin Overview + Operate | Merge into a single **Monitor** group |
| 7 | Nav mechanism | Keep each app's existing mechanism — portal stays data-driven (`NAV` array), admin stays hand-written JSX. No rewrite. |
| 8 | "Organisation" spelling | Keep existing British spelling — not changed gratuitously |

---

## 1. Target — Portal sidebar

Audience: developers. The 13-item `Use` bin splits by task (Build / Access / Catalog / Monitor); `Home` & `Quickstart` lift to an ungrouped top block; the `Account` grab-bag splits (Usage→Monitor, Transformation/Champions/Bookings→Grow).

| Group | Items (label → href) |
|-------|----------------------|
| *(top, no header)* | Home → `/portal` · Quickstart → `/portal/docs` |
| **Build** | Playground → `/portal/playground` · Agents → `/portal/agents` · Workflows → `/portal/workflows` · Prompts → `/portal/prompts` |
| **Access** | Models → `/portal/models` · API keys → `/portal/keys` |
| **Catalog** | MCP servers → `/portal/mcp` · Plugins → `/portal/plugins` · Skills → `/portal/skills` · Tools → `/portal/tools` |
| **Monitor** | Usage & spend → `/portal/usage` · Security → `/portal/security` |
| **Grow** | AI Transformation → `/portal/transformation` · Champions → `/portal/champions` · Bookings → `/portal/champions/bookings` |
| **League** | Challenges → `/portal/league` · Leaderboard → `/portal/league/leaderboard` · My Results → `/portal/league/results` · Store → `/portal/league/store` |
| **Account** | Settings → `/portal/settings` |

Every item already exists in today's `NAV` array — this is a re-grouping, not new pages. **Each item keeps its current icon.** `Home` and `Quickstart` keep their icons; only their group placement changes.

---

## 2. Target — Admin sidebar

Audience: platform operators/admins. Old `Overview` + `Operate` merge into `Monitor`; Champions collapses; new `Security` group homes the orphans.

| Group | Items (label → href) |
|-------|----------------------|
| **Monitor** | Dashboard → `/admin/dashboard` · Live requests → `/admin/requests` · Cost reports → `/admin/reports` · Alerts → `/admin/alerts` |
| **Organisation** | Org tree → `/admin/org` · Users → `/admin/users` |
| **AI Transformation** *(clickable header → `/admin/transformation`)* | GenAI Adoption → `/admin/genai-adoption` · AI Insights → `/admin/insights` · DevOps Agent → `/admin/devops` · Champions → `/admin/champions` ↳ Activity → `/admin/champions/activity` ↳ Flags → `/admin/champions/flags` |
| **Govern** | Guardrails → `/admin/guardrails` · Policies → `/admin/policies` · Quotas & budgets → `/admin/quotas` · Approvals → `/admin/approvals` · Audit log → `/admin/audit` |
| **Security** *(NEW)* | Targets → `/admin/security/targets` · Scan jobs → `/admin/security/jobs` · Team quotas → `/admin/security/quotas` |
| **Catalog** | MCP servers → `/admin/mcp` · Memory → `/admin/memory` · Skills → `/admin/skills` · Plugins → `/admin/plugins` |
| **Configure** | Models → `/admin/models` · Semantic cache → `/admin/cache` · Providers → `/admin/providers` · Auto-Drive → `/admin/providers#auto-drive` · Developer tools → `/admin/tools` |
| **League** | Seasons → `/admin/league/seasons` · Challenges → `/admin/league/challenges` · Proposals → `/admin/league/proposals` · Store editor → `/admin/league/store` |
| **Settings** | Entra ID groups → `/admin/settings/entra` · Sessions → `/admin/settings/sessions` |

`/admin/security` is a redirect to `/admin/security/targets`, so the `Security` group lists the three real pages directly (no phantom "Overview" item). The `AI Transformation` group retains its current clickable-section-header pattern (`NavSectionLink`).

---

## 3. Implementation notes

### Portal — `apps/portal/app/portal/_components/PortalShell.tsx`
- Restructure the `NAV` constant (currently 3 groups: `Use` / `League` / `Account`) into the groups in §1.
- For the ungrouped top block, give the first entry an empty group label (`group: ""`) and **guard the renderer** so a falsy `group` omits the `<div className="group">` header. This is the only renderer change.
- `isActive()` logic (special cases for `/portal` and `/portal/league`) is unchanged — hrefs don't change, so active highlighting keeps working.
- Reuse existing per-item `icon` values; no new icons.

### Admin — `apps/admin/app/admin/layout.tsx`
- Rearrange the `NavSection` / `NavSectionLink` / `NavItem` blocks (lines ~93–152) to match §2.
- Delete the two extra Champions `NavItem`s as flat siblings; render `Activity` and `Flags` as **indented sub-items** under `Champions`. Minimal approach: a thin `NavSubItem` wrapper (or a `NavItem` with larger left padding, e.g. `padding: '6px 14px 6px 28px'`) — no new dependency, no data-driven rewrite.
- Add the new **Security** `NavSection` with the three Scanner items.
- Merge old `Overview` + `Operate` into one `Monitor` `NavSection`.

### Route safety
All target hrefs map to pages that exist today (verified against the `app/` tree). No routes are added, removed, or renamed.

---

## 4. Non-goals

- **No page content changes.** Layout *inside* pages is sub-project B.
- **No converting Champions sub-pages to tabs** — nesting in the sidebar is the nav-scope fix; tabs are a within-page change.
- **No adding active-state highlighting to admin** (it has none today) — out of scope; don't add unrequested behaviour.
- **No rewrite of admin nav to data-driven**, and no change to portal's nav mechanism beyond the empty-header guard.
- **No route/URL changes.**

---

## 5. Acceptance criteria

1. **No dead links:** every sidebar item in both apps resolves to an existing route (manual click-through of all groups, no 404).
2. **Scanner reachable:** the admin **Security** group links Targets / Scan jobs / Team quotas; clicking the orphaned pages is now possible from the sidebar; `/admin/security` still redirects to targets.
3. **Champions collapsed:** admin sidebar shows `Champions` once, with `Activity` and `Flags` visually nested beneath it — no three flat siblings.
4. **Portal de-clustered:** the old 13-item `Use` group is gone; no group exceeds ~6 items; Home & Quickstart sit ungrouped at the top.
5. **Behaviour preserved:** portal active-state highlighting works on every route; the admin `AI Transformation` header still navigates to `/admin/transformation`.
6. **Surgical diff:** changes are limited to `PortalShell.tsx` and `admin/layout.tsx` (plus, at most, a small nav sub-item helper). No other files touched.
7. **Builds clean:** `pnpm --filter portal build` and `pnpm --filter admin build` succeed; `eslint` passes for both apps.

---

## 6. Verification plan

- Run both apps (`docker compose -f infra/docker-compose.yml up` or the dev scripts) and click every sidebar entry in each app, confirming the correct page loads.
- Confirm the admin Scanner pages, previously unreachable, now open from the **Security** group.
- Confirm `git diff --stat` shows only the two expected files (± one helper).

---

## 7. Future work

**Sub-project B — within-page layout cleanup.** After this reorg lands, audit all pages in both apps and produce a ranked shortlist of the worst "scattered" pages (controls/sections not grouped logically inside the page). Scope and spec those against the *new* navigation structure, page-by-page or in small clusters. Tracked separately; not part of this spec.
