from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_url: str = "postgresql://aigateway:aigateway@localhost:5432/aigateway"
    bus_provider: str = "memory"
    azure_service_bus_connection_string: str = ""
    azure_service_bus_topic: str = "gateway-events"
    azure_service_bus_subscription: str = "gateway-workers"
    appinsights_connection_string: str = ""


settings = Settings()
