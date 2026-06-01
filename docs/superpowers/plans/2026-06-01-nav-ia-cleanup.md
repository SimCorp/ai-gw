# Sidebar Navigation IA Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Regroup the portal and admin sidebars per the approved IA so items live in logical groups, the orphaned admin Scanner pages are reachable, and the Champions triplicate is collapsed — with zero changes to routes or page contents.

**Architecture:** Pure navigation restructure in two independent files. Portal nav is data-driven (a `NAV` array) — restructure the array + add a one-line empty-header guard. Admin nav is hand-written JSX (`NavSection`/`NavItem`) — rearrange it and add one small `NavSubItem` helper for indented children. No data-driven rewrite, no route changes.

**Tech Stack:** Next.js 15 (App Router), React 19, TypeScript, inline styles. No frontend unit-test runner exists.

**Spec:** `docs/superpowers/specs/2026-06-01-nav-ia-cleanup-design.md`

---

## Testing approach (read first)

There is **no frontend unit-test harness** (no vitest/jest/playwright), and this change is static nav config/markup — there is no logic to unit-test, and standing up a harness is explicitly out of scope. The executable verification for each task is:

1. **Dead-link check** — a bash snippet that extracts every nav href and asserts the matching `page.tsx` exists. This guards "no orphans / Scanner reachable / no dead links." Every href must print `OK`.
2. **Lint** — `pnpm --filter <pkg> lint` must pass.
3. **Build** — `pnpm --filter <pkg> build` must succeed (thorough; compiles TS/JSX).
4. **Manual click-through** — done at integration (Task 3), for visual/behaviour criteria (nesting, active-state).

The two tasks touch different files in different apps and are **fully independent** — they can run in parallel.

---

## Task 1: Portal sidebar regroup

**Files:**
- Modify: `apps/portal/app/portal/_components/PortalShell.tsx` (the `NAV` constant at lines ~8-46, and the render loop at lines ~100-117)

- [ ] **Step 1: Replace the `NAV` constant**

Replace the entire `const NAV = [ ... ];` block (currently the 3 groups `Use`/`League`/`Account`) with this 8-group structure. Every item already existed — this only re-groups them and keeps each item's existing icon. Note the first group has `group: ""` (rendered headerless).

```tsx
const NAV = [
  {
    group: "",
    items: [
      { href: "/portal",      label: "Home",       icon: <HomeIcon /> },
      { href: "/portal/docs", label: "Quickstart", icon: <DocIcon /> },
    ],
  },
  {
    group: "Build",
    items: [
      { href: "/portal/playground", label: "Playground", icon: <PlayIcon />, kbd: "⌘P" },
      { href: "/portal/agents",     label: "Agents",     icon: <AgentIcon /> },
      { href: "/portal/workflows",  label: "Workflows",  icon: <WorkflowIcon /> },
      { href: "/portal/prompts",    label: "Prompts",    icon: <PromptIcon /> },
    ],
  },
  {
    group: "Access",
    items: [
      { href: "/portal/models", label: "Models",   icon: <CubeIcon /> },
      { href: "/portal/keys",   label: "API keys", icon: <KeyIcon /> },
    ],
  },
  {
    group: "Catalog",
    items: [
      { href: "/portal/mcp",     label: "MCP servers", icon: <McpIcon /> },
      { href: "/portal/plugins", label: "Plugins",     icon: <PluginIcon /> },
      { href: "/portal/skills",  label: "Skills",      icon: <SkillIcon /> },
      { href: "/portal/tools",   label: "Tools",       icon: <WrenchIcon /> },
    ],
  },
  {
    group: "Monitor",
    items: [
      { href: "/portal/usage",    label: "Usage & spend", icon: <ChartIcon /> },
      { href: "/portal/security", label: "Security",      icon: <SecurityIcon /> },
    ],
  },
  {
    group: "Grow",
    items: [
      { href: "/portal/transformation",     label: "AI Transformation", icon: <TransformIcon /> },
      { href: "/portal/champions",          label: "Champions",         icon: <TrophyIcon /> },
      { href: "/portal/champions/bookings", label: "Bookings",          icon: <ResultsIcon /> },
    ],
  },
  {
    group: "League",
    items: [
      { href: "/portal/league",             label: "Challenges",  icon: <SwordIcon /> },
      { href: "/portal/league/leaderboard", label: "Leaderboard", icon: <TrophyIcon /> },
      { href: "/portal/league/results",     label: "My Results",  icon: <ResultsIcon /> },
      { href: "/portal/league/store",       label: "Store",       icon: <StoreIcon /> },
    ],
  },
  {
    group: "Account",
    items: [
      { href: "/portal/settings", label: "Settings", icon: <SettingsIcon /> },
    ],
  },
];
```

- [ ] **Step 2: Guard the group header so the headerless top block renders no label**

In the render loop (inside `<nav className="psidebar__nav">`), change the group wrapper so an empty `group` string omits the `<div className="group">` header and uses a stable key. Replace:

