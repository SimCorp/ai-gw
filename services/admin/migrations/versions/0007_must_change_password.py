"""admin_users: add must_change_password flag

New accounts (and the seeded dev account) are created with
must_change_password=TRUE so the user is forced to set a personal
password on first login.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-14
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE admin_users
        ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE
    """)
    # Existing dev account has not had its password set intentionally —
    # mark it so the user is prompted on next login.
    op.execute("""
        UPDATE admin_users SET must_change_password = TRUE
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE admin_users DROP COLUMN IF EXISTS must_change_password")
