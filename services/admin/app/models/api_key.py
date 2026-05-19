import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ARRAY, DateTime, ForeignKey, Index, Numeric, Text, text
# Note: developer_id references developers.id (raw-SQL table, not ORM-mapped).
# FK constraint exists in the DB via the baseline migration; the column is
# declared here without a SQLAlchemy ForeignKey so autogenerate doesn't fail
# trying to resolve the target table.
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class APIKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (
        Index("idx_api_keys_developer", "developer_id"),
        Index("idx_api_keys_expires_at", "expires_at",
              postgresql_where="(expires_at IS NOT NULL)"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    key_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    developer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    monthly_budget_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 8), nullable=True)
    scope: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'standard'"))
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{ai-gw:inference:*}'"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
