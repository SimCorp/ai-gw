import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class LeaderboardEntry(Base):
    __tablename__ = "league_leaderboard"

    season_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("league_seasons.id", ondelete="CASCADE"), primary_key=True)
    engineer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    composite_score: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False, server_default=text("0"))
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    points_earned: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
