from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://aigateway:aigateway@postgres:5432/aigateway"
    auth_url: str = "http://auth:8001"
    admin_url: str = "http://admin:8005"
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key: str = "sk-local-placeholder"
    embedding_base_url: str = "http://ollama:11434/v1"
    embedding_dimensions: int = 1536
    port: int = 8009


settings = Settings()
