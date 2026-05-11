from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://aigateway:aigateway@localhost:5432/aigateway"
    redis_url: str = "redis://localhost:6379/0"
    admin_url: str = "http://localhost:8005"
    identity_service_token: str = ""  # IDENTITY_SERVICE_TOKEN — leave empty to allow all (dev mode)


settings = Settings()
