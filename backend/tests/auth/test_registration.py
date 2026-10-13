import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.email import InMemoryEmailSender
from app.models import CustomerProfile, OwnerProfile, User
from tests.api_fixtures import DEFAULT_PASSWORD, register
from tests.conftest import requires_db

pytestmark = requires_db
URL = "/api/v1/auth/register"


def body(**overrides) -> dict:
    values = {
        "email": "Thandi.Nkosi@Example.com",
        "password": DEFAULT_PASSWORD,
        "full_name": "  Thandi Nkosi ",
        "phone_number": "082 123 4567",
        "account_type": "RENTER",
    }
    values.update(overrides)
    return values


def test_renter_registration(
    api: TestClient, db_session: Session, outbox: InMemoryEmailSender
) -> None:
    response = api.post(URL, json=body())

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "thandi.nkosi@example.com"
    assert data["full_name"] == "Thandi Nkosi"
    assert data["phone_number"] == "+27821234567"
    assert data["roles"] == ["RENTER"]
    assert data["status"] == "ACTIVE"
    assert data["email_verified"] is False
    assert "password" not in response.text and "password_hash" not in data

    user = db_session.scalar(select(User).where(User.email == "thandi.nkosi@example.com"))
    assert user.password_hash.startswith("$argon2id$")
    assert DEFAULT_PASSWORD not in user.password_hash
    assert db_session.scalar(select(CustomerProfile).where(CustomerProfile.user_id == user.id))

    assert len(outbox.outbox) == 1
    assert outbox.outbox[0].to == "thandi.nkosi@example.com"
    assert "carrental://verify-email?token=" in outbox.outbox[0].body


def test_owner_registration_creates_owner_profile(api: TestClient, db_session: Session) -> None:
    data = register(api, "owner1@example.com", "OWNER")

    assert data["roles"] == ["OWNER"]
    profile = db_session.scalar(select(OwnerProfile).where(OwnerProfile.user_id == data["id"]))
    assert profile is not None


@pytest.mark.parametrize(
    "overrides",
    [
        {"account_type": "ADMIN"},
        {"roles": ["ADMIN"]},
        {"role": "ADMIN"},
        {"status": "ACTIVE", "email_verified": True},
    ],
    ids=["admin-account-type", "roles-field", "role-field", "privileged-fields"],
)
def test_clients_cannot_choose_privileges(
    api: TestClient, db_session: Session, overrides: dict
) -> None:
    response = api.post(URL, json=body(**overrides))

    assert response.status_code == 422
    assert db_session.scalar(select(User).where(User.email == "thandi.nkosi@example.com")) is None


def test_duplicate_email_is_rejected_case_insensitively(api: TestClient) -> None:
    register(api, "dup@example.com")

    response = api.post(URL, json=body(email="DUP@example.com"))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_already_registered"


@pytest.mark.parametrize(
    ("overrides", "location"),
    [
        ({"password": "Zq9!x"}, "password"),
        ({"password": "x" * 129}, "password"),
        ({"email": "not-an-email"}, "email"),
        ({"phone_number": "12345"}, "phone_number"),
        ({"full_name": " "}, "full_name"),
        ({"password": "thandi.nkosi@example.com"}, None),
    ],
    ids=["short-password", "long-password", "bad-email", "bad-phone", "blank-name", "pw-is-email"],
)
def test_invalid_registration_input(api: TestClient, overrides: dict, location: str | None) -> None:
    response = api.post(URL, json=body(**overrides))

    assert response.status_code == 422
    error = response.json()["error"]
    if location:
        assert any(detail["location"][-1] == location for detail in error["details"])
    if "password" in overrides:  # submitted passwords are never echoed back
        assert overrides["password"] not in response.text


def test_email_failure_does_not_undo_registration(
    api: TestClient, outbox: InMemoryEmailSender, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_send(message):
        raise RuntimeError("provider down")

    monkeypatch.setattr(outbox, "send", broken_send)

    response = api.post(URL, json=body(email="unlucky@example.com"))

    assert response.status_code == 201
    assert login_works(api, "unlucky@example.com")


def login_works(api: TestClient, email: str) -> bool:
    response = api.post("/api/v1/auth/login", json={"email": email, "password": DEFAULT_PASSWORD})
    return response.status_code == 200
