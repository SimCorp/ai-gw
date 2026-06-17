from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str
    admin_token: str = ""
    litellm_url: str
    litellm_master_key: str
    cors_origins: list[str]
    training_rate_limit_per_hour: int = 10
    embedding_model: str = "text-embedding-3-small"


settings = Settings()
