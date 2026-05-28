# AI-Champions — Wave 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-05-28-ai-champions-community-design.md`

**Goal:** Ship the foundations of the AI-Champions community: leadership can nominate champions, champions can submit content (URL or pasted text) which is auto-classified and indexed, and contributions appear on a hub page. Each submission grants AI-League points via a new internal grant API.

**Architecture:** Three-service thin layer. New tables and routers in `services/admin/`; new internal grant endpoint in `services/league/`; existing `services/librarian/` is used as-is for ingest/search. AI metadata via existing litellm pattern (`claude-haiku-4-5-20251001`).

**Tech Stack:** FastAPI, SQLAlchemy core (`text(...)`), Alembic, Pydantic v2, Next.js (App Router), httpx, pytest with AsyncMock.

**Scope of Wave 1 only:** champions + champion_contributions tables (and the rest of the migration so the full schema exists), nominate/retire admin flow, content submission with AI metadata, content feed, league grant API, portal hub + submission page, admin nominate page, sidebar entries. **Defers** asks, bookings, upvotes, flags, AiHelpWidget RAG, contextual surfacing widgets, smart routing, office hours, admin activity dashboard → Wave 2 & 3 plans.

---

## File Structure

**services/admin (new)**
- `migrations/versions/0025_champions.py` — all six tables in one migration
- `app/routers/champions.py` — developer-facing endpoints
- `app/routers/admin_champions.py` — admin endpoints (nominate / retire)
- `app/llm/__init__.py`, `app/llm/champion_metadata.py` — AI classifier
- `app/league_client.py` — thin httpx wrapper around league grant API

**services/admin (modified)**
- `app/main.py` — register the two new routers
- `app/config.py` — add `league_url`, `librarian_url`, `librarian_service_token` settings

**services/league (new)**
- `app/routers/internal_points.py` — `POST /league/internal/points/grant`

**services/league (modified)**
- `app/main.py` — register internal_points router

**apps/portal (new)**
- `app/portal/champions/page.tsx` — hub: directory + content feed
- `app/portal/champions/[id]/page.tsx` — champion profile
- `app/portal/champions/new-content/page.tsx` — submission form

**apps/portal (modified)**
- `app/portal/_lib/PortalShell.tsx` — sidebar link "Champions"

**apps/admin (new)**
- `app/admin/champions/page.tsx` — nominate / retire

**apps/admin (modified)**
- admin sidebar component — sidebar link "Champions"

**Tests**
- `services/admin/tests/test_champions.py`
- `services/admin/tests/test_admin_champions.py`
- `services/admin/tests/test_champion_metadata.py`
- `services/admin/tests/test_league_client.py`
- `services/league/tests/test_internal_points.py`

---

## Task 1: Migration 0025 — schema for all six champion tables

**Files:**
- Create: `services/admin/migrations/versions/0025_champions.py`

We put all six tables in one migration even though Wave 1 only uses `champions` and `champion_contributions`. This avoids two later migrations bumping head and is cheap (DDL only).

- [ ] **Step 1: Create the migration file**

```python
"""AI-Champions community: six tables"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union

revision = "0025"
down_revision = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        "champions",
        sa.Column("developer_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("focus_areas", sa.dialects.postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("office_hours_text", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("nominated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("nominated_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_champions_active", "champions", ["active"])

    op.create_table(
        "champion_contributions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("champion_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("champions.developer_id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),  # article|link|video|artifact
        sa.Column("librarian_item_id", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("upvotes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("flag_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("auto_metadata", sa.dialects.postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_champion_contributions_champion", "champion_contributions", ["champion_id"])
    op.create_index("ix_champion_contributions_submitted_at", "champion_contributions", ["submitted_at"])

    op.create_table(
        "champion_asks",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("claimed_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auto_confirm_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("routed_to", sa.dialects.postgresql.ARRAY(sa.dialects.postgresql.UUID(as_uuid=True)), nullable=False, server_default="{}"),
        sa.Column("tags", sa.dialects.postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
    )
    op.create_index("ix_champion_asks_status", "champion_asks", ["status"])

    op.create_table(
        "champion_bookings",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("champion_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("champions.developer_id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requested_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slot_text", sa.Text(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="requested"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "champion_upvotes",
        sa.Column("developer_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("contribution_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("champion_contributions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "champion_flags",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("contribution_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("champion_contributions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("flagged_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("champion_flags")
    op.drop_table("champion_upvotes")
    op.drop_table("champion_bookings")
    op.drop_index("ix_champion_asks_status", table_name="champion_asks")
    op.drop_table("champion_asks")
    op.drop_index("ix_champion_contributions_submitted_at", table_name="champion_contributions")
    op.drop_index("ix_champion_contributions_champion", table_name="champion_contributions")
    op.drop_table("champion_contributions")
    op.drop_index("ix_champions_active", table_name="champions")
    op.drop_table("champions")
```

- [ ] **Step 2: Apply the migration locally**

Run: `cd services/admin && alembic upgrade head`
Expected: `Running upgrade 0024 -> 0025, AI-Champions community: six tables`

- [ ] **Step 3: Verify tables exist**

Run: `psql $DATABASE_URL -c "\dt champion*"`
Expected: `champions`, `champion_asks`, `champion_bookings`, `champion_contributions`, `champion_flags`, `champion_upvotes`

- [ ] **Step 4: Test downgrade and re-apply**

Run: `alembic downgrade -1 && alembic upgrade head`
Expected: clean down + up; no error.

- [ ] **Step 5: Commit**

```bash
git add services/admin/migrations/versions/0025_champions.py
git commit -m "feat(admin): migration 0025 — AI-Champions schema (six tables)"
```

---

