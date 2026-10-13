"""Application settings, loaded from environment variables (and backend/.env in development)."""

from enum import StrEnum
from functools import lru_cache
from typing import Annotated

from fastapi import Request
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

API_VERSION = "0.1.0"


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Environment = Environment.DEVELOPMENT
    app_name: str = "Car Rental API"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    # NoDecode: read the raw comma-separated string instead of expecting JSON.
    cors_origins: Annotated[list[str], NoDecode] = []
    # Required. SecretStr keeps the password out of logs and reprs.
    database_url: SecretStr
    database_echo: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("database_url")
    @classmethod
    def require_postgres_url(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must start with postgresql+psycopg://")
        return value

    @field_validator("log_level")
    @classmethod
    def normalise_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            raise ValueError(f"Invalid LOG_LEVEL: {value}")
        return level

    @property
    def docs_enabled(self) -> bool:
        """Interactive API docs are exposed only outside production."""
        return self.app_env != Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    """Settings from the process environment; used once when the app is created."""
    return Settings()


def get_app_settings(request: Request) -> Settings:
    """Request dependency: the settings this app instance was created with."""
    return request.app.state.settings
