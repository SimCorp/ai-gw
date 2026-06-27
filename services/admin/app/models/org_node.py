import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class OrganizationNode(Base):
    __tablename__ = "organization_nodes"
    __table_args__ = (
        UniqueConstraint("parent_id", "slug", name="org_nodes_parent_slug_key"),
        Index("idx_nodes_path", "path", postgresql_ops={"path": "text_pattern_ops"}),
        Index("idx_nodes_parent_id", "parent_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'team'"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organization_nodes.id", ondelete="CASCADE"),
        nullable=True,
    )
    path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    color: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    monthly_budget_usd: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    budget_alert_threshold: Mapped[float | None] = mapped_column(
        Numeric(4, 2), nullable=True, server_default=text("0.80")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()")
    )
    training_capture_enabled: Mapped[bool] = mapped_column(
        nullable=False, server_default=text("FALSE")
    )