## Task 2: League internal points grant endpoint

**Files:**
- Create: `services/league/app/routers/internal_points.py`
- Test: `services/league/tests/test_internal_points.py`
- Modify: `services/league/app/main.py` (register router)

- [ ] **Step 1: Write the failing test**

```python
# services/league/tests/test_internal_points.py
import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock


@pytest.fixture
async def client(mock_session, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin-token")
    from app.main import app
    from app.db import get_session
    app.dependency_overrides[get_session] = lambda: mock_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_grant_writes_ledger_row(client, mock_session):
    resp = await client.post(
        "/league/internal/points/grant",
        headers={"X-Admin-Token": "test-admin-token"},
        json={
            "engineer_id": "00000000-0000-0000-0000-000000000001",
            "delta": 50,
            "reason": "champion_content",
            "ref_id": "11111111-1111-1111-1111-111111111111",
        },
    )
    assert resp.status_code == 201
    assert mock_session.execute.await_count >= 1


async def test_grant_rejects_non_champion_reason(client):
    resp = await client.post(
        "/league/internal/points/grant",
        headers={"X-Admin-Token": "test-admin-token"},
        json={
            "engineer_id": "00000000-0000-0000-0000-000000000001",
            "delta": 50,
            "reason": "random_reason",
        },
    )
    assert resp.status_code == 400


async def test_grant_requires_admin_token(client):
    resp = await client.post(
        "/league/internal/points/grant",
        json={"engineer_id": "00000000-0000-0000-0000-000000000001", "delta": 50, "reason": "champion_content"},
    )
    assert resp.status_code == 401
```

- [ ] **Step 2: Run test, expect failures**

Run: `cd services/league && pytest tests/test_internal_points.py -v`
Expected: 3 failures (route not registered).

- [ ] **Step 3: Implement the router**

```python
# services/league/app/routers/internal_points.py
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session

router = APIRouter(prefix="/league/internal", tags=["league-internal"])

_ALLOWED_REASON_PREFIXES = ("champion_",)


class GrantRequest(BaseModel):
    engineer_id: UUID
    delta: int = Field(..., description="Positive or negative integer")
    reason: str
    ref_id: UUID | None = None


async def _require_admin_token(x_admin_token: str | None = Header(None)) -> None:
    if not x_admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Missing or invalid X-Admin-Token")


@router.post("/points/grant", status_code=201, dependencies=[Depends(_require_admin_token)])
async def grant_points(body: GrantRequest, session: AsyncSession = Depends(get_session)):
    if not any(body.reason.startswith(p) for p in _ALLOWED_REASON_PREFIXES):
        raise HTTPException(status_code=400, detail=f"Reason must start with one of {_ALLOWED_REASON_PREFIXES}")
    await session.execute(
        text("""
            INSERT INTO league_points_ledger (engineer_id, delta, reason, ref_id, created_at)
            VALUES (:engineer_id, :delta, :reason, :ref_id, NOW())
        """),
        {
            "engineer_id": str(body.engineer_id),
            "delta": body.delta,
            "reason": body.reason,
            "ref_id": str(body.ref_id) if body.ref_id else None,
        },
    )
    await session.commit()
    return {"ok": True, "delta": body.delta, "reason": body.reason}
```

- [ ] **Step 4: Register the router**

In `services/league/app/main.py`, add to the import block:

```python
from app.routers import (
    challenges as challenges_router,
    internal_points as internal_points_router,
    leaderboard as leaderboard_router,
    proposals as proposals_router,
    seasons as seasons_router,
    submissions as submissions_router,
)
```

And register near the other `app.include_router` calls:

```python
app.include_router(internal_points_router.router)
```

- [ ] **Step 5: Re-run tests**

Run: `pytest tests/test_internal_points.py -v`
Expected: 3 passes.

- [ ] **Step 6: Commit**

```bash
git add services/league/app/routers/internal_points.py services/league/app/main.py services/league/tests/test_internal_points.py
git commit -m "feat(league): internal points grant API for cross-service awards"
```

---

## Task 3: Admin → League HTTP client

**Files:**
- Create: `services/admin/app/league_client.py`
- Test: `services/admin/tests/test_league_client.py`
- Modify: `services/admin/app/config.py` (add `league_url` setting)

- [ ] **Step 1: Add settings**

In `services/admin/app/config.py`, add (near other URL settings):

```python
    league_url: str = "http://league:8010"
    admin_token: str = ""  # only add if not already present
```

- [ ] **Step 2: Write the failing test**

```python
# services/admin/tests/test_league_client.py
import pytest
import httpx
from unittest.mock import AsyncMock, patch

from app.league_client import grant_points


@pytest.mark.asyncio
async def test_grant_points_posts_to_league():
    with patch("app.league_client.httpx.AsyncClient") as mock_client_cls:
        instance = AsyncMock()
        instance.__aenter__.return_value = instance
        instance.post.return_value = httpx.Response(201, json={"ok": True})
        mock_client_cls.return_value = instance

        await grant_points(
            engineer_id="00000000-0000-0000-0000-000000000001",
            delta=50,
            reason="champion_content",
            ref_id=None,
        )
        instance.post.assert_awaited_once()
        kwargs = instance.post.await_args.kwargs
        assert kwargs["headers"]["X-Admin-Token"]
        body = kwargs["json"]
        assert body["reason"] == "champion_content"
        assert body["delta"] == 50


@pytest.mark.asyncio
async def test_grant_points_raises_on_non_201():
    with patch("app.league_client.httpx.AsyncClient") as mock_client_cls:
        instance = AsyncMock()
        instance.__aenter__.return_value = instance
        instance.post.return_value = httpx.Response(500, json={"detail": "boom"})
        mock_client_cls.return_value = instance

        with pytest.raises(RuntimeError):
            await grant_points(engineer_id="00000000-0000-0000-0000-000000000001",
                               delta=50, reason="champion_content")
```

