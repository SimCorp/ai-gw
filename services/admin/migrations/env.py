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
    if type_ == "table" and name in NON_ORM_TABLES:
        return False
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
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
