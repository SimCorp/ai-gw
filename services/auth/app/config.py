from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "postgresql+asyncpg://aigateway:aigateway@localhost:5432/aigateway"
    jwks_uri: str = "http://dex:5556/dex/keys"
    entra_tenant_id: str = "local"
    entra_client_id: str = "ai-gateway-admin"
    rate_limit_default_rpm: int = 1000


settings = Settings()
