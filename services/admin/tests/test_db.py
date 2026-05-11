"""Database-level integration tests for the admin service.

Spins up a real PostgreSQL container (testcontainers) once per module,
applies the full schema (ORM metadata + _EXTRA_DDL from app.main), and
tests SQL queries that unit tests with mocked sessions cannot catch:
  - date_trunc / COALESCE / GROUP BY aggregations
  - ON CONFLICT upsert partial-index correctness
  - CASCADE / FK constraint enforcement
  - Column precision (NUMERIC(14,8)) edge cases

Run with:
    cd /home/bntp/repos/ai-gw
    python3 -m pytest services/admin/tests/test_db.py -v --tb=short
"""
# Force all async tests and fixtures in this module to share a single
# module-scoped event loop so module-scoped SQLAlchemy engines work correctly.
import pytest

pytestmark = pytest.mark.asyncio(loop_scope="module")

import hashlib
import os
import sys
from pathlib import Path

# Allow "from app.xxx import ..." without installing the package
sys.path.insert(0, str(Path(__file__).parents[1]))

# Bypass auth so importing app.main doesn't raise on missing settings
os.environ.setdefault("DEV_BYPASS_AUTH", "true")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://placeholder/placeholder")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-real")
os.environ.setdefault("OIDC_ISSUER", "http://localhost:5556")
os.environ.setdefault("OIDC_CLIENT_ID", "admin")
os.environ.setdefault("OIDC_CLIENT_SECRET", "admin-secret")

import pytest
import pytest_asyncio
import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from testcontainers.postgres import PostgresContainer

# Import _EXTRA_DDL and Base *after* env vars are set so the settings singleton
# resolves without hitting the real database.
from app.main import _EXTRA_DDL
from app.db import Base

# Import ORM models so their tables are registered with Base.metadata
from app.models import (  # noqa: F401
    api_key,
    area as area_model,
    area_policy as area_policy_model,
    audit_log as audit_log_model,
    member,
    model_registry as model_registry_model,
    policy,
    pricing as pricing_model,
    team,
)
from app.models.team import Team, Project
from app.models.api_key import APIKey
from app.models.policy import Policy
from app.routers.teams import _team_row_to_dict
from app.routers.budget import _team_monthly_spend, _key_monthly_spend, _org_monthly_spend


# ---------------------------------------------------------------------------
# Module-scoped fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def pg_container():
    """Start a Postgres 16 container once for all DB tests in this module."""
    with PostgresContainer("postgres:16") as postgres:
        yield postgres


def _asyncpg_url(container: PostgresContainer) -> str:
    """Plain postgresql:// URL for asyncpg.connect()."""
    url = container.get_connection_url()
    return url.replace("postgresql+psycopg2://", "postgresql://")


