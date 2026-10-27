from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.core.errors import AppError
from app.core.rate_limits import enforce_request_limit


class SampleConflict(AppError):
    status_code = 409
    code = "sample_conflict"


class SampleBody(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)
    seats: int


def register_test_routes(app: FastAPI) -> None:
    """Routes that exist only inside these tests, to exercise the error handlers."""

    @app.post("/_test/validate")
    def validate(body: SampleBody) -> dict[str, str]:
        return {"email": body.email}

    @app.get("/_test/app-error")
    def app_error() -> None:
        raise SampleConflict("Vehicle is already booked for these dates.")

    @app.get("/_test/crash")
    def crash() -> None:
        raise RuntimeError("database password is hunter2")

    @app.get("/_test/rate-limit")
    def rate_limited(request: Request) -> dict[str, str]:
        enforce_request_limit(request, "test", 1, 60)
        return {"status": "ok"}


def test_unknown_route_returns_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not Found"}}
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert len(response.headers["X-Request-ID"]) == 32


def test_access_log_correlates_request_id_without_logging_query_values(
    client: TestClient, caplog
) -> None:
    response = client.get("/api/v1/does-not-exist?reset_token=private-value")
    access_log = next(record for record in caplog.records if record.message == "http_request")

    assert access_log.request_id == response.headers["X-Request-ID"]
    assert access_log.path == "/api/v1/does-not-exist"
    assert "private-value" not in access_log.getMessage()


def test_rate_limit_returns_retry_after_and_error_envelope(
    app: FastAPI, client: TestClient
) -> None:
    register_test_routes(app)

    assert client.get("/_test/rate-limit").status_code == 200
    response = client.get("/_test/rate-limit")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert response.json() == {
        "error": {"code": "rate_limited", "message": "Too many requests. Please try again later."}
    }


def test_wrong_method_returns_error_envelope(client: TestClient) -> None:
    response = client.post("/api/v1/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert "GET" in response.headers["allow"]


def test_validation_error_envelope(app: FastAPI, client: TestClient) -> None:
    register_test_routes(app)

    response = client.post(
        "/_test/validate", json={"email": "a@b.co", "password": "short", "seats": "many"}
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    locations = {tuple(detail["location"]) for detail in error["details"]}
    assert locations == {("body", "password"), ("body", "seats")}


def test_validation_error_does_not_echo_submitted_values(app: FastAPI, client: TestClient) -> None:
    register_test_routes(app)

    response = client.post(
        "/_test/validate", json={"email": "a@b.co", "password": "secret1", "seats": 4}
    )

    assert response.status_code == 422
    assert "secret1" not in response.text


def test_malformed_json_is_a_validation_error(app: FastAPI, client: TestClient) -> None:
    register_test_routes(app)

    response = client.post(
        "/_test/validate", content=b"{not json", headers={"content-type": "application/json"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_valid_request_passes_validation(app: FastAPI, client: TestClient) -> None:
    register_test_routes(app)

    response = client.post(
        "/_test/validate", json={"email": "a@b.co", "password": "long-enough", "seats": 4}
    )

    assert response.status_code == 200


def test_app_error_maps_to_status_and_code(app: FastAPI, client: TestClient) -> None:
    register_test_routes(app)

    response = client.get("/_test/app-error")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "sample_conflict",
            "message": "Vehicle is already booked for these dates.",
        }
    }


def test_unhandled_error_hides_internal_details(app: FastAPI, client: TestClient, caplog) -> None:
    register_test_routes(app)

    response = client.get("/_test/crash")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_server_error", "message": "An unexpected error occurred."}
    }
    assert "hunter2" not in response.text
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert len(response.headers["X-Request-ID"]) == 32
    # The real cause is still logged server-side for operators.
    assert "Unhandled error on GET /_test/crash" in caplog.text
