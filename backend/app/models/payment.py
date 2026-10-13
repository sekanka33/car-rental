import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import CURRENCY_ZAR, Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.booking import Booking
from app.models.enums import PaymentStatus


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

    booking: Mapped[Booking] = relationship()
