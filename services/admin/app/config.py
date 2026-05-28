import logging
import os

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

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
    league_url: str = "http://league:8010"

    # Secret used to encrypt the RSA identity signing key stored in Redis.
    # Use a long random string in production (e.g. openssl rand -hex 32).
    identity_key_secret: str = "dev-identity-key-secret-change-in-prod"

    # CORS — override in production to restrict allowed origins
    cors_origins: list[str] = [
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:8080",
    ]

    # Email domain restriction — empty list allows all domains
    allowed_email_domains: list[str] = []

    # Allow localhost/private-IP MCP URLs — safe to enable in development/staging
    mcp_allow_local_urls: bool = False

    def warn_dev_values(self) -> None:
        env = os.getenv("ENVIRONMENT", "development")
        is_prod = env not in ("development", "test", "ci")

        if self.secret_key == "change-me-in-production":
            if is_prod:
                raise ValueError(
                    "SECRET_KEY must be changed from the default placeholder in production"
                )
            logger.warning("SECURITY: SECRET_KEY is set to the development placeholder")

        if self.oidc_client_secret == "ai-gateway-admin-secret":
            if is_prod:
                raise ValueError(
                    "OIDC_CLIENT_SECRET must be changed from the default placeholder in production"
                )
            logger.warning("SECURITY: OIDC_CLIENT_SECRET is set to the development placeholder")

        if self.litellm_master_key == "sk-litellm-local-dev":
            if is_prod:
                raise ValueError(
                    "LITELLM_MASTER_KEY must be changed from the default placeholder in production"
                )
            logger.warning("SECURITY: LITELLM_MASTER_KEY is set to the development placeholder")

        if self.dev_bypass_auth:
            logger.warning("SECURITY: DEV_BYPASS_AUTH is enabled — admin auth is disabled")

        if not self.dev_bypass_auth and not self.admin_token:
            logger.warning(
                "SECURITY: DEV_BYPASS_AUTH=false but ADMIN_TOKEN is empty — all admin requests will return 500"
            )

        if not self.allowed_email_domains and is_prod:
            logger.warning(
                "SECURITY: ALLOWED_EMAIL_DOMAINS is not configured — any email address can register a developer account"
            )


settings = Settings()
settings.warn_dev_values()