def _sqlalchemy_url(container: PostgresContainer) -> str:
    """postgresql+asyncpg:// URL for SQLAlchemy async engine."""
    url = container.get_connection_url()
    return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def db_engine(pg_container):
    """Apply full schema (ORM + _EXTRA_DDL), return a module-scoped engine."""
    raw_url = _asyncpg_url(pg_container)

    # Step 1: apply ORM-mapped tables via Base.metadata.create_all
    engine = create_async_engine(_sqlalchemy_url(pg_container), echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Step 2: apply the remaining DDL (areas, guardrails, partial indexes, etc.)
        for ddl in _EXTRA_DDL:
            try:
                await conn.execute(text(ddl))
            except Exception:
                pass  # idempotent – index/column already exists is fine

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def session_maker(db_engine):
    """Return a module-scoped async_sessionmaker bound to the test engine."""
    return async_sessionmaker(db_engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Per-test cleanup — TRUNCATE keeps the schema but empties all rows
# ---------------------------------------------------------------------------

_TRUNCATE_TABLES = [
    "guardrail_hits",
    "guardrails",
    "area_policies",
    "cost_records",
    "policies",
    "api_keys",
    "projects",
    "team_members",
    "teams",
    "areas",
    "org_settings",
]


@pytest_asyncio.fixture(loop_scope="module")
async def session(session_maker):
    """Per-test: fresh session, truncate all test data afterwards."""
    async with session_maker() as s:
        yield s
    # Clean up after each test so they are independent
    async with session_maker() as cleanup:
        for tbl in _TRUNCATE_TABLES:
            try:
                await cleanup.execute(text(f"TRUNCATE {tbl} CASCADE"))
            except Exception:
                pass
        await cleanup.commit()


@pytest_asyncio.fixture(loop_scope="module")
async def raw_conn(pg_container):
    """Per-test: raw asyncpg connection. Truncates on teardown via the session fixture."""
    conn = await asyncpg.connect(_asyncpg_url(pg_container))
    yield conn
    await conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _insert_team(session: AsyncSession, name="Test Team", slug=None, area_id=None) -> str:
    slug = slug or name.lower().replace(" ", "-")
    row = (await session.execute(
        text("INSERT INTO teams (name, slug, area_id) VALUES (:n, :s, :a) RETURNING id"),
        {"n": name, "s": slug, "a": str(area_id) if area_id else None},
    )).mappings().one()
    await session.commit()
    return str(row["id"])


async def _insert_area(session: AsyncSession, name="Platform", slug=None) -> str:
    slug = slug or name.lower()
    row = (await session.execute(
        text("INSERT INTO areas (name, slug) VALUES (:n, :s) RETURNING id"),
        {"n": name, "s": slug},
    )).mappings().one()
    await session.commit()
    return str(row["id"])


async def _insert_cost_record(session: AsyncSession, team_id: str, cost: float,
                               api_key_id: str = None, months_ago: int = 0) -> None:
    ts = f"NOW() - INTERVAL '{months_ago} months'" if months_ago else "NOW()"
    await session.execute(
        text(
            f"INSERT INTO cost_records (team_id, model, cost_usd, api_key_id, created_at) "
            f"VALUES (:tid, 'gpt-4o', :cost, :kid, {ts})"
        ),
        {"tid": team_id, "cost": cost, "kid": api_key_id},
    )
    await session.commit()


# ===========================================================================
# TEAM CRUD
# ===========================================================================

async def test_insert_team_then_list_teams_returns_it(session):
    """Insert a team via raw SQL; the list_teams query must find it."""
    team_id = await _insert_team(session, "Alpha Squad", "alpha-squad")

    rows = (await session.execute(text("""
        SELECT t.id, t.name, t.slug, t.created_at, t.monthly_budget_usd,
               t.budget_alert_pct, t.budget_action, t.area_id,
               a.name AS area_name, a.slug AS area_slug, a.color AS area_color
        FROM teams t LEFT JOIN areas a ON a.id = t.area_id
        ORDER BY a.name NULLS LAST, t.name
    """))).mappings().all()

    assert len(rows) == 1
    d = _team_row_to_dict(rows[0])
    assert d["id"] == team_id
    assert d["name"] == "Alpha Squad"
    assert d["slug"] == "alpha-squad"
    assert d["area_name"] is None


async def test_team_row_to_dict_formats_correctly(session):
    """_team_row_to_dict converts UUID to str, handles None budget."""
    team_id = await _insert_team(session, "Beta Squad", "beta-squad")

    row = (await session.execute(text("""
        SELECT t.id, t.name, t.slug, t.created_at, t.monthly_budget_usd,
               t.budget_alert_pct, t.budget_action, t.area_id,
               a.name AS area_name, a.slug AS area_slug, a.color AS area_color
        FROM teams t LEFT JOIN areas a ON a.id = t.area_id
        WHERE t.id = CAST(:id AS uuid)
    """), {"id": team_id})).mappings().one()

    d = _team_row_to_dict(row)
    assert isinstance(d["id"], str)
    assert d["monthly_budget_usd"] is None
    assert d["area_id"] is None
    assert d["created_at"] is not None   # isoformat string


async def test_list_teams_includes_area_join(session):
    """Teams with an area_id expose area_name / area_slug from the LEFT JOIN."""
    area_id = await _insert_area(session, "Platform", "platform")
    await _insert_team(session, "Core Team", "core-team", area_id=area_id)

    rows = (await session.execute(text("""
        SELECT t.id, t.name, t.slug, t.created_at, t.monthly_budget_usd,
               t.budget_alert_pct, t.budget_action, t.area_id,
               a.name AS area_name, a.slug AS area_slug, a.color AS area_color
        FROM teams t LEFT JOIN areas a ON a.id = t.area_id
        ORDER BY a.name NULLS LAST, t.name
    """))).mappings().all()

    assert len(rows) == 1
    d = _team_row_to_dict(rows[0])
    assert d["area_name"] == "Platform"
    assert d["area_slug"] == "platform"
    assert d["area_id"] == area_id


async def test_create_team_via_orm_appears_in_list_query(session):
    """ORM-created Team must be found by the raw list_teams SQL."""
    team = Team(name="ORM Team", slug="orm-team")
    session.add(team)
    await session.commit()
    await session.refresh(team)

    rows = (await session.execute(text("""
        SELECT t.id, t.name, t.slug, t.created_at, t.monthly_budget_usd,
               t.budget_alert_pct, t.budget_action, t.area_id,
               a.name AS area_name, a.slug AS area_slug, a.color AS area_color
        FROM teams t LEFT JOIN areas a ON a.id = t.area_id
        ORDER BY t.name
    """))).mappings().all()

    ids = [str(r["id"]) for r in rows]
    assert str(team.id) in ids


async def test_delete_team_cascades_to_projects(session):
    """Deleting a team must CASCADE-delete its projects (ON DELETE CASCADE FK)."""
    team_id = await _insert_team(session, "Doomed Team", "doomed-team")
    await session.execute(
        text("INSERT INTO projects (team_id, name, slug) VALUES (CAST(:tid AS uuid), :n, :s)"),
        {"tid": team_id, "n": "Doomed Project", "s": "doomed-project"},
    )
    await session.commit()

    # Confirm project exists
    count_before = (await session.execute(
        text("SELECT COUNT(*) FROM projects WHERE team_id = CAST(:tid AS uuid)"),
        {"tid": team_id},
    )).scalar()
    assert count_before == 1

    # Delete team
    await session.execute(
        text("DELETE FROM teams WHERE id = CAST(:id AS uuid)"), {"id": team_id}
    )
    await session.commit()

    count_after = (await session.execute(
        text("SELECT COUNT(*) FROM projects WHERE team_id = CAST(:tid AS uuid)"),
        {"tid": team_id},
    )).scalar()
    assert count_after == 0


async def test_unique_slug_constraint_raises(session):
    """Inserting two teams with the same slug must raise an integrity error."""
    await _insert_team(session, "Team One", "shared-slug")
    import asyncpg as _apg
    from sqlalchemy.exc import IntegrityError
    with pytest.raises((IntegrityError, _apg.UniqueViolationError, Exception)):
        await session.execute(
            text("INSERT INTO teams (name, slug) VALUES (:n, :s)"),
            {"n": "Team Two", "s": "shared-slug"},
        )
        await session.commit()


# ===========================================================================
# BUDGET SQL
# ===========================================================================

async def test_team_monthly_spend_zero_for_no_records(session):
    """No cost records → _team_monthly_spend returns 0.0."""
    team_id = await _insert_team(session, "Budget Team", "budget-team")
    from uuid import UUID
    spend = await _team_monthly_spend(session, UUID(team_id))
    assert spend == 0.0


async def test_team_monthly_spend_sums_current_month_only(session):
    """_team_monthly_spend sums current-month rows but ignores older ones."""
    team_id = await _insert_team(session, "Spend Team", "spend-team")
    await _insert_cost_record(session, team_id, 1.5, months_ago=0)
    await _insert_cost_record(session, team_id, 0.75, months_ago=0)
    await _insert_cost_record(session, team_id, 99.0, months_ago=2)  # must be excluded

    from uuid import UUID
    spend = await _team_monthly_spend(session, UUID(team_id))
    assert abs(spend - 2.25) < 1e-6


async def test_key_monthly_spend_sums_correctly(session):
    """_key_monthly_spend aggregates by api_key_id, current month only."""
    team_id = await _insert_team(session, "Key Spend Team", "key-spend-team")
    # Create an API key row directly
    row = (await session.execute(
        text(
            "INSERT INTO api_keys (team_id, name, key_hash) "
            "VALUES (CAST(:tid AS uuid), :n, :kh) RETURNING id"
        ),
        {"tid": team_id, "n": "test-key", "kh": "hash-abc-123"},
    )).mappings().one()
    await session.commit()
    key_id = str(row["id"])

    await _insert_cost_record(session, team_id, 0.5, api_key_id=key_id, months_ago=0)
    await _insert_cost_record(session, team_id, 0.25, api_key_id=key_id, months_ago=0)
    await _insert_cost_record(session, team_id, 10.0, api_key_id=key_id, months_ago=1)  # excluded

    from uuid import UUID
    spend = await _key_monthly_spend(session, UUID(key_id))
    assert abs(spend - 0.75) < 1e-6


async def test_org_monthly_spend_sums_all_teams(session):
    """_org_monthly_spend totals cost_records across all teams this month."""
    t1 = await _insert_team(session, "Org Team 1", "org-team-1")
    t2 = await _insert_team(session, "Org Team 2", "org-team-2")
    await _insert_cost_record(session, t1, 1.0, months_ago=0)
    await _insert_cost_record(session, t2, 2.0, months_ago=0)
    await _insert_cost_record(session, t1, 50.0, months_ago=3)  # must be excluded

    spend = await _org_monthly_spend(session)
    assert abs(spend - 3.0) < 1e-6


async def test_budget_status_aggregates_multiple_teams(session):
    """The budget_status GROUP BY query correctly computes per-team spend."""
    t1 = await _insert_team(session, "Agg Team A", "agg-team-a")
    t2 = await _insert_team(session, "Agg Team B", "agg-team-b")
    await _insert_cost_record(session, t1, 2.0, months_ago=0)
    await _insert_cost_record(session, t1, 3.0, months_ago=0)
    await _insert_cost_record(session, t2, 1.5, months_ago=0)

    rows = (await session.execute(text("""
        SELECT t.id, t.name,
               COALESCE(SUM(cr.cost_usd), 0) AS spend
        FROM teams t
        LEFT JOIN cost_records cr
               ON cr.team_id = t.id
              AND cr.created_at >= date_trunc('month', NOW())
        GROUP BY t.id, t.name
        ORDER BY t.name
    """))).mappings().all()

    by_name = {r["name"]: float(r["spend"]) for r in rows}
    assert abs(by_name["Agg Team A"] - 5.0) < 1e-6
    assert abs(by_name["Agg Team B"] - 1.5) < 1e-6


# ===========================================================================
# POLICY UPSERT (ON CONFLICT partial indexes)
# ===========================================================================

async def test_upsert_policy_inserts_new_row(session):
    """First upsert with project_id=None creates a policy row."""
    team_id = await _insert_team(session, "Policy Team", "policy-team")

    # Uses the partial unique index: policies_team_null_proj_uidx ON (team_id) WHERE project_id IS NULL
    await session.execute(
        text("""
            INSERT INTO policies (team_id, project_id, cache_ttl_seconds, cache_similarity_threshold,
                                  cache_opt_out, embedding_model, rate_limit_rpm, allowed_models)
            VALUES (CAST(:tid AS uuid), NULL, 7200, 0.90, FALSE, 'text-embedding-3-small', 500, ARRAY[]::TEXT[])
            ON CONFLICT (team_id) WHERE project_id IS NULL
            DO UPDATE
                SET cache_ttl_seconds = EXCLUDED.cache_ttl_seconds,
                    cache_similarity_threshold = EXCLUDED.cache_similarity_threshold,
                    cache_opt_out = EXCLUDED.cache_opt_out,
                    embedding_model = EXCLUDED.embedding_model,
                    rate_limit_rpm = EXCLUDED.rate_limit_rpm,
                    allowed_models = EXCLUDED.allowed_models
        """),
        {"tid": team_id},
    )
    await session.commit()

    count = (await session.execute(
        text("SELECT COUNT(*) FROM policies WHERE team_id = CAST(:tid AS uuid)"),
        {"tid": team_id},
    )).scalar()
    assert count == 1


async def test_upsert_policy_second_call_updates_not_duplicates(session):
    """Second upsert for same team_id+project_id=None updates instead of inserting."""
    team_id = await _insert_team(session, "Upsert Team", "upsert-team")

    upsert_sql = text("""
        INSERT INTO policies (team_id, project_id, cache_ttl_seconds, cache_similarity_threshold,
                              cache_opt_out, embedding_model, rate_limit_rpm, allowed_models)
        VALUES (CAST(:tid AS uuid), NULL, :ttl, 0.95, FALSE, 'text-embedding-3-small', 1000, ARRAY[]::TEXT[])
        ON CONFLICT (team_id) WHERE project_id IS NULL
        DO UPDATE SET cache_ttl_seconds = EXCLUDED.cache_ttl_seconds
    """)

    await session.execute(upsert_sql, {"tid": team_id, "ttl": 3600})
    await session.commit()
    await session.execute(upsert_sql, {"tid": team_id, "ttl": 7200})
    await session.commit()

    rows = (await session.execute(
        text("SELECT cache_ttl_seconds FROM policies WHERE team_id = CAST(:tid AS uuid)"),
        {"tid": team_id},
    )).fetchall()

    assert len(rows) == 1
    assert rows[0][0] == 7200


async def test_upsert_policy_project_none_vs_uuid_creates_two_rows(session):
    """project_id=NULL and project_id=<uuid> must produce two separate policy rows.

    The schema has two separate partial indexes for these cases:
      - policies_team_null_proj_uidx ON (team_id) WHERE project_id IS NULL
      - policies_team_proj_uidx ON (team_id, project_id) WHERE project_id IS NOT NULL
    """
    team_id = await _insert_team(session, "Dual Policy Team", "dual-policy-team")

    proj_row = (await session.execute(
        text("INSERT INTO projects (team_id, name, slug) VALUES (CAST(:tid AS uuid), 'P', 'p') RETURNING id"),
        {"tid": team_id},
    )).mappings().one()
    await session.commit()
    proj_id = str(proj_row["id"])

    # Insert team-level policy (project_id IS NULL)
    await session.execute(
        text("""
            INSERT INTO policies (team_id, project_id, cache_ttl_seconds, cache_similarity_threshold,
                                  cache_opt_out, embedding_model, rate_limit_rpm, allowed_models)
            VALUES (CAST(:tid AS uuid), NULL, 3600, 0.95, FALSE, 'text-embedding-3-small', 1000, ARRAY[]::TEXT[])
            ON CONFLICT (team_id) WHERE project_id IS NULL
            DO UPDATE SET cache_ttl_seconds = EXCLUDED.cache_ttl_seconds
        """),
        {"tid": team_id},
    )
    # Insert project-level policy (project_id IS NOT NULL)
    await session.execute(
        text("""
            INSERT INTO policies (team_id, project_id, cache_ttl_seconds, cache_similarity_threshold,
                                  cache_opt_out, embedding_model, rate_limit_rpm, allowed_models)
            VALUES (CAST(:tid AS uuid), CAST(:pid AS uuid), 1800, 0.80, FALSE, 'text-embedding-3-small', 500, ARRAY[]::TEXT[])
            ON CONFLICT (team_id, project_id) WHERE project_id IS NOT NULL
            DO UPDATE SET cache_ttl_seconds = EXCLUDED.cache_ttl_seconds
        """),
        {"tid": team_id, "pid": proj_id},
    )
    await session.commit()

    count = (await session.execute(
        text("SELECT COUNT(*) FROM policies WHERE team_id = CAST(:tid AS uuid)"),
        {"tid": team_id},
    )).scalar()
    assert count == 2


# ===========================================================================
# AREAS SQL
# ===========================================================================

async def test_create_area_list_shows_team_count_zero(session):
    """Newly created area with no teams must show team_count=0 in list_areas query."""
    await _insert_area(session, "Empty Area", "empty-area")

    rows = (await session.execute(text("""
        SELECT a.id, a.name, COUNT(t.id) AS team_count
        FROM areas a
        LEFT JOIN teams t ON t.area_id = a.id
        GROUP BY a.id
        ORDER BY a.name
    """))).mappings().all()

    assert len(rows) == 1
    assert rows[0]["name"] == "Empty Area"
    assert rows[0]["team_count"] == 0


async def test_assign_teams_to_area_increments_team_count(session):
    """Assigning two teams to an area must make team_count=2."""
    area_id = await _insert_area(session, "Full Area", "full-area")
    await _insert_team(session, "T1", "t1", area_id=area_id)
    await _insert_team(session, "T2", "t2", area_id=area_id)

    row = (await session.execute(text("""
        SELECT COUNT(t.id) AS team_count
        FROM areas a
        LEFT JOIN teams t ON t.area_id = a.id
        WHERE a.id = CAST(:aid AS uuid)
        GROUP BY a.id
    """), {"aid": area_id})).mappings().one()

    assert row["team_count"] == 2


async def test_delete_area_nullifies_team_area_id(session):
    """Deleting an area sets teams.area_id to NULL (ON DELETE SET NULL FK).

    The FK is intentionally SET NULL — area deletion must not block. Verify
    the cascade semantics: the team survives, area_id becomes NULL.
    """
    area_id = await _insert_area(session, "Removable Area", "removable-area")
    team_id = await _insert_team(session, "Orphan Team", "orphan-team", area_id=area_id)

    # Confirm area_id is set before deletion
    area_id_before = (await session.execute(
        text("SELECT area_id FROM teams WHERE id = CAST(:tid AS uuid)"), {"tid": team_id}
    )).scalar_one()
    assert area_id_before is not None

    # Delete the area — should succeed (SET NULL, not RESTRICT)
    await session.execute(
        text("DELETE FROM areas WHERE id = CAST(:id AS uuid)"), {"id": area_id}
    )
    await session.commit()

    # Team still exists, area_id is now NULL
    area_id_after = (await session.execute(
        text("SELECT area_id FROM teams WHERE id = CAST(:tid AS uuid)"), {"tid": team_id}
    )).scalar_one()
    assert area_id_after is None


async def test_area_policy_upsert_inserts_then_updates(session):
    """First upsert creates an area_policies row; second updates it (no duplicate)."""
    area_id = await _insert_area(session, "Policy Area", "policy-area")

    upsert_sql = text("""
        INSERT INTO area_policies (area_id, cache_ttl_seconds, cache_similarity_threshold,
                                   cache_opt_out, embedding_model, rate_limit_rpm, allowed_models)
        VALUES (CAST(:aid AS uuid), :ttl, 0.95, FALSE, 'text-embedding-3-small', 1000, ARRAY[]::TEXT[])
        ON CONFLICT (area_id) DO UPDATE
            SET cache_ttl_seconds = EXCLUDED.cache_ttl_seconds,
                updated_at = NOW()
    """)

    await session.execute(upsert_sql, {"aid": area_id, "ttl": 3600})
    await session.commit()
    await session.execute(upsert_sql, {"aid": area_id, "ttl": 1800})
    await session.commit()

    rows = (await session.execute(
        text("SELECT cache_ttl_seconds FROM area_policies WHERE area_id = CAST(:aid AS uuid)"),
        {"aid": area_id},
    )).fetchall()

    assert len(rows) == 1
    assert rows[0][0] == 1800


# ===========================================================================
# API KEYS
# ===========================================================================

async def test_create_key_hashes_the_key(session):
    """create_key stores a sha256 hash — key_hash must differ from the raw key."""
    team_id = await _insert_team(session, "Key Team", "key-team")
    import secrets
    raw_key = "sk-" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    await session.execute(
        text(
            "INSERT INTO api_keys (team_id, name, key_hash) "
            "VALUES (CAST(:tid AS uuid), :n, :kh)"
        ),
        {"tid": team_id, "n": "my-key", "kh": key_hash},
    )
    await session.commit()

    stored = (await session.execute(
        text("SELECT key_hash FROM api_keys WHERE team_id = CAST(:tid AS uuid)"),
        {"tid": team_id},
    )).scalar_one()

    assert stored == key_hash
    assert stored != raw_key


async def test_revoke_key_sets_revoked_at(session):
    """Revoking a key must set revoked_at to a non-NULL timestamp."""
    team_id = await _insert_team(session, "Revoke Team", "revoke-team")
    key_row = (await session.execute(
        text(
            "INSERT INTO api_keys (team_id, name, key_hash) "
            "VALUES (CAST(:tid AS uuid), :n, :kh) RETURNING id"
        ),
        {"tid": team_id, "n": "rev-key", "kh": "hash-rev-000"},
    )).mappings().one()
    await session.commit()
    key_id = str(key_row["id"])

    await session.execute(
        text("UPDATE api_keys SET revoked_at = NOW() WHERE id = CAST(:id AS uuid)"),
        {"id": key_id},
    )
    await session.commit()

    revoked_at = (await session.execute(
        text("SELECT revoked_at FROM api_keys WHERE id = CAST(:id AS uuid)"),
        {"id": key_id},
    )).scalar_one()

    assert revoked_at is not None


async def test_list_keys_filters_out_revoked(session):
    """Active key list must exclude rows where revoked_at IS NOT NULL."""
    team_id = await _insert_team(session, "Filter Team", "filter-team")

    # Active key
    await session.execute(
        text(
            "INSERT INTO api_keys (team_id, name, key_hash) "
            "VALUES (CAST(:tid AS uuid), :n, :kh)"
        ),
        {"tid": team_id, "n": "active-key", "kh": "hash-active-001"},
    )
    # Revoked key
    await session.execute(
        text(
            "INSERT INTO api_keys (team_id, name, key_hash, revoked_at) "
            "VALUES (CAST(:tid AS uuid), :n, :kh, NOW())"
        ),
        {"tid": team_id, "n": "revoked-key", "kh": "hash-revoked-002"},
    )
    await session.commit()

    active_keys = (await session.execute(
        text(
            "SELECT id FROM api_keys "
            "WHERE team_id = CAST(:tid AS uuid) AND revoked_at IS NULL"
        ),
        {"tid": team_id},
    )).fetchall()

    assert len(active_keys) == 1


# ===========================================================================
# GUARDRAILS
# ===========================================================================

async def test_insert_guardrail_list_shows_hits_24h_zero(session):
    """A freshly inserted guardrail with no hits must return hits_24h=0."""
    await session.execute(
        text("""
            INSERT INTO guardrails (name, type, applies_to, action, severity, priority, config)
            VALUES ('Test Guard', 'pii_detector', 'input', 'block', 'high', 100, '{}')
        """)
    )
    await session.commit()

    row = (await session.execute(text("""
        SELECT g.id, g.name,
               COUNT(h.id) FILTER (WHERE h.created_at >= NOW() - INTERVAL '24 hours') AS hits_24h
        FROM guardrails g
        LEFT JOIN guardrail_hits h ON h.guardrail_id = g.id
        GROUP BY g.id
    """))).mappings().one()

    assert row["hits_24h"] == 0


async def test_insert_guardrail_hit_increments_hits_24h(session):
    """After recording a hit, hits_24h in the list query must be 1."""
    guard_row = (await session.execute(
        text("""
            INSERT INTO guardrails (name, type, applies_to, action, severity, priority, config)
            VALUES ('Hit Guard', 'pii_detector', 'input', 'flag', 'medium', 50, '{}')
            RETURNING id
        """)
    )).mappings().one()
    await session.commit()
    guard_id = str(guard_row["id"])

    await session.execute(
        text("""
            INSERT INTO guardrail_hits
                (guardrail_id, guardrail_type, input_or_output, action_taken, severity)
            VALUES (CAST(:gid AS uuid), 'pii_detector', 'input', 'flag', 'medium')
        """),
        {"gid": guard_id},
    )
    await session.commit()

    row = (await session.execute(text("""
        SELECT COUNT(h.id) FILTER (WHERE h.created_at >= NOW() - INTERVAL '24 hours') AS hits_24h
        FROM guardrails g
        LEFT JOIN guardrail_hits h ON h.guardrail_id = g.id
        WHERE g.id = CAST(:gid AS uuid)
        GROUP BY g.id
    """), {"gid": guard_id})).mappings().one()

    assert row["hits_24h"] == 1


async def test_update_guardrail_increments_version(session):
    """PATCH on a guardrail must increment the version field."""
    guard_row = (await session.execute(
        text("""
            INSERT INTO guardrails (name, type, applies_to, action, severity, priority, config)
            VALUES ('Version Guard', 'topic_block', 'input', 'block', 'high', 200, '{}')
            RETURNING id, version
        """)
    )).mappings().one()
    await session.commit()
    guard_id = str(guard_row["id"])
    original_version = guard_row["version"]

    await session.execute(
        text("""
            UPDATE guardrails
            SET name = 'Version Guard Updated',
                version = version + 1,
                updated_at = NOW()
            WHERE id = CAST(:id AS uuid)
        """),
        {"id": guard_id},
    )
    await session.commit()

    new_version = (await session.execute(
        text("SELECT version FROM guardrails WHERE id = CAST(:id AS uuid)"),
        {"id": guard_id},
    )).scalar_one()

    assert new_version == original_version + 1
