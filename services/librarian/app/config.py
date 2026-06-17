from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str

    # Auth service — validates the sk-* Bearer on MCP requests.
    auth_url: str

    # Embedding model config — routed through the gateway's own litellm proxy,
    # not a direct provider call. litellm holds the provider keys and exposes
    # embedding models (see services/litellm/config.yaml). The service only needs
    # a gateway key and the model name; switch EMBEDDING_MODEL to any embedding
    # model the gateway exposes (now or in future) without touching code.
    embedding_base_url: str
    embedding_api_key: str  # gateway key (LITELLM_MASTER_KEY)
    embedding_model: str = "text-embedding-3-small"

    # URL of the cache service (used by the research agent to call the LLM)
    cache_url: str

    # How often (seconds) the background research loop polls for stale topics
    research_interval_seconds: int = 3600

    # CORS origins allowed to call the librarian directly from the browser.
    # Default is the portal origin only; set CORS_ORIGINS=* only if you need
    # to allow all origins (operator's explicit choice).
    cors_origins: str

    # Service token for /ingest and /mcp/tools/ingest endpoints.
    # An empty value fails open (unauthenticated); set explicitly.
    librarian_service_token: str  # LIBRARIAN_SERVICE_TOKEN


settings = Settings()
