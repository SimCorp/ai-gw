import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Policy(Base):
    __tablename__ = "policies"
    __table_args__ = (
        # The original UNIQUE(team_id, project_id) was replaced by two partial
        # indexes for correct ON CONFLICT behaviour with nullable project_id.
        # Migration 0025 renamed the underlying column team_id -> node_id and
        # renamed these indexes to policies_node_*; the ORM attribute is kept
        # as `team_id` (mapped to the `node_id` column) so call sites are
        # unchanged, but the index definitions must reference the real column.
        Index("policies_node_null_proj_uidx", "node_id",
              unique=True, postgresql_where="(project_id IS NULL)"),
        Index("policies_node_proj_uidx", "node_id", "project_id",
              unique=True, postgresql_where="(project_id IS NOT NULL)"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    # Column was renamed team_id -> node_id in migration 0025 (now FK to
    # organization_nodes in the DB). The Python attribute name `team_id` is
    # preserved to avoid touching every call site; only the underlying column
    # name is remapped to `node_id`.
    # No declarative ForeignKey: the old teams.id target no longer exists and
    # the organization_nodes model is not registered in this service's
    # Base.metadata, so a declarative FK here would fail mapper table-sort on
    # flush. The real FK (policies_node_id_fkey -> organization_nodes) is owned
    # by the migration; the ORM does not need to mirror it.
    team_id: Mapped[uuid.UUID] = mapped_column("node_id", UUID(as_uuid=True), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    cache_ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3600")
    cache_similarity_threshold: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.95")
    cache_opt_out: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    embedding_model: Mapped[str] = mapped_column(Text, nullable=False, server_default="'text-embedding-3-small'")
    rate_limit_rpm: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1000")
    allowed_models: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False, server_default=text("ARRAY[]::TEXT[]"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()"))
