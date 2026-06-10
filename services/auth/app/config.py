from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str
    database_url: str
    jwks_uri: str
    entra_tenant_id: str
    entra_client_id: str
    admin_url: str
    rate_limit_default_rpm: int = 1000


settings = Settings()
