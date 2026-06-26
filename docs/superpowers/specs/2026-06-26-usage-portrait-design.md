# Usage Portrait — Design Spec

**Issue:** #193  
**Date:** 2026-06-26  
**Status:** approved for implementation

## Overview

Each developer's portal home page shows a small, AI-generated ink-style illustration that reflects their last 7 days of gateway usage. It's generated once per ISO week, cached in Postgres, and loaded lazily so it never blocks the page. Clicking an expand button reveals a one-liner explanation for each scene element ("The owl represents your heavy Opus use this week").

## Architecture

### Layers

```
[Portal home page]
  └─ <UsagePortrait> component (lazy fetch on mount)
       └─ GET /portrait/me (admin service, auth: dev session token)
            ├─ check usage_portraits table for current ISO week
            ├─ if cached → return base64 PNG + scene_data JSON
            └─ if missing →
                 ├─ query cost_records (past 7 days, this developer)
                 ├─ compute scene description (rule-based Python)
                 ├─ POST litellm /v1/images/generations (dall-e-3, 1024×1024)
                 ├─ store PNG bytes + scene_data in usage_portraits
                 └─ return base64 PNG + scene_data JSON
```

DALL-E 3 is added to the litellm model list as `dall-e-3` via the existing Azure OpenAI credentials (`AZURE_API_BASE` / `AZURE_API_KEY` / `AZURE_API_VERSION`). This routes the image-gen call through the gateway — the feature is self-demonstrating.

### Data model

New table `usage_portraits`:

| Column | Type | Notes |
|---|---|---|
| `developer_id` | `UUID NOT NULL` | FK → `developers(id) ON DELETE CASCADE` |
| `week_start` | `DATE NOT NULL` | ISO Monday for the week (Monday=1) |
| `scene_prompt` | `TEXT NOT NULL` | Full DALL-E prompt for auditing |
| `scene_data` | `JSONB NOT NULL DEFAULT '{}'` | `{creature, atmosphere, machinery, time, scale}` each with `{name, reason}` (season deferred to v2) |
| `image_data` | `BYTEA NOT NULL` | Raw PNG bytes from DALL-E |
| `generated_at` | `TIMESTAMPTZ NOT NULL DEFAULT NOW()` | |

Primary key: `(developer_id, week_start)`. Storage is bounded: one PNG per developer per week, old weeks are overwritten on regenerate and cleaned up by a future maintenance job (out of scope for v1).

### Scene description rules

All signals come from `cost_records` WHERE `developer_id = $1 AND created_at >= NOW() - INTERVAL '7 days'`.

| Signal | Derived from | → Illustration element |
|---|---|---|
| `top_model` | `model` with highest `COUNT(*)` | Creature: Sonnet→songbird, Opus→owl, Haiku→hummingbird, GPT-4→raven, others→heron |
| `cache_hit_pct` | `AVG(cache_hit::int)` | Atmosphere: ≥50%→clear morning light, <50%→dense fog |
| `tool_ratio` | `COUNT(*) FILTER (WHERE tool_invocation_count > 0)` / `COUNT(*)` — fraction of requests that used any tool (0.0–1.0) | Machinery: ≥0.3→clockwork gears and instruments in the scene, else none |
| `peak_hour` | `EXTRACT(hour FROM created_at)` mode | Time: 0–6→moonlit, 7–11→dawn, 12–17→afternoon, 18–23→dusk |
| `request_count` | `COUNT(*)` | Scale: ≥100→dense ancient forest, ≥20→forest clearing, else→single tree |
| `budget_efficiency` | `(budget_usd - spent_usd) / budget_usd` (or 1.0 if no budget) | Season: ≥0.5→spring bloom, ≥0.0→late summer, <0.0→scorched summer *(v2 — not implemented in v1)* |

Final prompt template:
```
{scale}, {creature} perched{machinery}, {atmosphere}, {time},
fine-line ink drawing, botanical illustration, monochromatic, high detail
```

If a developer has no usage data (new user), the portrait endpoint returns `404` and the component shows nothing.

### API

**`GET /portrait/me`** — developer auth required

Success (200):
```json
{
  "image_base64": "<base64-encoded PNG>",
  "mime": "image/png",
  "week_start": "2026-06-23",
  "scene_data": {
    "creature": {"name": "owl", "reason": "Most-used model: claude-opus-4-7"},
    "atmosphere": {"name": "dense fog", "reason": "Cache hit rate: 31%"},
    "machinery": {"name": "clockwork gears", "reason": "High tool-call usage"},
    "time": {"name": "moonlit scene", "reason": "Peak usage: 01:00–04:00"},
    "scale": {"name": "dense ancient forest", "reason": "142 requests this week"}
  }
}
```

No-data (404): developer has no `cost_records` in the past 7 days.

Generation error (502): DALL-E call failed — component handles silently (no portrait shown).

### litellm config addition

```yaml
- model_name: dall-e-3
  litellm_params:
    model: azure/dall-e-3
    api_base: os.environ/AZURE_API_BASE
    api_key: os.environ/AZURE_API_KEY
    api_version: "2024-02-01"  # DALL-E 3 requires 2024-02-01+
```

## Portal component

`<UsagePortrait>` is a client component placed below the welcome hero on the portal home, visible only to returning users (same `!firstRun` gate as the stat strip). It loads lazily after mount.

**States:**
- **Loading:** card skeleton (no layout shift — fixed height 240px)
- **No data (404):** component renders nothing (`null`)
- **Error (other):** component renders nothing
- **Success:** portrait image + "What does this mean?" toggle that expands a panel listing each scene element and its reason

**Layout:**
```
┌─────────────────────────────────────────────────────────┐
│ Your usage portrait           this week · ink sketch    │
├─────────────────────────────────────────────────────────┤
│  [1024×1024 image, displayed at 100% width, max 480px]  │
│                                                         │
│  ▸ What does this mean?                                 │
└─────────────────────────────────────────────────────────┘
```

Expanded explanation:
```
│  ▾ What does this mean?                                 │
│    🦉 Owl         Most-used model: claude-opus-4-7      │
│    🌫 Dense fog   Cache hit rate: 31%                   │
│    ⚙ Gears       High tool-call usage                  │
│    🌙 Moonlit     Peak usage: 01:00–04:00               │
│    🌳 Dense       142 requests this week                │
│    🌸 Spring      Using 68% of budget                   │
```

The component fetches with the dev-session `Authorization: Bearer <token>` header (same pattern as the existing insights fetch).

## Error handling

- DALL-E 3 call fails → endpoint returns 502; component silently hides (no error message shown to user — portrait is a delight feature, not a critical path)
- No Azure DALL-E deployment → same 502 path
- DB write fails after successful generation → return the image anyway; next week will regenerate
- Generation timeout (>60s) → `httpx.TimeoutException` → 502

## Out of scope (v1)

- Style picker (ink sketch is hardcoded)
- Regenerate button
- Team-level portrait
- Background pre-generation worker
- Image expiry / cleanup job

## Migration

`services/admin/migrations/versions/0036_portrait_cache.py`

## Files changed

| File | Change |
|---|---|
| `services/admin/migrations/versions/0036_portrait_cache.py` | New migration |
| `services/admin/app/routers/portrait.py` | New router |
| `services/admin/app/main.py` | Register portrait router |
| `services/litellm/config.yaml` | Add `dall-e-3` model |
| `apps/portal/app/(app)/page.tsx` | Import + render `<UsagePortrait>` |
| `apps/portal/app/(app)/_components/UsagePortrait.tsx` | New component |
