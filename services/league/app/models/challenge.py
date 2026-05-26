import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Challenge(Base):
    __tablename__ = "league_challenges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    season_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("league_seasons.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    training_inputs: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    hidden_test_suite: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    allowed_models: Mapped[list] = mapped_column(ARRAY(Text), nullable=False, server_default=text("ARRAY['claude-sonnet-4-6']"))
    max_tokens_budget: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("4096"))
    max_league_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    scores_revealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))
    proposed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