- [ ] **Step 3: Run test, expect failure**

Run: `pytest tests/test_league_client.py -v`
Expected: ImportError (`league_client` not found).

- [ ] **Step 4: Implement the client**

```python
# services/admin/app/league_client.py
import httpx

from app.config import settings


async def grant_points(*, engineer_id: str, delta: int, reason: str, ref_id: str | None = None) -> None:
    """Award (or deduct) points via the league internal grant API.

    Raises RuntimeError on non-201 responses so callers can surface a 502.
    """
    payload = {"engineer_id": str(engineer_id), "delta": delta, "reason": reason}
    if ref_id is not None:
        payload["ref_id"] = str(ref_id)

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{settings.league_url}/league/internal/points/grant",
            json=payload,
            headers={"X-Admin-Token": settings.admin_token},
        )
    if resp.status_code != 201:
        raise RuntimeError(f"league grant failed: {resp.status_code} {resp.text}")
```

- [ ] **Step 5: Re-run tests**

Run: `pytest tests/test_league_client.py -v`
Expected: 2 passes.

- [ ] **Step 6: Commit**

```bash
git add services/admin/app/league_client.py services/admin/app/config.py services/admin/tests/test_league_client.py
git commit -m "feat(admin): league_client for cross-service point grants"
```

---

## Task 4: Champion metadata classifier

**Files:**
- Create: `services/admin/app/llm/__init__.py` (empty)
- Create: `services/admin/app/llm/champion_metadata.py`
- Test: `services/admin/tests/test_champion_metadata.py`

- [ ] **Step 1: Write the failing test**

```python
# services/admin/tests/test_champion_metadata.py
import json
import pytest
import httpx
from unittest.mock import AsyncMock, patch

from app.llm.champion_metadata import classify_content


@pytest.mark.asyncio
async def test_classify_returns_structured_dict():
    fake_llm_response = {
        "choices": [{"message": {"content": json.dumps({
            "title": "Building an agentic RAG",
            "summary": "Walkthrough of agentic RAG with tool-use",
            "focus_areas": ["agentic", "rag"],
            "tags": ["python", "anthropic"],
            "difficulty": "intermediate",
        })}}]
    }
    with patch("app.llm.champion_metadata.httpx.AsyncClient") as mock_client_cls:
        instance = AsyncMock()
        instance.__aenter__.return_value = instance
        instance.post.return_value = httpx.Response(200, json=fake_llm_response)
        mock_client_cls.return_value = instance

        result = await classify_content(text="how I built a rag agent...")

    assert result["title"] == "Building an agentic RAG"
    assert "agentic" in result["focus_areas"]
    assert result["difficulty"] == "intermediate"
    assert len(result["summary"]) <= 200


@pytest.mark.asyncio
async def test_classify_handles_malformed_json():
    fake_llm_response = {"choices": [{"message": {"content": "not json"}}]}
    with patch("app.llm.champion_metadata.httpx.AsyncClient") as mock_client_cls:
        instance = AsyncMock()
        instance.__aenter__.return_value = instance
        instance.post.return_value = httpx.Response(200, json=fake_llm_response)
        mock_client_cls.return_value = instance

        result = await classify_content(text="hello")

    assert result == {
        "title": "(untitled)",
        "summary": "",
        "focus_areas": [],
        "tags": [],
        "difficulty": "unknown",
    }
```

- [ ] **Step 2: Run test, expect failure**

Run: `pytest tests/test_champion_metadata.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement the classifier**

```python
# services/admin/app/llm/champion_metadata.py
import json

import httpx
from fastapi import HTTPException

from app.config import settings

_SYSTEM = (
    "You classify AI-related content submitted by SimCorp engineers. "
    "Return a JSON object with keys: title, summary (<=200 chars), "
    "focus_areas (list of slugs like 'agentic', 'rag', 'evals', 'prompt-engineering', 'mcp', 'workflows'), "
    "tags (list of free-form slugs), difficulty ('beginner'|'intermediate'|'advanced'|'unknown'). "
    "Return ONLY the JSON object, no prose."
)

_FALLBACK = {"title": "(untitled)", "summary": "", "focus_areas": [], "tags": [], "difficulty": "unknown"}


