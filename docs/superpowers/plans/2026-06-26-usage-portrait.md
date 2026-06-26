# Usage Portrait Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a weekly AI-generated ink-style illustration to the developer portal home page that reflects each developer's last-7-days gateway usage patterns.

**Architecture:** On-demand generation — `GET /portrait/me` in the admin service checks Postgres for a cached portrait for the current ISO week; if missing, assembles a scene description from `cost_records`, calls DALL-E 3 via litellm with `response_format: b64_json`, and stores the raw PNG bytes. The portal renders the base64 image lazily after the page loads.

**Tech Stack:** FastAPI (admin service), SQLAlchemy/asyncpg, httpx, Alembic, Next.js 14 (portal), TypeScript

## Global Constraints

- Admin service tests run from `services/admin/`: `pytest tests/ -v`
- No `tests/__init__.py` in the test directory
- Use `op.execute(text(...))` for raw SQL in migrations (not `op.create_table`)
- Portal home uses inline style objects (no Tailwind); CSS classes from `@aigw/ui` (`card`, `card__head`, `card__title`, `card__sub`, `card__body`, `Skeleton`)
- Developer ID for DB queries: `developer["user_id"]` from `_get_current_developer` dependency
- litellm is called via `settings.litellm_url` + path, with `Authorization: Bearer {settings.litellm_master_key}`
- DALL-E 3 image request body: `{"model": "dall-e-3", "prompt": "...", "n": 1, "size": "1024x1024", "quality": "standard", "response_format": "b64_json"}`
- DALL-E 3 response: `data[0]["b64_json"]` (base64 PNG, no second download needed)
- Week start: `date.today() - timedelta(days=date.today().weekday())` (ISO Monday)

---

## Task 1: Add DALL-E 3 to litellm config

**Files:**
- Modify: `services/litellm/config.yaml`

**Interfaces:**
- Produces: `dall-e-3` available at `POST {litellm_url}/v1/images/generations`

- [ ] **Step 1: Add the model entry**

In `services/litellm/config.yaml`, add the following entry to `model_list` after the existing Azure OpenAI models (after `azure-gpt-4.1`):

```yaml
  # ── Azure OpenAI — Image generation ─────────────────────────────────────────
  - model_name: dall-e-3
    litellm_params:
      model: azure/dall-e-3
      api_base: os.environ/AZURE_API_BASE
      api_key: os.environ/AZURE_API_KEY
      api_version: os.environ/AZURE_API_VERSION
```

- [ ] **Step 2: Commit**

```bash
git add services/litellm/config.yaml
git commit -m "feat(litellm): add dall-e-3 model via Azure OpenAI"
```

---

## Task 2: DB migration — usage_portraits table

**Files:**
- Create: `services/admin/migrations/versions/0036_portrait_cache.py`

**Interfaces:**
- Produces: table `usage_portraits(developer_id UUID, week_start DATE, scene_prompt TEXT, scene_data JSONB, image_data BYTEA, generated_at TIMESTAMPTZ)` with PK `(developer_id, week_start)`

- [ ] **Step 1: Create the migration file**

Create `services/admin/migrations/versions/0036_portrait_cache.py`:

```python
"""Usage portrait cache — stores weekly AI-generated developer illustrations.

Revision ID: 0036
Revises: 0035
Create Date: 2026-06-26
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS usage_portraits (
            developer_id  UUID        NOT NULL REFERENCES developers(id) ON DELETE CASCADE,
            week_start    DATE        NOT NULL,
            scene_prompt  TEXT        NOT NULL,
            scene_data    JSONB       NOT NULL DEFAULT '{}',
            image_data    BYTEA       NOT NULL,
            generated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (developer_id, week_start)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_usage_portraits_developer "
        "ON usage_portraits(developer_id, week_start DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS usage_portraits")
```

- [ ] **Step 2: Verify the migration parses correctly**

```bash
cd services/admin && python -c "from migrations.versions import v0036_portrait_cache" 2>/dev/null || python -c "import importlib.util; s=importlib.util.spec_from_file_location('m','migrations/versions/0036_portrait_cache.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print('ok')"
```

Expected: `ok` (no import errors)

- [ ] **Step 3: Commit**

```bash
git add services/admin/migrations/versions/0036_portrait_cache.py
git commit -m "feat(admin/db): add usage_portraits table (migration 0036)"
```

