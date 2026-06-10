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

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
