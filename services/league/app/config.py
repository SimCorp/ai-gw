from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://aigateway:aigateway@localhost:5432/aigateway"
    redis_url: str = "redis://localhost:6379/0"
    dev_bypass_auth: bool = False
    admin_token: str = ""
    litellm_url: str = "http://litellm:8003"
    litellm_master_key: str = "sk-litellm-local-dev"
    cors_origins: list[str] = ["http://localhost:3001", "http://localhost:3002"]
    training_rate_limit_per_hour: int = 10


settings = Settings()
