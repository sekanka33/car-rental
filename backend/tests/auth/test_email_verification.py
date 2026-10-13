from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.integrations.email import InMemoryEmailSender
from app.models import UserActionToken
from tests.auth.conftest import Account
from tests.conftest import requires_db

pytestmark = requires_db
VERIFY = "/api/v1/auth/verify-email"


def latest_token(outbox: InMemoryEmailSender) -> str:
    return outbox.outbox[-1].body.split("token=")[1].split()[0]


def test_verify_email_with_link_token(
    api: TestClient, renter: Account, outbox: InMemoryEmailSender
) -> None:
    response = api.post(VERIFY, json={"token": latest_token(outbox)})

    assert response.status_code == 200
    assert api.get("/api/v1/users/me", headers=renter.headers).json()["email_verified"] is True


def test_verification_token_is_single_use(
    api: TestClient, renter: Account, outbox: InMemoryEmailSender
) -> None:
    token = latest_token(outbox)
    api.post(VERIFY, json={"token": token})

    response = api.post(VERIFY, json={"token": token})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_or_expired_token"


def test_unknown_and_expired_tokens_rejected(
    api: TestClient, renter: Account, outbox: InMemoryEmailSender, db_session: Session
) -> None:
    assert api.post(VERIFY, json={"token": "x" * 43}).status_code == 400

    db_session.execute(
        update(UserActionToken).values(
            created_at=datetime.now(UTC) - timedelta(days=3),
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )
    assert api.post(VERIFY, json={"token": latest_token(outbox)}).status_code == 400


def test_resend_replaces_previous_link(
    api: TestClient, renter: Account, outbox: InMemoryEmailSender
) -> None:
    first = latest_token(outbox)

    response = api.post("/api/v1/auth/verify-email/resend", headers=renter.headers)

    assert response.status_code == 202
    second = latest_token(outbox)
    assert second != first
    assert api.post(VERIFY, json={"token": first}).status_code == 400
    assert api.post(VERIFY, json={"token": second}).status_code == 200


def test_resend_requires_authentication(api: TestClient) -> None:
    assert api.post("/api/v1/auth/verify-email/resend").status_code == 401