---

## Task 3: Scene assembly + portrait router

**Files:**
- Create: `services/admin/app/routers/portrait.py`
- Create: `services/admin/tests/test_portrait.py`

**Interfaces:**
- Consumes: `_get_current_developer` from `app.routers.dev_auth`, `get_session` from `app.db`, `settings` from `app.config`
- Produces:
  - `_build_scene(stats: dict) -> tuple[str, dict]` — pure function, testable
  - `router` — FastAPI APIRouter with prefix `/portrait`, tag `portrait`
  - `GET /portrait/me` → `{"image_base64": str, "mime": "image/png", "week_start": str, "scene_data": dict}` or 404

- [ ] **Step 1: Write the failing unit test first**

Create `services/admin/tests/test_portrait.py`:

```python
"""Tests for usage portrait generation."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Pure unit tests for _build_scene
# ---------------------------------------------------------------------------


def test_build_scene_opus_foggy_tools():
    from app.routers.portrait import _build_scene

    stats = {
        "top_model": "claude-opus-4-7",
        "cache_hit_pct": 0.25,   # below 0.5 → fog
        "tool_ratio": 0.5,       # above 0.3 → gears
        "peak_hour": 2,          # 0-6 → moonlit
        "request_count": 120,    # ≥100 → dense forest
    }
    prompt, scene_data = _build_scene(stats)

    assert "owl" in prompt
    assert "fog" in prompt
    assert "gear" in prompt
    assert "moonlit" in prompt
    assert "dense" in prompt
    assert len(scene_data) == 5
    for key in ("creature", "atmosphere", "machinery", "time", "scale"):
        assert key in scene_data
        assert "name" in scene_data[key]
        assert "reason" in scene_data[key]


def test_build_scene_sonnet_clear_no_tools():
    from app.routers.portrait import _build_scene

    stats = {
        "top_model": "claude-sonnet-4-6",
        "cache_hit_pct": 0.72,   # ≥ 0.5 → clear morning light
        "tool_ratio": 0.0,       # < 0.3 → no machinery
        "peak_hour": 10,         # 7-11 → dawn
        "request_count": 15,     # < 20 → single tree
    }
    prompt, scene_data = _build_scene(stats)

    assert "songbird" in prompt
    assert "morning" in prompt
    assert "gear" not in prompt
    assert "dawn" in prompt
    assert "single tree" in prompt


def test_build_scene_unknown_model_uses_default():
    from app.routers.portrait import _build_scene

    stats = {
        "top_model": "some-unknown-model",
        "cache_hit_pct": 0.5,
        "tool_ratio": 0.0,
        "peak_hour": 14,
        "request_count": 50,
    }
    prompt, scene_data = _build_scene(stats)
    assert "heron" in prompt


# ---------------------------------------------------------------------------
# Endpoint: 404 when developer has no cost_records
# ---------------------------------------------------------------------------


@pytest.fixture
async def portrait_client_no_data():
    from app.db import get_session
    from app.main import app
    from app.routers.dev_auth import _get_current_developer

    dev_id = str(uuid.uuid4())

    async def fake_developer():
        return {"user_id": dev_id, "email": "dev@example.com", "developer_id": dev_id}

    fake_session = AsyncMock()
    # portrait cache miss: first execute (cache lookup) returns no row
    # usage stats query: second execute returns a row with request_count = 0
    no_row = MagicMock()
    no_row.mappings.return_value.first.return_value = None

    zero_stats = MagicMock()
    mapping = MagicMock()
    mapping.__getitem__ = lambda self, k: {"top_model": None, "cache_hit_pct": None,
                                            "tool_ratio": None, "peak_hour": None,
                                            "request_count": 0}[k]
    zero_stats.mappings.return_value.one.return_value = mapping

    fake_session.execute = AsyncMock(side_effect=[no_row, zero_stats])

    async def override_session():
        yield fake_session

    app.dependency_overrides[_get_current_developer] = fake_developer
    app.dependency_overrides[get_session] = override_session
    app.state.redis = AsyncMock()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_portrait_me_returns_404_when_no_usage(portrait_client_no_data):
    resp = await portrait_client_no_data.get("/portrait/me")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to confirm they fail (module not found)**

```bash
cd services/admin && pytest tests/test_portrait.py -v 2>&1 | head -20
```

Expected: `ImportError` or `ModuleNotFoundError: No module named 'app.routers.portrait'`

- [ ] **Step 3: Implement portrait.py**

Create `services/admin/app/routers/portrait.py`:

```python
"""Developer usage portrait — AI-generated weekly illustration from usage telemetry."""

