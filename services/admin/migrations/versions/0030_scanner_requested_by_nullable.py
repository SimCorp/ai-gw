"""Make scan_jobs.requested_by nullable for API key callers"""
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE scan_jobs ALTER COLUMN requested_by DROP NOT NULL")
    op.execute("ALTER TABLE scan_jobs ALTER COLUMN requested_by DROP CONSTRAINT IF EXISTS scan_jobs_requested_by_fkey")


def downgrade():
    op.execute("ALTER TABLE scan_jobs ALTER COLUMN requested_by SET NOT NULL")
