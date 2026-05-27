import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Score(Base):
    __tablename__ = "league_scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("league_submissions.id", ondelete="CASCADE"), nullable=False, unique=True)
    quality: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("0"))
    robustness: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("0"))
    token_efficiency: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("0"))
    speed: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("0"))
    cost_efficiency: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("0"))
    improvement_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("50"))
    creativity: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("50"))
    composite: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False, server_default=text("0"))
