"""Add scim_external_id for Azure Entra SCIM provisioning"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union

revision = "0020"
down_revision = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column("users", sa.Column("scim_external_id", sa.Text(), nullable=True))
    op.create_index(
        "idx_users_scim_external_id",
        "users",
        ["scim_external_id"],
        unique=True,
        postgresql_where=sa.text("scim_external_id IS NOT NULL"),
    )


def downgrade():
    op.drop_index("idx_users_scim_external_id", table_name="users")
    op.drop_column("users", "scim_external_id")
