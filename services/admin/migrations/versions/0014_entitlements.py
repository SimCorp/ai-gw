"""Entitlement model: api_key scopes array, unit_lead role, access_grants table

Revision ID: 0014
Revises: 0013
"""
from alembic import op
from typing import Sequence, Union

revision = "0014"
down_revision = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # 1. Add scopes array to api_keys (replaces the single-string `scope` field)
    op.execute("""
        ALTER TABLE api_keys
        ADD COLUMN IF NOT EXISTS scopes TEXT[] NOT NULL DEFAULT '{ai-gw:inference:*}'
    """)

    # 2. Backfill existing keys: map legacy scope values to the new array
    op.execute("""
        UPDATE api_keys
        SET scopes = CASE
            WHEN scope = 'standard' THEN ARRAY['ai-gw:inference:*']
            WHEN scope = 'readonly' THEN ARRAY['ai-gw:metrics:read']
            ELSE ARRAY['ai-gw:inference:*']
        END
        WHERE scopes = '{ai-gw:inference:*}'
    """)

    # 3. Add 'unit' as a valid scope_type in user_roles
    #    (The existing scope_type column is TEXT with no check constraint — just document it)
    op.execute("""
        COMMENT ON COLUMN user_roles.scope_type IS
        'global | area | unit | team — scope level for this role binding'
    """)

    # 4. Create access_grants table for cross-team ReBAC
    op.execute("""
        CREATE TABLE IF NOT EXISTS access_grants (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            grantor_team_id  UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            grantee_team_id  UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            resource_type    TEXT NOT NULL,
            resource_id      UUID,
            scopes           TEXT[] NOT NULL,
            expires_at       TIMESTAMPTZ,
            granted_by       UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT access_grants_different_teams CHECK (grantor_team_id != grantee_team_id)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_access_grants_grantee
        ON access_grants(grantee_team_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_access_grants_grantor
        ON access_grants(grantor_team_id)
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS access_grants")
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS scopes")
