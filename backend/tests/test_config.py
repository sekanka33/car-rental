from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Environment, Settings
from tests.conftest import make_settings


def test_defaults_are_development_without_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("APP_ENV", "APP_NAME", "LOG_LEVEL", "CORS_ORIGINS"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.app_env is Environment.DEVELOPMENT
    assert settings.cors_origins == []
    assert settings.docs_enabled


def test_settings_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_NAME", "Rental API (env)")
    monkeypatch.setenv("LOG_LEVEL", "warning")
    monkeypatch.setenv("CORS_ORIGINS", "https://admin.example.co.za, http://localhost:8081 ,")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.app_env is Environment.PRODUCTION
    assert settings.app_name == "Rental API (env)"
    assert settings.log_level == "WARNING"
    assert settings.cors_origins == ["https://admin.example.co.za", "http://localhost:8081"]
    assert not settings.docs_enabled


@pytest.mark.parametrize(
    "overrides", [{"app_env": "prod"}, {"log_level": "LOUD"}], ids=["bad-env", "bad-log-level"]
)
def test_invalid_settings_are_rejected(overrides: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        make_settings(**overrides)


def test_cors_allows_only_configured_origins(client_for: Callable[..., TestClient]) -> None:
    client = client_for(cors_origins=["http://localhost:8081"])
    preflight = {"access-control-request-method": "GET"}

    allowed = client.options(
        "/api/v1/health", headers={"origin": "http://localhost:8081", **preflight}
    )
    blocked = client.options(
        "/api/v1/health", headers={"origin": "https://evil.example", **preflight}
    )

    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:8081"
    assert "access-control-allow-origin" not in blocked.headers
