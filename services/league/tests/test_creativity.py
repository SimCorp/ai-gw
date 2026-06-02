# services/league/tests/test_creativity.py
"""Tests for POST /challenges/{challenge_id}/score-creativity endpoint."""

import os
import uuid
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest

os.environ.setdefault("DEV_BYPASS_AUTH", "false")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.scoring import centroid, cosine_distance, score_creativity  # noqa: E402

_CHALLENGE_ID = str(uuid.uuid4())
_SEASON_ID = str(uuid.uuid4())
_USER_A = str(uuid.uuid4())
_USER_B = str(uuid.uuid4())

# Two orthogonal unit vectors — expected values derived from the real helpers.
_VEC_A = [1.0, 0.0]
_VEC_B = [0.0, 1.0]


def _expected_creativity(vec, all_vecs):
    c = centroid(all_vecs)
    return score_creativity(cosine_distance(vec, c))


@asynccontextmanager
async def _app_client(db_session, mock_redis, *, admin_token="test-admin-token"):
    """Context manager: FastAPI test client with DB override and admin auth configured."""
    from app.config import settings
    from app.db import get_session
    from app.main import app
    from httpx import ASGITransport, AsyncClient

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    original_bypass = settings.dev_bypass_auth
    original_token = settings.admin_token
    settings.dev_bypass_auth = False
    settings.admin_token = admin_token

    try:
        with patch("app.main.aioredis.from_url", return_value=mock_redis):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                yield c
    finally:
        settings.dev_bypass_auth = original_bypass
        settings.admin_token = original_token
        app.dependency_overrides.clear()


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
async def seeded_db(db_session):
    """Seed season → challenge → 2 submissions + score rows."""
    from sqlalchemy import text

    await db_session.execute(
        text("INSERT INTO league_seasons (id, name, status, starts_at, ends_at) VALUES (:id, 'S1', 'active', '2026-01-01', '2026-12-31')"),
        {"id": _SEASON_ID},
    )
    await db_session.execute(
        text("INSERT INTO league_challenges (id, season_id, title, goal, status) VALUES (:id, :sid, 'C1', 'g', 'closed')"),
        {"id": _CHALLENGE_ID, "sid": _SEASON_ID},
    )

    sub_a_id = str(uuid.uuid4())
    sub_b_id = str(uuid.uuid4())
    for sub_id, uid, prompt in [
        (sub_a_id, _USER_A, "prompt_a"),
        (sub_b_id, _USER_B, "prompt_b"),
    ]:
        await db_session.execute(
            text("INSERT INTO league_submissions (id, challenge_id, engineer_id, mode, system_prompt, prompt_hash) VALUES (:id, :cid, :uid, 'league', :prompt, 'h')"),
            {"id": sub_id, "cid": _CHALLENGE_ID, "uid": uid, "prompt": prompt},
        )
        await db_session.execute(
            text(
                "INSERT INTO league_scores"
                " (submission_id, quality, robustness, token_efficiency, speed,"
                "  cost_efficiency, improvement_rate, creativity, composite)"
                " VALUES (:sid, 80, 70, 60, 55, 65, 50, 50, 650)"
            ),
            {"sid": sub_id},
        )
    await db_session.commit()
    return {"sub_a_id": sub_a_id, "sub_b_id": sub_b_id}


# ── tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_score_creativity_updates_scores_values(seeded_db, db_session, mock_redis):
    """Endpoint updates creativity + composite; values match cosine-distance calculation."""
    from sqlalchemy import text

    embed_map = {"prompt_a": _VEC_A, "prompt_b": _VEC_B}

    async def fake_embed_batch(prompts):
        return [embed_map[p] for p in prompts]

    async with _app_client(db_session, mock_redis) as c:
        with patch("app.routers.submissions._embed_batch", new=fake_embed_batch):
            resp = await c.post(
                f"/challenges/{_CHALLENGE_ID}/score-creativity",
                headers={"X-Admin-Token": "test-admin-token"},
            )

    assert resp.status_code == 200
    assert resp.json()["scored"] == 2

    rows = (
        await db_session.execute(
            text("SELECT creativity, composite FROM league_scores WHERE submission_id IN (:a, :b)"),
            {"a": seeded_db["sub_a_id"], "b": seeded_db["sub_b_id"]},
        )
    ).fetchall()

    assert len(rows) == 2

    expected_a = _expected_creativity(_VEC_A, [_VEC_A, _VEC_B])
    expected_b = _expected_creativity(_VEC_B, [_VEC_A, _VEC_B])
    actual_creativities = sorted(float(r[0]) for r in rows)
    expected_creativities = sorted([expected_a, expected_b])
    assert actual_creativities == pytest.approx(expected_creativities, abs=0.1)

    # composite must have been recomputed (was seeded as 650)
    composites = [float(r[1]) for r in rows]
    assert all(c != 650.0 for c in composites)


@pytest.mark.anyio
async def test_score_creativity_requires_admin(seeded_db, db_session, mock_redis):
    """Returns 403 without admin credentials (require_admin_auth raises 403, not 401)."""
    async with _app_client(db_session, mock_redis) as c:
        resp = await c.post(f"/challenges/{_CHALLENGE_ID}/score-creativity")
        # No X-Admin-Token header → 403
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_score_creativity_404_unknown_challenge(db_session, mock_redis):
    """Returns 404 for a challenge ID that doesn't exist."""
    async with _app_client(db_session, mock_redis) as c:
        resp = await c.post(
            f"/challenges/{uuid.uuid4()}/score-creativity",
            headers={"X-Admin-Token": "test-admin-token"},
        )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_score_creativity_noop_fewer_than_2_submissions(db_session, mock_redis):
    """Returns scored=0 with reason when fewer than 2 scored submissions exist."""
    from sqlalchemy import text

    season_id = str(uuid.uuid4())
    challenge_id = str(uuid.uuid4())

    await db_session.execute(
        text("INSERT INTO league_seasons (id, name, status, starts_at, ends_at) VALUES (:id, 'S2', 'active', '2026-01-01', '2026-12-31')"),
        {"id": season_id},
    )
    await db_session.execute(
        text("INSERT INTO league_challenges (id, season_id, title, goal, status) VALUES (:id, :sid, 'C2', 'g', 'closed')"),
        {"id": challenge_id, "sid": season_id},
    )
    sub_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    await db_session.execute(
        text("INSERT INTO league_submissions (id, challenge_id, engineer_id, mode, system_prompt, prompt_hash) VALUES (:id, :cid, :uid, 'league', 'only prompt', 'h')"),
        {"id": sub_id, "cid": challenge_id, "uid": user_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO league_scores"
            " (submission_id, quality, robustness, token_efficiency, speed,"
            "  cost_efficiency, improvement_rate, creativity, composite)"
            " VALUES (:sid, 80, 70, 60, 55, 65, 50, 50, 650)"
        ),
        {"sid": sub_id},
    )
    await db_session.commit()

    async with _app_client(db_session, mock_redis) as c:
        resp = await c.post(
            f"/challenges/{challenge_id}/score-creativity",
            headers={"X-Admin-Token": "test-admin-token"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["scored"] == 0
    assert "need >= 2" in body["reason"]