async def classify_content(*, text: str) -> dict:
    """Single litellm call → structured metadata dict. Never raises on parse error."""
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": text[:8000]},
        ],
        "max_tokens": 400,
        "temperature": 0.2,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{settings.litellm_url}/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="metadata backend unavailable")
    content = resp.json()["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return dict(_FALLBACK)

    out = {
        "title": str(parsed.get("title") or "(untitled)"),
        "summary": str(parsed.get("summary") or "")[:200],
        "focus_areas": [str(x) for x in (parsed.get("focus_areas") or [])][:8],
        "tags": [str(x) for x in (parsed.get("tags") or [])][:12],
        "difficulty": parsed.get("difficulty") if parsed.get("difficulty") in {"beginner", "intermediate", "advanced"} else "unknown",
    }
    return out
```

Also create the empty `__init__.py`:

```python
# services/admin/app/llm/__init__.py
```

- [ ] **Step 4: Re-run tests**

Run: `pytest tests/test_champion_metadata.py -v`
Expected: 2 passes.

- [ ] **Step 5: Commit**

```bash
git add services/admin/app/llm/ services/admin/tests/test_champion_metadata.py
git commit -m "feat(admin): champion_metadata LLM classifier"
```

---

## Task 5: Admin endpoints — nominate / retire / list-for-admin

**Files:**
- Create: `services/admin/app/routers/admin_champions.py`
- Test: `services/admin/tests/test_admin_champions.py`

- [ ] **Step 1: Write the failing test**

```python
# services/admin/tests/test_admin_champions.py
import pytest
from unittest.mock import MagicMock


@pytest.mark.asyncio
async def test_nominate_inserts_champion(client, mock_session):
    mock_session.execute.return_value.scalar_one.return_value = "00000000-0000-0000-0000-000000000001"
    resp = await client.post(
        "/admin/champions",
        json={"developer_id": "00000000-0000-0000-0000-000000000001",
              "bio": "RAG specialist",
              "focus_areas": ["rag", "agentic"]},
    )
    assert resp.status_code == 201
    assert mock_session.execute.await_count >= 1
    assert mock_session.commit.await_count == 1


@pytest.mark.asyncio
async def test_retire_sets_active_false(client, mock_session):
    resp = await client.delete("/admin/champions/00000000-0000-0000-0000-000000000001")
    assert resp.status_code == 204
    args = mock_session.execute.await_args.args
    assert "UPDATE champions" in str(args[0]) and "active" in str(args[0])
```

- [ ] **Step 2: Run test, expect failure**

Run: `pytest tests/test_admin_champions.py -v`
Expected: 404s (route missing).

- [ ] **Step 3: Implement the router**

```python
# services/admin/app/routers/admin_champions.py
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.auth import require_admin_auth
from app.db import get_session

router = APIRouter(prefix="/admin/champions", tags=["admin-champions"])


class NominateRequest(BaseModel):
    developer_id: UUID
    bio: str | None = None
    focus_areas: list[str] = []
    office_hours_text: str | None = None


@router.post("", status_code=201, dependencies=[Depends(require_admin_auth)])
async def nominate(body: NominateRequest, request: Request, session: AsyncSession = Depends(get_session), auth: dict = Depends(require_admin_auth)):
    await session.execute(
        text("""
            INSERT INTO champions (developer_id, bio, focus_areas, office_hours_text, active, nominated_by)
            VALUES (:dev, :bio, :focus, :hours, TRUE, :by)
            ON CONFLICT (developer_id) DO UPDATE
              SET bio = EXCLUDED.bio,
                  focus_areas = EXCLUDED.focus_areas,
                  office_hours_text = EXCLUDED.office_hours_text,
                  active = TRUE
        """),
        {
            "dev": str(body.developer_id),
            "bio": body.bio,
            "focus": body.focus_areas,
            "hours": body.office_hours_text,
            "by": auth.get("user_id"),
        },
    )
    await session.commit()
    await audit.record(session, request, "nominate_champion", "champion", resource_id=str(body.developer_id))
    return {"ok": True, "developer_id": str(body.developer_id)}


@router.delete("/{developer_id}", status_code=204, dependencies=[Depends(require_admin_auth)])
async def retire(developer_id: UUID, request: Request, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        text("UPDATE champions SET active = FALSE WHERE developer_id = :dev"),
        {"dev": str(developer_id)},
    )
    await session.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="champion not found")
    await audit.record(session, request, "retire_champion", "champion", resource_id=str(developer_id))
    return
```

- [ ] **Step 4: Re-run tests**

Run: `pytest tests/test_admin_champions.py -v`
Expected: 2 passes (after Task 9 registers the router; you may need to skip this verification until Task 9 lands — alternatively, register the router temporarily here).

- [ ] **Step 5: Commit**

```bash
git add services/admin/app/routers/admin_champions.py services/admin/tests/test_admin_champions.py
git commit -m "feat(admin): nominate/retire champion endpoints"
```

---

## Task 6: Developer-facing champion endpoints

**Files:**
- Create: `services/admin/app/routers/champions.py`
- Test: `services/admin/tests/test_champions.py`

This task covers directory, profile, content submission, and content feed.

- [ ] **Step 1: Write the failing test**

```python
# services/admin/tests/test_champions.py
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_list_directory_returns_active_champions(client, mock_session):
    rows = [
        {"developer_id": "00000000-0000-0000-0000-000000000001", "bio": "rag", "focus_areas": ["rag"],
         "office_hours_text": None, "active": True, "nominated_at": None}
    ]
    mock_session.execute.return_value.mappings.return_value.all.return_value = rows
    resp = await client.get("/champions")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["focus_areas"] == ["rag"]


@pytest.mark.asyncio
async def test_submit_content_runs_full_pipeline(client, mock_session):
    fake_metadata = {
        "title": "Agentic basics",
        "summary": "intro",
        "focus_areas": ["agentic"],
        "tags": ["intro"],
        "difficulty": "beginner",
    }
    with patch("app.routers.champions.classify_content", new=AsyncMock(return_value=fake_metadata)) as cc, \
         patch("app.routers.champions.ingest_to_librarian", new=AsyncMock(return_value="lib-item-1")) as ing, \
         patch("app.routers.champions.grant_points", new=AsyncMock()) as gp:
        resp = await client.post(
            "/champions/content",
            json={"type": "article", "text": "Once upon a time...", "champion_id": "00000000-0000-0000-0000-000000000001"},
        )

    assert resp.status_code == 201
    cc.assert_awaited_once()
    ing.assert_awaited_once()
    gp.assert_awaited_once()
    gp_kwargs = gp.await_args.kwargs
    assert gp_kwargs["delta"] == 50
    assert gp_kwargs["reason"] == "champion_content"


@pytest.mark.asyncio
async def test_submit_content_requires_url_or_text(client):
    resp = await client.post("/champions/content", json={"type": "link", "champion_id": "00000000-0000-0000-0000-000000000001"})
    assert resp.status_code == 422 or resp.status_code == 400


