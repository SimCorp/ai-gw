"""Agentic transformation: session_type, achievements, leaderboard opt-in

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-13
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Session type classification
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE session_type_enum AS ENUM ('interactive', 'agentic', 'autonomous');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    op.execute("""
        ALTER TABLE sessions
        ADD COLUMN IF NOT EXISTS session_type session_type_enum
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_type
        ON sessions (session_type, first_request_at DESC)
    """)

    # Developer achievements
    op.execute("""
        CREATE TABLE IF NOT EXISTS developer_achievements (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            developer_id    UUID NOT NULL REFERENCES developers(id) ON DELETE CASCADE,
            achievement     TEXT NOT NULL,
            earned_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            metadata        JSONB,
            UNIQUE (developer_id, achievement)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_achievements_developer
        ON developer_achievements (developer_id, earned_at DESC)
    """)

    # Leaderboard opt-in (one row per developer per scope)
    op.execute("""
        CREATE TABLE IF NOT EXISTS developer_leaderboard_opt_in (
            developer_id    UUID NOT NULL REFERENCES developers(id) ON DELETE CASCADE,
            scope           TEXT NOT NULL CHECK (scope IN ('team', 'company')),
            opted_in_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (developer_id, scope)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS developer_leaderboard_opt_in")
    op.execute("DROP TABLE IF EXISTS developer_achievements")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS session_type")
    op.execute("DROP TYPE IF EXISTS session_type_enum")
