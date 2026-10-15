"""Inbox, preferences, devices and the administrators' failed-delivery view."""

import pytest
from sqlalchemy import select

from app.models import PushToken
from app.services import notifications
from tests.api_fixtures import login, register
from tests.conftest import requires_db
from tests.notifications.conftest import user_id

pytestmark = requires_db
ME = "/api/v1/notifications/me"
TOKEN = "ExponentPushToken[bbbbbbbbbbbbbbbbbbbbbb]"


@pytest.fixture
def inbox(db_session, renter):
    uid = user_id(db_session, "renter@example.com")
    for n in range(3):
        notifications.notify(db_session, uid, "t.e", title=f"N{n}", body="b", dedupe_key=f"api:{n}")
    db_session.flush()
    return uid


def test_inbox_lists_and_marks_read(api, renter, owner, inbox) -> None:
    body = api.get(ME, headers=renter.headers).json()
    assert body["unread"] == 3 and len(body["items"]) == 3

    first = body["items"][0]["id"]
    assert api.post(f"{ME}/{first}/read", headers=renter.headers).json()["read_at"]
    assert api.get(ME, headers=renter.headers).json()["unread"] == 2
    assert len(api.get(f"{ME}?unread_only=true", headers=renter.headers).json()["items"]) == 2

    assert api.post(f"{ME}/{first}/read", headers=owner.headers).status_code == 404  # not theirs
    assert api.post(f"{ME}/read-all", headers=renter.headers).status_code == 204
    assert api.get(ME, headers=renter.headers).json()["unread"] == 0
    assert api.get(ME, headers=owner.headers).json() == {"items": [], "unread": 0}


def test_inbox_needs_a_session(api) -> None:
    assert api.get(ME).status_code == 401


def test_preferences(api, renter) -> None:
    assert api.get(f"{ME}/preferences", headers=renter.headers).json()["email_enabled"] is True
    body = api.put(f"{ME}/preferences", headers=renter.headers, json={"push_enabled": False}).json()
    assert (body["email_enabled"], body["push_enabled"]) == (True, False)
    assert "always emailed" in body["note"]


def test_push_tokens_follow_the_signed_in_account(api, renter, owner, db_session) -> None:
    bad = api.post(f"{ME}/push-tokens", headers=renter.headers, json={"token": "not-an-expo-token"})
    assert bad.status_code == 422

    assert (
        api.post(
            f"{ME}/push-tokens", headers=renter.headers, json={"token": TOKEN, "platform": "ios"}
        ).status_code
        == 204
    )
    # The same phone signs in as someone else: the token moves.
    assert (
        api.post(f"{ME}/push-tokens", headers=owner.headers, json={"token": TOKEN}).status_code
        == 204
    )
    row = db_session.scalar(select(PushToken).where(PushToken.token == TOKEN))
    assert row.user_id == user_id(db_session, "owner@example.com")

    # Removing it as the previous user does nothing; as the owner it disables it.
    api.post(f"{ME}/push-tokens/remove", headers=renter.headers, json={"token": TOKEN})
    db_session.refresh(row)
    assert row.disabled_at is None
    api.post(f"{ME}/push-tokens/remove", headers=owner.headers, json={"token": TOKEN})
    db_session.refresh(row)
    assert row.disabled_reason == "signed out"


def test_admin_sees_and_retries_failed_deliveries(api, admin, renter, inbox, db_session) -> None:
    from app.integrations.email import EmailDeliveryError
    from tests.conftest import make_settings

    class Down:
        def send(self, message):
            raise EmailDeliveryError("SMTP delivery failed: timeout")

    notifications.dispatch_due(db_session, make_settings(notification_max_attempts=1), Down(), None)

    failed = api.get("/api/v1/admin/notifications", headers=admin.headers).json()
    assert failed["total"] == 3 and {i["channel"] for i in failed["items"]} == {"EMAIL"}
    assert failed["items"][0]["user_email"] == "renter@example.com"
    skipped = api.get("/api/v1/admin/notifications?status=SKIPPED", headers=admin.headers).json()
    assert skipped["total"] == 3  # push: no device

    target = failed["items"][0]["id"]
    assert (
        api.post(f"/api/v1/admin/notifications/{target}/retry", headers=admin.headers).status_code
        == 204
    )
    assert (
        api.post(f"/api/v1/admin/notifications/{target}/retry", headers=admin.headers).status_code
        == 409
    )
    assert api.get("/api/v1/admin/notifications", headers=renter.headers).status_code == 403


def test_signing_in_again_on_a_new_phone(api, db_session) -> None:
    register(api, "multi@example.com", "RENTER")
    account = login(api, "multi@example.com")
    for token in (TOKEN, "ExponentPushToken[cccccccccccccccccccccc]"):
        api.post(f"{ME}/push-tokens", headers=account.headers, json={"token": token})
    active = db_session.scalars(
        select(PushToken).where(
            PushToken.user_id == user_id(db_session, "multi@example.com"),
            PushToken.disabled_at.is_(None),
        )
    ).all()
    assert len(active) == 2