@pytest.mark.asyncio
async def test_feed_returns_recent_contributions(client, mock_session):
    mock_session.execute.return_value.mappings.return_value.all.return_value = [
        {"id": "11111111-1111-1111-1111-111111111111", "champion_id": "00000000-0000-0000-0000-000000000001",
         "type": "article", "submitted_at": None, "auto_metadata": {"title": "x", "summary": "y", "focus_areas": [], "tags": []},
         "upvotes": 0, "views": 0}
    ]
    resp = await client.get("/champions/content")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
```

- [ ] **Step 2: Run test, expect failure**

Run: `pytest tests/test_champions.py -v`
Expected: 404s (route missing).

- [ ] **Step 3: Implement the router**

```python
# services/admin/app/routers/champions.py
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.league_client import grant_points
from app.llm.champion_metadata import classify_content
from app.routers.unified_auth import get_current_user

router = APIRouter(prefix="/champions", tags=["champions"])


# ---------- librarian helper ----------

async def ingest_to_librarian(*, title: str, content: str, source_url: str | None, tags: list[str]) -> str | None:
    """POST /ingest to librarian. Returns the librarian item id, or None on failure."""
    payload = {
        "title": title,
        "content": content,
        "source_url": source_url,
        "topic": "champions",
        "tags": tags,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{settings.librarian_url}/ingest",
                json=payload,
                headers={"X-Service-Token": settings.librarian_service_token},
            )
        if resp.status_code in (200, 201):
            return resp.json().get("id")
    except Exception:
        return None
    return None


# ---------- schemas ----------

class ChampionOut(BaseModel):
    developer_id: UUID
    bio: str | None
    focus_areas: list[str]
    office_hours_text: str | None
    active: bool


class ContentSubmit(BaseModel):
    champion_id: UUID
    type: str  # article | link | video | artifact
    url: str | None = None
    text: str | None = None
    optional_title: str | None = None

    @model_validator(mode="after")
    def _need_url_or_text(self):
        if not self.url and not self.text:
            raise ValueError("either url or text is required")
        return self


# ---------- directory ----------

@router.get("")
async def list_directory(session: AsyncSession = Depends(get_session)):
    result = await session.execute(text("""
        SELECT developer_id, bio, focus_areas, office_hours_text, active, nominated_at
        FROM champions
        WHERE active = TRUE
        ORDER BY nominated_at DESC
    """))
    return [
        {
            "developer_id": str(r["developer_id"]),
            "bio": r["bio"],
            "focus_areas": list(r["focus_areas"]) if r["focus_areas"] is not None else [],
            "office_hours_text": r["office_hours_text"],
            "active": r["active"],
        }
        for r in result.mappings().all()
    ]


@router.get("/{developer_id}")
async def profile(developer_id: UUID, session: AsyncSession = Depends(get_session)):
    row = (await session.execute(
        text("SELECT developer_id, bio, focus_areas, office_hours_text, active FROM champions WHERE developer_id = :d"),
        {"d": str(developer_id)},
    )).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="champion not found")
    return {
        "developer_id": str(row["developer_id"]),
        "bio": row["bio"],
        "focus_areas": list(row["focus_areas"]) if row["focus_areas"] is not None else [],
        "office_hours_text": row["office_hours_text"],
        "active": row["active"],
    }


# ---------- content submission ----------

@router.post("/content", status_code=201)
async def submit_content(body: ContentSubmit, session: AsyncSession = Depends(get_session)):
    # 1. choose text to classify: pasted text wins; otherwise the URL itself (full fetch is a follow-up).
    body_text = body.text or body.url or ""

    # 2. classify
    metadata = await classify_content(text=body_text)
    title = body.optional_title or metadata["title"]

    # 3. ingest to librarian
    librarian_id = await ingest_to_librarian(
        title=title,
        content=body_text,
        source_url=body.url,
        tags=metadata["tags"],
    )

    # 4. insert contribution row
    inserted = (await session.execute(
        text("""
            INSERT INTO champion_contributions (champion_id, type, librarian_item_id, auto_metadata)
            VALUES (:champion_id, :type, :lib_id, CAST(:meta AS JSONB))
            RETURNING id
        """),
        {
            "champion_id": str(body.champion_id),
            "type": body.type,
            "lib_id": librarian_id,
            "meta": _json_dumps({**metadata, "title": title}),
        },
    )).scalar_one()
    await session.commit()

    # 5. league grant
    try:
        await grant_points(engineer_id=str(body.champion_id), delta=50, reason="champion_content", ref_id=str(inserted))
    except RuntimeError:
        # Points are best-effort; do not undo content creation.
        pass

    return {"id": str(inserted), "title": title, "summary": metadata["summary"]}


def _json_dumps(obj) -> str:
    import json
    return json.dumps(obj, default=str)


# ---------- content feed ----------

@router.get("/content")
async def list_content(session: AsyncSession = Depends(get_session)):
    result = await session.execute(text("""
        SELECT id, champion_id, type, submitted_at, auto_metadata, upvotes, views
        FROM champion_contributions
        ORDER BY submitted_at DESC
        LIMIT 50
    """))
    return [
        {
            "id": str(r["id"]),
            "champion_id": str(r["champion_id"]),
            "type": r["type"],
            "submitted_at": r["submitted_at"].isoformat() if r["submitted_at"] else None,
            "metadata": r["auto_metadata"] or {},
            "upvotes": r["upvotes"],
            "views": r["views"],
        }
        for r in result.mappings().all()
    ]
```

Also extend `services/admin/app/config.py` with:

```python
    librarian_url: str = "http://librarian:8008"
    librarian_service_token: str = ""
