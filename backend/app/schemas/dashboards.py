import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import BookingStatus, DeliveryStatus, VehicleDocumentType, VehicleStatus
from app.schemas.payments import PaymentResponse


class OwnerBookingVehicle(BaseModel):
    id: uuid.UUID
    make: str
    model: str
    year: int
    registration_number: str


class OwnerBookingResponse(BaseModel):
    """A booking of the owner's car. The renter's contact details are only given to the
    delivery person, on the delivery (BR-7.14)."""

    id: uuid.UUID
    reference: str
    status: BookingStatus
    vehicle: OwnerBookingVehicle
    start_at: datetime
    end_at: datetime
    rental_days: int
    total_amount: Decimal
    currency: str
    renter_first_name: str
    delivery_id: uuid.UUID | None
    delivery_status: DeliveryStatus | None
    cancelled_at: datetime | None

    @classmethod
    def from_model(cls, booking, delivery: tuple[uuid.UUID, DeliveryStatus] | None):
        vehicle = booking.vehicle
        return cls(
            id=booking.id,
            reference=booking.reference,
            status=booking.status,
            vehicle=OwnerBookingVehicle(
                id=vehicle.id,
                make=vehicle.make,
                model=vehicle.model,
                year=vehicle.year,
                registration_number=vehicle.registration_number,
            ),
            start_at=booking.start_at,
            end_at=booking.end_at,
            rental_days=booking.rental_days,
            total_amount=booking.total_amount,
            currency=booking.currency,
            renter_first_name=booking.renter.full_name.split()[0],
            delivery_id=delivery[0] if delivery else None,
            delivery_status=delivery[1] if delivery else None,
            cancelled_at=booking.cancelled_at,
        )


class EarningLineResponse(BaseModel):
    booking_id: uuid.UUID
    reference: str
    status: BookingStatus
    vehicle: str = Field(description="Make and model")
    start_at: datetime
    end_at: datetime
    collected: Decimal
    refunded: Decimal = Field(description="Refunds issued or in progress")
    net: Decimal


class MonthTotalResponse(BaseModel):
    month: str = Field(description="YYYY-MM, by rental start (South African time)")
    bookings: int
    collected: Decimal
    refunded: Decimal
    net: Decimal


class EarningsResponse(BaseModel):
    year: int
    currency: str = "ZAR"
    basis: str = Field(
        default=(
            "Gross: money collected for your cars minus refunds, before any platform "
            "commission. Payouts are arranged separately."
        )
    )
    collected: Decimal
    refunded: Decimal
    net: Decimal
    months: list[MonthTotalResponse]
    bookings: list[EarningLineResponse]

    @classmethod
    def from_result(cls, earnings) -> "EarningsResponse":
        return cls(
            year=earnings.year,
            collected=earnings.collected,
            refunded=earnings.refunded,
            net=earnings.net,
            months=[
                MonthTotalResponse(
                    month=m.month,
                    bookings=m.bookings,
                    collected=m.collected,
                    refunded=m.refunded,
                    net=m.net,
                )
                for m in earnings.months
            ],
            bookings=[
                EarningLineResponse(
                    booking_id=line.booking.id,
                    reference=line.booking.reference,
                    status=line.booking.status,
                    vehicle=f"{line.booking.vehicle.make} {line.booking.vehicle.model}",
                    start_at=line.booking.start_at,
                    end_at=line.booking.end_at,
                    collected=line.collected,
                    refunded=line.refunded,
                    net=line.net,
                )
                for line in earnings.lines
            ],
        )


class ExpiringDocumentResponse(BaseModel):
    vehicle_id: uuid.UUID
    vehicle: str
    document_type: VehicleDocumentType
    expiry_date: date
    expired: bool


class OwnerDashboardResponse(BaseModel):
    vehicles_by_status: dict[VehicleStatus, int]
    upcoming_bookings: int
    active_rentals: int
    deliveries_to_do: int
    returns_to_record: int
    month_net: Decimal = Field(description="Gross this calendar month (see /earnings)")
    year_net: Decimal
    currency: str = "ZAR"
    expiring_documents: list[ExpiringDocumentResponse]
    next_booking: OwnerBookingResponse | None


class RenterPaymentResponse(PaymentResponse):
    booking_reference: str
    vehicle: str = Field(description="Make and model")
