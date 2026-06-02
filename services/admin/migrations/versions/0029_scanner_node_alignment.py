"""Align scanner tables and organization_nodes with the org-nodes model"""

from typing import Sequence, Union

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Add scanner_quota to organization_nodes
    op.execute("""
        ALTER TABLE organization_nodes
        ADD COLUMN IF NOT EXISTS scanner_quota JSONB NOT NULL
        DEFAULT '{"daily_limit": 3, "allow_external_targets": false, "max_tier": "quick"}'::jsonb
    """)

    # Rename scan_targets.team_id → node_id.
    # On a fresh chain, 0026 already created scan_targets with a node_id column
    # (and its inline FK), so there is no team_id to rename — guard the whole
    # block on the legacy team_id column actually being present.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'scan_targets' AND column_name = 'team_id'
            ) THEN
                ALTER TABLE scan_targets RENAME COLUMN team_id TO node_id;
                ALTER TABLE scan_targets
                    ADD CONSTRAINT scan_targets_node_id_fkey
                    FOREIGN KEY (node_id) REFERENCES organization_nodes(id)
                    ON DELETE SET NULL NOT VALID;
                ALTER TABLE scan_targets ALTER COLUMN node_id DROP NOT NULL;
            END IF;
        END $$;
    """)

    # Rename scan_jobs.team_id → node_id (same fresh-vs-legacy guard).
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'scan_jobs' AND column_name = 'team_id'
            ) THEN
                ALTER TABLE scan_jobs RENAME COLUMN team_id TO node_id;
                ALTER TABLE scan_jobs
                    ADD CONSTRAINT scan_jobs_node_id_fkey
                    FOREIGN KEY (node_id) REFERENCES organization_nodes(id)
                    ON DELETE SET NULL NOT VALID;
                ALTER TABLE scan_jobs ALTER COLUMN node_id DROP NOT NULL;
            END IF;
        END $$;
    """)
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