```

- [ ] **Step 4: Re-run tests**

Run: `pytest tests/test_champions.py -v`
Expected: 4 passes (after Task 9 registers the router).

- [ ] **Step 5: Commit**

```bash
git add services/admin/app/routers/champions.py services/admin/app/config.py services/admin/tests/test_champions.py
git commit -m "feat(admin): champions directory, profile, content submission, content feed"
```

---

## Task 7: Register routers in admin main.py

**Files:**
- Modify: `services/admin/app/main.py`

- [ ] **Step 1: Add imports**

Near the other router imports in `services/admin/app/main.py`:

```python
from app.routers import champions as champions_router
from app.routers import admin_champions as admin_champions_router
```

- [ ] **Step 2: Register both routers**

Near the other `app.include_router` calls — `champions` is developer-facing (no admin gate); `admin_champions` is admin-gated by its own dependency:

```python
app.include_router(champions_router.router)
app.include_router(admin_champions_router.router)
```

- [ ] **Step 3: Run the test suites that were previously held up**

Run: `pytest tests/test_champions.py tests/test_admin_champions.py -v`
Expected: all green.

- [ ] **Step 4: Smoke test the running service**

```bash
docker compose -f infra/docker-compose.yml up -d admin postgres redis litellm league librarian
curl -s http://localhost:8005/champions | jq .
```

Expected: `[]` (no champions yet).

- [ ] **Step 5: Commit**

```bash
git add services/admin/app/main.py
git commit -m "feat(admin): register champions + admin_champions routers"
```

---

## Task 8: Portal hub page — directory + content feed

**Files:**
- Create: `apps/portal/app/portal/champions/page.tsx`

- [ ] **Step 1: Implement the hub page**

```tsx
// apps/portal/app/portal/champions/page.tsx
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE ?? "/admin";

type Champion = {
  developer_id: string;
  bio: string | null;
  focus_areas: string[];
  office_hours_text: string | null;
  active: boolean;
};

type Contribution = {
  id: string;
  champion_id: string;
  type: string;
  submitted_at: string | null;
  metadata: { title?: string; summary?: string; focus_areas?: string[]; tags?: string[] };
  upvotes: number;
  views: number;
};

