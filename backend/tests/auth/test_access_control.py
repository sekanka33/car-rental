"""Role-based access control and account suspension."""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, User
from tests.api_fixtures import Account, login
from tests.conftest import requires_db

pytestmark = requires_db

# Endpoints intentionally reachable without an access token.
PUBLIC_ENDPOINTS = {
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/verify-email"),
    ("POST", "/api/v1/auth/password-reset/request"),
    ("POST", "/api/v1/auth/password-reset/confirm"),
}


def api_endpoints(app: FastAPI) -> list[tuple[str, str]]:
    """Every documented API operation, taken from the app's OpenAPI schema."""
    return sorted(
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    )


def test_every_non_public_endpoint_rejects_anonymous_requests(
    api_app: FastAPI, api: TestClient
) -> None:
    protected = [e for e in api_endpoints(api_app) if e not in PUBLIC_ENDPOINTS]
    assert protected, "expected protected endpoints"

    for method, path in protected:
        url = path.replace("{user_id}", str(uuid.uuid4()))
        response = api.request(method, url, json={})
        assert response.status_code == 401, f"{method} {path} -> {response.status_code}"


def test_public_endpoint_list_is_current(api_app: FastAPI) -> None:
    """Fails when a public endpoint is removed/renamed, so this allow-list stays honest."""
    assert PUBLIC_ENDPOINTS <= set(api_endpoints(api_app))


def test_owner_only_endpoint(
    api: TestClient, renter: Account, owner: Account, admin: Account
) -> None:
    url = "/api/v1/owners/me/profile"

    assert api.get(url, headers=owner.headers).status_code == 200
    assert api.get(url, headers=renter.headers).status_code == 403
    assert api.get(url, headers=admin.headers).status_code == 403


@pytest.mark.parametrize("who", ["renter", "owner"])
def test_non_admins_cannot_use_admin_endpoints(
    api: TestClient, request: pytest.FixtureRequest, who: str, db_session: Session
) -> None:
    account: Account = request.getfixturevalue(who)
    target = db_session.scalar(select(User.id).where(User.email == account.email))

    assert api.get("/api/v1/admin/users", headers=account.headers).status_code == 403
    response = api.post(
        f"/api/v1/admin/users/{target}/suspend", headers=account.headers, json={"reason": "test"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_admin_can_list_users(api: TestClient, admin: Account, renter: Account) -> None:
    response = api.get("/api/v1/admin/users", headers=admin.headers)

    assert response.status_code == 200
    emails = {user["email"] for user in response.json()["items"]}
    assert {"admin@example.com", "renter@example.com"} <= emails


def _user_id(db_session: Session, email: str) -> uuid.UUID:
    return db_session.scalar(select(User.id).where(User.email == email))


def test_suspension_blocks_access_immediately(
    api: TestClient, admin: Account, renter: Account, db_session: Session
) -> None:
    target = _user_id(db_session, renter.email)

    response = api.post(
        f"/api/v1/admin/users/{target}/suspend",
        headers=admin.headers,
        json={"reason": "Fraudulent documents"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "SUSPENDED"
    # Existing access token, refresh token and new logins are all refused.
    assert api.get("/api/v1/users/me", headers=renter.headers).status_code == 401
    assert (
        api.post("/api/v1/auth/refresh", json={"refresh_token": renter.refresh_token}).status_code
        == 401
    )
    blocked = api.post(
        "/api/v1/auth/login", json={"email": renter.email, "password": renter.password}
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "account_suspended"

    reactivated = api.post(f"/api/v1/admin/users/{target}/reactivate", headers=admin.headers)
    assert reactivated.status_code == 200
    assert login(api, renter.email).access_token

    actions = db_session.scalars(
        select(AuditLog.action).where(AuditLog.entity_id == str(target)).order_by(AuditLog.id)
    ).all()
    assert actions == ["user.suspended", "user.reactivated"]


def test_suspension_rules(
    api: TestClient, admin: Account, renter: Account, db_session: Session
) -> None:
    admin_id = _user_id(db_session, admin.email)
    target = _user_id(db_session, renter.email)
    suspend = lambda user_id: api.post(  # noqa: E731
        f"/api/v1/admin/users/{user_id}/suspend", headers=admin.headers, json={"reason": "Policy"}
    )

    assert suspend(admin_id).status_code == 400  # not yourself
    assert suspend(uuid.uuid4()).status_code == 404
    assert suspend(target).status_code == 200
    assert suspend(target).status_code == 409  # already suspended
    assert (
        api.post(f"/api/v1/admin/users/{admin_id}/reactivate", headers=admin.headers).status_code
        == 409
    )
    missing_reason = api.post(
        f"/api/v1/admin/users/{target}/suspend", headers=admin.headers, json={}
    )
    assert missing_reason.status_code == 422


@pytest.mark.parametrize(
    ("status", "code"),
    [("SUSPENDED", "account_suspended"), ("DEACTIVATED", "account_inactive")],
)
def test_account_status_is_checked_on_every_request(
    api: TestClient, renter: Account, db_session: Session, status: str, code: str
) -> None:
    """Even if a status change skipped token revocation, the status check still blocks access."""
    user = db_session.scalar(select(User).where(User.email == renter.email))
    user.status = status
    user.suspended_at = func.now() if status == "SUSPENDED" else None
    db_session.flush()

    response = api.get("/api/v1/users/me", headers=renter.headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == code
