"""Dashboard views for owners (bookings of their cars, earnings, summary) and renters
(payment history). Read-only."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession, OwnerUser, RenterUser
from app.schemas.dashboards import (
    EarningsResponse,
    ExpiringDocumentResponse,
    OwnerBookingResponse,
    OwnerDashboardResponse,
    RenterPaymentResponse,
)
from app.schemas.payments import PaymentResponse
from app.services import dashboards
from app.services.verification import today_in_south_africa

router = APIRouter(tags=["dashboards"])


@router.get("/owners/me/bookings", response_model=list[OwnerBookingResponse])
def list_bookings_of_my_cars(
    user: OwnerUser,
    session: DbSession,
    scope: dashboards.OwnerScope = "upcoming",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[OwnerBookingResponse]:
    """Paid-for bookings of your cars: `upcoming` (confirmed, not yet on the way), `active`
    (on the way or rented), `past` (completed or cancelled) or `all`."""
    rows = dashboards.list_owner_bookings(session, user, scope=scope, limit=limit, offset=offset)
    deliveries = dashboards.deliveries_by_booking(session, [b.id for b in rows])
    return [OwnerBookingResponse.from_model(b, deliveries.get(b.id)) for b in rows]


@router.get("/owners/me/earnings", response_model=EarningsResponse)
def read_my_earnings(
    user: OwnerUser,
    session: DbSession,
    year: Annotated[int | None, Query(ge=2020, le=2100)] = None,
) -> EarningsResponse:
    """Gross collected per booking and per month (OPEN-1: no commission is deducted yet)."""
    year = year or today_in_south_africa().year
    return EarningsResponse.from_result(dashboards.owner_earnings(session, user, year=year))


@router.get("/owners/me/dashboard", response_model=OwnerDashboardResponse)
def read_owner_dashboard(user: OwnerUser, session: DbSession) -> OwnerDashboardResponse:
    """Counts, what needs doing, this month's gross and documents expiring within 30 days."""
    summary = dashboards.owner_summary(session, user)
    today = today_in_south_africa()
    next_booking = summary.next_booking
    deliveries = dashboards.deliveries_by_booking(
        session, [next_booking.id] if next_booking else []
    )
    return OwnerDashboardResponse(
        vehicles_by_status=summary.vehicles_by_status,
        upcoming_bookings=summary.upcoming_bookings,
        active_rentals=summary.active_rentals,
        deliveries_to_do=summary.deliveries_to_do,
        returns_to_record=summary.returns_to_record,
        month_net=summary.month_net,
        year_net=summary.year_net,
        expiring_documents=[
            ExpiringDocumentResponse(
                vehicle_id=e.vehicle.id,
                vehicle=f"{e.vehicle.make} {e.vehicle.model} ({e.vehicle.registration_number})",
                document_type=e.document_type,
                expiry_date=e.expiry_date,
                expired=e.expiry_date <= today,
            )
            for e in summary.expiring_documents
        ],
        next_booking=OwnerBookingResponse.from_model(next_booking, deliveries.get(next_booking.id))
        if next_booking
        else None,
    )


@router.get("/customers/me/payments", response_model=list[RenterPaymentResponse])
def list_my_payments(
    user: RenterUser,
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RenterPaymentResponse]:
    """Every payment attempt across your bookings, newest first, with refunds."""
    return [
        RenterPaymentResponse(
            **PaymentResponse.from_model(p).model_dump(),
            booking_reference=p.booking.reference,
            vehicle=f"{p.booking.vehicle.make} {p.booking.vehicle.model}",
        )
        for p in dashboards.list_renter_payments(session, user, limit=limit, offset=offset)
    ]