```tsx
        {NAV.map((section) => (
          <div key={section.group}>
            <div className="group">{section.group}</div>
```

with:

```tsx
        {NAV.map((section) => (
          <div key={section.group || "top"}>
            {section.group && <div className="group">{section.group}</div>}
```

Leave the rest of the loop (the `section.items.map(...)` Link block) unchanged.

- [ ] **Step 3: Run the dead-link check**

Run:

```bash
cd /home/bntp/repos/ai-gw
grep -oE 'href: "/portal[^"]*"' apps/portal/app/portal/_components/PortalShell.tsx \
  | sed -E 's/href: "//; s/"$//' | sort -u | while read -r r; do
    p="${r#/portal}"; p="${p%%#*}"
    f="apps/portal/app/portal${p}/page.tsx"
    [ -f "$f" ] && echo "OK   $r" || echo "MISS $r -> $f"
  done
```

Expected: every line starts with `OK` (e.g. `OK   /portal`, `OK   /portal/docs`, `OK   /portal/champions/bookings`). Zero `MISS` lines.

- [ ] **Step 4: Lint and build**

Run:

```bash
cd /home/bntp/repos/ai-gw
pnpm --filter @aigw/portal lint
pnpm --filter @aigw/portal build
```

Expected: lint passes; build completes with no type errors.

- [ ] **Step 5: Commit**

```bash
cd /home/bntp/repos/ai-gw
git add apps/portal/app/portal/_components/PortalShell.tsx
git commit -m "feat(portal): regroup sidebar nav — Build/Access/Catalog/Monitor/Grow"
```

---

## Task 2: Admin sidebar regroup

**Files:**
- Modify: `apps/admin/app/admin/layout.tsx` (the nav body at lines ~93-152; add a `NavSubItem` helper near the other `Nav*` functions at lines ~189-221)

- [ ] **Step 1: Add the `NavSubItem` helper**

Immediately after the existing `NavItem` function (ends ~line 221), add an indented, muted variant used for Champions' nested children:

```tsx
function NavSubItem({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      style={{
        display: 'block',
        padding: '6px 14px 6px 30px',
        fontSize: 12.5,
        color: 'var(--side-fg-mute)',
        borderRadius: 4,
        margin: '1px 6px',
        textDecoration: 'none',
      }}
      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--side-active)'; (e.currentTarget as HTMLElement).style.color = 'var(--side-fg)'; }}
      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = ''; (e.currentTarget as HTMLElement).style.color = 'var(--side-fg-mute)'; }}
    >
      {label}
    </Link>
  );
}
```

- [ ] **Step 2: Replace the nav body**

Replace the entire contents of the `<div style={{ flex: 1, overflowY: 'auto' }}>` block (the 8 current `NavSection`/`NavSectionLink` blocks) with the structure below. Changes vs current: old `Overview` + `Operate` merged into `Monitor`; Champions' two extra flat siblings become `NavSubItem`s; new `Security` group added; existing labels (e.g. "Model registry", "Cost reports", "Audit log") preserved.

```tsx
              <div style={{ flex: 1, overflowY: 'auto' }}>
                <NavSection label="Monitor">
                  <NavItem href="/admin/dashboard" label="Dashboard" />
                  <NavItem href="/admin/requests" label="Live requests" />
                  <NavItem href="/admin/reports" label="Cost reports" />
                  <NavItem href="/admin/alerts" label="Alerts" />
                </NavSection>

                <NavSection label="Organisation">
                  <NavItem href="/admin/org" label="Org tree" />
                  <NavItem href="/admin/users" label="Users" />
                </NavSection>

                <NavSectionLink href="/admin/transformation" label="AI Transformation">
                  <NavItem href="/admin/genai-adoption" label="GenAI Adoption" />
                  <NavItem href="/admin/insights" label="AI Insights" />
                  <NavItem href="/admin/devops" label="DevOps Agent" />
                  <NavItem href="/admin/champions" label="Champions" />
                  <NavSubItem href="/admin/champions/activity" label="Activity" />
                  <NavSubItem href="/admin/champions/flags" label="Flags" />
                </NavSectionLink>

                <NavSection label="Govern">
                  <NavItem href="/admin/guardrails" label="Guardrails" />
                  <NavItem href="/admin/policies" label="Policies" />
                  <NavItem href="/admin/quotas" label="Quotas & budgets" />
                  <NavItem href="/admin/approvals" label="Approvals" />
                  <NavItem href="/admin/audit" label="Audit log" />
                </NavSection>

                <NavSection label="Security">
                  <NavItem href="/admin/security/targets" label="Targets" />
                  <NavItem href="/admin/security/jobs" label="Scan jobs" />
                  <NavItem href="/admin/security/quotas" label="Team quotas" />
                </NavSection>

                <NavSection label="Catalog">
                  <NavItem href="/admin/mcp" label="MCP servers" />
                  <NavItem href="/admin/memory" label="Memory" />
                  <NavItem href="/admin/skills" label="Skills" />
                  <NavItem href="/admin/plugins" label="Plugins" />
                </NavSection>

                <NavSection label="Configure">
                  <NavItem href="/admin/models" label="Model registry" />
                  <NavItem href="/admin/cache" label="Semantic cache" />
                  <NavItem href="/admin/providers" label="Providers" />
                  <NavItem href="/admin/providers#auto-drive" label="Auto-Drive" />
                  <NavItem href="/admin/tools" label="Developer tools" />
                </NavSection>

                <NavSection label="League">
                  <NavItem href="/admin/league/seasons" label="Seasons" />
                  <NavItem href="/admin/league/challenges" label="Challenges" />
                  <NavItem href="/admin/league/proposals" label="Proposals" />
                  <NavItem href="/admin/league/store" label="Store editor" />
                </NavSection>

                <NavSection label="Settings">
                  <NavItem href="/admin/settings/entra" label="Entra ID groups" />
                  <NavItem href="/admin/settings/sessions" label="Sessions" />
                </NavSection>
              </div>
```

