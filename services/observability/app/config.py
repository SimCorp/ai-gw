from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://aigateway:aigateway@localhost:5432/aigateway"
    redis_url: str = "redis://localhost:6379/0"
    bus_provider: str = "memory"
    azure_service_bus_connection_string: str = ""
    azure_service_bus_topic: str = "gateway-events"
    azure_service_bus_subscription: str = "gateway-workers"
    appinsights_connection_string: str = ""
    internal_api_key: str = "change-me-internal-key"


settings = Settings()
