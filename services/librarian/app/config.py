from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://aigateway:aigateway@localhost:5432/aigateway"
    redis_url: str = "redis://localhost:6379/0"

    # Embedding model config — same defaults as the cache service
    embedding_api_key: str = "sk-local-placeholder"
    embedding_base_url: str = "http://ollama:11434/v1"
    embedding_model: str = "text-embedding-3-small"

    # URL of the cache service (used by the research agent to call the LLM)
    cache_url: str = "http://cache:8002"

    # How often (seconds) the background research loop polls for stale topics
    research_interval_seconds: int = 3600

    # CORS origins allowed to call the librarian directly from the browser.
    # Default is the portal origin only; set CORS_ORIGINS=* only if you need
    # to allow all origins (operator's explicit choice).
    cors_origins: str = "http://localhost:3002"

    # Service token for /ingest and /mcp/tools/ingest endpoints.
    # Leave empty to allow unauthenticated access in dev mode (fail open).
    librarian_service_token: str = ""  # LIBRARIAN_SERVICE_TOKEN


settings = Settings()
