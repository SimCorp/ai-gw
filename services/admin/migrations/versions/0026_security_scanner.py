# services/admin/migrations/versions/0025_security_scanner.py
"""Add security scanner tables"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY, TEXT
from typing import Sequence, Union

revision = "0026"
down_revision = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # scan_targets, scan_jobs, scan_findings were created by an earlier migration
    # path before this migration was formally numbered.  The tables already exist
    # in the live DB, so this upgrade is a no-op for schema changes.
    # The teams.scanner_quota column add is also skipped because the teams table
    # was dropped in migration 0025 (org_nodes refactor).
    # If running against a truly clean DB, the tables must be created via raw SQL:
    conn = op.get_bind()
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS scan_targets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            node_id UUID REFERENCES organization_nodes(id) ON DELETE SET NULL,
            url TEXT NOT NULL,
            label TEXT NOT NULL,
            openapi_spec_url TEXT,
            allowed_scan_types TEXT[] NOT NULL DEFAULT ARRAY['ai','api','network']::text[],
            status TEXT NOT NULL DEFAULT 'pending_approval',
            approved_by UUID REFERENCES users(id),
            approved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_by UUID REFERENCES users(id) NOT NULL,
            notes TEXT
        )
    """))
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS scan_jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            node_id UUID REFERENCES organization_nodes(id) ON DELETE SET NULL,
            target_id UUID REFERENCES scan_targets(id),
            requested_by UUID REFERENCES users(id) NOT NULL,
            scan_types TEXT[] NOT NULL,
            tier TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            trigger TEXT NOT NULL DEFAULT 'manual',
            ci_ref TEXT,
            queued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            error_message TEXT,
            worker_id TEXT,
            partial_results BOOLEAN NOT NULL DEFAULT false
        )
    """))
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS scan_findings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            job_id UUID REFERENCES scan_jobs(id) ON DELETE CASCADE NOT NULL,
            scanner TEXT NOT NULL,
            severity TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            evidence JSONB,
            remediation TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_scan_findings_job_id ON scan_findings(job_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_scan_findings_severity ON scan_findings(severity)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_scan_jobs_node_id ON scan_jobs(node_id)"))
    conn.execute(sa.text("""
        ALTER TABLE organization_nodes
        ADD COLUMN IF NOT EXISTS scanner_quota JSONB NOT NULL
        DEFAULT '{"daily_limit": 3, "allow_external_targets": false, "max_tier": "quick"}'::jsonb
    """))


def downgrade():
    op.drop_index("ix_scan_findings_severity")
    op.drop_index("ix_scan_findings_job_id")
    op.drop_index("ix_scan_jobs_node_id")
    op.drop_table("scan_findings")
    op.drop_table("scan_jobs")
    op.drop_table("scan_targets")
    op.drop_column("organization_nodes", "scanner_quota")
