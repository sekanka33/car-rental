import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.booking import Booking
from app.models.enums import DeliveryStatus
from app.models.user import User


class Delivery(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Delivery of a booked vehicle to the renter (one per booking)."""

    __tablename__ = "deliveries"
    __table_args__ = (
        CheckConstraint("dropoff_latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint("dropoff_longitude BETWEEN -180 AND 180", name="longitude_range"),
        CheckConstraint(
            "(dropoff_latitude IS NULL) = (dropoff_longitude IS NULL)", name="coordinates_paired"
        ),
        CheckConstraint(
            "status <> 'DELIVERED' OR delivered_at IS NOT NULL", name="delivered_has_timestamp"
        ),
    )

    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bookings.id", ondelete="RESTRICT"), unique=True
    )
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[DeliveryStatus] = mapped_column(
        str_enum(DeliveryStatus, "delivery_status"),
        default=DeliveryStatus.PENDING_ASSIGNMENT,
        server_default="PENDING_ASSIGNMENT",
    )
    scheduled_for: Mapped[datetime | None]
    dropoff_address: Mapped[str] = mapped_column(Text)
    dropoff_latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    dropoff_longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    started_at: Mapped[datetime | None]
    delivered_at: Mapped[datetime | None]
    cancelled_at: Mapped[datetime | None]
    notes: Mapped[str | None] = mapped_column(Text)

    booking: Mapped[Booking] = relationship()
    assigned_to: Mapped[User | None] = relationship()
