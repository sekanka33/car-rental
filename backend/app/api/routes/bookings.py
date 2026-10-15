import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import (
    AppSettings,
    DbSession,
    DocumentStorageDep,
    PaymentProviderDep,
    RenterUser,
    TrackingHubDep,
)
from app.api.routes.customers import PRIVATE_FILE_HEADERS
from app.models.enums import BookingStatus
from app.schemas.bookings import BookingCreate, BookingResponse, CancelBooking
from app.schemas.deliveries import AcknowledgeHandover, DeliveryResponse
from app.services import bookings, deliveries, payments, tracking

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=BookingResponse)
def create_booking(
    body: BookingCreate, user: RenterUser, session: DbSession, settings: AppSettings
) -> BookingResponse:
    """Reserve a vehicle. The backend checks eligibility and availability and calculates the
    price. The booking is PENDING_PAYMENT and holds the dates until `hold_expires_at`."""
    booking = bookings.create_booking(
        session,
        settings,
        user,
        vehicle_id=body.vehicle_id,
        start_at=body.start_at,
        end_at=body.end_at,
        delivery_address=body.delivery_address,
    )
    return BookingResponse.from_model(booking)


@router.get("", response_model=list[BookingResponse])
def list_my_bookings(
    user: RenterUser,
    session: DbSession,
    status_filter: Annotated[BookingStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[BookingResponse]:
    """Booking history, newest first."""
    rows = bookings.list_own_bookings(
        session, user, status=status_filter, limit=limit, offset=offset
    )
    return [BookingResponse.from_model(b) for b in rows]


@router.get("/{booking_id}", response_model=BookingResponse)
def read_my_booking(booking_id: uuid.UUID, user: RenterUser, session: DbSession) -> BookingResponse:
    return BookingResponse.from_model(bookings.get_own_booking(session, user, booking_id))


@router.post("/{booking_id}/cancel", response_model=BookingResponse)
def cancel_my_booking(
    booking_id: uuid.UUID,
    body: CancelBooking,
    user: RenterUser,
    session: DbSession,
    provider: PaymentProviderDep,
    hub: TrackingHubDep,
) -> BookingResponse:
    """Cancel an unpaid hold, or a confirmed booking before it starts. A paid booking is
    refunded in full (default policy until OPEN-2 is decided)."""
    booking = bookings.cancel_as_renter(session, user, booking_id, body.reason)
    payments.refund_cancelled_booking(
        session, provider, booking, actor=user, reason=booking.cancellation_reason or "Cancelled"
    )
    tracking.publish_for_booking(hub, session, booking.id)
    return BookingResponse.from_model(bookings.get_booking(session, booking.id))


@router.get("/{booking_id}/delivery", response_model=DeliveryResponse)
def read_my_delivery(
    booking_id: uuid.UUID, user: RenterUser, session: DbSession
) -> DeliveryResponse:
    """Delivery status, time, handover and return records (exists once the booking is paid)."""
    return DeliveryResponse.for_renter(deliveries.get_booking_delivery(session, user, booking_id))


@router.post("/{booking_id}/delivery/acknowledge", response_model=DeliveryResponse)
def acknowledge_handover(
    booking_id: uuid.UUID, body: AcknowledgeHandover, user: RenterUser, session: DbSession
) -> DeliveryResponse:
    """Confirm you have the car, optionally noting anything you disagree with.
    This starts the rental."""
    return DeliveryResponse.for_renter(
        deliveries.acknowledge_handover(session, user, booking_id, body.notes)
    )


@router.post("/{booking_id}/return-request", response_model=DeliveryResponse)
def request_return(booking_id: uuid.UUID, user: RenterUser, session: DbSession) -> DeliveryResponse:
    """Tell the owner you are ready to hand the car back."""
    return DeliveryResponse.for_renter(deliveries.request_return(session, user, booking_id))


@router.get("/{booking_id}/delivery/photos/{photo_id}", response_class=Response)
def read_delivery_photo(
    booking_id: uuid.UUID,
    photo_id: uuid.UUID,
    user: RenterUser,
    session: DbSession,
    storage: DocumentStorageDep,
) -> Response:
    delivery = deliveries.get_booking_delivery(session, user, booking_id)
    content_type, data = deliveries.read_photo(session, storage, delivery, photo_id)
    return Response(content=data, media_type=content_type, headers=PRIVATE_FILE_HEADERS)
