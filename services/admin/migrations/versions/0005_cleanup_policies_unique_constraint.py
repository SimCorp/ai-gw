"""cleanup: drop stale policies_team_id_project_id_key constraint

The original UNIQUE(team_id, project_id) constraint on the policies table
was replaced in migration 0001 with two partial unique indexes
(policies_team_null_proj_uidx and policies_team_proj_uidx) to support
ON CONFLICT with nullable project_id. The old non-partial constraint was
never explicitly dropped and still exists in databases migrated from init.sql.

This migration removes it.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-12
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE policies DROP CONSTRAINT IF EXISTS policies_team_id_project_id_key")


def downgrade() -> None:
    # Restore the non-partial unique constraint (note: partial indexes still exist)
    op.execute(
        "ALTER TABLE policies ADD CONSTRAINT policies_team_id_project_id_key "
        "UNIQUE (team_id, project_id)"
    )
