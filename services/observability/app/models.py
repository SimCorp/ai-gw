from datetime import datetime, timezone

from pydantic import BaseModel, Field


class GatewayEvent(BaseModel):
    team_id: str
    project_id: str | None = None
    key_id: str | None = None
    model: str | None = None
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd: float = 0.0
    cache_hit: bool = False
    latency_ms: int | None = None
    error: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Enhanced telemetry (Tier 2)
    session_trace_id: str | None = None
    tool_invocation_count: int = 0
    retry_count: int = 0
    request_error_type: str | None = None
    cache_namespace: str | None = None
    # Claude Code context headers (Tier 3)
    repo: str | None = None
    session_purpose: str | None = None
    # Lightweight intent classification (no prompt stored)
    request_intent: str | None = None
