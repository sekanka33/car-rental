import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    literal_column,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import CURRENCY_ZAR, Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.enums import BLOCKING_BOOKING_STATUSES, BookingStatus
from app.models.user import User
from app.models.vehicle import Vehicle, VehiclePrice

_BLOCKING_SQL = ", ".join(f"'{status.value}'" for status in BLOCKING_BOOKING_STATUSES)


class Booking(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A rental reservation with a frozen copy of the price agreed at booking time."""

    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("end_at > start_at", name="period_valid"),
        CheckConstraint("rental_days > 0", name="rental_days_positive"),
        CheckConstraint("daily_rate > 0", name="daily_rate_positive"),
        CheckConstraint("delivery_fee >= 0", name="delivery_fee_non_negative"),
        CheckConstraint("deposit_amount >= 0", name="deposit_non_negative"),
        CheckConstraint("rental_amount = daily_rate * rental_days", name="rental_amount_matches"),
        CheckConstraint("total_amount = rental_amount + delivery_fee", name="total_amount_matches"),
        CheckConstraint(f"currency = '{CURRENCY_ZAR}'", name="currency_zar"),
        CheckConstraint(
            "status <> 'PENDING_PAYMENT' OR hold_expires_at IS NOT NULL",
            name="pending_payment_has_hold",
        ),
        # No two reserving bookings for the same vehicle may overlap in time.
        
        ExcludeConstraint(
            ("vehicle_id", "="),
            (
                func.tstzrange(
                    literal_column("start_at"), literal_column("end_at"), literal_column("'[)'")
                ),
                "&&",
            ),
            name="ex_bookings_vehicle_period_overlap",
            using="gist",
            where=text(f"status IN ({_BLOCKING_SQL})"),
        ),
        Index("ix_bookings_vehicle_start", "vehicle_id", "start_at"),
        Index("ix_bookings_renter_created", "renter_id", "created_at"),
        Index("ix_bookings_status_hold", "status", "hold_expires_at"),
        CheckConstraint(
            "(status = 'CANCELLED') = (cancelled_at IS NOT NULL)", name="cancellation_consistent"
        ),
    )

    reference: Mapped[str] = mapped_column(String(20), unique=True)
    renter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id", ondelete="RESTRICT"))
    vehicle_price_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicle_prices.id", ondelete="RESTRICT")
    )
    start_at: Mapped[datetime]
    end_at: Mapped[datetime]
    status: Mapped[BookingStatus] = mapped_column(
        str_enum(BookingStatus, "booking_status"),
        default=BookingStatus.PENDING_PAYMENT,
        server_default="PENDING_PAYMENT",
    )
    hold_expires_at: Mapped[datetime | None]

    # Price snapshot (copied from vehicle_prices; never recalculated afterwards).
    daily_rate: Mapped[Decimal]
    rental_days: Mapped[int] = mapped_column(Integer)
    rental_amount: Mapped[Decimal]
    delivery_fee: Mapped[Decimal]
    deposit_amount: Mapped[Decimal]
    total_amount: Mapped[Decimal]
    currency: Mapped[str] = mapped_column(
        String(3), default=CURRENCY_ZAR, server_default=CURRENCY_ZAR
    )

    delivery_address: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None]
    cancelled_at: Mapped[datetime | None]
    cancelled_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    cancellation_reason: Mapped[str | None] = mapped_column(String(500))

    renter: Mapped[User] = relationship(foreign_keys=[renter_id])
    vehicle: Mapped[Vehicle] = relationship()
    price: Mapped[VehiclePrice] = relationship()