- [ ] **Step 3: Run the dead-link check**

Run:

```bash
cd /home/bntp/repos/ai-gw
grep -oE 'href="/admin[^"]*"' apps/admin/app/admin/layout.tsx \
  | sed -E 's/href="//; s/"$//' | sort -u | while read -r r; do
    p="${r#/admin}"; p="${p%%#*}"
    f="apps/admin/app/admin${p}/page.tsx"
    [ -f "$f" ] && echo "OK   $r" || echo "MISS $r -> $f"
  done
```

Expected: every line starts with `OK`, including `OK   /admin/security/targets`, `OK   /admin/security/jobs`, `OK   /admin/security/quotas`, `OK   /admin/champions/activity`, `OK   /admin/champions/flags`, `OK   /admin/providers` (the `#auto-drive` hash is stripped). Zero `MISS` lines.

- [ ] **Step 4: Lint and build**

Run:

```bash
cd /home/bntp/repos/ai-gw
pnpm --filter @aigw/admin lint
pnpm --filter @aigw/admin build
```

Expected: lint passes; build completes with no type errors (the new `NavSubItem` is referenced and defined).

- [ ] **Step 5: Commit**

```bash
cd /home/bntp/repos/ai-gw
git add apps/admin/app/admin/layout.tsx
git commit -m "feat(admin): regroup sidebar nav — Monitor merge, Security group, collapse Champions"
```

---

## Task 3: Integration verification

**Files:** none (verification only)

- [ ] **Step 1: Confirm a surgical diff**

Run:

```bash
cd /home/bntp/repos/ai-gw
git diff --stat HEAD~2
```

Expected: exactly two files changed — `apps/portal/app/portal/_components/PortalShell.tsx` and `apps/admin/app/admin/layout.tsx`. No other files.

- [ ] **Step 2: Manual click-through**

Start the apps (`docker compose -f infra/docker-compose.yml up`, or `pnpm --filter @aigw/portal dev` / `pnpm --filter @aigw/admin dev`) and verify:
- **Portal:** sidebar shows the headerless Home/Quickstart top block, then Build / Access / Catalog / Monitor / Grow / League / Account. Every item navigates to the correct page; the active item still highlights.
- **Admin:** sidebar shows Monitor / Organisation / AI Transformation / Govern / Security / Catalog / Configure / League / Settings. The **Security** group opens the Scanner pages (previously unreachable). Under AI Transformation, **Champions** shows **Activity** and **Flags** indented beneath it. Clicking the "AI Transformation" header still goes to `/admin/transformation`.

- [ ] **Step 3: Push**

```bash
cd /home/bntp/repos/ai-gw
git push
```

---

## Self-Review (completed during planning)

**1. Spec coverage:**
- Portal 13-item bin split → Task 1 (Build/Access/Catalog/Monitor groups). ✓
- Portal Account grab-bag split (Usage→Monitor, Transformation/Champions/Bookings→Grow) → Task 1. ✓
- Home/Quickstart ungrouped top → Task 1 Steps 1–2 (`group: ""` + header guard). ✓
- Admin Overview+Operate→Monitor → Task 2. ✓
- Admin Champions collapse + nest → Task 2 (`NavSubItem`). ✓
- Admin Scanner orphans homed → Task 2 (Security group). ✓
- "No dead links / Scanner reachable / no orphans" acceptance → dead-link check (Tasks 1 & 2, Step 3). ✓
- "Surgical diff" acceptance → Task 3 Step 1. ✓
- Behaviour preserved (active-state, AI Transformation header) → Task 3 Step 2. ✓

**2. Placeholder scan:** No TBD/TODO; all code blocks are complete and copy-pasteable. ✓

**3. Type consistency:** `NavSubItem({ href, label })` defined in Task 2 Step 1 matches its usage in Step 2. Portal `NAV` item shape (`href`/`label`/`icon`/optional `kbd`) matches the existing render loop, unchanged. ✓

---

## Execution Handoff

The two implementation tasks are independent (different files, different apps) and suit **parallel** execution. Task 3 is verification, run after both land.
