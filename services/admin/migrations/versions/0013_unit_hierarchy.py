"""Add parent_unit_id to units for nested hierarchy (AD-style OU nesting)

Revision ID: 0013
Revises: 0012
"""
from typing import Sequence, Union

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("""
        ALTER TABLE units
        ADD COLUMN IF NOT EXISTS parent_unit_id UUID REFERENCES units(id) ON DELETE SET NULL
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_units_parent_unit_id ON units(parent_unit_id)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_units_parent_unit_id")
    op.execute("ALTER TABLE units DROP COLUMN IF EXISTS parent_unit_id")
