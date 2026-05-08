import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Boolean, DateTime, Float, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    cache_ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3600")
    cache_similarity_threshold: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.95")
    cache_opt_out: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    embedding_model: Mapped[str] = mapped_column(String, nullable=False, server_default="'text-embedding-3-small'")
    rate_limit_rpm: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1000")
    allowed_models: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, server_default=text("ARRAY[]::TEXT[]"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()"))
