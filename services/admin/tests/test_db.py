"""Database-level integration tests for the admin service.

Spins up a real PostgreSQL container (testcontainers) once per module,
applies the full schema via Alembic migrations (replaces the old
_EXTRA_DDL approach removed in T0), and
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

from app.db import Base

# Import ORM models so their tables are registered with Base.metadata
from app.models import (  # noqa: F401
    api_key,
    audit_log as audit_log_model,
    member,
    model_registry as model_registry_model,
    policy,
    pricing as pricing_model,
)
from app.routers.budget import _key_monthly_spend, _org_monthly_spend


# ---------------------------------------------------------------------------
# Module-scoped fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def pg_container():
    """Start a Postgres 16 container once for all DB tests in this module."""
    with PostgresContainer("pgvector/pgvector:pg16") as postgres:
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
    """Apply full schema via Alembic migrations, return a module-scoped engine."""
    import subprocess
    from pathlib import Path

    sqlalchemy_url = _sqlalchemy_url(pg_container)

    # Run `alembic upgrade head` from the service root so the relative
    # 'migrations' path in alembic.ini resolves correctly.
    service_root = Path(__file__).parents[1]
    result = subprocess.run(
        ["alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=str(service_root),
        env={**os.environ, "DATABASE_URL": sqlalchemy_url},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic upgrade failed:\n{result.stderr}\n{result.stdout}")

    engine = create_async_engine(sqlalchemy_url, echo=False)
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
    "cost_records",
    "policies",
    "api_keys",
    "projects",
    "node_members",
    "role_assignments",
    "organization_nodes",
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

import uuid as _uuid


async def _insert_node(session: AsyncSession, name="Test Team", slug=None,
                       type="team", parent_id=None) -> str:
    """Insert an organization_nodes row and return its id.

    Replaces the old _insert_team / _insert_area helpers — teams/areas tables
    were dropped in migration 0025 in favour of the organization_nodes tree.
    """
    slug = slug or name.lower().replace(" ", "-")
    nid = str(_uuid.uuid4())
    if parent_id:
        parent_path = (await session.execute(
            text("SELECT path FROM organization_nodes WHERE id = CAST(:pid AS uuid)"),
            {"pid": parent_id},
        )).scalar_one()
        path = f"{parent_path}/{nid}"
    else:
        path = f"/{nid}"
    await session.execute(
        text("""
            INSERT INTO organization_nodes (id, name, slug, type, parent_id, path)
            VALUES (CAST(:id AS uuid), :n, :s, :t, CAST(:pid AS uuid), :path)
        """),
        {"id": nid, "n": name, "s": slug, "t": type, "pid": parent_id, "path": path},
    )
    await session.commit()
    return nid


async def _insert_cost_record(session: AsyncSession, node_id: str, cost: float,
                               api_key_id: str = None, months_ago: int = 0) -> None:
    ts = f"NOW() - INTERVAL '{months_ago} months'" if months_ago else "NOW()"
    await session.execute(
        text(
            f"INSERT INTO cost_records (node_id, model, cost_usd, api_key_id, created_at) "
            f"VALUES (CAST(:nid AS uuid), 'gpt-4o', :cost, :kid, {ts})"
        ),
        {"nid": node_id, "cost": cost, "kid": api_key_id},
    )
    await session.commit()


# ===========================================================================
# ORGANIZATION NODE CRUD
#
# Rewritten from the old TEAM CRUD section. The teams/areas tables (and the
# _team_row_to_dict / area-join queries) were removed in migration 0025;
# teams are now rows in organization_nodes. Tests covering the dropped
# team↔area join and the ON DELETE CASCADE teams→projects FK are removed —
# that functionality no longer exists (projects.team_id is now a plain
# nullable column with no FK).
# ===========================================================================

async def test_insert_node_then_list_returns_it(session):
    """Insert a node via raw SQL; the list_nodes query must find it."""
    node_id = await _insert_node(session, "Alpha Squad", "alpha-squad", type="team")

    rows = (await session.execute(text("""
        SELECT id, name, slug, type, parent_id, path
        FROM organization_nodes
        ORDER BY path
    """))).mappings().all()

    assert len(rows) == 1
    assert str(rows[0]["id"]) == node_id
    assert rows[0]["name"] == "Alpha Squad"
    assert rows[0]["slug"] == "alpha-squad"
    assert rows[0]["type"] == "team"
    assert rows[0]["parent_id"] is None


async def test_node_tree_path_materialization(session):
    """A child node's path must be prefixed by its parent's path (materialized
    path inheritance — the basis for can_access prefix matching)."""
    area_id = await _insert_node(session, "Platform", "platform", type="area")
    team_id = await _insert_node(session, "Core Team", "core-team",
                                 type="team", parent_id=area_id)

    area_path = (await session.execute(
        text("SELECT path FROM organization_nodes WHERE id = CAST(:id AS uuid)"),
        {"id": area_id},
    )).scalar_one()
    team_path = (await session.execute(
        text("SELECT path FROM organization_nodes WHERE id = CAST(:id AS uuid)"),
        {"id": team_id},
    )).scalar_one()

    assert team_path.startswith(area_path + "/")
    assert team_path == f"{area_path}/{team_id}"


async def test_delete_parent_cascades_to_children(session):
    """Deleting a parent node CASCADE-deletes descendants
    (organization_nodes.parent_id ON DELETE CASCADE)."""
    area_id = await _insert_node(session, "Doomed Area", "doomed-area", type="area")
    await _insert_node(session, "Doomed Team", "doomed-team",
                       type="team", parent_id=area_id)

    count_before = (await session.execute(
        text("SELECT COUNT(*) FROM organization_nodes WHERE parent_id = CAST(:pid AS uuid)"),
        {"pid": area_id},
    )).scalar()
    assert count_before == 1

    await session.execute(
        text("DELETE FROM organization_nodes WHERE id = CAST(:id AS uuid)"), {"id": area_id}
    )
    await session.commit()

    total_after = (await session.execute(
        text("SELECT COUNT(*) FROM organization_nodes")
    )).scalar()
    assert total_after == 0


async def test_unique_path_constraint_raises(session):
    """organization_nodes.path is UNIQUE — two nodes cannot share a path."""
    nid = await _insert_node(session, "Node One", "node-one", type="team")
    dup_path = (await session.execute(
        text("SELECT path FROM organization_nodes WHERE id = CAST(:id AS uuid)"),
        {"id": nid},
    )).scalar_one()

    import asyncpg as _apg
    from sqlalchemy.exc import IntegrityError
    with pytest.raises((IntegrityError, _apg.UniqueViolationError, Exception)):
        await session.execute(
            text("INSERT INTO organization_nodes (name, slug, type, path) "
                 "VALUES (:n, :s, 'team', :p)"),
            {"n": "Node Two", "s": "node-two", "p": dup_path},
        )
        await session.commit()


async def test_unique_parent_slug_constraint_raises(session):
    """organization_nodes has UNIQUE(parent_id, slug) — two siblings cannot
    share a slug under the same parent."""
    area_id = await _insert_node(session, "Parent Area", "parent-area", type="area")
    await _insert_node(session, "Dup", "dup-slug", type="team", parent_id=area_id)

    import asyncpg as _apg
    from sqlalchemy.exc import IntegrityError
    with pytest.raises((IntegrityError, _apg.UniqueViolationError, Exception)):
        # Same slug under the same parent — distinct path so only the
        # (parent_id, slug) constraint can fire.
        await session.execute(
            text("""
                INSERT INTO organization_nodes (name, slug, type, parent_id, path)
                VALUES (:n, 'dup-slug', 'team', CAST(:pid AS uuid), :path)
            """),
            {"n": "Dup Two", "pid": area_id, "path": f"/{area_id}/other"},
        )
        await session.commit()


# ===========================================================================
# BUDGET SQL
# ===========================================================================

# _team_monthly_spend tests REMOVED — the helper queried cost_records.team_id,
# a column dropped in migration 0025 (cost_records now uses node_id), and the
# helper itself was removed. Per-node spend is covered by nodes.py budget rollup.


async def test_key_monthly_spend_sums_correctly(session):
    """_key_monthly_spend aggregates by api_key_id, current month only."""
    node_id = await _insert_node(session, "Key Spend Team", "key-spend-team")
    # Create an API key row directly (api_keys.team_id → node_id in migration 0025)
    row = (await session.execute(
        text(
            "INSERT INTO api_keys (node_id, name, key_hash) "
            "VALUES (CAST(:nid AS uuid), :n, :kh) RETURNING id"
        ),
        {"nid": node_id, "n": "test-key", "kh": "hash-abc-123"},
    )).mappings().one()
    await session.commit()
    key_id = str(row["id"])

    await _insert_cost_record(session, node_id, 0.5, api_key_id=key_id, months_ago=0)
    await _insert_cost_record(session, node_id, 0.25, api_key_id=key_id, months_ago=0)
    await _insert_cost_record(session, node_id, 10.0, api_key_id=key_id, months_ago=1)  # excluded

    from uuid import UUID
    spend = await _key_monthly_spend(session, UUID(key_id))
    assert abs(spend - 0.75) < 1e-6


async def test_org_monthly_spend_sums_all_nodes(session):
    """_org_monthly_spend totals cost_records across all nodes this month."""
    n1 = await _insert_node(session, "Org Team 1", "org-team-1")
    n2 = await _insert_node(session, "Org Team 2", "org-team-2")
    await _insert_cost_record(session, n1, 1.0, months_ago=0)
    await _insert_cost_record(session, n2, 2.0, months_ago=0)
    await _insert_cost_record(session, n1, 50.0, months_ago=3)  # must be excluded

    spend = await _org_monthly_spend(session)
    assert abs(spend - 3.0) < 1e-6


async def test_budget_status_aggregates_multiple_nodes(session):
    """The budget_status GROUP BY query correctly computes per-node spend
    (cost_records.team_id → node_id, joined to organization_nodes)."""
    n1 = await _insert_node(session, "Agg Team A", "agg-team-a")
    n2 = await _insert_node(session, "Agg Team B", "agg-team-b")
    await _insert_cost_record(session, n1, 2.0, months_ago=0)
    await _insert_cost_record(session, n1, 3.0, months_ago=0)
    await _insert_cost_record(session, n2, 1.5, months_ago=0)

    rows = (await session.execute(text("""
        SELECT n.id, n.name,
               COALESCE(SUM(cr.cost_usd), 0) AS spend
        FROM organization_nodes n
        LEFT JOIN cost_records cr
               ON cr.node_id = n.id
              AND cr.created_at >= date_trunc('month', NOW())
        GROUP BY n.id, n.name
        ORDER BY n.name
    """))).mappings().all()

    by_name = {r["name"]: float(r["spend"]) for r in rows}
    assert abs(by_name["Agg Team A"] - 5.0) < 1e-6
    assert abs(by_name["Agg Team B"] - 1.5) < 1e-6


# ===========================================================================
# POLICY UPSERT (ON CONFLICT partial indexes)
# ===========================================================================

async def test_upsert_policy_inserts_new_row(session):
    """First upsert with project_id=None creates a policy row.

    policies.team_id was renamed to node_id in migration 0025, and the partial
    unique indexes are now policies_node_null_proj_uidx / policies_node_proj_uidx.
    """
    node_id = await _insert_node(session, "Policy Team", "policy-team")

    await session.execute(
        text("""
            INSERT INTO policies (node_id, project_id, cache_ttl_seconds, cache_similarity_threshold,
                                  cache_opt_out, embedding_model, rate_limit_rpm, allowed_models)
            VALUES (CAST(:nid AS uuid), NULL, 7200, 0.90, FALSE, 'text-embedding-3-small', 500, ARRAY[]::TEXT[])
            ON CONFLICT (node_id) WHERE project_id IS NULL
            DO UPDATE
                SET cache_ttl_seconds = EXCLUDED.cache_ttl_seconds,
                    cache_similarity_threshold = EXCLUDED.cache_similarity_threshold,
                    cache_opt_out = EXCLUDED.cache_opt_out,
                    embedding_model = EXCLUDED.embedding_model,
                    rate_limit_rpm = EXCLUDED.rate_limit_rpm,
                    allowed_models = EXCLUDED.allowed_models
        """),
        {"nid": node_id},
    )
    await session.commit()

    count = (await session.execute(
        text("SELECT COUNT(*) FROM policies WHERE node_id = CAST(:nid AS uuid)"),
        {"nid": node_id},
    )).scalar()
    assert count == 1


async def test_upsert_policy_second_call_updates_not_duplicates(session):
    """Second upsert for same node_id+project_id=None updates instead of inserting."""
    node_id = await _insert_node(session, "Upsert Team", "upsert-team")

    upsert_sql = text("""
        INSERT INTO policies (node_id, project_id, cache_ttl_seconds, cache_similarity_threshold,
                              cache_opt_out, embedding_model, rate_limit_rpm, allowed_models)
        VALUES (CAST(:nid AS uuid), NULL, :ttl, 0.95, FALSE, 'text-embedding-3-small', 1000, ARRAY[]::TEXT[])
        ON CONFLICT (node_id) WHERE project_id IS NULL
        DO UPDATE SET cache_ttl_seconds = EXCLUDED.cache_ttl_seconds
    """)

    await session.execute(upsert_sql, {"nid": node_id, "ttl": 3600})
    await session.commit()
    await session.execute(upsert_sql, {"nid": node_id, "ttl": 7200})
    await session.commit()

    rows = (await session.execute(
        text("SELECT cache_ttl_seconds FROM policies WHERE node_id = CAST(:nid AS uuid)"),
        {"nid": node_id},
    )).fetchall()

    assert len(rows) == 1
    assert rows[0][0] == 7200


async def test_upsert_policy_project_none_vs_uuid_creates_two_rows(session):
    """project_id=NULL and project_id=<uuid> must produce two separate policy rows.

    The schema has two separate partial indexes for these cases (migration 0025):
      - policies_node_null_proj_uidx ON (node_id) WHERE project_id IS NULL
      - policies_node_proj_uidx ON (node_id, project_id) WHERE project_id IS NOT NULL
    """
    node_id = await _insert_node(session, "Dual Policy Team", "dual-policy-team")

    # projects.team_id is now a plain nullable column (FK to teams dropped); we
    # only need a project id to key the project-level policy.
    proj_row = (await session.execute(
        text("INSERT INTO projects (team_id, name, slug) VALUES (CAST(:tid AS uuid), 'P', 'p') RETURNING id"),
        {"tid": node_id},
    )).mappings().one()
    await session.commit()
    proj_id = str(proj_row["id"])

    # Insert node-level policy (project_id IS NULL)
    await session.execute(
        text("""
            INSERT INTO policies (node_id, project_id, cache_ttl_seconds, cache_similarity_threshold,
                                  cache_opt_out, embedding_model, rate_limit_rpm, allowed_models)
            VALUES (CAST(:nid AS uuid), NULL, 3600, 0.95, FALSE, 'text-embedding-3-small', 1000, ARRAY[]::TEXT[])
            ON CONFLICT (node_id) WHERE project_id IS NULL
            DO UPDATE SET cache_ttl_seconds = EXCLUDED.cache_ttl_seconds
        """),
        {"nid": node_id},
    )
    # Insert project-level policy (project_id IS NOT NULL)
    await session.execute(
        text("""
            INSERT INTO policies (node_id, project_id, cache_ttl_seconds, cache_similarity_threshold,
                                  cache_opt_out, embedding_model, rate_limit_rpm, allowed_models)
            VALUES (CAST(:nid AS uuid), CAST(:pid AS uuid), 1800, 0.80, FALSE, 'text-embedding-3-small', 500, ARRAY[]::TEXT[])
            ON CONFLICT (node_id, project_id) WHERE project_id IS NOT NULL
            DO UPDATE SET cache_ttl_seconds = EXCLUDED.cache_ttl_seconds
        """),
        {"nid": node_id, "pid": proj_id},
    )
    await session.commit()

    count = (await session.execute(
        text("SELECT COUNT(*) FROM policies WHERE node_id = CAST(:nid AS uuid)"),
        {"nid": node_id},
    )).scalar()
    assert count == 2


# ===========================================================================
# AREAS SQL — REMOVED
#
# The areas and area_policies tables and the teams.area_id FK were dropped in
# migration 0025. Area-as-a-row is now an organization_nodes row with
# type='area', covered by the ORGANIZATION NODE CRUD tests above (tree path
# materialization, cascade delete). The old team_count / SET-NULL / area_policy
# upsert tests are gone because that schema no longer exists.
# ===========================================================================


# ===========================================================================
# API KEYS  (api_keys.team_id → node_id in migration 0025)
# ===========================================================================

async def test_create_key_hashes_the_key(session):
    """create_key stores a sha256 hash — key_hash must differ from the raw key."""
    node_id = await _insert_node(session, "Key Team", "key-team")
    import secrets
    raw_key = "sk-" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    await session.execute(
        text(
            "INSERT INTO api_keys (node_id, name, key_hash) "
            "VALUES (CAST(:nid AS uuid), :n, :kh)"
        ),
        {"nid": node_id, "n": "my-key", "kh": key_hash},
    )
    await session.commit()

    stored = (await session.execute(
        text("SELECT key_hash FROM api_keys WHERE node_id = CAST(:nid AS uuid)"),
        {"nid": node_id},
    )).scalar_one()

    assert stored == key_hash
    assert stored != raw_key


async def test_revoke_key_sets_revoked_at(session):
    """Revoking a key must set revoked_at to a non-NULL timestamp."""
    node_id = await _insert_node(session, "Revoke Team", "revoke-team")
    key_row = (await session.execute(
        text(
            "INSERT INTO api_keys (node_id, name, key_hash) "
            "VALUES (CAST(:nid AS uuid), :n, :kh) RETURNING id"
        ),
        {"nid": node_id, "n": "rev-key", "kh": "hash-rev-000"},
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
    node_id = await _insert_node(session, "Filter Team", "filter-team")

    # Active key
    await session.execute(
        text(
            "INSERT INTO api_keys (node_id, name, key_hash) "
            "VALUES (CAST(:nid AS uuid), :n, :kh)"
        ),
        {"nid": node_id, "n": "active-key", "kh": "hash-active-001"},
    )
    # Revoked key
    await session.execute(
        text(
            "INSERT INTO api_keys (node_id, name, key_hash, revoked_at) "
            "VALUES (CAST(:nid AS uuid), :n, :kh, NOW())"
        ),
        {"nid": node_id, "n": "revoked-key", "kh": "hash-revoked-002"},
    )
    await session.commit()

    active_keys = (await session.execute(
        text(
            "SELECT id FROM api_keys "
            "WHERE node_id = CAST(:nid AS uuid) AND revoked_at IS NULL"
        ),
        {"nid": node_id},
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
