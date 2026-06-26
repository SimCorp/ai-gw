"""Training signal capture — Stage 1 of the model optimization flywheel.

Adds per-key and per-org opt-in flags and a training_candidates table for
prompt/completion capture. Both flags default FALSE; production capture
requires a completed DPA review before any node is toggled on.

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
    op.execute(
        "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS capture_content BOOL NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE organization_nodes ADD COLUMN IF NOT EXISTS "
        "training_capture_enabled BOOL NOT NULL DEFAULT FALSE"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS training_candidates (
            id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            session_trace_id TEXT,
            team_id          TEXT        NOT NULL,
            model            TEXT,
            prompt           TEXT        NOT NULL,
            completion       TEXT        NOT NULL,
            latency_ms       INT,
            explicit_rating  SMALLINT,
            exported_at      TIMESTAMPTZ,
            captured_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # Supports export queries (team + unexported) and 90-day retention scan
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_training_candidates_export "
        "ON training_candidates (team_id, exported_at, captured_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_training_candidates_retention "
        "ON training_candidates (captured_at) WHERE exported_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS training_candidates")
    op.execute("ALTER TABLE organization_nodes DROP COLUMN IF EXISTS training_capture_enabled")
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS capture_content")
