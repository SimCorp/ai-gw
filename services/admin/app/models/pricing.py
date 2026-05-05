from datetime import datetime

from sqlalchemy import DateTime, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ModelPricing(Base):
    __tablename__ = "model_pricing"

    model_prefix: Mapped[str] = mapped_column(String, primary_key=True)
    price_input_per_1k: Mapped[float] = mapped_column(Numeric(12, 8), nullable=False)
    price_output_per_1k: Mapped[float] = mapped_column(Numeric(12, 8), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()")
    )
