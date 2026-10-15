"""Notifications (FR-36): an in-app inbox, email and push, sent through an outbox.

1. `notify()` is called by the business services inside the transaction that makes the change,
   so a notification exists if and only if the change was committed. A `dedupe_key` makes each
   event notify once, however often the code path runs (webhook retries, reconciliation...).
2. Each notification gets one delivery per channel. `dispatch_due()` sends due deliveries,
   locking them with SKIP LOCKED so several workers never send the same one twice. Failures
   are retried with backoff (1 min, 5 min, 30 min, 2 h); after NOTIFICATION_MAX_ATTEMPTS the
   delivery is FAILED and shows up for administrators, who can retry it.
3. Preferences are checked again at send time. Essential notifications (payment receipts,
   refunds, cancellations) are emailed even when email is turned off.

Account emails (verification, password reset) are sent directly by app/services/auth.py.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.errors import NotFoundError
from app.integrations.email import EmailDeliveryError, EmailMessage, EmailSender
from app.integrations.push import PushDeliveryError, PushMessage, PushProvider, is_expo_token
from app.models import (
    Notification,
    NotificationDelivery,
    NotificationPreference,
    PushToken,
    User,
)
from app.models.enums import DeliveryAttemptStatus, NotificationChannel, UserStatus

logger = logging.getLogger(__name__)
A = DeliveryAttemptStatus
BACKOFF = [timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=30), timedelta(hours=2)]
BATCH = 50


def _now() -> datetime:
    return datetime.now(UTC)


# --- creating notifications -------------------------------------------------------------------


def notify(
    session: Session,
    user_id: uuid.UUID,
    event: str,
    *,
    title: str,
    body: str,
    dedupe_key: str,
    link: str | None = None,
    essential: bool = False,
) -> bool:
    """Queue a notification in the caller's transaction. Returns False if this event was
    already notified (same dedupe key). The caller commits."""
    notification_id = session.scalar(
        insert(Notification)
        .values(
            id=uuid.uuid4(),
            user_id=user_id,
            event=event,
            title=title[:120],
            body=body,
            link=link,
            dedupe_key=dedupe_key[:200],
            essential=essential,
        )
        .on_conflict_do_nothing(index_elements=["dedupe_key"])
        .returning(Notification.id)
    )
    if notification_id is None:
        return False
    now = _now()
    for channel in NotificationChannel:
        session.add(
            NotificationDelivery(
                notification_id=notification_id, channel=channel, next_attempt_at=now
            )
        )
    return True


# --- preferences and devices ------------------------------------------------------------------


def get_preferences(session: Session, user: User) -> NotificationPreference:
    preference = session.get(NotificationPreference, user.id)
    return preference or NotificationPreference(
        user_id=user.id, email_enabled=True, push_enabled=True
    )


def set_preferences(
    session: Session, user: User, *, email_enabled: bool | None, push_enabled: bool | None
) -> NotificationPreference:
    preference = session.get(NotificationPreference, user.id)
    if preference is None:
        preference = NotificationPreference(user_id=user.id, email_enabled=True, push_enabled=True)
        session.add(preference)
    if email_enabled is not None:
        preference.email_enabled = email_enabled
    if push_enabled is not None:
        preference.push_enabled = push_enabled
    session.commit()
    return preference


class InvalidPushTokenError(Exception):
    pass


def register_push_token(session: Session, user: User, token: str, platform: str) -> PushToken:
    """Store this device's Expo token for the user. A token that moves to another account
    (shared phone, new login) belongs to the newest account only."""
    if not is_expo_token(token):
        raise InvalidPushTokenError(token)
    existing = session.scalar(select(PushToken).where(PushToken.token == token).with_for_update())
    if existing is None:
        existing = PushToken(user_id=user.id, token=token, platform=platform)
        session.add(existing)
    else:
        existing.user_id = user.id
        existing.platform = platform
        existing.disabled_at = None
        existing.disabled_reason = None
        existing.updated_at = _now()
    session.commit()
    return existing


def unregister_push_token(session: Session, user: User, token: str) -> None:
    """On logout: stop pushing to this device for this user."""
    session.execute(
        update(PushToken)
        .where(
            PushToken.token == token, PushToken.user_id == user.id, PushToken.disabled_at.is_(None)
        )
        .values(disabled_at=_now(), disabled_reason="signed out")
    )
    session.commit()


# --- inbox ------------------------------------------------------------------------------------


def list_inbox(
    session: Session, user: User, *, unread_only: bool, limit: int, offset: int
) -> tuple[list[Notification], int]:
    query = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    items = list(
        session.scalars(
            query.order_by(Notification.created_at.desc(), Notification.id)
            .limit(limit)
            .offset(offset)
        )
    )
    unread = session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
    )
    return items, unread or 0


def mark_read(session: Session, user: User, notification_id: uuid.UUID) -> Notification:
    notification = session.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise NotFoundError("Notification not found.")
    if notification.read_at is None:
        notification.read_at = _now()
        session.commit()
    return notification


def mark_all_read(session: Session, user: User) -> int:
    result = session.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=_now())
    )
    session.commit()
    return result.rowcount


# --- sending ----------------------------------------------------------------------------------


@dataclass
class DispatchResult:
    sent: int = 0
    skipped: int = 0
    retrying: int = 0
    failed: int = 0


def app_link(settings: Settings, path: str) -> str:
    """carrental:// + "/bookings/1" -> carrental://bookings/1 (the scheme's // is kept);
    https://app.example.com + "/bookings/1" -> https://app.example.com/bookings/1."""
    base = settings.app_link_base_url
    return (base if base.endswith("/") else base + "/") + path.lstrip("/")


