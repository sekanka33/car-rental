import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.booking import Booking
from app.models.enums import DeliveryExceptionKind, DeliveryStatus, FuelLevel, HandoverKind
from app.models.user import User


class Delivery(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Delivery of a booked vehicle to the renter (one per booking), and its return."""

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
        CheckConstraint(
            "status NOT IN ('SCHEDULED', 'EN_ROUTE', 'DELIVERED') OR scheduled_for IS NOT NULL",
            name="scheduled_has_time",
        ),
        CheckConstraint(
            "status NOT IN ('EN_ROUTE', 'DELIVERED') OR started_at IS NOT NULL",
            name="started_has_timestamp",
        ),
        CheckConstraint(
            "(status = 'CANCELLED') = (cancelled_at IS NOT NULL)", name="cancellation_consistent"
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
        default=DeliveryStatus.PENDING_SCHEDULE,
        server_default="PENDING_SCHEDULE",
    )
    scheduled_for: Mapped[datetime | None]
    dropoff_address: Mapped[str] = mapped_column(Text)
    dropoff_latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    dropoff_longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    started_at: Mapped[datetime | None]
    delivered_at: Mapped[datetime | None]
    cancelled_at: Mapped[datetime | None]
    notes: Mapped[str | None] = mapped_column(Text)
    # Live tracking (Stage 13): the drop-off is geocoded once; the ETA is refreshed at most
    # every ETA_REFRESH_SECONDS while the delivery is EN_ROUTE.
    geocode_attempted_at: Mapped[datetime | None]
    eta_seconds: Mapped[int | None] = mapped_column(Integer)
    eta_distance_m: Mapped[int | None] = mapped_column(Integer)
    eta_computed_at: Mapped[datetime | None]

    booking: Mapped[Booking] = relationship()
    assigned_to: Mapped[User | None] = relationship()
    records: Mapped[list["HandoverRecord"]] = relationship(
        back_populates="delivery", order_by="HandoverRecord.recorded_at"
    )
    exceptions: Mapped[list["DeliveryException"]] = relationship(
        back_populates="delivery", order_by="DeliveryException.created_at"
    )

    def record(self, kind: HandoverKind) -> "HandoverRecord | None":
        return next((r for r in self.records if r.kind == kind), None)


class DeliveryLocationUpdate(UUIDPrimaryKeyMixin, Base):
    """A position sent by the delivery person while EN_ROUTE (BR-7.2). Not audited: it is
    personal data kept only for LOCATION_RETENTION_DAYS (BR-7.5)."""

    __tablename__ = "delivery_location_updates"
    __table_args__ = (
        Index("ix_delivery_location_updates_delivery_recorded", "delivery_id", "recorded_at"),
        Index("ix_delivery_location_updates_received", "received_at"),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="longitude_range"),
        CheckConstraint("accuracy_m IS NULL OR accuracy_m >= 0", name="accuracy_non_negative"),
        CheckConstraint(
            "heading IS NULL OR (heading >= 0 AND heading < 360)", name="heading_range"
        ),
        CheckConstraint("speed_mps IS NULL OR speed_mps >= 0", name="speed_non_negative"),
    )

    delivery_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deliveries.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    accuracy_m: Mapped[Decimal | None] = mapped_column(Numeric(7, 1))
    heading: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    speed_mps: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    recorded_at: Mapped[datetime]  # device time of the fix
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())


class HandoverRecord(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Condition of the vehicle when it is handed to the renter, and when it comes back."""

    __tablename__ = "handover_records"
    __table_args__ = (
        Index("uq_handover_records_delivery_kind", "delivery_id", "kind", unique=True),
        CheckConstraint("odometer_km >= 0 AND odometer_km < 2000000", name="odometer_range"),
        CheckConstraint(
            "kind = 'HANDOVER' OR renter_acknowledged_at IS NULL", name="only_handover_acknowledged"
        ),
    )

    delivery_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deliveries.id", ondelete="RESTRICT"))
    kind: Mapped[HandoverKind] = mapped_column(str_enum(HandoverKind, "handover_kind"))
    recorded_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    recorded_at: Mapped[datetime]
    odometer_km: Mapped[int] = mapped_column(Integer)
    fuel_level: Mapped[FuelLevel] = mapped_column(str_enum(FuelLevel, "fuel_level"))
    condition_notes: Mapped[str | None] = mapped_column(String(2000))
    renter_acknowledged_at: Mapped[datetime | None]
    renter_notes: Mapped[str | None] = mapped_column(String(1000))

    delivery: Mapped[Delivery] = relationship(back_populates="records")
    photos: Mapped[list["HandoverPhoto"]] = relationship(
        back_populates="record", order_by="HandoverPhoto.created_at"
    )


class HandoverPhoto(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "handover_photos"
    __table_args__ = (CheckConstraint("size_bytes > 0", name="size_positive"),)

    record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("handover_records.id", ondelete="RESTRICT"), index=True
    )
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    content_type: Mapped[str] = mapped_column(String(50))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))

    record: Mapped[HandoverRecord] = relationship(back_populates="photos")


class DeliveryException(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A problem reported by the delivery person. All but DELAY stop the delivery."""

    __tablename__ = "delivery_exceptions"
    __table_args__ = (
        CheckConstraint(
            "(resolved_at IS NULL) = (resolution IS NULL)", name="resolution_consistent"
        ),
    )

    delivery_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deliveries.id", ondelete="RESTRICT"), index=True
    )
    kind: Mapped[DeliveryExceptionKind] = mapped_column(
        str_enum(DeliveryExceptionKind, "delivery_exception_kind")
    )
    notes: Mapped[str] = mapped_column(String(1000))
    reported_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    resolved_at: Mapped[datetime | None]
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    resolution: Mapped[str | None] = mapped_column(String(1000))

    delivery: Mapped[Delivery] = relationship(back_populates="exceptions")
