from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str

    # Auth service — validates the sk-* Bearer on the query/management surface.
    auth_url: str

    # Shared secret for trusted service-to-service callers (e.g. the admin
    # backend proxying the portal's Knowledge Graphs page). A request bearing
    # X-Service-Token matching this value bypasses the user sk-* check. Empty
    # disables the bypass (sk-* required). Mirrors librarian's X-Service-Token.
    graphify_service_token: str = ""

    # Build-time LLM routing. `graphify extract` parses code locally (tree-sitter,
    # no API calls); only docs/PDF/images/audio/video go to an LLM. We point its
    # OpenAI backend at the gateway's governed entry point (cache:8002/v1) so
    # extraction calls are authed, rate-limited, cost-attributed and observable.
    # The key must be a real sk-* registered in the auth DB and tied to a team —
    # cache rejects unauthenticated calls. See aigw cache-auth contract.
    graphify_openai_base_url: str = "http://cache:8002/v1"
    graphify_openai_model: str = "gpt-4o-mini"
    graphify_gateway_key: str = ""

    # GitHub token for cloning private repos. Least-privilege, read-only, scoped
    # to the registered repos. Injected via env from pass; never hand-written.
    github_token: str = ""
    # Owner/org used to build clone URLs when a repo is registered by short name.
    github_org: str = "SimCorp"

    # Where graph artefacts live on the shared volume.
    graphify_out_dir: str = "/graphify-out"

    # Identifies this worker in the graph_builds.claimed_by column.
    worker_id: str = "graphify-worker-1"

    # How often (seconds) the build worker polls for queued jobs.
    build_poll_interval_seconds: int = 5

    # CORS origins allowed to call graphify directly from the browser (portal).
    cors_origins: str = "*"


settings = Settings()
