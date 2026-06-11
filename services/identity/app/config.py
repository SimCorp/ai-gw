from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str
    admin_url: str
    identity_service_token: str  # IDENTITY_SERVICE_TOKEN — empty value allows all (set explicitly)


settings = Settings()
