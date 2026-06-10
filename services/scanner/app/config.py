from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str
    auth_url: str
    internal_api_key: str
    scanner_worker_secret: str
    scan_job_queue_key: str = "scanner:jobs:queue"
    max_container_timeout_seconds: int = 900
    environment: str = "production"
    docker_network: str = "aigateway"

    # Tool-container spawn runtime: "aca_job" (Azure Container Apps Jobs) or
    # "docker" (local fallback). Env: SCANNER_CONTAINER_RUNTIME.
    scanner_container_runtime: str = "docker"
    # ACA-Jobs runtime config (only required when scanner_container_runtime=aca_job).
    # Env var names below are what bicep must wire to match.
    scanner_runner_job_name: str = ""  # SCANNER_RUNNER_JOB_NAME — e.g. job-scanner-runner-<env>-sdc
    azure_resource_group: str = ""  # AZURE_RESOURCE_GROUP
    azure_subscription_id: str = ""  # AZURE_SUBSCRIPTION_ID
    runs_share_name: str = ""  # AIGW_RUNS_SHARE — Azure Files share for tool output exchange
    runs_storage_account: str = ""  # AIGW_RUNS_STORAGE_ACCOUNT — storage account hosting the share
    scanner_aca_poll_interval_s: float = 2.0  # SCANNER_ACA_POLL_INTERVAL_S

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
