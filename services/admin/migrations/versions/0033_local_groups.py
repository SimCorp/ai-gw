"""Add local_groups + local_group_members for unmanaged (local-account) identities.

Local accounts (bcrypt login, no Entra group) get real roles by being members
of a local group that is bound to an organization node via a role_assignments
row. The role_assignments.entra_group_id column is reused as a generic group
key — it holds either an Entra group GUID or a local group id namespaced
``lcl-<uuid>`` (so the two namespaces never collide).
"""

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS local_groups (
            id         TEXT PRIMARY KEY,
            name       TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS local_group_members (
            group_id TEXT NOT NULL REFERENCES local_groups(id) ON DELETE CASCADE,
            user_id  UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            PRIMARY KEY (group_id, user_id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_local_group_members_user ON local_group_members(user_id)"
    )
    # role_assignments.entra_group_id is a generic group key: an Entra group GUID
    # or a local group id (lcl-<uuid>). Local groups bind to a node via a normal
    # role_assignments row whose entra_group_id holds the lcl-... id.
    op.execute(
        "COMMENT ON COLUMN role_assignments.entra_group_id IS "
        "'Generic group key: Entra group GUID or local group id (lcl-<uuid>)'"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS local_group_members")
    op.execute("DROP TABLE IF EXISTS local_groups")
    op.execute("COMMENT ON COLUMN role_assignments.entra_group_id IS NULL")
