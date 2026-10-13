import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import AppSettings, DbSession, RenterUser
from app.models.enums import BookingStatus
from app.schemas.bookings import BookingCreate, BookingResponse, CancelBooking
from app.services import bookings

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
    booking_id: uuid.UUID, body: CancelBooking, user: RenterUser, session: DbSession
) -> BookingResponse:
    """Cancel an unpaid hold, or a confirmed booking before it starts."""
    return BookingResponse.from_model(
        bookings.cancel_as_renter(session, user, booking_id, body.reason)
    )