import base64
import logging
from datetime import date, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.routers.dev_auth import _get_current_developer

log = logging.getLogger(__name__)

router = APIRouter(prefix="/portrait", tags=["portrait"])

_CREATURE_MAP: dict[str, tuple[str, str]] = {
    "claude-sonnet-4-6": ("a songbird", "🐦"),
    "claude-opus-4-7": ("an owl", "🦉"),
    "claude-haiku-4-5": ("a hummingbird", "🦜"),
    "github-gpt-4o": ("a raven", "🐦‍⬛"),
    "gemini-1.5-pro": ("a peacock", "🦚"),
}
_DEFAULT_CREATURE: tuple[str, str] = ("a heron", "🦢")

_HOUR_BUCKETS = [
    (range(0, 7),  "moonlit scene",      "peak usage in late-night hours"),
    (range(7, 12), "dawn light",         "peak usage in morning hours"),
    (range(12, 18), "afternoon light",   "peak usage in afternoon hours"),
    (range(18, 24), "dusk",             "peak usage in evening hours"),
]


def _build_scene(stats: dict) -> tuple[str, dict]:
    """Assemble a DALL-E prompt and explanation from usage telemetry.

    Args:
        stats: dict with keys top_model, cache_hit_pct, tool_ratio, peak_hour,
               request_count. Values may be None if the developer has no usage.

    Returns:
        (prompt_str, scene_data_dict) where scene_data has keys:
        creature, atmosphere, machinery, time, scale
    """
    top_model: str | None = stats.get("top_model")
    cache_hit_pct: float = float(stats.get("cache_hit_pct") or 0.0)
    tool_ratio: float = float(stats.get("tool_ratio") or 0.0)
    peak_hour: int = int(stats.get("peak_hour") or 12)
    request_count: int = int(stats.get("request_count") or 0)

    creature_name, creature_emoji = _CREATURE_MAP.get(top_model or "", _DEFAULT_CREATURE)
    creature_reason = f"Most-used model: {top_model}" if top_model else "Default"

    atmosphere = "clear morning light" if cache_hit_pct >= 0.5 else "dense fog"
    atmosphere_reason = f"Cache hit rate: {cache_hit_pct:.0%}"

    if tool_ratio >= 0.3:
        machinery = ", clockwork gears and instruments nearby"
        machinery_name = "clockwork gears"
        machinery_reason = f"High tool-call usage ({tool_ratio:.0%} of requests used tools)"
    else:
        machinery = ""
        machinery_name = "none"
        machinery_reason = f"Low tool-call usage ({tool_ratio:.0%} of requests used tools)"

    time_name, time_reason = "afternoon light", "peak usage in afternoon hours"
    for hour_range, t_name, t_reason in _HOUR_BUCKETS:
        if peak_hour in hour_range:
            time_name, time_reason = t_name, t_reason
            break

    if request_count >= 100:
        scale = "a dense ancient forest"
        scale_reason = f"{request_count} requests this week"
    elif request_count >= 20:
        scale = "a forest clearing"
        scale_reason = f"{request_count} requests this week"
    else:
        scale = "a single ancient tree"
        scale_reason = f"{request_count} requests this week"

    prompt = (
        f"{scale}, {creature_name} perched{machinery}, {atmosphere}, "
        f"{time_name}, fine-line ink drawing, botanical illustration, "
        f"monochromatic, high detail"
    )

    scene_data = {
        "creature":    {"name": creature_name,   "emoji": creature_emoji,  "reason": creature_reason},
        "atmosphere":  {"name": atmosphere,       "emoji": "🌫" if "fog" in atmosphere else "☀️", "reason": atmosphere_reason},
        "machinery":   {"name": machinery_name,   "emoji": "⚙️",            "reason": machinery_reason},
        "time":        {"name": time_name,        "emoji": "🌙" if "moonlit" in time_name else "⏰", "reason": time_reason},
        "scale":       {"name": scale,            "emoji": "🌲",            "reason": scale_reason},
    }
    return prompt, scene_data


