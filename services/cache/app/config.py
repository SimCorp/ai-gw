from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379/0"
    litellm_url: str = "http://litellm:8003"
    litellm_master_key: str = "sk-litellm-local-dev"
    auth_url: str = "http://auth:8001"
    observability_url: str = "http://observability:8004"
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key: str = "sk-placeholder"
    embedding_base_url: str = "http://ollama:11434/v1"
    default_similarity_threshold: float = 0.95
    default_ttl_seconds: int = 3600
    internal_api_key: str = "sk-internal-local"
    conversation_turn_limit: int = 3
    budget_check_enabled: bool = True


settings = Settings()
