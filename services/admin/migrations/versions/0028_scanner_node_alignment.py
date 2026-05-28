"""Align scanner tables and organization_nodes with the org-nodes model"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union

revision = "0028"
down_revision = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Add scanner_quota to organization_nodes
    op.execute("""
        ALTER TABLE organization_nodes
        ADD COLUMN IF NOT EXISTS scanner_quota JSONB NOT NULL
        DEFAULT '{"daily_limit": 3, "allow_external_targets": false, "max_tier": "quick"}'::jsonb
    """)

    # Rename scan_targets.team_id → node_id
    op.execute("ALTER TABLE scan_targets RENAME COLUMN team_id TO node_id")
    op.execute("""
        ALTER TABLE scan_targets
        ADD CONSTRAINT scan_targets_node_id_fkey
        FOREIGN KEY (node_id) REFERENCES organization_nodes(id)
        ON DELETE SET NULL
        NOT VALID
    """)
    op.execute("ALTER TABLE scan_targets ALTER COLUMN node_id DROP NOT NULL")

    # Rename scan_jobs.team_id → node_id
    op.execute("ALTER TABLE scan_jobs RENAME COLUMN team_id TO node_id")
    op.execute("""
        ALTER TABLE scan_jobs
        ADD CONSTRAINT scan_jobs_node_id_fkey
        FOREIGN KEY (node_id) REFERENCES organization_nodes(id)
        ON DELETE SET NULL
        NOT VALID
    """)
    op.execute("ALTER TABLE scan_jobs ALTER COLUMN node_id DROP NOT NULL")
    op.execute("DROP INDEX IF EXISTS ix_scan_jobs_team_id")
    op.execute("CREATE INDEX IF NOT EXISTS ix_scan_jobs_node_id ON scan_jobs(node_id)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_scan_jobs_node_id")
    op.execute("CREATE INDEX IF NOT EXISTS ix_scan_jobs_team_id ON scan_jobs(node_id)")
    op.execute("ALTER TABLE scan_jobs DROP CONSTRAINT IF EXISTS scan_jobs_node_id_fkey")
    op.execute("ALTER TABLE scan_jobs RENAME COLUMN node_id TO team_id")
    op.execute("ALTER TABLE scan_jobs ALTER COLUMN team_id SET NOT NULL")
    op.execute("ALTER TABLE scan_targets DROP CONSTRAINT IF EXISTS scan_targets_node_id_fkey")
    op.execute("ALTER TABLE scan_targets RENAME COLUMN node_id TO team_id")
    op.execute("ALTER TABLE scan_targets ALTER COLUMN team_id SET NOT NULL")
    op.execute("ALTER TABLE organization_nodes DROP COLUMN IF EXISTS scanner_quota")
