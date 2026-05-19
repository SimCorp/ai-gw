"""Add unit_lead to user_invitations role check; add unit to scope_type check

Revision ID: 0015
Revises: 0014
"""
from alembic import op
from typing import Sequence, Union

revision = "0015"
down_revision = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("""
        ALTER TABLE user_invitations
        DROP CONSTRAINT IF EXISTS user_invitations_role_check
    """)
    op.execute("""
        ALTER TABLE user_invitations
        ADD CONSTRAINT user_invitations_role_check
        CHECK (role = ANY (ARRAY[
            'platform_admin', 'area_owner', 'unit_lead',
            'team_admin', 'developer', 'viewer', 'service_account'
        ]))
    """)

    op.execute("""
        ALTER TABLE user_invitations
        DROP CONSTRAINT IF EXISTS user_invitations_scope_type_check
    """)
    op.execute("""
        ALTER TABLE user_invitations
        ADD CONSTRAINT user_invitations_scope_type_check
        CHECK (scope_type = ANY (ARRAY['global', 'area', 'unit', 'team']))
    """)


def downgrade():
    op.execute("ALTER TABLE user_invitations DROP CONSTRAINT IF EXISTS user_invitations_role_check")
    op.execute("""
        ALTER TABLE user_invitations
        ADD CONSTRAINT user_invitations_role_check
        CHECK (role = ANY (ARRAY[
            'platform_admin', 'area_owner', 'team_admin',
            'developer', 'viewer', 'service_account'
        ]))
    """)
    op.execute("ALTER TABLE user_invitations DROP CONSTRAINT IF EXISTS user_invitations_scope_type_check")
    op.execute("""
        ALTER TABLE user_invitations
        ADD CONSTRAINT user_invitations_scope_type_check
        CHECK (scope_type = ANY (ARRAY['global', 'area', 'team']))
    """)
