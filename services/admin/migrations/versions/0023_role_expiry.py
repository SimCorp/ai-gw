"""Add expiry and reason to user_roles (granted_by already exists as UUID column)"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column("user_roles", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_roles", sa.Column("grant_reason", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("user_roles", "grant_reason")
    op.drop_column("user_roles", "expires_at")
