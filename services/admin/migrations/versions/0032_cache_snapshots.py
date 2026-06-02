"""Add cache_snapshots table for time-series analytics"""

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS cache_snapshots (
            id          BIGSERIAL PRIMARY KEY,
            captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            hit_rate    NUMERIC(5,4),  -- 0.0-1.0
            requests_60s INT,
            redis_mem_mb NUMERIC(8,2),
            redis_ping_ms NUMERIC(8,2)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cache_snapshots_captured_at ON cache_snapshots(captured_at DESC)"
    )
    # Retention: keep only 30 days (managed by application DELETE on insert)


def downgrade():
    op.execute("DROP TABLE IF EXISTS cache_snapshots")
