from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.integrations.email import InMemoryEmailSender
from app.models import AuditLog, UserActionToken
from app.models.enums import UserActionTokenPurpose
from tests.api_fixtures import Account
from tests.auth.test_email_verification import latest_token
from tests.conftest import requires_db

pytestmark = requires_db
REQUEST = "/api/v1/auth/password-reset/request"
CONFIRM = "/api/v1/auth/password-reset/confirm"
NEW_PASSWORD = "a-brand-new-passphrase"


def request_reset(api: TestClient, email: str):
    return api.post(REQUEST, json={"email": email})


def test_reset_request_does_not_reveal_whether_account_exists(
    api: TestClient, renter: Account, outbox: InMemoryEmailSender
) -> None:
    sent_before = len(outbox.outbox)

    known = request_reset(api, renter.email)
    unknown = request_reset(api, "nobody@example.com")

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(outbox.outbox) == sent_before + 1  # only the real account got an email
    assert "reset-password?token=" in outbox.outbox[-1].body


def test_reset_changes_password_and_signs_out_everywhere(
    api: TestClient, renter: Account, outbox: InMemoryEmailSender, db_session: Session
) -> None:
    request_reset(api, renter.email)

    response = api.post(CONFIRM, json={"token": latest_token(outbox), "new_password": NEW_PASSWORD})

    assert response.status_code == 200
    assert api.get("/api/v1/users/me", headers=renter.headers).status_code == 401
    assert (
        api.post("/api/v1/auth/refresh", json={"refresh_token": renter.refresh_token}).status_code
        == 401
    )
    old = api.post("/api/v1/auth/login", json={"email": renter.email, "password": renter.password})
    assert old.status_code == 401
    new = api.post("/api/v1/auth/login", json={"email": renter.email, "password": NEW_PASSWORD})
    assert new.status_code == 200
    audit = db_session.scalars(select(AuditLog.action)).all()
    assert "user.password_reset" in audit


def test_reset_token_single_use_and_latest_only(
    api: TestClient, renter: Account, outbox: InMemoryEmailSender
) -> None:
    request_reset(api, renter.email)
    first = latest_token(outbox)
    request_reset(api, renter.email)
    second = latest_token(outbox)

    assert api.post(CONFIRM, json={"token": first, "new_password": NEW_PASSWORD}).status_code == 400
    assert (
        api.post(CONFIRM, json={"token": second, "new_password": NEW_PASSWORD}).status_code == 200
    )
    assert (
        api.post(CONFIRM, json={"token": second, "new_password": NEW_PASSWORD}).status_code == 400
    )


def test_expired_reset_token_rejected(
    api: TestClient, renter: Account, outbox: InMemoryEmailSender, db_session: Session
) -> None:
    request_reset(api, renter.email)
    db_session.execute(
        update(UserActionToken)
        .where(UserActionToken.purpose == UserActionTokenPurpose.PASSWORD_RESET)
        .values(
            created_at=datetime.now(UTC) - timedelta(hours=2),
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )

    response = api.post(CONFIRM, json={"token": latest_token(outbox), "new_password": NEW_PASSWORD})
    assert response.status_code == 400


def test_email_verification_token_cannot_reset_password(
    api: TestClient, renter: Account, outbox: InMemoryEmailSender
) -> None:
    verification_token = latest_token(outbox)  # sent at registration

    response = api.post(CONFIRM, json={"token": verification_token, "new_password": NEW_PASSWORD})
    assert response.status_code == 400


def test_new_password_is_validated(
    api: TestClient, renter: Account, outbox: InMemoryEmailSender
) -> None:
    request_reset(api, renter.email)

    response = api.post(CONFIRM, json={"token": latest_token(outbox), "new_password": "short"})
    assert response.status_code == 422
