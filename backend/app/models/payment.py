import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    CURRENCY_ZAR,
    Base,
    CreatedAtMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    str_enum,
)
from app.models.booking import Booking
from app.models.enums import PaymentStatus, RefundStatus


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A payment attempt for a booking. Status is only changed by verified provider events."""

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(f"currency = '{CURRENCY_ZAR}'", name="currency_zar"),
        CheckConstraint(
            "status <> 'SUCCEEDED' OR paid_at IS NOT NULL", name="succeeded_has_paid_at"
        ),
        # Each provider transaction maps to exactly one payment record.
        Index("uq_payments_provider_reference", "provider", "provider_reference", unique=True),
        # A booking can never have two successful payments recorded.
        Index(
            "uq_payments_one_success_per_booking",
            "booking_id",
            unique=True,
            postgresql_where=text("status = 'SUCCEEDED'"),
        ),
    )

    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bookings.id", ondelete="RESTRICT"), index=True
    )
    provider: Mapped[str] = mapped_column(String(40))
    provider_reference: Mapped[str | None] = mapped_column(String(255))
    amount: Mapped[Decimal]
    currency: Mapped[str] = mapped_column(
        String(3), default=CURRENCY_ZAR, server_default=CURRENCY_ZAR
    )
    status: Mapped[PaymentStatus] = mapped_column(
        str_enum(PaymentStatus, "payment_status"),
        default=PaymentStatus.PENDING,
        server_default="PENDING",
    )
    paid_at: Mapped[datetime | None]
    failure_reason: Mapped[str | None] = mapped_column(String(500))
    checkout_url: Mapped[str | None] = mapped_column(String(500))
    provider_transaction_id: Mapped[str | None] = mapped_column(String(64))
    last_verified_at: Mapped[datetime | None]
    initiated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )

    booking: Mapped[Booking] = relationship()
    refunds: Mapped[list["Refund"]] = relationship(
        back_populates="payment", order_by="Refund.created_at"
    )


class PaymentEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A signature-verified provider notification. The unique (provider, event_key) makes
    processing idempotent: a re-delivered webhook is recorded once and processed once."""

    __tablename__ = "payment_events"
    __table_args__ = (
        Index("uq_payment_events_provider_key", "provider", "event_key", unique=True),
    )

    provider: Mapped[str] = mapped_column(String(40))
    event_key: Mapped[str] = mapped_column(String(64))  # SHA-256 of the raw signed body
    event_type: Mapped[str] = mapped_column(String(80))
    reference: Mapped[str | None] = mapped_column(String(255), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    processed_at: Mapped[datetime | None]
    outcome: Mapped[str | None] = mapped_column(String(200))


class Refund(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "refunds"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(f"currency = '{CURRENCY_ZAR}'", name="currency_zar"),
        CheckConstraint(
            "status <> 'PROCESSED' OR processed_at IS NOT NULL", name="processed_has_timestamp"
        ),
        Index("uq_refunds_provider_refund_id", "provider", "provider_refund_id", unique=True),
    )

    payment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"), index=True
    )
    provider: Mapped[str] = mapped_column(String(40))
    provider_refund_id: Mapped[str | None] = mapped_column(String(64))
    amount: Mapped[Decimal]
    currency: Mapped[str] = mapped_column(
        String(3), default=CURRENCY_ZAR, server_default=CURRENCY_ZAR
    )
    status: Mapped[RefundStatus] = mapped_column(
        str_enum(RefundStatus, "refund_status"),
        default=RefundStatus.PENDING,
        server_default="PENDING",
    )
    reason: Mapped[str] = mapped_column(String(500))
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    processed_at: Mapped[datetime | None]
    failure_reason: Mapped[str | None] = mapped_column(String(500))

    payment: Mapped[Payment] = relationship(back_populates="refunds")
