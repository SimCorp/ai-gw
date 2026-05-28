"""Contractor access isolation: is_contractor, access_expires_at, allowed_models"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0021"
down_revision = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("is_contractor", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "users",
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("allowed_models", ARRAY(sa.Text()), nullable=True),
    )


def downgrade():
    op.drop_column("users", "allowed_models")
    op.drop_column("users", "access_expires_at")
    op.drop_column("users", "is_contractor")
