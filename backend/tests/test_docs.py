from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize("env", ["development", "test", "staging"])
def test_docs_available_outside_production(client_for: Callable[..., TestClient], env: str) -> None:
    client = client_for(app_env=env)

    assert client.get("/docs").status_code == 200
    schema = client.get("/api/v1/openapi.json")
    assert schema.status_code == 200
    assert "/api/v1/health" in schema.json()["paths"]


def test_docs_disabled_in_production(client_for: Callable[..., TestClient]) -> None:
    client = client_for(
        app_env="production",
        email_backend="smtp",
        smtp_host="smtp.example.com",
        cors_origins=["https://admin.example.com"],
    )

    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/api/v1/openapi.json").status_code == 404
    # The API itself still works.
    assert client.get("/api/v1/health").status_code in {200, 503}
