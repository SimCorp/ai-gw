"""AI-Champions community: six tables"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union

revision = "0025"
down_revision = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        "champions",
        sa.Column("developer_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("focus_areas", sa.dialects.postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("office_hours_text", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("nominated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("nominated_by", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_champions_active", "champions", ["active"])

    op.create_table(
        "champion_contributions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("champion_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("champions.developer_id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("librarian_item_id", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("upvotes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("flag_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("auto_metadata", sa.dialects.postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_champion_contributions_champion", "champion_contributions", ["champion_id"])
    op.create_index("ix_champion_contributions_submitted_at", "champion_contributions", ["submitted_at"])

    op.create_table(
        "champion_asks",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_by", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("claimed_by", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auto_confirm_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("routed_to", sa.dialects.postgresql.ARRAY(sa.dialects.postgresql.UUID(as_uuid=True)), nullable=False, server_default="{}"),
        sa.Column("tags", sa.dialects.postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
    )
    op.create_index("ix_champion_asks_status", "champion_asks", ["status"])

    op.create_table(
        "champion_bookings",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("champion_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("champions.developer_id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requested_by", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slot_text", sa.Text(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="requested"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_champion_bookings_champion", "champion_bookings", ["champion_id"])

    op.create_table(
        "champion_upvotes",
        sa.Column("developer_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("contribution_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("champion_contributions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_champion_upvotes_contribution", "champion_upvotes", ["contribution_id"])

    op.create_table(
        "champion_flags",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("contribution_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("champion_contributions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("flagged_by", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("champion_flags")
    op.drop_index("ix_champion_upvotes_contribution", table_name="champion_upvotes")
    op.drop_table("champion_upvotes")
    op.drop_index("ix_champion_bookings_champion", table_name="champion_bookings")
    op.drop_table("champion_bookings")
    op.drop_index("ix_champion_asks_status", table_name="champion_asks")
    op.drop_table("champion_asks")
    op.drop_index("ix_champion_contributions_submitted_at", table_name="champion_contributions")
    op.drop_index("ix_champion_contributions_champion", table_name="champion_contributions")
    op.drop_table("champion_contributions")
    op.drop_index("ix_champions_active", table_name="champions")
    op.drop_table("champions")
