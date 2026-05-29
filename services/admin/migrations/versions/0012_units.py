"""Add units table — intermediate level between areas and teams

Revision ID: 0012
Revises: 0011
"""
from typing import Sequence, Union

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # units table
    op.execute("""
        CREATE TABLE IF NOT EXISTS units (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            area_id     UUID NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
            name        TEXT NOT NULL,
            slug        TEXT NOT NULL,
            description TEXT,
            color       TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(area_id, slug)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_units_area_id ON units(area_id)")

    # add unit_id to teams (nullable for migration safety)
    op.execute("ALTER TABLE teams ADD COLUMN IF NOT EXISTS unit_id UUID REFERENCES units(id) ON DELETE SET NULL")
    op.execute("CREATE INDEX IF NOT EXISTS idx_teams_unit_id ON teams(unit_id)")

    # backfill: for each area, create a "General" unit and assign existing teams to it
    op.execute("""
        INSERT INTO units (area_id, name, slug, description)
        SELECT id, 'General', 'general', 'Default unit — created automatically during migration'
        FROM areas
        ON CONFLICT DO NOTHING
    """)
    op.execute("""
        UPDATE teams t
        SET unit_id = u.id
        FROM units u
        WHERE u.area_id = t.area_id AND u.slug = 'general'
          AND t.unit_id IS NULL
    """)


def downgrade():
    op.execute("ALTER TABLE teams DROP COLUMN IF EXISTS unit_id")
    op.execute("DROP TABLE IF EXISTS units")
