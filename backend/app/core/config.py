"""Application settings, loaded from environment variables (and backend/.env in development)."""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Request
from pydantic import Field, SecretStr, field_validator, model_validator
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

    # Authentication. JWT_SECRET_KEY is required: generate with
    # python -c "import secrets; print(secrets.token_urlsafe(64))"
    jwt_secret_key: SecretStr = Field(min_length=32)
    jwt_issuer: str = "car-rental-api"
    jwt_audience: str = "car-rental-clients"
    access_token_ttl_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_ttl_days: int = Field(default=30, ge=1, le=90)
    email_verification_ttl_hours: int = Field(default=48, ge=1, le=168)
    password_reset_ttl_minutes: int = Field(default=30, ge=5, le=120)

    # Email delivery. "smtp" works with any provider offering SMTP + STARTTLS.
    # "console" only logs messages and is refused in production.
    email_backend: Literal["console", "smtp"] = "console"
    email_from: str = "CarHire SA <no-reply@example.com>"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    # Links in emails start with this URL (the mobile app's deep-link scheme).
    app_link_base_url: str = "carrental://"

    # Renter eligibility and identity documents.
    min_renter_age: int = Field(default=18, ge=18, le=30)
    # Keyed hash for ID/licence numbers (duplicate detection without storing them).
    # Required; changing it later breaks duplicate detection for existing records.
    document_hash_key: SecretStr = Field(min_length=32)
    # Private directory for uploaded documents (never served statically).
    document_storage_dir: Path = Path("storage/private")
    max_document_bytes: int = Field(default=10 * 1024 * 1024, ge=100 * 1024, le=25 * 1024 * 1024)

    # Bookings.
    booking_hold_minutes: int = Field(default=15, ge=5, le=60)
    booking_min_lead_minutes: int = Field(default=120, ge=0, le=7 * 24 * 60)
    booking_max_days: int = Field(default=30, ge=1, le=90)
    max_pending_bookings_per_renter: int = Field(default=2, ge=1, le=10)

    # Payments (Paystack). Without a secret key, payments are disabled (503).
    # Only test keys (sk_test_...) are accepted unless ALLOW_LIVE_PAYMENTS is true:
    # no real money moves without an explicit decision.
    paystack_secret_key: SecretStr | None = None
    paystack_public_key: str | None = None  # not used by the backend; kept for completeness
    paystack_base_url: str = "https://api.paystack.co"
    allow_live_payments: bool = False
    # Where Paystack sends the customer after checkout (must be http(s)).
    payment_callback_url: str | None = None

    # Live delivery tracking (Stage 13).
    # Server key for the Geocoding and Routes APIs. Without it there is no ETA; tracking works.
    google_maps_api_key: SecretStr | None = None
    location_min_interval_seconds: int = Field(default=5, ge=1, le=60)
    location_max_age_seconds: int = Field(default=600, ge=30, le=3600)  # older fixes rejected
    eta_refresh_seconds: int = Field(default=60, ge=15, le=600)  # Routes API calls per delivery
    location_retention_days: int = Field(default=90, ge=1, le=3650)

    # Notifications (Stage 16). Email uses EMAIL_BACKEND above; push uses the Expo Push Service.
    push_enabled: bool = True
    expo_access_token: SecretStr | None = None  # only if "enhanced push security" is on in EAS
    # The API process sends due notifications every N seconds; 0 turns the built-in worker off
    # (then run `python -m app.cli send-notifications` from cron or a separate process).
    notification_worker_seconds: int = Field(default=15, ge=0, le=3600)
    notification_max_attempts: int = Field(default=5, ge=1, le=10)
    notification_retention_days: int = Field(default=180, ge=7, le=3650)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator(
        "paystack_secret_key", "google_maps_api_key", "expo_access_token", mode="before"
    )
    @classmethod
    def empty_key_means_disabled(cls, value: object) -> object:
        return None if value in ("", None) else value

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

    @model_validator(mode="after")
    def production_requirements(self) -> "Settings":
        if self.app_env == Environment.PRODUCTION and self.email_backend == "console":
            raise ValueError("EMAIL_BACKEND=console is not allowed in production; use smtp")
        if self.email_backend == "smtp" and not self.smtp_host:
            raise ValueError("SMTP_HOST is required when EMAIL_BACKEND=smtp")
        if self.paystack_secret_key is not None:
            key = self.paystack_secret_key.get_secret_value()
            if key.startswith("sk_live_") and not self.allow_live_payments:
                raise ValueError(
                    "A live Paystack key is configured but ALLOW_LIVE_PAYMENTS is not true. "
                    "Use a test key (sk_test_...) until live payments are explicitly approved."
                )
            if not key.startswith(("sk_test_", "sk_live_")):
                raise ValueError("PAYSTACK_SECRET_KEY must start with sk_test_ or sk_live_")
        return self

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
