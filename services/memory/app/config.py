from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    auth_url: str
    admin_url: str
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key: str
    embedding_base_url: str
    embedding_dimensions: int = 1536
    port: int = 8009


settings = Settings()
