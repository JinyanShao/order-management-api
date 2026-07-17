from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Order Management API"
    database_url: str = "postgresql+psycopg://orders:orders@localhost:5432/orders"
    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    cors_origins: list[str] = ["http://localhost:3000"]
    trusted_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