def _email_text(settings: Settings, user: User, notification: Notification) -> EmailMessage:
    first_name = user.full_name.split()[0]
    lines = [f"Hi {first_name},", "", notification.body]
    if notification.link:
        lines += [
            "",
            f"Open in the app: {app_link(settings, notification.link)}",
        ]
    lines += [
        "",
        "— CarHire SA",
        "",
        "You can choose which messages you get by email in the app: Profile > Notifications."
        if not notification.essential
        else "This message is about your booking or payment, so it is always sent by email.",
    ]
    return EmailMessage(to=user.email, subject=notification.title, body="\n".join(lines))


class _Skip(Exception):
    pass


def _send_email(settings, sender, notification, user, preference) -> None:
    if not (preference.email_enabled or notification.essential):
        raise _Skip("email turned off")
    sender.send(_email_text(settings, user, notification))


def _send_push(session, push, notification, user, preference) -> None:
    if not preference.push_enabled:
        raise _Skip("push turned off")
    if push is None:
        raise _Skip("push not configured")
    tokens = list(
        session.scalars(
            select(PushToken).where(PushToken.user_id == user.id, PushToken.disabled_at.is_(None))
        )
    )
    if not tokens:
        raise _Skip("no device registered")
    data = {"notification_id": str(notification.id), "link": notification.link}
    tickets = push.send(
        [
            PushMessage(to=t.token, title=notification.title, body=notification.body, data=data)
            for t in tokens
        ]
    )
    delivered = False
    errors = []
    for token, ticket in zip(tokens, tickets, strict=True):
        if ticket.ok:
            delivered = True
        elif ticket.device_gone:
            token.disabled_at, token.disabled_reason = _now(), "DeviceNotRegistered"
        else:
            errors.append(ticket.error)
    if not delivered:
        if errors:
            raise PushDeliveryError(f"Expo refused the message: {', '.join(sorted(set(errors)))}")
        raise _Skip("no device registered")  # every token had been uninstalled


