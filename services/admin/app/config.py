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
    # Explicit base URL for OIDC redirect_uri. Must be set in production to avoid
    # Host-header manipulation. Defaults to request.base_url for local/dev only.
    oidc_base_url: str = ""

    # Deployment environment. Set to "development" or "test" in non-production
    # compose/CI configs to allow OIDC fallback to request.base_url when
    # OIDC_BASE_URL is unset. Defaults to "production" (secure/fail-closed).
    environment: str = "production"

    litellm_master_key: str

    # Sibling service URLs for system health checks
    auth_url: str
    cache_url: str
    litellm_url: str
    observability_url: str
    league_url: str
    librarian_url: str
    librarian_service_token: str = ""

    # Graphify service — proxied by the Knowledge Graphs admin page. The token
    # must match graphify's GRAPHIFY_SERVICE_TOKEN (defaults to the stack key).
    graphify_url: str = "http://graphify:8012"
    graphify_service_token: str = ""

    # Observability backends queried by the DevOps agent (defaults = single-host stack).
    loki_url: str = "http://obs-loki:3100"
    prometheus_url: str = "http://obs-prometheus:9090"

    # GitHub — read-only token (actions:read) used by the agentic-workflows
    # status page to list gh-aw workflow runs. Empty disables the feature.
    github_token: str = ""
    github_repo: str = "SimCorp/ai-gw"

    # Secret used to encrypt the RSA identity signing key stored in Redis.
    # Use a long random string in production (e.g. openssl rand -hex 32).
    identity_key_secret: str

    # CORS — restrict allowed origins
    cors_origins: list[str]

    # Email domain restriction — empty list allows all domains
    allowed_email_domains: list[str] = []


settings = Settings()
