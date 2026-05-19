"""Entra ID group → gateway role mappings for Azure AD OIDC integration

Revision ID: 0016
Revises: 0015
"""
from alembic import op
from typing import Sequence, Union

revision = "0016"
down_revision = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS entra_group_role_mappings (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entra_group_id   TEXT NOT NULL,
            entra_group_name TEXT,
            role             TEXT NOT NULL,
            scope_type       TEXT NOT NULL DEFAULT 'global',
            scope_id         UUID,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_by       UUID REFERENCES users(id) ON DELETE SET NULL,
            CONSTRAINT entra_group_role_mappings_unique UNIQUE (entra_group_id, role, scope_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_entra_group_mappings_group_id
        ON entra_group_role_mappings(entra_group_id)
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS entra_group_role_mappings")
