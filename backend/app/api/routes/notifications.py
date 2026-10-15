"""In-app inbox, notification preferences and push devices (any signed-in user), and the
administrators' view of deliveries that could not be sent."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field, StringConstraints

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.core.errors import AppError
from app.models.enums import DeliveryAttemptStatus, NotificationChannel
from app.schemas.auth import RequestModel
from app.services import notifications

router = APIRouter(tags=["notifications"])


class InvalidPushToken(AppError):
    status_code = 422
    code = "invalid_push_token"


class NotRetryable(AppError):
    status_code = 409
    code = "not_retryable"


class NotificationResponse(BaseModel):
    id: uuid.UUID
    event: str
    title: str
    body: str
    link: str | None = Field(description="Path in the app to open, e.g. /bookings/<id>")
    created_at: datetime
    read_at: datetime | None


class InboxResponse(BaseModel):
    items: list[NotificationResponse]
    unread: int


class PreferencesResponse(BaseModel):
    email_enabled: bool
    push_enabled: bool
    note: str = "Payment receipts, refunds and cancellations are always emailed."


class PreferencesUpdate(RequestModel):
    email_enabled: bool | None = None
    push_enabled: bool | None = None


class PushTokenRequest(RequestModel):
    token: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=200)]
    platform: Literal["ios", "android", "web"] = "android"


class PushTokenRemoval(RequestModel):
    token: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=200)]


def _item(n) -> NotificationResponse:
    return NotificationResponse(
        id=n.id,
        event=n.event,
        title=n.title,
        body=n.body,
        link=n.link,
        created_at=n.created_at,
        read_at=n.read_at,
    )


@router.get("/notifications/me", response_model=InboxResponse)
def read_inbox(
    user: CurrentUser,
    session: DbSession,
    unread_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InboxResponse:
    """Your notifications, newest first, with the number still unread."""
    items, unread = notifications.list_inbox(
        session, user, unread_only=unread_only, limit=limit, offset=offset
    )
    return InboxResponse(items=[_item(n) for n in items], unread=unread)


@router.post("/notifications/me/{notification_id}/read", response_model=NotificationResponse)
def mark_read(notification_id: uuid.UUID, user: CurrentUser, session: DbSession):
    return _item(notifications.mark_read(session, user, notification_id))


@router.post("/notifications/me/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(user: CurrentUser, session: DbSession) -> None:
    notifications.mark_all_read(session, user)


@router.get("/notifications/me/preferences", response_model=PreferencesResponse)
def read_preferences(user: CurrentUser, session: DbSession) -> PreferencesResponse:
    p = notifications.get_preferences(session, user)
    return PreferencesResponse(email_enabled=p.email_enabled, push_enabled=p.push_enabled)


@router.put("/notifications/me/preferences", response_model=PreferencesResponse)
def update_preferences(
    body: PreferencesUpdate, user: CurrentUser, session: DbSession
) -> PreferencesResponse:
    p = notifications.set_preferences(
        session, user, email_enabled=body.email_enabled, push_enabled=body.push_enabled
    )
    return PreferencesResponse(email_enabled=p.email_enabled, push_enabled=p.push_enabled)


@router.post("/notifications/me/push-tokens", status_code=status.HTTP_204_NO_CONTENT)
def register_push_token(body: PushTokenRequest, user: CurrentUser, session: DbSession) -> None:
    """Register this device's Expo push token (call after every sign-in)."""
    try:
        notifications.register_push_token(session, user, body.token, body.platform)
    except notifications.InvalidPushTokenError as exc:
        raise InvalidPushToken("This is not an Expo push token.") from exc


@router.post("/notifications/me/push-tokens/remove", status_code=status.HTTP_204_NO_CONTENT)
def remove_push_token(body: PushTokenRemoval, user: CurrentUser, session: DbSession) -> None:
    """Stop push notifications to this device (call before signing out)."""
    notifications.unregister_push_token(session, user, body.token)


# --- administrators -----------------------------------------------------------------------------


class AdminDeliveryResponse(BaseModel):
    id: uuid.UUID
    channel: NotificationChannel
    status: DeliveryAttemptStatus
    attempts: int
    last_error: str | None
    next_attempt_at: datetime
    sent_at: datetime | None
    updated_at: datetime
    event: str
    title: str
    user_id: uuid.UUID
    user_email: str
    created_at: datetime


class AdminDeliveryList(BaseModel):
    items: list[AdminDeliveryResponse]
    total: int


@router.get("/admin/notifications", response_model=AdminDeliveryList, tags=["admin: notifications"])
def list_deliveries(
    _: AdminUser,
    session: DbSession,
    status_filter: Annotated[DeliveryAttemptStatus | None, Query(alias="status")] = (
        DeliveryAttemptStatus.FAILED
    ),
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminDeliveryList:
    """Email and push deliveries, most recently changed first (default: failed ones)."""
    rows, total = notifications.list_deliveries(
        session, status=status_filter, limit=limit, offset=offset
    )
    return AdminDeliveryList(
        items=[
            AdminDeliveryResponse(
                id=d.id,
                channel=d.channel,
                status=d.status,
                attempts=d.attempts,
                last_error=d.last_error,
                next_attempt_at=d.next_attempt_at,
                sent_at=d.sent_at,
                updated_at=d.updated_at,
                event=d.notification.event,
                title=d.notification.title,
                user_id=d.notification.user_id,
                user_email=d.notification.user.email,
                created_at=d.notification.created_at,
            )
            for d in rows
        ],
        total=total,
    )


@router.post(
    "/admin/notifications/{delivery_id}/retry",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["admin: notifications"],
)
def retry_delivery(delivery_id: uuid.UUID, _: AdminUser, session: DbSession) -> None:
    """Send a FAILED delivery again (attempts start over)."""
    try:
        notifications.retry_delivery(session, delivery_id)
    except notifications.NotRetryableError as exc:
        raise NotRetryable(f"Only failed deliveries can be retried (this one is {exc}).") from exc
