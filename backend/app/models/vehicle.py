import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    CURRENCY_ZAR,
    Base,
    CreatedAtMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    str_enum,
)
from app.models.enums import FuelType, Transmission, VehicleDocumentType, VehicleStatus
from app.models.user import OwnerProfile


class Vehicle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        CheckConstraint("year BETWEEN 1981 AND 2100", name="year_range"),
        CheckConstraint("seats BETWEEN 1 AND 60", name="seats_range"),
        CheckConstraint(
            "registration_number = upper(btrim(registration_number))"
            " AND char_length(registration_number) BETWEEN 2 AND 20",
            name="registration_number_normalised",
        ),
        # 17-character VIN (ISO 3779); letters I, O and Q are never used.
        CheckConstraint("vin ~ '^[A-HJ-NPR-Z0-9]{17}$'", name="vin_format"),
        CheckConstraint(
            "status <> 'APPROVED' OR approved_at IS NOT NULL", name="approved_has_timestamp"
        ),
        Index("ix_vehicles_status_city", "status", "city"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("owner_profiles.id", ondelete="RESTRICT"), index=True
    )
    make: Mapped[str] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(80))
    year: Mapped[int] = mapped_column(SmallInteger)
    registration_number: Mapped[str] = mapped_column(String(20), unique=True)
    vin: Mapped[str] = mapped_column(String(17), unique=True)
    colour: Mapped[str | None] = mapped_column(String(40))
    transmission: Mapped[Transmission] = mapped_column(str_enum(Transmission, "transmission"))
    fuel_type: Mapped[FuelType] = mapped_column(str_enum(FuelType, "fuel_type"))
    seats: Mapped[int] = mapped_column(SmallInteger)
    city: Mapped[str] = mapped_column(String(100))
    province: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[VehicleStatus] = mapped_column(
        str_enum(VehicleStatus, "vehicle_status"),
        default=VehicleStatus.DRAFT,
        server_default="DRAFT",
    )
    submitted_at: Mapped[datetime | None]
    approved_at: Mapped[datetime | None]
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(500))

    owner: Mapped[OwnerProfile] = relationship()
    images: Mapped[list["VehicleImage"]] = relationship(
        back_populates="vehicle", order_by="VehicleImage.sort_order", cascade="all, delete-orphan"
    )
    prices: Mapped[list["VehiclePrice"]] = relationship(
        back_populates="vehicle", order_by="VehiclePrice.effective_from.desc()"
    )
    documents: Mapped[list["VehicleDocument"]] = relationship(
        back_populates="vehicle",
        order_by="VehicleDocument.created_at.desc()",
        cascade="all, delete-orphan",
    )
    availability_blocks: Mapped[list["VehicleAvailabilityBlock"]] = relationship(
        back_populates="vehicle",
        order_by="VehicleAvailabilityBlock.start_at",
        cascade="all, delete-orphan",
    )


class VehicleImage(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Photo metadata. Files live in private object storage, referenced by storage_key."""

    __tablename__ = "vehicle_images"
    __table_args__ = (
        Index("uq_vehicle_images_vehicle_sort", "vehicle_id", "sort_order", unique=True),
        CheckConstraint("sort_order >= 0", name="sort_order_non_negative"),
        CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png', 'image/webp')", name="content_type_allowed"
        ),
        CheckConstraint("size_bytes > 0", name="size_positive"),
    )

    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    content_type: Mapped[str] = mapped_column(String(50))
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))

    vehicle: Mapped[Vehicle] = relationship(back_populates="images")


class VehicleDocument(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A private vehicle document (registration, licence disc, insurance, roadworthy).

    Documents are append-only: a renewal is a new row, and the newest row of each type is
    the current one. Files live in private storage under storage_key.
    """

    __tablename__ = "vehicle_documents"
    __table_args__ = (
        Index("ix_vehicle_documents_vehicle_type", "vehicle_id", "document_type", "created_at"),
        CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png', 'application/pdf')",
            name="content_type_allowed",
        ),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        CheckConstraint(
            "document_type NOT IN ('LICENCE_DISC', 'INSURANCE') OR expiry_date IS NOT NULL",
            name="expiring_documents_have_expiry",
        ),
    )

    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"))
    document_type: Mapped[VehicleDocumentType] = mapped_column(
        str_enum(VehicleDocumentType, "vehicle_document_type")
    )
    expiry_date: Mapped[date | None]
    storage_key: Mapped[str] = mapped_column(String(200), unique=True)
    content_type: Mapped[str] = mapped_column(String(50))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))

    vehicle: Mapped[Vehicle] = relationship(back_populates="documents")


class VehicleAvailabilityBlock(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A period the owner has blocked (vehicle not available to rent)."""

    __tablename__ = "vehicle_availability_blocks"
    __table_args__ = (
        CheckConstraint("end_at > start_at", name="period_valid"),
        Index("ix_vehicle_availability_blocks_vehicle_start", "vehicle_id", "start_at"),
    )

    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"))
    start_at: Mapped[datetime]
    end_at: Mapped[datetime]
    reason: Mapped[str | None] = mapped_column(String(200))
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))

    vehicle: Mapped[Vehicle] = relationship(back_populates="availability_blocks")


class VehiclePrice(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Append-only official price history. The current price is the latest effective row."""

    __tablename__ = "vehicle_prices"
    __table_args__ = (
        CheckConstraint("daily_rate > 0", name="daily_rate_positive"),
        CheckConstraint("delivery_fee >= 0", name="delivery_fee_non_negative"),
        CheckConstraint("deposit_amount >= 0", name="deposit_non_negative"),
        CheckConstraint(f"currency = '{CURRENCY_ZAR}'", name="currency_zar"),
        Index("ix_vehicle_prices_vehicle_effective", "vehicle_id", "effective_from"),
    )

    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id", ondelete="RESTRICT"))
    daily_rate: Mapped[Decimal]
    delivery_fee: Mapped[Decimal] = mapped_column(default=Decimal("0.00"), server_default="0")
    deposit_amount: Mapped[Decimal] = mapped_column(default=Decimal("0.00"), server_default="0")
    currency: Mapped[str] = mapped_column(
        String(3), default=CURRENCY_ZAR, server_default=CURRENCY_ZAR
    )
    effective_from: Mapped[datetime] = mapped_column(server_default=func.now())
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    change_reason: Mapped[str | None] = mapped_column(String(500))

    vehicle: Mapped[Vehicle] = relationship(back_populates="prices")
