"""Request-scoped session dependency and the database-aware health check."""

from collections.abc import Callable

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from tests.conftest import requires_db


@requires_db
def test_failed_request_rolls_back_its_writes(app: FastAPI, migrated_engine) -> None:
    @app.post("/_test/write-then-fail")
    def write_then_fail(session: Session = Depends(get_db)) -> None:  # noqa: B008
        session.execute(text("INSERT INTO roles (id, name, description) VALUES (99, 'ADMIN', 'x')"))
        raise RuntimeError("boom")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/_test/write-then-fail")

    assert response.status_code == 500
    with migrated_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM roles WHERE id = 99")) == 0


@requires_db
def test_committed_work_is_persisted(app: FastAPI, migrated_engine) -> None:
    @app.post("/_test/write-and-commit")
    def write_and_commit(session: Session = Depends(get_db)) -> dict[str, str]:  # noqa: B008
        session.execute(
            text(
                "INSERT INTO users (email, password_hash, full_name) "
                "VALUES ('commit-test@example.com', 'x', 'Commit Test')"
            )
        )
        session.commit()
        return {"ok": "yes"}

    with TestClient(app) as client:
        assert client.post("/_test/write-and-commit").status_code == 200

    with migrated_engine.begin() as connection:
        email = "commit-test@example.com"
        assert (
            connection.scalar(text("SELECT count(*) FROM users WHERE email = :e"), {"e": email})
            == 1
        )
        connection.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})


def test_health_reports_unavailable_database(client_for: Callable[..., TestClient]) -> None:
    from tests.conftest import UNREACHABLE_DATABASE_URL

    response = client_for(database_url=UNREACHABLE_DATABASE_URL).get("/api/v1/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "unavailable"
