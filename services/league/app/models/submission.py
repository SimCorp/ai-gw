import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Submission(Base):
    __tablename__ = "league_submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    challenge_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("league_challenges.id", ondelete="CASCADE"), nullable=False)
    engineer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    tool_config: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    run_results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    prompt_hash: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
