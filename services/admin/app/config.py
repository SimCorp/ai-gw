import warnings

from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_PLACEHOLDERS = {"change-me-in-production", "ai-gateway-admin-secret"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://aigateway:aigateway@localhost:5432/aigateway"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me-in-production"
    admin_token: str = ""  # required when dev_bypass_auth=False
    dev_bypass_auth: bool = False
    oidc_issuer: str = "http://dex:5556/dex"
    oidc_client_id: str = "ai-gateway-admin"
    oidc_client_secret: str = "ai-gateway-admin-secret"

    litellm_master_key: str = "sk-litellm-local-dev"

    # Sibling service URLs for system health checks
    auth_url: str = "http://auth:8001"
    cache_url: str = "http://cache:8002"
    litellm_url: str = "http://litellm:8003"
    observability_url: str = "http://observability:8004"


    def warn_dev_values(self) -> None:
        if self.secret_key in _DEV_PLACEHOLDERS:
            warnings.warn("SECRET_KEY is set to the development placeholder — set a real value", stacklevel=2)
        if self.oidc_client_secret in _DEV_PLACEHOLDERS:
            warnings.warn("OIDC_CLIENT_SECRET is set to the development placeholder", stacklevel=2)
        if not self.dev_bypass_auth and not self.admin_token:
            warnings.warn(
                "DEV_BYPASS_AUTH=false but ADMIN_TOKEN is empty — all admin requests will return 500",
                stacklevel=2,
            )


settings = Settings()
settings.warn_dev_values()
