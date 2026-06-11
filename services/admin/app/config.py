from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str
    secret_key: str
    admin_token: str = ""  # required for X-Admin-Token auth path; empty disables it
    oidc_issuer: str
    oidc_client_id: str = "ai-gateway-admin"
    # Optional until the Entra app-registration exists (plan Workstream H.2);
    # empty disables OIDC client-secret auth (admin-portal SSO) but lets the
    # service start. Set via Key Vault once the registration is created.
    oidc_client_secret: str = ""

    litellm_master_key: str

    # Sibling service URLs for system health checks
    auth_url: str
    cache_url: str
    litellm_url: str
    observability_url: str
    league_url: str
    librarian_url: str
    librarian_service_token: str = ""

    # Secret used to encrypt the RSA identity signing key stored in Redis.
    # Use a long random string in production (e.g. openssl rand -hex 32).
    identity_key_secret: str

    # CORS — restrict allowed origins
    cors_origins: list[str]

    # Email domain restriction — empty list allows all domains
    allowed_email_domains: list[str] = []


settings = Settings()
