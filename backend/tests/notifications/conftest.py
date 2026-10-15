import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.push import InMemoryPushProvider
from app.models import Notification, NotificationDelivery, User
from tests.api_fixtures import *  # noqa: F403  (shared API fixtures)
from tests.payments.fake_provider import FakePaymentProvider
from tests.tracking.conftest import alice, delivery_id  # noqa: F401  (a paid booking + delivery)


@pytest.fixture
def payment_provider() -> FakePaymentProvider:
    return FakePaymentProvider()


@pytest.fixture
def push() -> InMemoryPushProvider:
    return InMemoryPushProvider()


def user_id(session: Session, email: str):
    return session.scalar(select(User.id).where(User.email == email))


def events(session: Session, email: str) -> list[str]:
    """Events notified to a user, oldest first."""
    rows = session.scalars(
        select(Notification)
        .where(Notification.user_id == user_id(session, email))
        .order_by(Notification.created_at, Notification.event)
    )
    return [n.event for n in rows]


def latest(session: Session, email: str, event: str) -> Notification:
    return session.scalar(
        select(Notification)
        .where(Notification.user_id == user_id(session, email), Notification.event == event)
        .order_by(Notification.created_at.desc())
        .limit(1)
    )


def deliveries(session: Session, notification: Notification) -> dict[str, NotificationDelivery]:
    rows = session.scalars(
        select(NotificationDelivery).where(NotificationDelivery.notification_id == notification.id)
    )
    return {d.channel.value: d for d in rows}
