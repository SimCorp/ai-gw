from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str
    litellm_url: str
    litellm_master_key: str
    auth_url: str
    observability_url: str
    # Embeddings route through the gateway's litellm proxy (single model egress),
    # not a direct provider call. embedding_base_url / embedding_api_key mirror
    # litellm_url / litellm_master_key; switch embedding_model to any embedding
    # model litellm exposes.
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key: str  # gateway key (LITELLM_MASTER_KEY)
    embedding_base_url: str
    default_similarity_threshold: float = 0.95
    default_ttl_seconds: int = 3600
    internal_api_key: str
    conversation_turn_limit: int = 3
    budget_check_enabled: bool = True
    autoroute_enabled: bool = False
    autoroute_models: str = "claude-haiku-4-5,gpt-4o-mini"


settings = Settings()
