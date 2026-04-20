import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseConfig(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://sfa:sfa@localhost:5432/sfa"
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    APP_ENV: str = "development"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    SECRET_KEY: str
    API_FOOTBALL_KEY: str = ""
    API_FOOTBALL_BASE_URL: str = "https://v3.football.api-sports.io"

    def model_post_init(self, __context) -> None:
        if not self.SECRET_KEY:
            raise ValueError(
                "SECRET_KEY is required but was not set. "
                "Please set the SECRET_KEY environment variable."
            )


class DevelopmentConfig(BaseConfig):
    DEBUG: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class ProductionConfig(BaseConfig):
    DEBUG: bool = False

    model_config = SettingsConfigDict(extra="ignore")


class TestConfig(BaseConfig):
    DATABASE_URL: str = "postgresql+asyncpg://sfa:sfa@localhost:5432/sfa_test"
    CELERY_TASK_ALWAYS_EAGER: bool = True
    DEBUG: bool = True

    model_config = SettingsConfigDict(extra="ignore")


_config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "test": TestConfig,
}


def get_settings() -> BaseConfig:
    env = os.environ.get("APP_ENV", "development")
    config_class = _config_map.get(env, DevelopmentConfig)
    return config_class()