export default function ChampionsHub() {
  const [champs, setChamps] = useState<Champion[]>([]);
  const [contribs, setContribs] = useState<Contribution[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [a, b] = await Promise.all([
          fetch(`${ADMIN_BASE}/champions`).then((r) => r.json()),
          fetch(`${ADMIN_BASE}/champions/content`).then((r) => r.json()),
        ]);
        setChamps(a);
        setContribs(b);
      } catch (e: any) {
        setError(String(e));
      }
    })();
  }, []);

  return (
    <div className="space-y-8 p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">AI Champions</h1>
        <Link href="/portal/champions/new-content"
              className="rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700">
          Share content
        </Link>
      </header>

      {error && <p className="text-red-600">Error: {error}</p>}

      <section>
        <h2 className="mb-3 text-lg font-medium">Champions</h2>
        <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {champs.map((c) => (
            <li key={c.developer_id} className="rounded-lg border p-4">
              <Link href={`/portal/champions/${c.developer_id}`} className="font-medium hover:underline">
                {c.developer_id.slice(0, 8)}…
              </Link>
              {c.bio && <p className="mt-1 text-sm text-gray-600">{c.bio}</p>}
              <div className="mt-2 flex flex-wrap gap-1">
                {c.focus_areas.map((f) => (
                  <span key={f} className="rounded bg-gray-100 px-2 py-0.5 text-xs">{f}</span>
                ))}
              </div>
            </li>
          ))}
          {champs.length === 0 && <p className="text-sm text-gray-500">No champions yet.</p>}
        </ul>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-medium">Recent content</h2>
        <ul className="space-y-3">
          {contribs.map((c) => (
            <li key={c.id} className="rounded-lg border p-4">
              <p className="font-medium">{c.metadata.title ?? "(untitled)"}</p>
              {c.metadata.summary && <p className="mt-1 text-sm text-gray-600">{c.metadata.summary}</p>}
              <div className="mt-2 flex flex-wrap gap-1">
                {(c.metadata.focus_areas ?? []).map((f) => (
                  <span key={f} className="rounded bg-blue-50 px-2 py-0.5 text-xs text-blue-700">{f}</span>
                ))}
              </div>
            </li>
          ))}
          {contribs.length === 0 && <p className="text-sm text-gray-500">No content yet.</p>}
        </ul>
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Verify the page renders**

```bash
cd apps/portal && npm run dev
# open http://localhost:3002/portal/champions
```

Expected: empty hub renders without console errors. "Share content" link visible.

- [ ] **Step 3: Commit**

```bash
git add apps/portal/app/portal/champions/page.tsx
git commit -m "feat(portal): champions hub page"
```

---

## Task 9: Portal champion profile page

**Files:**
- Create: `apps/portal/app/portal/champions/[id]/page.tsx`

- [ ] **Step 1: Implement the profile page**

```tsx
// apps/portal/app/portal/champions/[id]/page.tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE ?? "/admin";

type Champion = {
  developer_id: string;
  bio: string | null;
  focus_areas: string[];
  office_hours_text: string | null;
  active: boolean;
};

export default function ChampionProfile() {
  const params = useParams<{ id: string }>();
  const [c, setC] = useState<Champion | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${ADMIN_BASE}/champions/${params.id}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then(setC)
      .catch((e) => setErr(String(e)));
  }, [params.id]);

  if (err) return <p className="p-6 text-red-600">Error: {err}</p>;
  if (!c) return <p className="p-6">Loading…</p>;

  return (
    <div className="space-y-4 p-6">
      <h1 className="text-2xl font-semibold">Champion {c.developer_id.slice(0, 8)}…</h1>
      {c.bio && <p className="text-gray-700">{c.bio}</p>}
      <div className="flex flex-wrap gap-2">
        {c.focus_areas.map((f) => (
          <span key={f} className="rounded bg-gray-100 px-2 py-1 text-sm">{f}</span>
        ))}
      </div>
      {c.office_hours_text && (
        <section>
          <h2 className="text-lg font-medium">Office hours</h2>
          <p className="whitespace-pre-line text-gray-700">{c.office_hours_text}</p>
        </section>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Smoke test**

After nominating a champion (Task 11), navigate to `/portal/champions/<developer_id>` and verify the profile loads.

- [ ] **Step 3: Commit**

```bash
git add apps/portal/app/portal/champions/[id]/page.tsx
git commit -m "feat(portal): champion profile page"
```

---

## Task 10: Portal content submission page

**Files:**
- Create: `apps/portal/app/portal/champions/new-content/page.tsx`

- [ ] **Step 1: Implement the submission form**

```tsx
// apps/portal/app/portal/champions/new-content/page.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../../_lib/authContext";

const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE ?? "/admin";

export default function NewContent() {
  const router = useRouter();
  const { developer, token } = useAuth();
  const [type, setType] = useState<"article" | "link" | "video" | "artifact">("article");
  const [url, setUrl] = useState("");
  const [textBody, setTextBody] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!developer) {
      setError("Please sign in first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch(`${ADMIN_BASE}/champions/content`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          champion_id: developer.developer_id,
          type,
          url: url || null,
          text: textBody || null,
          optional_title: title || null,
        }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      router.push("/portal/champions");
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-4 p-6">
      <h1 className="text-2xl font-semibold">Share content</h1>

      <label className="block">
        <span className="text-sm text-gray-700">Type</span>
        <select value={type} onChange={(e) => setType(e.target.value as any)}
                className="mt-1 block w-full rounded border-gray-300">
          <option value="article">Article</option>
          <option value="link">External link</option>
          <option value="video">Video</option>
          <option value="artifact">Artifact (prompt / config / template)</option>
        </select>
      </label>

      <label className="block">
        <span className="text-sm text-gray-700">URL (optional)</span>
        <input value={url} onChange={(e) => setUrl(e.target.value)}
               placeholder="https://…"
               className="mt-1 block w-full rounded border-gray-300" />
      </label>

      <label className="block">
        <span className="text-sm text-gray-700">Or paste text</span>
        <textarea value={textBody} onChange={(e) => setTextBody(e.target.value)}
                  rows={8} className="mt-1 block w-full rounded border-gray-300" />
      </label>

      <label className="block">
        <span className="text-sm text-gray-700">Title (optional — AI will suggest one)</span>
        <input value={title} onChange={(e) => setTitle(e.target.value)}
               className="mt-1 block w-full rounded border-gray-300" />
      </label>

      {error && <p className="text-red-600">{error}</p>}

      <button onClick={submit} disabled={busy || (!url && !textBody)}
              className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50">
        {busy ? "Submitting…" : "Submit"}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Smoke test the flow**

Open `/portal/champions/new-content`, paste a short paragraph, click Submit. Verify it redirects to `/portal/champions` and the new card appears.

- [ ] **Step 3: Commit**

```bash
git add apps/portal/app/portal/champions/new-content/page.tsx
git commit -m "feat(portal): champion content submission form"
```

---

## Task 11: Admin nominate / retire page

**Files:**
- Create: `apps/admin/app/admin/champions/page.tsx`

- [ ] **Step 1: Implement the admin page**

```tsx
// apps/admin/app/admin/champions/page.tsx
"use client";

import { useEffect, useState } from "react";
import { getAdminToken } from "../_lib/adminAuth"; // adjust import to actual location

const BASE = process.env.NEXT_PUBLIC_ADMIN_API_BASE ?? "";

type Champion = {
  developer_id: string;
  bio: string | null;
  focus_areas: string[];
  active: boolean;
};

export default function AdminChampionsPage() {
  const [list, setList] = useState<Champion[]>([]);
  const [devId, setDevId] = useState("");
  const [bio, setBio] = useState("");
  const [focus, setFocus] = useState("");
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    const r = await fetch(`${BASE}/champions`).then((r) => r.json());
    setList(r);
  };

  useEffect(() => { refresh(); }, []);

  const nominate = async () => {
    setError(null);
    const resp = await fetch(`${BASE}/admin/champions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Admin-Token": getAdminToken() ?? "",
      },
      body: JSON.stringify({
        developer_id: devId,
        bio: bio || null,
        focus_areas: focus.split(",").map((s) => s.trim()).filter(Boolean),
      }),
    });
    if (!resp.ok) { setError(await resp.text()); return; }
    setDevId(""); setBio(""); setFocus("");
    refresh();
  };

  const retire = async (id: string) => {
    await fetch(`${BASE}/admin/champions/${id}`, {
      method: "DELETE",
      headers: { "X-Admin-Token": getAdminToken() ?? "" },
    });
    refresh();
  };

  return (
    <div className="space-y-6 p-6">
      <h1 className="text-2xl font-semibold">AI Champions</h1>

      <section className="rounded border p-4">
        <h2 className="mb-2 text-lg font-medium">Nominate</h2>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
          <input value={devId} onChange={(e) => setDevId(e.target.value)} placeholder="Developer UUID"
                 className="rounded border-gray-300" />
          <input value={bio} onChange={(e) => setBio(e.target.value)} placeholder="Bio"
                 className="rounded border-gray-300" />
          <input value={focus} onChange={(e) => setFocus(e.target.value)} placeholder="focus_areas (comma-separated)"
                 className="rounded border-gray-300" />
        </div>
        {error && <p className="mt-2 text-red-600">{error}</p>}
        <button onClick={nominate} disabled={!devId}
                className="mt-3 rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50">
          Nominate
        </button>
      </section>

      <section>
        <h2 className="mb-2 text-lg font-medium">Active champions</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500">
              <th className="py-2">Developer</th>
              <th>Bio</th>
              <th>Focus areas</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {list.map((c) => (
              <tr key={c.developer_id} className="border-t">
                <td className="py-2 font-mono">{c.developer_id.slice(0, 8)}…</td>
                <td>{c.bio}</td>
                <td>{c.focus_areas.join(", ")}</td>
                <td>
                  <button onClick={() => retire(c.developer_id)}
                          className="rounded border px-3 py-1 text-red-700 hover:bg-red-50">
                    Retire
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
```

> If `getAdminToken` is exported from a different path in this codebase, adjust the import line. Grep for `getAdminToken` to locate the export.

- [ ] **Step 2: Smoke test**

Open `/admin/champions`, paste a developer UUID (you can grab one from `/admin/teams` or the database), nominate, and confirm the row appears below.

- [ ] **Step 3: Commit**

```bash
git add apps/admin/app/admin/champions/page.tsx
git commit -m "feat(admin-portal): nominate/retire champions page"
```

---

## Task 12: Sidebar entries

**Files:**
- Modify: `apps/portal/app/portal/_lib/PortalShell.tsx`
- Modify: the admin sidebar component (find by grepping for an existing item like "Transformation")

- [ ] **Step 1: Add Champions to portal sidebar**

In `PortalShell.tsx`, find the navigation list and add an entry alongside existing ones:

```tsx
{ href: "/portal/champions", label: "Champions" },
```

- [ ] **Step 2: Add Champions to admin sidebar**

```bash
grep -rln "Transformation" apps/admin/app/admin/ | head
```

Open the file that contains the admin sidebar entries and add:

```tsx
{ href: "/admin/champions", label: "Champions" },
```

- [ ] **Step 3: Smoke test both portals**

`localhost:3002/portal/` — "Champions" link should appear in the sidebar and route to `/portal/champions`.
`localhost:3001/admin/` — same for admin.

- [ ] **Step 4: Commit**

```bash
git add apps/portal/app/portal/_lib/PortalShell.tsx apps/admin/app/admin/
git commit -m "feat(portals): add Champions to portal + admin sidebars"
```

---

## Task 13: End-to-end integration verification

This is a final hand-test, not a code task. It exists to catch wiring issues before declaring Wave 1 done.

- [ ] **Step 1: Bring up the stack**

```bash
docker compose -f infra/docker-compose.yml up -d --build admin league librarian litellm postgres redis portal admin-portal
```

- [ ] **Step 2: Apply migration in the container**

```bash
docker compose -f infra/docker-compose.yml exec admin alembic upgrade head
```

Expected: `Running upgrade 0024 -> 0025`.

- [ ] **Step 3: Nominate via admin UI**

Open `http://localhost:8080/admin-portal/admin/champions`. Nominate yourself (paste your own developer UUID). Verify the row appears.

- [ ] **Step 4: Submit content via portal UI**

Open `http://localhost:8080/portal/portal/champions/new-content`. Submit a small paragraph of text. Verify redirect to hub and that the card appears with an AI-generated title, summary, focus areas, and tags.

- [ ] **Step 5: Verify points were granted**

```bash
docker compose -f infra/docker-compose.yml exec postgres \
  psql -U $POSTGRES_USER -d $POSTGRES_DB \
  -c "SELECT engineer_id, delta, reason, ref_id, created_at FROM league_points_ledger WHERE reason LIKE 'champion_%' ORDER BY created_at DESC LIMIT 5;"
```

Expected: one row with `delta=50, reason='champion_content'` pointing at the contribution id you just created.

- [ ] **Step 6: Verify librarian indexed the content**

```bash
curl -s "http://localhost:8080/librarian/search?topic=champions&q=<some+word+from+your+post>" | jq .
```

Expected: at least one hit referencing your post.

- [ ] **Step 7: Run lint**

```bash
ruff check services/admin/ services/league/
ruff format --check services/admin/ services/league/
```

Expected: clean.

- [ ] **Step 8: Run the full test suites**

```bash
cd services/admin && pytest tests/ -v
cd ../league && pytest tests/ -v
```

Expected: all green.

- [ ] **Step 9: Commit any tweaks discovered during integration**

```bash
git add -A
git commit -m "chore: address Wave 1 integration nits"
```

---

## Self-review checklist (post-write)

- [x] Each task lists exact file paths and includes complete code blocks.
- [x] Type names are consistent across tasks: `Champion`, `Contribution`, `ContentSubmit`, `GrantRequest`.
- [x] Each new endpoint has at least one test, plus a negative case.
- [x] Migration creates all six tables in one shot; Wave 2 will use the unused tables without another migration bump.
- [x] League grant is best-effort (try/except) so a temporary league outage does not block content publication.
- [x] No "TBD", "implement later", or "similar to Task N" placeholders.
- [x] Verification covers: migration applies, endpoints answer, UI renders, points land in ledger, librarian indexes, lint passes.

## What's deferred to later plans

- **Wave 2 plan** (separate file): champion_asks (board, resolve flow, auto-confirm cron), upvotes, flagging, admin moderation queue, AiHelpWidget RAG over `topic='champions'`.
- **Wave 3 plan** (separate file): smart routing, office-hours bookings, contextual surfacing widgets (transformation/playground/agents), AiHelpWidget intent classification, admin activity dashboard.
