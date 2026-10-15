import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.enums import DeliveryAttemptStatus, NotificationChannel
from app.models.user import User


class Notification(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Something a user should know about (FR-36). It is shown in the app's inbox and sent by
    email and/or push through its `deliveries`. Written in the same transaction as the event
    that caused it (outbox), so it is never lost and never sent for a rolled-back change."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index(
            "ix_notifications_user_unread",
            "user_id",
            postgresql_where=text("read_at IS NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    event: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    # Path inside the app, e.g. "/bookings/<id>" (opened from the inbox, a push or an email).
    link: Mapped[str | None] = mapped_column(String(200))
    # One notification per event occurrence, however often the code path runs.
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    # Payment receipts, refunds and cancellations are emailed even if the user turned email off.
    essential: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    read_at: Mapped[datetime | None]

    user: Mapped[User] = relationship()
    deliveries: Mapped[list["NotificationDelivery"]] = relationship(
        back_populates="notification", cascade="all, delete-orphan", passive_deletes=True
    )


class NotificationDelivery(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        Index(
            "ix_notification_deliveries_due",
            "next_attempt_at",
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index("uq_notification_deliveries_channel", "notification_id", "channel", unique=True),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        CheckConstraint("status <> 'SENT' OR sent_at IS NOT NULL", name="sent_has_timestamp"),
    )

    notification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE")
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        str_enum(NotificationChannel, "notification_channel")
    )
    status: Mapped[DeliveryAttemptStatus] = mapped_column(
        str_enum(DeliveryAttemptStatus, "notification_delivery_status"),
        default=DeliveryAttemptStatus.PENDING,
        server_default="PENDING",
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_attempt_at: Mapped[datetime]
    last_error: Mapped[str | None] = mapped_column(String(500))
    sent_at: Mapped[datetime | None]

    notification: Mapped[Notification] = relationship(back_populates="deliveries")


class PushToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An Expo push token of one of the user's devices."""

    __tablename__ = "push_tokens"
    __table_args__ = (
        Index(
            "ix_push_tokens_user_active", "user_id", postgresql_where=text("disabled_at IS NULL")
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token: Mapped[str] = mapped_column(String(200), unique=True)
    platform: Mapped[str] = mapped_column(String(10))
    disabled_at: Mapped[datetime | None]
    disabled_reason: Mapped[str | None] = mapped_column(String(100))


class NotificationPreference(TimestampMixin, Base):
    """Per-user channel choices. In-app notifications are always kept."""

    __tablename__ = "notification_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
