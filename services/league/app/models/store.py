import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class StoreItem(Base):
    __tablename__ = "league_store_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    point_cost: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    asset_url: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    exclusive_season_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("league_seasons.id", ondelete="SET NULL"), nullable=True)
    exclusive_top_n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))


class Purchase(Base):
    __tablename__ = "league_purchases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    engineer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("league_store_items.id", ondelete="CASCADE"), nullable=False)
    points_spent: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