async def _fetch_usage_stats(session: AsyncSession, developer_id: str) -> dict:
    row = (
        await session.execute(
            text("""
                SELECT
                    mode() WITHIN GROUP (ORDER BY model)                           AS top_model,
                    AVG(cache_hit::int)                                            AS cache_hit_pct,
                    SUM(tool_invocation_count)::float / NULLIF(COUNT(*), 0)        AS tool_ratio,
                    mode() WITHIN GROUP (ORDER BY EXTRACT(hour FROM created_at))   AS peak_hour,
                    COUNT(*)                                                        AS request_count
                FROM cost_records
                WHERE developer_id = CAST(:dev_id AS uuid)
                  AND created_at >= NOW() - INTERVAL '7 days'
            """),
            {"dev_id": developer_id},
        )
    ).mappings().one()
    return dict(row)


async def _generate_image(prompt: str) -> bytes:
    """Call litellm /v1/images/generations and return raw PNG bytes."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{settings.litellm_url}/v1/images/generations",
            json={
                "model": "dall-e-3",
                "prompt": prompt,
                "n": 1,
                "size": "1024x1024",
                "quality": "standard",
                "response_format": "b64_json",
            },
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
        )
    if resp.status_code != 200:
        log.error("DALL-E 3 generation failed: %s %s", resp.status_code, resp.text[:200])
        raise HTTPException(status_code=502, detail="Image generation failed")
    b64 = resp.json()["data"][0]["b64_json"]
    return base64.b64decode(b64)


@router.get("/me")
async def get_my_portrait(
    session: AsyncSession = Depends(get_session),
    developer: dict = Depends(_get_current_developer),
):
    """Return this week's usage portrait for the current developer.

    Generated on first call of the week; cached for subsequent calls.
    Returns 404 if the developer has no usage data in the past 7 days.
    """
    developer_id: str = developer["user_id"]
    week_start: date = date.today() - timedelta(days=date.today().weekday())

    # Check cache
    cached = (
        await session.execute(
            text("""
                SELECT scene_data, image_data
                FROM usage_portraits
                WHERE developer_id = CAST(:dev_id AS uuid) AND week_start = :week
            """),
            {"dev_id": developer_id, "week": week_start},
        )
    ).mappings().first()

    if cached:
        return {
            "image_base64": base64.b64encode(bytes(cached["image_data"])).decode(),
            "mime": "image/png",
            "week_start": week_start.isoformat(),
            "scene_data": cached["scene_data"],
        }

    # Fetch usage stats
    stats = await _fetch_usage_stats(session, developer_id)
    if not stats.get("request_count"):
        raise HTTPException(status_code=404, detail="No usage data available for portrait")

    # Build scene and generate image
    prompt, scene_data = _build_scene(stats)
    image_bytes = await _generate_image(prompt)

    # Store in DB
    await session.execute(
        text("""
            INSERT INTO usage_portraits (developer_id, week_start, scene_prompt, scene_data, image_data)
            VALUES (CAST(:dev_id AS uuid), :week, :prompt, CAST(:scene AS jsonb), :image)
            ON CONFLICT (developer_id, week_start) DO UPDATE
                SET scene_prompt = EXCLUDED.scene_prompt,
                    scene_data   = EXCLUDED.scene_data,
                    image_data   = EXCLUDED.image_data,
                    generated_at = NOW()
        """),
        {
            "dev_id": developer_id,
            "week": week_start,
            "prompt": prompt,
            "scene": __import__("json").dumps(scene_data),
            "image": image_bytes,
        },
    )
    await session.commit()

    return {
        "image_base64": base64.b64encode(image_bytes).decode(),
        "mime": "image/png",
        "week_start": week_start.isoformat(),
        "scene_data": scene_data,
    }
```

- [ ] **Step 4: Run the tests**

```bash
cd services/admin && pytest tests/test_portrait.py -v
```

Expected output: all 4 tests pass:
```
tests/test_portrait.py::test_build_scene_opus_foggy_tools PASSED
tests/test_portrait.py::test_build_scene_sonnet_clear_no_tools PASSED
tests/test_portrait.py::test_build_scene_unknown_model_uses_default PASSED
tests/test_portrait.py::test_portrait_me_returns_404_when_no_usage PASSED
```

- [ ] **Step 5: Commit**

```bash
git add services/admin/app/routers/portrait.py services/admin/tests/test_portrait.py
git commit -m "feat(admin): usage portrait router — _build_scene + GET /portrait/me"
```

---

## Task 4: Register portrait router in main.py

**Files:**
- Modify: `services/admin/app/main.py`

**Interfaces:**
- Consumes: `portrait.router` from `app.routers.portrait`
- Produces: `GET /portrait/me` reachable at `http://admin:8005/portrait/me` with dev session auth

- [ ] **Step 1: Add the import**

In `services/admin/app/main.py`, find the `insights as insights_router` import block (around line 92). Add the portrait import in the same alphabetical section:

```python
from app.routers import (
    portrait as portrait_router,
)
```

Place it after the `portrait` comes alphabetically (between `policies` and `pricing`-ish — just keep the imports sorted).

- [ ] **Step 2: Register the router**

Near line 613 in `main.py`, where `insights_router.router` is registered with its own auth comment, add:

```python
app.include_router(portrait_router.router)  # own auth: dev session
```

Place it on the line after `insights_router.router`:
```python
app.include_router(insights_router.router)  # own auth per endpoint (admin or dev session)
app.include_router(portrait_router.router)  # own auth: dev session
```

- [ ] **Step 3: Run the existing admin test suite to ensure no regressions**

```bash
cd services/admin && pytest tests/test_admin.py tests/test_api_keys.py -v 2>&1 | tail -10
```

Expected: all tests pass (no import errors from the new router).

- [ ] **Step 4: Also run the portrait tests**

```bash
cd services/admin && pytest tests/test_portrait.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add services/admin/app/main.py
git commit -m "feat(admin): register portrait router"
```

---

## Task 5: Portal — UsagePortrait component

**Files:**
- Create: `apps/portal/app/(app)/_components/UsagePortrait.tsx`

**Interfaces:**
- Consumes: `useAuth()` from `../_lib/authContext` (for `token`), `ADMIN_BASE` constant already defined in `page.tsx` (copy it), `Skeleton` from `@aigw/ui`
- Produces: `<UsagePortrait />` default export — renders nothing on no-data or error, renders a card with portrait image + explanation panel on success

- [ ] **Step 1: Create the component**

Create `apps/portal/app/(app)/_components/UsagePortrait.tsx`:

```tsx
"use client";

import { useState, useEffect } from "react";
import { Skeleton } from "@aigw/ui";
import { useAuth } from "../_lib/authContext";

const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? "http://localhost:8005";

interface SceneElement {
  name: string;
  emoji: string;
  reason: string;
}

interface PortraitData {
  image_base64: string;
  mime: string;
  week_start: string;
  scene_data: Record<string, SceneElement>;
}

export default function UsagePortrait() {
  const { token } = useAuth();
  const [data, setData] = useState<PortraitData | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!token) { setLoading(false); return; }
    fetch(`${ADMIN_BASE}/portrait/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => (r.ok ? r.json() : null))
      .then((d: PortraitData | null) => setData(d))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [token]);

  if (!loading && !data) return null;

  return (
    <div className="card" style={{ marginBottom: 14 }}>
      <div className="card__head">
        <h3 className="card__title">Your usage portrait</h3>
        <span className="card__sub">
          {data ? `week of ${data.week_start} · ink sketch` : "generating…"}
        </span>
      </div>
      <div className="card__body">
        {loading ? (
          <Skeleton width="100%" height={240} style={{ borderRadius: "var(--r-2)" }} />
        ) : data ? (
          <>
            <img
              src={`data:${data.mime};base64,${data.image_base64}`}
              alt="Your AI usage portrait"
              style={{
                width: "100%",
                maxWidth: 480,
                borderRadius: "var(--r-2)",
                display: "block",
              }}
            />
            <div style={{ marginTop: 12 }}>
              <button
                className="btn btn--ghost btn--sm"
                onClick={() => setOpen(o => !o)}
                style={{ fontSize: 12.5 }}
              >
                {open ? "▾" : "▸"} What does this mean?
              </button>
              {open && (
                <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 5 }}>
                  {Object.entries(data.scene_data).map(([, el]) => (
                    <div key={el.name} style={{ display: "flex", gap: 10, fontSize: 12.5 }}>
                      <span style={{ width: 20, textAlign: "center", flexShrink: 0 }}>{el.emoji}</span>
                      <span style={{ fontWeight: 500, color: "var(--fg-1)", minWidth: 120 }}>{el.name}</span>
                      <span className="muted">{el.reason}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd apps/portal && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors (or only pre-existing ones unrelated to UsagePortrait.tsx).

- [ ] **Step 3: Commit**

```bash
git add "apps/portal/app/(app)/_components/UsagePortrait.tsx"
git commit -m "feat(portal): add UsagePortrait component"
```

---

## Task 6: Wire UsagePortrait into portal home page

**Files:**
- Modify: `apps/portal/app/(app)/page.tsx`

**Interfaces:**
- Consumes: `UsagePortrait` default export from `./_components/UsagePortrait`
- Produces: Portrait card rendered below the hero, above the stat strip, for returning users only

- [ ] **Step 1: Add the import**

At the top of `apps/portal/app/(app)/page.tsx`, after the existing imports, add:

```tsx
import UsagePortrait from "./_components/UsagePortrait";
```

- [ ] **Step 2: Add the component to the JSX**

Find the stat strip section in `page.tsx` (around line 289):

```tsx
      {/* Stat strip — returning users */}
      {!firstRun && (
        <div className="stat-strip">
```

Insert the `<UsagePortrait />` block immediately before that comment, gated on the same `!firstRun` condition:

```tsx
      {/* Usage portrait — returning users only */}
      {!firstRun && <UsagePortrait />}

      {/* Stat strip — returning users */}
      {!firstRun && (
        <div className="stat-strip">
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd apps/portal && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 4: Run the portal frontend tests**

```bash
cd apps/portal && npx vitest run 2>&1 | tail -10
```

Expected: all tests pass (no regressions from the import).

- [ ] **Step 5: Commit**

```bash
git add "apps/portal/app/(app)/page.tsx"
git commit -m "feat(portal): render UsagePortrait on home page for returning users"
```

---

## Task 7: Run full admin test suite and lint

**Files:** none (verification only)

- [ ] **Step 1: Run all admin tests**

```bash
cd services/admin && pytest tests/ -v 2>&1 | tail -20
```

Expected: all tests pass. Fix any failures before proceeding.

- [ ] **Step 2: Run ruff**

```bash
ruff check services/admin/app/routers/portrait.py services/admin/tests/test_portrait.py
ruff format services/admin/app/routers/portrait.py services/admin/tests/test_portrait.py
```

Expected: no errors. If `ruff format` makes changes, commit them:

```bash
git add services/admin/app/routers/portrait.py services/admin/tests/test_portrait.py
git commit -m "style: ruff format portrait files"
```

- [ ] **Step 3: Confirm all six files changed**

```bash
git log --oneline -8
```

Expected: at least these commits visible:
- `feat(litellm): add dall-e-3 model via Azure OpenAI`
- `feat(admin/db): add usage_portraits table (migration 0036)`
- `feat(admin): usage portrait router — _build_scene + GET /portrait/me`
- `feat(admin): register portrait router`
- `feat(portal): add UsagePortrait component`
- `feat(portal): render UsagePortrait on home page for returning users`

---

## Self-Review

**Spec coverage check:**

| Spec section | Task |
|---|---|
| Add dall-e-3 to litellm | Task 1 |
| usage_portraits DB table | Task 2 |
| Scene description rules (all 5 signals) | Task 3, `_build_scene` |
| GET /portrait/me, cache check, 404, 502 | Task 3, `get_my_portrait` |
| Register router (own dev session auth) | Task 4 |
| UsagePortrait component (lazy, skeleton, expand panel) | Task 5 |
| Render on portal home, !firstRun gate | Task 6 |
| Tests: _build_scene pure unit, 404 on no data | Task 3 |

**Placeholder scan:** No TBD or TODO. All SQL, TypeScript, and Python is complete.

**Type consistency:**
- `_build_scene(stats: dict) -> tuple[str, dict]` — used in Task 3 tests and implementation consistently
- `developer["user_id"]` — confirmed from `dev_auth.py` pattern; used in Task 3 and tested in Task 3 fixture
- `PortraitData.scene_data` is `Record<string, SceneElement>` — `scene_data` returned from `_build_scene` matches this shape (each key has `name`, `emoji`, `reason`)
- `ADMIN_BASE` is independently defined in `UsagePortrait.tsx` (same pattern as `page.tsx` which also defines it as a module-level constant)
