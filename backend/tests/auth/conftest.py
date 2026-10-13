"""API-level fixtures for authentication tests.

Requests run inside the per-test database transaction (db_session), so everything an
endpoint commits is rolled back after the test.
"""

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.integrations.email import InMemoryEmailSender
from app.main import create_app
from app.services.accounts import create_admin
from tests.conftest import make_settings

DEFAULT_PASSWORD = "correct-horse-battery"


@pytest.fixture
def outbox() -> InMemoryEmailSender:
    return InMemoryEmailSender()


@pytest.fixture
def api_app(db_session: Session, outbox: InMemoryEmailSender) -> FastAPI:
    app = create_app(make_settings(), email_sender=outbox)

    def _test_db() -> Iterator[Session]:
        try:
            yield db_session
        except Exception:
            db_session.rollback()  # rolls back to the test's savepoint
            raise

    app.dependency_overrides[get_db] = _test_db
    return app


@pytest.fixture
def api(api_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(api_app, raise_server_exceptions=False) as client:
        yield client


@dataclass
class Account:
    email: str
    password: str
    access_token: str
    refresh_token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


def register(api: TestClient, email: str, account_type: str = "RENTER", **extra) -> dict:
    body = {
        "email": email,
        "password": DEFAULT_PASSWORD,
        "full_name": "Test Person",
        "account_type": account_type,
        **extra,
    }
    response = api.post("/api/v1/auth/register", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def login(api: TestClient, email: str, password: str = DEFAULT_PASSWORD) -> Account:
    response = api.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    tokens = response.json()
    return Account(email, password, tokens["access_token"], tokens["refresh_token"])


@pytest.fixture
def renter(api: TestClient) -> Account:
    register(api, "renter@example.com", "RENTER")
    return login(api, "renter@example.com")


@pytest.fixture
def owner(api: TestClient) -> Account:
    register(api, "owner@example.com", "OWNER")
    return login(api, "owner@example.com")


@pytest.fixture
def admin(api: TestClient, db_session: Session) -> Account:
    create_admin(
        db_session, email="admin@example.com", full_name="Platform Admin", password=DEFAULT_PASSWORD
    )
    return login(api, "admin@example.com")
