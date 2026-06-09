import json
import logging
import os
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

import app.models  # noqa: F401 — registers all ORM models with Base.metadata
from app.config import settings
from app.db import async_session_maker, engine
from app.redis_utils import make_redis
from app.routers import challenges as challenges_router
from app.routers import internal_points as internal_points_router
from app.routers import leaderboard as leaderboard_router
from app.routers import proposals as proposals_router
from app.routers import seasons as seasons_router
from app.routers import store as store_router
from app.routers import submissions as submissions_router
from app.seed_data import CHALLENGES, PROPOSALS, SEASONS, STORE_ITEMS

log = logging.getLogger(__name__)


async def _seed_demo_content() -> None:
    """Insert demo seasons, challenges, store items and proposals on a fresh DB.

    Idempotent via WHERE NOT EXISTS on natural keys (name/title). Safe to run
    on every startup — only inserts what's missing.

    Skipped when:
      - LEAGUE_DISABLE_SEED=1 in env (lets tests opt out), or
      - dev_bypass_auth is False (production)
    """
    if os.getenv("LEAGUE_DISABLE_SEED") == "1":
        log.info("league seed skipped (LEAGUE_DISABLE_SEED=1)")
        return
    env = os.getenv("ENVIRONMENT", "production")
    if env not in ("development", "test", "ci"):
        log.info("league seed skipped (ENVIRONMENT=%s)", env)
        return

    async with async_session_maker() as session:
        # 1. Seasons — insert if name doesn't exist
        for s in SEASONS:
            await session.execute(
                text("""
                INSERT INTO league_seasons (name, status, starts_at, ends_at, scoring_weights, season_multiplier)
                SELECT :name, :status, :starts_at, :ends_at, CAST(:weights AS jsonb), :multiplier
                WHERE NOT EXISTS (SELECT 1 FROM league_seasons WHERE name = :name)
            """),
                {
                    "name": s["name"],
                    "status": s["status"],
                    "starts_at": s["starts_at"],
                    "ends_at": s["ends_at"],
                    "weights": json.dumps(s["scoring_weights"]),
                    "multiplier": s["season_multiplier"],
                },
            )

        # 2. Resolve season name → id
        season_rows = (await session.execute(text("SELECT id, name FROM league_seasons"))).mappings().all()
        season_id_by_name = {r["name"]: r["id"] for r in season_rows}

        # 3. Challenges — insert if (season_id, title) doesn't exist
        for c in CHALLENGES:
            sid = season_id_by_name.get(c["season_name"])
            if not sid:
                continue
            await session.execute(
                text("""
                INSERT INTO league_challenges
                  (season_id, title, goal, training_inputs, hidden_test_suite,
                   allowed_models, max_tokens_budget, max_league_attempts, status,
                   scores_revealed_at)
                SELECT :sid, :title, :goal,
                       CAST(:training AS jsonb), CAST(:hidden AS jsonb),
                       :models, 4096, 3, :status,
                       CASE WHEN :status = 'closed' THEN NOW() ELSE NULL END
                WHERE NOT EXISTS (
                    SELECT 1 FROM league_challenges
                    WHERE season_id = :sid AND title = :title
                )
            """),
                {
                    "sid": str(sid),
                    "title": c["title"],
                    "goal": c["goal"],
                    "training": json.dumps(c["training_inputs"]),
                    "hidden": json.dumps(c["hidden_test_suite"]),
                    "models": ["claude-sonnet-4-6", "gpt-4o", "gpt-4o-mini"],
                    "status": c["status"],
                },
            )

        # 4. Store items — insert if name doesn't exist
        for item in STORE_ITEMS:
            exclusive_sid = season_id_by_name.get(item.get("exclusive_season_name", ""))
            await session.execute(
                text("""
                INSERT INTO league_store_items
                  (name, type, point_cost, asset_url, exclusive_season_id, exclusive_top_n)
                SELECT :name, :type, :cost, :url, :sid, :top_n
                WHERE NOT EXISTS (SELECT 1 FROM league_store_items WHERE name = :name)
            """),
                {
                    "name": item["name"],
                    "type": item["type"],
                    "cost": item["point_cost"],
                    "url": item["asset_url"],
                    "sid": str(exclusive_sid) if exclusive_sid else None,
                    "top_n": item.get("exclusive_top_n"),
                },
            )

        # 5. Proposals — need dev@simcorp.com's user id; skip silently if missing
        dev_id = (await session.execute(text("SELECT id FROM users WHERE email = 'dev@simcorp.com' LIMIT 1"))).scalar()
        admin_id = (await session.execute(text("SELECT id FROM users WHERE email = 'admin@simcorp.com' LIMIT 1"))).scalar()

        if dev_id:
            for p in PROPOSALS:
                reviewer = admin_id if p["status"] in ("approved", "rejected") else None
                await session.execute(
                    text("""
                    INSERT INTO league_challenge_proposals
                      (proposed_by, title, goal, notes, status, reviewed_by, reviewer_notes)
                    SELECT :proposer, :title, :goal, :notes, :status, :reviewer, :review_notes
                    WHERE NOT EXISTS (
                        SELECT 1 FROM league_challenge_proposals WHERE title = :title
                    )
                """),
                    {
                        "proposer": str(dev_id),
                        "title": p["title"],
                        "goal": p["goal"],
                        "notes": p.get("notes", ""),
                        "status": p["status"],
                        "reviewer": str(reviewer) if reviewer else None,
                        "review_notes": p.get("reviewer_notes", ""),
                    },
                )

        await session.commit()
        log.info("league seed complete")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = make_redis(settings.redis_url)
    async with async_session_maker() as session:
        await session.execute(text("ALTER TABLE league_purchases ADD COLUMN IF NOT EXISTS equipped BOOLEAN NOT NULL DEFAULT FALSE"))
        await session.commit()
    try:
        await _seed_demo_content()
    except Exception as exc:
        # Don't fail startup if seed fails (e.g. users table not yet migrated)
        log.warning("league seed failed: %s", exc)
    yield
    await app.state.redis.aclose()


_is_dev = os.getenv("ENVIRONMENT", "production") in ("development", "test", "ci")

app = FastAPI(
    title="AI Gateway — League Service",
    lifespan=lifespan,
    docs_url="/docs" if _is_dev else None,
    redoc_url="/redoc" if _is_dev else None,
    openapi_url="/openapi.json" if _is_dev else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Admin-Token"],
    allow_credentials=True,
)


app.include_router(seasons_router.router)
app.include_router(challenges_router.router)
app.include_router(submissions_router.router)
app.include_router(leaderboard_router.router)
app.include_router(store_router.router)
app.include_router(proposals_router.router)
app.include_router(internal_points_router.router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}


@app.get("/ready", tags=["health"])
async def ready():
    errors: dict[str, str] = {}
    try:
        await app.state.redis.ping()
    except Exception as exc:
        errors["redis"] = str(exc)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        errors["postgres"] = str(exc)
    if errors:
        return JSONResponse({"status": "not_ready", "errors": errors}, status_code=503)
    return {"status": "ready"}
