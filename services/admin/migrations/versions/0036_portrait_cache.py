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
            developer_id  UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
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
