"""workflow_runs + run_nodes + work_queue

Adds the run state machine tables. Includes a partial index on work_queue
matching the spec's SELECT … FOR UPDATE SKIP LOCKED claim pattern.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-11
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enum type (idempotent guard for the rare re-run-on-existing-DB case)
    op.execute("DO $$ BEGIN CREATE TYPE run_status AS ENUM ('pending','running','succeeded','failed','cancelled'); EXCEPTION WHEN duplicate_object THEN null; END $$")

    op.create_table(
        "workflow_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workflow_id", UUID(as_uuid=True), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum("pending", "running", "succeeded", "failed", "cancelled", name="run_status", create_type=False), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("inputs", JSONB, nullable=True),
        sa.Column("outputs", JSONB, nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("triggered_by", UUID(as_uuid=True), nullable=False),
        sa.Column("triggered_by_kind", sa.String(), nullable=False),
        sa.Column("team_id", UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("scoped_api_key_id", UUID(as_uuid=True), sa.ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_workflow_runs_team_created", "workflow_runs", ["team_id", sa.text("created_at DESC")])
    op.create_index("idx_workflow_runs_status", "workflow_runs", ["status"])

    op.create_table(
        "run_nodes",
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.String(), nullable=False),
        sa.Column("iteration", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.Enum("pending", "running", "succeeded", "failed", "cancelled", name="run_status", create_type=False), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("inputs", JSONB, nullable=True),
        sa.Column("outputs", JSONB, nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("run_id", "node_id", "iteration", name="run_nodes_pk"),
    )

    op.create_table(
        "work_queue",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.String(), nullable=False),
        sa.Column("iteration", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("claimed_by", sa.String(), nullable=True),
        sa.Column("claim_expires", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.execute("CREATE INDEX work_queue_available_idx ON work_queue (available_at) WHERE claimed_by IS NULL")
    op.create_index("work_queue_claim_expires_idx", "work_queue", ["claim_expires"])


def downgrade() -> None:
    op.drop_index("work_queue_claim_expires_idx", table_name="work_queue")
    op.execute("DROP INDEX IF EXISTS work_queue_available_idx")
    op.drop_table("work_queue")
    op.drop_table("run_nodes")
    op.drop_index("idx_workflow_runs_status", table_name="workflow_runs")
    op.drop_index("idx_workflow_runs_team_created", table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.execute("DROP TYPE IF EXISTS run_status")
