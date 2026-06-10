"""Agent Relay configuration. Reads from env vars set in docker-compose."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str
    relay_secret: str  # RELAY_SECRET — empty value allows all (set explicitly)

    model_config = {"env_file": ".env", "extra": "ignore"}


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
