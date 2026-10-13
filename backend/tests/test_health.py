from fastapi.testclient import TestClient

from app.core.config import API_VERSION
from tests.conftest import requires_db


@requires_db
def test_health_returns_ok(client: TestClient, migrated_engine) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Car Rental API",
        "version": API_VERSION,
        "environment": "test",
        "database": "ok",
    }


def test_health_is_only_served_under_api_prefix(client: TestClient) -> None:
    assert client.get("/health").status_code == 404
