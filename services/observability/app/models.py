from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class GatewayEvent(BaseModel):
    team_id: str
    project_id: str | None = None
    model: str | None = None
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd: float = 0.0
    cache_hit: bool = False
    latency_ms: int | None = None
    error: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
