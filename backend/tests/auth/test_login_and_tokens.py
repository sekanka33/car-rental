from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import RefreshToken, User
from tests.api_fixtures import Account, login, register
from tests.conftest import TEST_JWT_SECRET, requires_db

pytestmark = requires_db
ME = "/api/v1/users/me"


def test_login_returns_tokens_and_records_login(
    api: TestClient, renter: Account, db_session: Session
) -> None:
    response = api.get(ME, headers=renter.headers)

    assert response.status_code == 200
    assert response.json()["email"] == "renter@example.com"
    user = db_session.scalar(select(User).where(User.email == "renter@example.com"))
    assert user.last_login_at is not None


def test_login_is_case_insensitive_on_email(api: TestClient) -> None:
    register(api, "mixed@example.com")

    assert login(api, "MIXED@Example.com").access_token


def test_wrong_password_and_unknown_email_get_the_same_answer(api: TestClient) -> None:
    register(api, "known@example.com")

    wrong = api.post(
        "/api/v1/auth/login", json={"email": "known@example.com", "password": "nope-nope"}
    )
    unknown = api.post(
        "/api/v1/auth/login", json={"email": "ghost@example.com", "password": "nope-nope"}
    )

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["error"]["code"] == "invalid_credentials"
    assert wrong.headers["www-authenticate"] == "Bearer"


def test_protected_endpoint_requires_valid_token(api: TestClient, renter: Account) -> None:
    cases = {
        "missing": {},
        "wrong-scheme": {"Authorization": f"Basic {renter.access_token}"},
        "garbage": {"Authorization": "Bearer not.a.jwt"},
        "foreign-signature": {
            "Authorization": "Bearer "
            + create_access_token(
                user_id=__import__("uuid").uuid4(),
                token_version=0,
                secret="attacker-secret-0123456789abcdefghijklmn",
                issuer="car-rental-api",
                audience="car-rental-clients",
                ttl=timedelta(minutes=5),
            )
        },
    }
    for name, headers in cases.items():
        response = api.get(ME, headers=headers)
        assert response.status_code == 401, name
        assert response.json()["error"]["code"] == "not_authenticated", name


def test_expired_access_token_rejected(
    api: TestClient, renter: Account, db_session: Session
) -> None:
    user = db_session.scalar(select(User).where(User.email == renter.email))
    expired = create_access_token(
        user_id=user.id,
        token_version=user.token_version,
        secret=TEST_JWT_SECRET,
        issuer="car-rental-api",
        audience="car-rental-clients",
        ttl=timedelta(minutes=15),
        now=datetime.now(UTC) - timedelta(hours=1),
    )

    assert api.get(ME, headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_refresh_rotates_tokens(api: TestClient, renter: Account) -> None:
    response = api.post("/api/v1/auth/refresh", json={"refresh_token": renter.refresh_token})

    assert response.status_code == 200
    new = response.json()
    assert new["refresh_token"] != renter.refresh_token
    assert (
        api.get(ME, headers={"Authorization": f"Bearer {new['access_token']}"}).status_code == 200
    )
    # The old refresh token is single-use.
    again = api.post("/api/v1/auth/refresh", json={"refresh_token": renter.refresh_token})
    assert again.status_code == 401


def test_refresh_token_reuse_revokes_the_whole_session(api: TestClient, renter: Account) -> None:
    rotated = api.post("/api/v1/auth/refresh", json={"refresh_token": renter.refresh_token}).json()

    # An attacker replays the stolen original token...
    assert (
        api.post("/api/v1/auth/refresh", json={"refresh_token": renter.refresh_token}).status_code
        == 401
    )
    # ...so the legitimate, newer token is revoked too.
    response = api.post("/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]})
    assert response.status_code == 401


def test_other_sessions_survive_reuse_detection(api: TestClient, renter: Account) -> None:
    second_device = login(api, renter.email)
    api.post("/api/v1/auth/refresh", json={"refresh_token": renter.refresh_token})
    api.post("/api/v1/auth/refresh", json={"refresh_token": renter.refresh_token})  # reuse

    response = api.post("/api/v1/auth/refresh", json={"refresh_token": second_device.refresh_token})
    assert response.status_code == 200


def test_expired_refresh_token_rejected(
    api: TestClient, renter: Account, db_session: Session
) -> None:
    db_session.execute(
        update(RefreshToken).values(
            created_at=datetime.now(UTC) - timedelta(days=40),
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
    )

    response = api.post("/api/v1/auth/refresh", json={"refresh_token": renter.refresh_token})
    assert response.status_code == 401


def test_refresh_tokens_are_stored_hashed(renter: Account, db_session: Session) -> None:
    hashes = db_session.scalars(select(RefreshToken.token_hash)).all()

    assert hashes and renter.refresh_token not in hashes


def test_logout_revokes_refresh_token(api: TestClient, renter: Account) -> None:
    assert (
        api.post("/api/v1/auth/logout", json={"refresh_token": renter.refresh_token}).status_code
        == 204
    )

    response = api.post("/api/v1/auth/refresh", json={"refresh_token": renter.refresh_token})
    assert response.status_code == 401
    # Logging out twice (or with an unknown token) is harmless.
    assert (
        api.post("/api/v1/auth/logout", json={"refresh_token": renter.refresh_token}).status_code
        == 204
    )


def test_logout_all_invalidates_access_and_refresh_tokens(api: TestClient, renter: Account) -> None:
    other = login(api, renter.email)

    assert api.post("/api/v1/auth/logout-all", headers=renter.headers).status_code == 204

    assert api.get(ME, headers=renter.headers).status_code == 401
    assert api.get(ME, headers=other.headers).status_code == 401
    for token in (renter.refresh_token, other.refresh_token):
        assert api.post("/api/v1/auth/refresh", json={"refresh_token": token}).status_code == 401
    assert login(api, renter.email).access_token  # can sign in again
