# ai-gw Portal Redesign — "Circuit Duotone" Design Spec

**Date:** 2026-06-10
**Scope:** Full UX overhaul of `apps/admin` (38 pages) and `apps/portal` (37 pages).
**Status:** Approved (decisions validated interactively with mockups).

## Goals

- Modern, snappy product feel across both portals.
- Light + dark themes (system default, persisted user toggle).
- One distinct, ownable **ai-gw** brand replacing the generic "AI" branding and the two divergent per-app skins.
- Navigation that scales to ~40 pages per app, with keyboard-first speed (⌘K).

## Brand

- **Name/wordmark:** `ai-gw` in Geist; rail shows a tiny mono suffix `/admin` or `/dev`.
- **Logo:** "circuit node" — a diamond node with gradient trace lines in/out (the gateway as a network node). Used for icon.svg, rail mark, login screens.
- **Brand gradient:** indigo `#6366f1` → fuchsia `#d946ef`. Used as a **trace only**: 1px borders on emphasized cards, active-tab underlines, the logo. Never fills surfaces; no gradient text blocks; no aurora backgrounds.
- **One brand, two accents:** admin uses the indigo end, portal the fuchsia end. Everything else (type, components, layout) is identical between apps.

## Visual language — "Circuit Duotone"

- Neutral surfaces; hairline (1px) borders; radii 6–8px; quiet glass (subtle translucency) allowed in dark mode only.
- Mono uppercase **microlabels** for data labels (e.g. `REQUESTS_24H`), set in Geist Mono with letterspacing.
- **Tabular numerals** for all data values and table number cells.
- Restrained shadows; motion is fast and small (~100–150ms); respect `prefers-reduced-motion`.
- Typography: **Geist** (sans) + **Geist Mono**, self-hosted via the `geist` npm package.

## Theming

- `[data-theme="light"|"dark"]` on `<html>`, managed by `next-themes` (`enableSystem`, persisted). Dark is the temporary default until the page sweep removes hardcoded dark-only inline colors; then default flips to system.
- `[data-surface="admin"|"portal"]` on `<html>` maps **accent tokens only**.

## Token architecture (`packages/ui/src/styles/`)

- `primitives.css` — raw scales (neutral/indigo/fuchsia/status ramps, radii, spacing, type, shadows).
- `theme.css` — semantic tokens, `:root` = light, `[data-theme="dark"]` overrides: `--bg --surface --surface-2 --surface-soft --rule --rule-strong --fg-1/2/3 --accent --accent-hover --accent-soft --accent-fg --trace-from --trace-to --good/--warn/--bad (+softs)`.
- `surface.css` — per-app accent mapping only.
- `compat.css` — legacy aliases (`--sc-blue → var(--accent)`, `--side-* → panel tokens`, …) so the ~2,500 existing inline `var()` references keep working during migration.
- `base.css`, `components.css` (existing class names reimplemented), `shell.css` (rail/panel/topbar/cmdk), `density.css`, `league.css` (game sub-theme, scoped to `[data-zone="league"]`).

## App shell (both apps)

Slim icon rail (one icon per nav domain; logo top; theme toggle + user at bottom) → contextual panel listing the active domain's pages (collapsible, persisted) → topbar with breadcrumb + ⌘K command palette (cmdk) indexing all pages and key actions.

## Deep UX reworks

1. **Admin dashboard** — KPI row with sparklines, live request feed, top teams/models, alerts + approvals quick actions.
2. **Portal home + API keys** — first-run "get to first request" checklist (create key → copy snippet → first request lands); key creation dialog with one-time reveal.
3. **Playground** — params panel, streamed transcript, side-by-side model compare.
4. **AI-League** — complete game-like experience: quest board with QuestCards (difficulty pips, XP), XP bar + level badges, podium leaderboard, reward shop with points wallet, confetti moments. Scoped sub-theme (`[data-zone="league"]`): gold/XP tokens, glow, larger radii, more generous gradient — still inside the brand.

All other pages: restyled via tokens/components; structure preserved. Data layer (TanStack Query, fetch wrappers, auth) untouched throughout.
