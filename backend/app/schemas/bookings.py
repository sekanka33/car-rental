import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, StringConstraints, field_validator

from app.models.enums import BookingStatus
from app.schemas.auth import RequestModel


class BookingCreate(RequestModel):
    """Only what the renter chooses. Prices and status are decided by the backend."""

    vehicle_id: uuid.UUID
    start_at: datetime
    end_at: datetime
    delivery_address: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=5, max_length=300)
    ]

    @field_validator("start_at", "end_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("must include a timezone")
        return value


class CancelBooking(RequestModel):
    reason: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
        | None
    ) = None


class AdminCancelBooking(RequestModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class BookingVehicle(BaseModel):
    id: uuid.UUID
    make: str
    model: str
    year: int
    city: str
    province: str
    primary_photo_url: str | None


class PriceBreakdown(BaseModel):
    daily_rate: Decimal
    rental_days: int
    rental_amount: Decimal
    delivery_fee: Decimal
    deposit_amount: Decimal
    total_amount: Decimal
    currency: str


class BookingResponse(BaseModel):
    id: uuid.UUID
    reference: str
    status: BookingStatus
    vehicle: BookingVehicle
    start_at: datetime
    end_at: datetime
    hold_expires_at: datetime | None
    price: PriceBreakdown
    delivery_address: str | None
    created_at: datetime
    confirmed_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None

    @classmethod
    def from_model(cls, booking, **extra) -> "BookingResponse":
        from app.api.routes.marketplace import _photo_url

        vehicle = booking.vehicle
        primary = vehicle.images[0] if vehicle.images else None
        return cls(
            id=booking.id,
            reference=booking.reference,
            status=booking.status,
            vehicle=BookingVehicle(
                id=vehicle.id,
                make=vehicle.make,
                model=vehicle.model,
                year=vehicle.year,
                city=vehicle.city,
                province=vehicle.province,
                primary_photo_url=_photo_url(vehicle.id, primary.id) if primary else None,
            ),
            start_at=booking.start_at,
            end_at=booking.end_at,
            hold_expires_at=booking.hold_expires_at
            if booking.status == BookingStatus.PENDING_PAYMENT
            else None,
            price=PriceBreakdown(
                daily_rate=booking.daily_rate,
                rental_days=booking.rental_days,
                rental_amount=booking.rental_amount,
                delivery_fee=booking.delivery_fee,
                deposit_amount=booking.deposit_amount,
                total_amount=booking.total_amount,
                currency=booking.currency,
            ),
            delivery_address=booking.delivery_address,
            created_at=booking.created_at,
            confirmed_at=booking.confirmed_at,
            cancelled_at=booking.cancelled_at,
            cancellation_reason=booking.cancellation_reason,
            **extra,
        )


class BookingRenter(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str


class AdminBookingResponse(BookingResponse):
    renter: BookingRenter
    owner_user_id: uuid.UUID
    cancelled_by_id: uuid.UUID | None
