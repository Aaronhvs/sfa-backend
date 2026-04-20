from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    APP_ENV: str = "development"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    SECRET_KEY: str

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://sfa:sfa@localhost:5432/sfa"

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"

    # External APIs
    API_FOOTBALL_KEY: str = ""
    API_FOOTBALL_BASE_URL: str = "https://v3.football.api-sports.io"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
