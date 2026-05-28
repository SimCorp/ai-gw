from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://gateway:gateway@localhost:5432/gateway"
    redis_url: str = "redis://localhost:6379/0"
    auth_url: str = "http://localhost:8001"
    internal_api_key: str = "dev-internal-key"
    scanner_worker_secret: str = "dev-worker-secret"
    scan_job_queue_key: str = "scanner:jobs:queue"
    max_container_timeout_seconds: int = 900
    environment: str = "development"
    docker_network: str = "aigateway"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
