import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AdminUser, DbSession, PaymentProviderDep, TrackingHubDep
from app.models.enums import BookingStatus
from app.schemas.bookings import AdminBookingResponse, AdminCancelBooking, BookingRenter
from app.services import bookings, payments, tracking

router = APIRouter(prefix="/admin/bookings", tags=["admin: bookings"])


def _admin_view(booking) -> AdminBookingResponse:
    return AdminBookingResponse.from_model(
        booking,
        renter=BookingRenter(
            id=booking.renter.id, full_name=booking.renter.full_name, email=booking.renter.email
        ),
        owner_user_id=booking.vehicle.owner.user_id,
        cancelled_by_id=booking.cancelled_by_id,
    )


@router.get("", response_model=list[AdminBookingResponse])
def list_bookings(
    _: AdminUser,
    session: DbSession,
    status_filter: Annotated[BookingStatus | None, Query(alias="status")] = None,
    vehicle_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AdminBookingResponse]:
    rows = bookings.list_bookings(
        session, status=status_filter, vehicle_id=vehicle_id, limit=limit, offset=offset
    )
    return [_admin_view(b) for b in rows]


@router.get("/{booking_id}", response_model=AdminBookingResponse)
def read_booking(booking_id: uuid.UUID, _: AdminUser, session: DbSession) -> AdminBookingResponse:
    return _admin_view(bookings.get_booking(session, booking_id))


@router.post("/{booking_id}/cancel", response_model=AdminBookingResponse)
def cancel_booking(
    booking_id: uuid.UUID,
    body: AdminCancelBooking,
    admin: AdminUser,
    session: DbSession,
    provider: PaymentProviderDep,
    hub: TrackingHubDep,
) -> AdminBookingResponse:
    """Cancel with a reason. A paid booking is refunded in full (default policy)."""
    booking = bookings.cancel_as_admin(session, admin, booking_id, body.reason)
    payments.refund_cancelled_booking(session, provider, booking, actor=admin, reason=body.reason)
    tracking.publish_for_booking(hub, session, booking.id)
    return _admin_view(bookings.get_booking(session, booking.id))
