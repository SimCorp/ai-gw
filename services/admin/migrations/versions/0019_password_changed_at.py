# services/admin/migrations/versions/0019_password_changed_at.py
"""Add password_changed_at for session invalidation on password change

Revision ID: 0019
Revises: 0018
"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union

revision = "0019"
down_revision = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column("users", sa.Column(
        "password_changed_at",
        sa.DateTime(timezone=True),
        nullable=True,
    ))
    op.execute("UPDATE users SET password_changed_at = created_at WHERE password_changed_at IS NULL")


def downgrade():
    op.drop_column("users", "password_changed_at")
