import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Season(Base):
    __tablename__ = "league_seasons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'upcoming'"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scoring_weights: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text(
            "'{\"quality\":0.35,\"robustness\":0.20,\"token_efficiency\":0.15,"
            "\"speed\":0.10,\"cost_efficiency\":0.10,\"improvement_rate\":0.05,"
            "\"creativity\":0.05}'"
        ),
    )
    season_multiplier: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, server_default=text("1.0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
