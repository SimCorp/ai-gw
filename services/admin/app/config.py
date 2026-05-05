from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://aigateway:aigateway@localhost:5432/aigateway"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me-in-production"
    admin_token: str = ""  # required when dev_bypass_auth=False
    dev_bypass_auth: bool = True
    oidc_issuer: str = "http://dex:5556/dex"
    oidc_client_id: str = "ai-gateway-admin"
    oidc_client_secret: str = "ai-gateway-admin-secret"


settings = Settings()
