"""Invitations and service accounts

Adds:
  - user_invitations: token-based invite flow with scoped role grants
  - service_accounts: API-key-only principals with lifecycle management

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-13
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_invitations (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email           VARCHAR(255) NOT NULL,
            role            TEXT NOT NULL CHECK (role IN (
                                'platform_admin', 'area_owner', 'team_admin',
                                'developer', 'viewer', 'service_account')),
            scope_type      TEXT NOT NULL DEFAULT 'global'
                                CHECK (scope_type IN ('global', 'area', 'team')),
            scope_id        UUID,
            token_hash      TEXT NOT NULL UNIQUE,
            invited_by      UUID REFERENCES users(id) ON DELETE SET NULL,
            expires_at      TIMESTAMPTZ NOT NULL,
            accepted_at     TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_invitations_email ON user_invitations(email)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_invitations_token ON user_invitations(token_hash)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_invitations_expires ON user_invitations(expires_at) WHERE accepted_at IS NULL")

    op.execute("""
        CREATE TABLE IF NOT EXISTS service_accounts (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name            VARCHAR(200) NOT NULL,
            description     TEXT NOT NULL DEFAULT '',
            key_hash        TEXT NOT NULL UNIQUE,
            key_prefix      VARCHAR(20) NOT NULL,
            owner_user_id   UUID REFERENCES users(id) ON DELETE SET NULL,
            team_id         UUID REFERENCES teams(id) ON DELETE SET NULL,
            status          TEXT NOT NULL DEFAULT 'active'
                                CHECK (status IN ('active', 'suspended', 'revoked')),
            created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
            last_used_at    TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_service_accounts_team ON service_accounts(team_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_service_accounts_status ON service_accounts(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_service_accounts_key ON service_accounts(key_hash)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS service_accounts")
    op.execute("DROP TABLE IF EXISTS user_invitations")
