from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://aigateway:aigateway@localhost:5432/aigateway"
    redis_url: str = "redis://localhost:6379/0"

    # Auth service — validates the sk-* Bearer on MCP requests.
    auth_url: str = "http://auth:8001"

    # Embedding model config — routed through the gateway's own litellm proxy,
    # not a direct provider call. litellm holds the provider keys and exposes
    # embedding models (see services/litellm/config.yaml). The service only needs
    # a gateway key and the model name; switch EMBEDDING_MODEL to any embedding
    # model the gateway exposes (now or in future) without touching code.
    embedding_base_url: str = "http://litellm:8003/v1"
    embedding_api_key: str = "sk-litellm-local-dev"  # gateway key (LITELLM_MASTER_KEY)
    embedding_model: str = "text-embedding-3-small"

    # URL of the cache service (used by the research agent to call the LLM)
    cache_url: str = "http://cache:8002"

    # How often (seconds) the background research loop polls for stale topics
    research_interval_seconds: int = 3600

    # CORS origins allowed to call the librarian directly from the browser.
    # Default is the portal origin only; set CORS_ORIGINS=* only if you need
    # to allow all origins (operator's explicit choice).
    cors_origins: str = "http://localhost:3002,http://localhost:8080"

    # Service token for /ingest and /mcp/tools/ingest endpoints.
    # Leave empty to allow unauthenticated access in dev mode (fail open).
    librarian_service_token: str = ""  # LIBRARIAN_SERVICE_TOKEN


settings = Settings()
