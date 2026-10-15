"""Sending: channels, preferences, devices, retries and failures."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.integrations.email import EmailDeliveryError, InMemoryEmailSender
from app.models import NotificationPreference, PushToken, User
from app.models.enums import DeliveryAttemptStatus, UserStatus
from app.services import notifications
from tests.conftest import make_settings, requires_db
from tests.notifications.conftest import deliveries, latest, user_id

pytestmark = requires_db
EMAIL = "alice@example.com"
TOKEN = "ExponentPushToken[aaaaaaaaaaaaaaaaaaaaaa]"
SETTINGS = make_settings(app_link_base_url="carrental://")


class FlakyEmail(InMemoryEmailSender):
    def __init__(self, failures: int) -> None:
        super().__init__()
        self.failures = failures

    def send(self, message) -> None:
        if self.failures:
            self.failures -= 1
            raise EmailDeliveryError("SMTP delivery failed: SMTPServerDisconnected")
        super().send(message)


@pytest.fixture
def uid(db_session, alice):
    return user_id(db_session, EMAIL)


def queue(session: Session, uid, key="k1", *, essential=False, link="/bookings/b1"):
    notifications.notify(
        session,
        uid,
        "test.event",
        title="Booking confirmed",
        body="All set.",
        dedupe_key=key,
        link=link,
        essential=essential,
    )
    return latest(session, EMAIL, "test.event")


def device(session: Session, uid, token=TOKEN) -> PushToken:
    token_row = PushToken(user_id=uid, token=token, platform="android")
    session.add(token_row)
    session.flush()
    return token_row


def status(session, note) -> dict[str, str]:
    session.expire_all()
    return {channel: d.status.value for channel, d in deliveries(session, note).items()}


def test_email_and_push_are_sent_with_a_link_into_the_app(db_session, uid, push) -> None:
    device(db_session, uid)
    note = queue(db_session, uid)
    email = InMemoryEmailSender()

    result = notifications.dispatch_due(db_session, SETTINGS, email, push)

    assert (result.sent, result.skipped) == (2, 0)
    assert status(db_session, note) == {"EMAIL": "SENT", "PUSH": "SENT"}
    message = email.outbox[-1]
    assert message.to == EMAIL and message.subject == "Booking confirmed"
    assert "carrental://bookings/b1" in message.body and message.body.startswith("Hi ")
    assert push.sent[0].to == TOKEN and push.sent[0].data == {
        "notification_id": str(note.id),
        "link": "/bookings/b1",
    }


def test_push_is_skipped_without_a_device_and_nothing_is_resent(db_session, uid, push) -> None:
    note = queue(db_session, uid)
    notifications.dispatch_due(db_session, SETTINGS, InMemoryEmailSender(), push)
    again = notifications.dispatch_due(db_session, SETTINGS, InMemoryEmailSender(), push)

    assert status(db_session, note) == {"EMAIL": "SENT", "PUSH": "SKIPPED"}
    assert deliveries(db_session, note)["PUSH"].last_error == "no device registered"
    assert (again.sent, again.skipped) == (0, 0)


def test_preferences_are_respected_except_for_essential_emails(db_session, uid, push) -> None:
    device(db_session, uid)
    db_session.add(NotificationPreference(user_id=uid, email_enabled=False, push_enabled=False))
    db_session.flush()
    optional = queue(db_session, uid, "k-optional")
    essential = queue(db_session, uid, "k-essential", essential=True)
    email = InMemoryEmailSender()

    notifications.dispatch_due(db_session, SETTINGS, email, push)

    assert status(db_session, optional) == {"EMAIL": "SKIPPED", "PUSH": "SKIPPED"}
    assert status(db_session, essential) == {"EMAIL": "SENT", "PUSH": "SKIPPED"}
    assert len(email.outbox) == 1 and "always sent by email" in email.outbox[0].body
    assert push.sent == []


def test_uninstalled_devices_are_disabled(db_session, uid, push) -> None:
    gone = device(db_session, uid, "ExponentPushToken[gonegonegonegonegone]")
    device(db_session, uid, "ExponentPushToken[livelivelivelivelive]")
    push.gone.add(gone.token)
    note = queue(db_session, uid)

    notifications.dispatch_due(db_session, SETTINGS, InMemoryEmailSender(), push)

    assert status(db_session, note)["PUSH"] == "SENT"
    db_session.refresh(gone)
    assert gone.disabled_reason == "DeviceNotRegistered" and gone.disabled_at is not None


def test_failures_are_retried_with_backoff_then_marked_failed(db_session, uid, push) -> None:
    note = queue(db_session, uid)
    email = FlakyEmail(failures=99)
    settings = make_settings(notification_max_attempts=3)
    now = datetime.now(UTC)

    first = notifications.dispatch_due(db_session, settings, email, push, now=now)
    delivery = deliveries(db_session, note)["EMAIL"]
    assert first.retrying == 1 and delivery.status == DeliveryAttemptStatus.PENDING
    assert delivery.next_attempt_at == now + timedelta(minutes=1)
    assert (
        notifications.dispatch_due(db_session, settings, email, push, now=now).retrying == 0
    )  # not due yet

    notifications.dispatch_due(db_session, settings, email, push, now=now + timedelta(minutes=1))
    assert deliveries(db_session, note)["EMAIL"].next_attempt_at == now + timedelta(minutes=6)
    last = notifications.dispatch_due(
        db_session, settings, email, push, now=now + timedelta(minutes=6)
    )

    delivery = deliveries(db_session, note)["EMAIL"]
    assert (
        last.failed == 1
        and delivery.status == DeliveryAttemptStatus.FAILED
        and delivery.attempts == 3
    )
    assert "SMTPServerDisconnected" in delivery.last_error


def test_a_transient_failure_then_success(db_session, uid, push) -> None:
    note = queue(db_session, uid)
    email = FlakyEmail(failures=1)
    now = datetime.now(UTC)
    notifications.dispatch_due(db_session, SETTINGS, email, push, now=now)
    notifications.dispatch_due(db_session, SETTINGS, email, push, now=now + timedelta(minutes=2))

    delivery = deliveries(db_session, note)["EMAIL"]
    assert (
        delivery.status == DeliveryAttemptStatus.SENT
        and delivery.attempts == 2
        and delivery.last_error is None
    )


def test_push_outage_is_retried(db_session, uid, push) -> None:
    device(db_session, uid)
    note = queue(db_session, uid)
    push.fail_next = True
    notifications.dispatch_due(db_session, SETTINGS, InMemoryEmailSender(), push)
    assert deliveries(db_session, note)["PUSH"].status == DeliveryAttemptStatus.PENDING


def test_inactive_accounts_get_nothing(db_session, uid, push) -> None:
    note = queue(db_session, uid)
    user = db_session.get(User, uid)
    user.status, user.suspended_at = UserStatus.SUSPENDED, datetime.now(UTC)
    db_session.flush()
    email = InMemoryEmailSender()
    notifications.dispatch_due(db_session, SETTINGS, email, push)

    assert status(db_session, note) == {"EMAIL": "SKIPPED", "PUSH": "SKIPPED"}
    assert email.outbox == []


def test_admin_retry_starts_over(db_session, uid, push) -> None:
    note = queue(db_session, uid)
    notifications.dispatch_due(
        db_session, make_settings(notification_max_attempts=1), FlakyEmail(9), push
    )
    failed = deliveries(db_session, note)["EMAIL"]
    assert failed.status == DeliveryAttemptStatus.FAILED

    notifications.retry_delivery(db_session, failed.id)
    notifications.dispatch_due(db_session, SETTINGS, InMemoryEmailSender(), push)
    assert deliveries(db_session, note)["EMAIL"].status == DeliveryAttemptStatus.SENT
    with pytest.raises(notifications.NotRetryableError):
        notifications.retry_delivery(db_session, failed.id)


def test_purge_deletes_old_notifications_with_their_deliveries(db_session, uid) -> None:
    note = queue(db_session, uid)
    note.created_at = datetime.now(UTC) - timedelta(days=200)
    db_session.flush()
    assert notifications.purge_old(db_session, make_settings(notification_retention_days=180)) == 1


@pytest.mark.parametrize(
    ("base", "expected"),
    [
        ("carrental://", "carrental://bookings/b1"),
        ("https://app.example.com", "https://app.example.com/bookings/b1"),
        ("https://app.example.com/", "https://app.example.com/bookings/b1"),
    ],
)
def test_app_links(base, expected) -> None:
    assert notifications.app_link(make_settings(app_link_base_url=base), "/bookings/b1") == expected
