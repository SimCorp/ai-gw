"""Alembic environment for the admin service.

Runs migrations using a sync (psycopg2) URL even though the app uses asyncpg
at runtime. Autogenerate respects an include_object filter that skips tables
managed by raw SQL (not ORM-mapped) so autogenerate diffs only reflect drift
on tables we actually own through SQLAlchemy models.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make app importable when running `alembic upgrade head` from this dir
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import Base + all ORM models so their metadata is registered
from app.db import Base  # noqa: E402
from app.models import (  # noqa: E402,F401
    agent,
    api_key,
    area,
    area_policy,
    audit_log,
    mcp,
    member,
    model_registry,
    plugin,
    policy,
    pricing,
    team,
    workflow,
    workflow_run,
)

# Tables that are managed by raw-SQL migrations (not ORM-mapped).
# autogenerate must NOT propose dropping these even though no model exists.
NON_ORM_TABLES = {
    "developers",
    "developer_activity_log",
    "developer_output_events",
    "sessions",
    "org_settings",
    "admin_users",
    "cost_records",
    "ai_insights",
    "guardrails",
    "guardrail_hits",
}


def include_object(obj, name, type_, reflected, compare_to):
    # Skip non-ORM raw-SQL tables
    if type_ == "table" and name in NON_ORM_TABLES:
        return False
    # Skip LiteLLM Prisma-managed tables (share the same DB, owned by LiteLLM)
    if type_ == "table" and (name.startswith("LiteLLM_") or name.startswith("_prisma")):
        return False
    # Skip provider_keys table (created lazily by settings router, not in ORM)
    if type_ == "table" and name == "provider_keys":
        return False
    # Skip tables from other services that share the same Postgres database
    # (identity service, librarian service — managed by their own startup DDL)
    if type_ == "table" and name in {
        "agent_identities", "knowledge_items", "research_topics",
    }:
        return False
    # These indexes were created via raw SQL in the baseline migration with DESC
    # column ordering. Alembic can't compare them cleanly because the column
    # spec differs between raw SQL and the ORM Index() definition. They work
    # correctly in the DB; we exclude them from autogenerate to avoid noise.
    _RAW_SQL_INDEXES = {
        "idx_workflow_runs_team_created",
        "audit_log_timestamp_idx",
        "idx_workflows_team",
    }
    if type_ == "index" and name in _RAW_SQL_INDEXES:
        return False

    # Skip FK constraints that reference non-ORM tables (developers, etc.) —
    # these exist in the DB via the baseline migration but aren't declared in
    # models because the target tables are excluded from ORM mapping.
    if type_ == "foreign_key_constraint":
        try:
            for fk in obj.elements:
                referred_table = fk.column.table.name if fk.column is not None else ""
                if referred_table in NON_ORM_TABLES:
                    return False
        except Exception:
            pass
    return True


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Allow DATABASE_URL env var to override the placeholder in alembic.ini.
# Always coerce to sync psycopg2 driver (Alembic operations are synchronous).
db_url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
db_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
db_url = db_url.replace("postgresql://", "postgresql+psycopg2://")
config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=False,  # VARCHAR vs TEXT is cosmetic; suppress noise
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
