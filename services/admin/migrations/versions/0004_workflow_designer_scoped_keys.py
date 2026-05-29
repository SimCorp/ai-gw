"""api_keys: add scope + expires_at for scoped per-run keys

Workflow runs issue a short-lived API key per run; agents call back into
the gateway with that key. expires_at lets the auth layer reject after
the run is done; scope marks the key as 'workflow-run' (vs a regular
team key) for audit.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-11
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("scope", sa.String(), nullable=False, server_default=sa.text("'standard'")))
    op.add_column("api_keys", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("idx_api_keys_expires_at", "api_keys", ["expires_at"], postgresql_where=sa.text("expires_at IS NOT NULL"))


def downgrade() -> None:
    op.drop_index("idx_api_keys_expires_at", table_name="api_keys")
    op.drop_column("api_keys", "expires_at")
    op.drop_column("api_keys", "scope")
