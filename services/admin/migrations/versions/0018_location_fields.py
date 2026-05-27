# services/admin/migrations/versions/0018_location_fields.py
"""Add location field to teams and areas

Revision ID: 0018
Revises: 0017
"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union

revision = "0018"
down_revision = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column("teams", sa.Column("location", sa.Text(), nullable=True))
    op.add_column("areas", sa.Column("location", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("teams", "location")
    op.drop_column("areas", "location")
