# services/admin/migrations/versions/0025_security_scanner.py
"""Add security scanner tables"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY, TEXT
from typing import Sequence, Union

revision = "0025"
down_revision = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        "scan_targets",
        sa.Column("id", UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("team_id", UUID(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("openapi_spec_url", sa.Text(), nullable=True),
        sa.Column("allowed_scan_types", ARRAY(TEXT), nullable=False, server_default=sa.text("ARRAY['ai','api','network']::text[]")),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending_approval"),
        sa.Column("approved_by", UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_table(
        "scan_jobs",
        sa.Column("id", UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("team_id", UUID(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("target_id", UUID(), sa.ForeignKey("scan_targets.id"), nullable=False),
        sa.Column("requested_by", UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scan_types", ARRAY(TEXT), nullable=False),
        sa.Column("tier", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("trigger", sa.Text(), nullable=False, server_default="manual"),
        sa.Column("ci_ref", sa.Text(), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("worker_id", sa.Text(), nullable=True),
        sa.Column("partial_results", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_table(
        "scan_findings",
        sa.Column("id", UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("job_id", UUID(), sa.ForeignKey("scan_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scanner", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", JSONB(), nullable=True),
        sa.Column("remediation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_scan_findings_job_id", "scan_findings", ["job_id"])
    op.create_index("ix_scan_findings_severity", "scan_findings", ["severity"])
    op.create_index("ix_scan_jobs_team_id", "scan_jobs", ["team_id"])
    op.add_column(
        "teams",
        sa.Column(
            "scanner_quota",
            JSONB(),
            nullable=False,
            server_default=sa.text('\'{"daily_limit": 3, "allow_external_targets": false, "max_tier": "quick"}\'::jsonb'),
        ),
    )


def downgrade():
    op.drop_column("teams", "scanner_quota")
    op.drop_index("ix_scan_findings_severity")
    op.drop_index("ix_scan_findings_job_id")
    op.drop_index("ix_scan_jobs_team_id")
    op.drop_table("scan_findings")
    op.drop_table("scan_jobs")
    op.drop_table("scan_targets")
