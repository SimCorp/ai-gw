"""Add budget columns to areas and units for hierarchical cost delegation"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union

revision = "0024"
down_revision = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column("areas", sa.Column("monthly_budget_usd", sa.Numeric(12, 2), nullable=True))
    op.add_column("areas", sa.Column("budget_alert_threshold", sa.Numeric(4, 2), nullable=True, server_default="0.80"))
    op.add_column("units", sa.Column("monthly_budget_usd", sa.Numeric(12, 2), nullable=True))
    op.add_column("units", sa.Column("budget_alert_threshold", sa.Numeric(4, 2), nullable=True, server_default="0.80"))


def downgrade():
    op.drop_column("units", "budget_alert_threshold")
    op.drop_column("units", "monthly_budget_usd")
    op.drop_column("areas", "budget_alert_threshold")
    op.drop_column("areas", "monthly_budget_usd")
