"""Delivery views differ by role: the renter sees the delivery person's first name only; the
delivery person sees what they need to deliver (renter name and phone, address, vehicle);
administrators see everything, including exception resolutions."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.models.enums import (
    BookingStatus,
    DeliveryExceptionKind,
    DeliveryStatus,
    FuelLevel,
    HandoverKind,
)
from app.schemas.auth import RequestModel

Notes = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)]


class ScheduleDelivery(RequestModel):
    scheduled_for: datetime | None = Field(
        default=None, description="Omit to deliver at the rental start"
    )

    @field_validator("scheduled_for")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("must include a timezone")
        return value


class LocationUpdate(RequestModel):
    latitude: Decimal = Field(ge=-90, le=90, max_digits=9, decimal_places=6)
    longitude: Decimal = Field(ge=-180, le=180, max_digits=9, decimal_places=6)
    accuracy_m: Decimal | None = Field(default=None, ge=0, le=100_000, decimal_places=1)
    heading: Decimal | None = Field(default=None, ge=0, lt=360, decimal_places=1)
    speed_mps: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=1)
    recorded_at: datetime = Field(description="When the phone took the fix (with timezone)")

    @field_validator("latitude", "longitude", mode="before")
    @classmethod
    def round_coordinates(cls, value: object) -> object:
        """Phones report more decimals than we store (6 ≈ 11 cm)."""
        return round(Decimal(str(value)), 6) if isinstance(value, int | float | str) else value

    @field_validator("accuracy_m", "heading", "speed_mps", mode="before")
    @classmethod
    def round_one_decimal(cls, value: object) -> object:
        return round(Decimal(str(value)), 1) if isinstance(value, int | float | str) else value

    @field_validator("recorded_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("must include a timezone")
        return value


class HandoverCreate(RequestModel):
    odometer_km: int = Field(ge=0, lt=2_000_000)
    fuel_level: FuelLevel
    condition_notes: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None
    ) = None


class ExceptionCreate(RequestModel):
    kind: DeliveryExceptionKind
    notes: Notes


class AcknowledgeHandover(RequestModel):
    notes: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
        | None
    ) = Field(default=None, description="Anything you disagree with in the handover record")


class AdminReschedule(RequestModel):
    scheduled_for: datetime
    note: Notes

    @field_validator("scheduled_for")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("must include a timezone")
        return value


class AdminReassign(RequestModel):
    user_id: uuid.UUID


class ResolveException(RequestModel):
    note: Notes


class HandoverPhotoResponse(BaseModel):
    id: uuid.UUID
    url: str
    content_type: str
    created_at: datetime


class HandoverRecordResponse(BaseModel):
    kind: HandoverKind
    recorded_at: datetime
    odometer_km: int
    fuel_level: FuelLevel
    condition_notes: str | None
    renter_acknowledged_at: datetime | None
    renter_notes: str | None
    photos: list[HandoverPhotoResponse]


class ExceptionResponse(BaseModel):
    id: uuid.UUID
    kind: DeliveryExceptionKind
    notes: str
    created_at: datetime
    resolved_at: datetime | None
    resolution: str | None


class DeliveryVehicle(BaseModel):
    make: str
    model: str
    year: int


class DeliveryResponse(BaseModel):
    """What the renter sees."""

    id: uuid.UUID
    booking_id: uuid.UUID
    booking_reference: str
    booking_status: BookingStatus
    status: DeliveryStatus
    scheduled_for: datetime | None
    dropoff_address: str
    started_at: datetime | None
    delivered_at: datetime | None
    delivery_person_first_name: str | None
    handover: HandoverRecordResponse | None
    return_record: HandoverRecordResponse | None
    exceptions: list[ExceptionResponse]

    @staticmethod
    def _fields(delivery, photo_url) -> dict:
        def record(kind: HandoverKind) -> HandoverRecordResponse | None:
            found = delivery.record(kind)
            if found is None:
                return None
            return HandoverRecordResponse(
                kind=found.kind,
                recorded_at=found.recorded_at,
                odometer_km=found.odometer_km,
                fuel_level=found.fuel_level,
                condition_notes=found.condition_notes,
                renter_acknowledged_at=found.renter_acknowledged_at,
                renter_notes=found.renter_notes,
                photos=[
                    HandoverPhotoResponse(
                        id=p.id,
                        url=photo_url(p.id),
                        content_type=p.content_type,
                        created_at=p.created_at,
                    )
                    for p in found.photos
                ],
            )

        booking = delivery.booking
        assignee = delivery.assigned_to
        return {
            "id": delivery.id,
            "booking_id": booking.id,
            "booking_reference": booking.reference,
            "booking_status": booking.status,
            "status": delivery.status,
            "scheduled_for": delivery.scheduled_for,
            "dropoff_address": delivery.dropoff_address,
            "started_at": delivery.started_at,
            "delivered_at": delivery.delivered_at,
            "delivery_person_first_name": assignee.full_name.split()[0] if assignee else None,
            "handover": record(HandoverKind.HANDOVER),
            "return_record": record(HandoverKind.RETURN),
            "exceptions": [
                ExceptionResponse(
                    id=e.id,
                    kind=e.kind,
                    notes=e.notes,
                    created_at=e.created_at,
                    resolved_at=e.resolved_at,
                    resolution=e.resolution,
                )
                for e in delivery.exceptions
            ],
        }

    @classmethod
    def for_renter(cls, delivery) -> "DeliveryResponse":
        prefix = f"/api/v1/bookings/{delivery.booking_id}/delivery/photos"
        return cls(**cls._fields(delivery, lambda pid: f"{prefix}/{pid}"))


class DeliveryRenter(BaseModel):
    full_name: str
    phone_number: str | None


class AssignedDeliveryResponse(DeliveryResponse):
    """What the delivery person sees."""

    vehicle: DeliveryVehicle
    registration_number: str
    rental_start_at: datetime
    rental_end_at: datetime
    renter: DeliveryRenter

    @classmethod
    def for_assignee(cls, delivery) -> "AssignedDeliveryResponse":
        prefix = f"/api/v1/owners/me/deliveries/{delivery.id}/photos"
        booking = delivery.booking
        vehicle = booking.vehicle
        return cls(
            **cls._fields(delivery, lambda pid: f"{prefix}/{pid}"),
            vehicle=DeliveryVehicle(make=vehicle.make, model=vehicle.model, year=vehicle.year),
            registration_number=vehicle.registration_number,
            rental_start_at=booking.start_at,
            rental_end_at=booking.end_at,
            renter=DeliveryRenter(
                full_name=booking.renter.full_name, phone_number=booking.renter.phone_number
            ),
        )


class AdminDeliveryResponse(AssignedDeliveryResponse):
    assigned_to_id: uuid.UUID | None
    renter_id: uuid.UUID
    has_open_exception: bool

    @classmethod
    def for_admin(cls, delivery) -> "AdminDeliveryResponse":
        base = AssignedDeliveryResponse.for_assignee(delivery).model_dump()
        prefix = f"/api/v1/admin/deliveries/{delivery.id}/photos"
        for key in ("handover", "return_record"):
            if base[key]:
                for photo in base[key]["photos"]:
                    photo["url"] = f"{prefix}/{photo['id']}"
        return cls(
            **base,
            assigned_to_id=delivery.assigned_to_id,
            renter_id=delivery.booking.renter_id,
            has_open_exception=any(e.resolved_at is None for e in delivery.exceptions),
        )
