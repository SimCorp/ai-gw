"""Role taxonomy rename + direct user assignments on role_assignments.

Changes:
  - platform_admin → gateway_admin (rename in DB)
  - developer → engineer (rename in DB)
  - viewer → reporter (rename in DB)
  - area_owner / unit_lead / team_admin: unchanged
  - entra_group_id: made nullable (to allow user-based rows)
  - user_id UUID: new column for direct user role assignments
  - Mutual exclusion: exactly one of (entra_group_id, user_id) must be set
"""

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. Rename roles ───────────────────────────────────────────────────────
    op.execute("UPDATE role_assignments SET role = 'gateway_admin' WHERE role = 'platform_admin'")
    op.execute("UPDATE role_assignments SET role = 'engineer'       WHERE role = 'developer'")
    op.execute("UPDATE role_assignments SET role = 'reporter'       WHERE role = 'viewer'")

    # ── 2. Replace role CHECK constraint ─────────────────────────────────────
    op.execute("ALTER TABLE role_assignments DROP CONSTRAINT IF EXISTS role_assignments_role_check")
    op.execute("""
        ALTER TABLE role_assignments
        ADD CONSTRAINT role_assignments_role_check
        CHECK (role IN ('gateway_admin','area_owner','unit_lead','team_admin','engineer','reporter'))
    """)

    # ── 3. Make entra_group_id nullable (user-based rows won't have it) ───────
    op.execute("ALTER TABLE role_assignments ALTER COLUMN entra_group_id DROP NOT NULL")

    # ── 4. Add user_id column ─────────────────────────────────────────────────
    op.execute("""
        ALTER TABLE role_assignments
        ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE CASCADE
    """)

    # ── 5. Mutual exclusion: exactly one subject ──────────────────────────────
    op.execute("""
        ALTER TABLE role_assignments
        ADD CONSTRAINT role_assignments_subject_check
        CHECK (
            (user_id IS NOT NULL AND entra_group_id IS NULL) OR
            (user_id IS NULL     AND entra_group_id IS NOT NULL)
        )
    """)

    # ── 6. Indexes for user_id lookups ────────────────────────────────────────
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_role_assignments_user ON role_assignments(user_id)"
    )
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_ra_user_role_node
        ON role_assignments(user_id, role, node_id)
        WHERE user_id IS NOT NULL
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_ra_user_role_node")
    op.execute("DROP INDEX IF EXISTS idx_role_assignments_user")
    op.execute(
        "ALTER TABLE role_assignments DROP CONSTRAINT IF EXISTS role_assignments_subject_check"
    )
    op.execute("ALTER TABLE role_assignments DROP COLUMN IF EXISTS user_id")
    op.execute("ALTER TABLE role_assignments ALTER COLUMN entra_group_id SET NOT NULL")
    op.execute("ALTER TABLE role_assignments DROP CONSTRAINT IF EXISTS role_assignments_role_check")
    op.execute("""
        ALTER TABLE role_assignments
        ADD CONSTRAINT role_assignments_role_check
        CHECK (role IN ('platform_admin','area_owner','unit_lead','team_admin','developer','viewer'))
    """)
    op.execute("UPDATE role_assignments SET role = 'platform_admin' WHERE role = 'gateway_admin'")
    op.execute("UPDATE role_assignments SET role = 'developer'       WHERE role = 'engineer'")
    op.execute("UPDATE role_assignments SET role = 'viewer'          WHERE role = 'reporter'")