def dispatch_due(
    session: Session,
    settings: Settings,
    email_sender: EmailSender,
    push: PushProvider | None,
    *,
    now: datetime | None = None,
    limit: int = BATCH,
) -> DispatchResult:
    """Send deliveries that are due. Safe to run from several processes at once."""
    now = now or _now()
    result = DispatchResult()
    deliveries = list(
        session.scalars(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.status == A.PENDING,
                NotificationDelivery.next_attempt_at <= now,
            )
            .order_by(NotificationDelivery.next_attempt_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
            .options(
                selectinload(NotificationDelivery.notification).selectinload(Notification.user)
            )
        )
    )
    for delivery in deliveries:
        notification = delivery.notification
        user = notification.user
        preference = get_preferences(session, user)
        delivery.attempts += 1
        try:
            if user.status != UserStatus.ACTIVE:
                raise _Skip("account not active")
            if delivery.channel == NotificationChannel.EMAIL:
                _send_email(settings, email_sender, notification, user, preference)
            else:
                _send_push(session, push, notification, user, preference)
        except _Skip as reason:
            delivery.status, delivery.last_error = A.SKIPPED, str(reason)
            result.skipped += 1
        except Exception as exc:  # noqa: BLE001 - any failure to send is retried, then FAILED
            if not isinstance(exc, EmailDeliveryError | PushDeliveryError):
                logger.exception("Unexpected error sending notification %s", delivery.id)
            delivery.last_error = str(exc)[:500]
            if delivery.attempts >= settings.notification_max_attempts:
                delivery.status = A.FAILED
                result.failed += 1
                logger.warning(
                    "Notification %s %s failed for good: %s",
                    notification.event,
                    delivery.channel,
                    exc,
                )
            else:
                delivery.next_attempt_at = (
                    now + BACKOFF[min(delivery.attempts - 1, len(BACKOFF) - 1)]
                )
                result.retrying += 1
        else:
            delivery.status, delivery.sent_at, delivery.last_error = A.SENT, now, None
            result.sent += 1
    session.commit()
    return result


def dispatch_all(session, settings, email_sender, push, *, now=None) -> DispatchResult:
    """Run `dispatch_due` until nothing due is left (CLI and worker)."""
    total = DispatchResult()
    while True:
        batch = dispatch_due(session, settings, email_sender, push, now=now)
        for field in ("sent", "skipped", "retrying", "failed"):
            setattr(total, field, getattr(total, field) + getattr(batch, field))
        if sum((batch.sent, batch.skipped, batch.retrying, batch.failed)) < BATCH:
            return total


# --- administration ---------------------------------------------------------------------------


def list_deliveries(
    session: Session, *, status: DeliveryAttemptStatus | None, limit: int, offset: int
) -> tuple[list[NotificationDelivery], int]:
    conditions = [NotificationDelivery.status == status] if status else []
    total = session.scalar(
        select(func.count()).select_from(NotificationDelivery).where(*conditions)
    )
    rows = session.scalars(
        select(NotificationDelivery)
        .where(*conditions)
        .options(selectinload(NotificationDelivery.notification).selectinload(Notification.user))
        .order_by(NotificationDelivery.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows), total or 0


class NotRetryableError(Exception):
    pass


def retry_delivery(session: Session, delivery_id: uuid.UUID) -> NotificationDelivery:
    delivery = session.get(NotificationDelivery, delivery_id, with_for_update=True)
    if delivery is None:
        raise NotFoundError("Notification delivery not found.")
    if delivery.status != A.FAILED:
        raise NotRetryableError(delivery.status)
    delivery.status, delivery.attempts, delivery.next_attempt_at = A.PENDING, 0, _now()
    session.commit()
    return delivery


def purge_old(session: Session, settings: Settings, *, now: datetime | None = None) -> int:
    cutoff = (now or _now()) - timedelta(days=settings.notification_retention_days)
    result = session.execute(
        Notification.__table__.delete().where(Notification.created_at < cutoff)
    )
    session.commit()
    return result.rowcount
