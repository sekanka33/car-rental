"""Bookings: creation with backend eligibility, availability and pricing; holds and expiry;
cancellation; and the booking status state machine (BR-5).

Default cancellation policy while OPEN-2 is undecided: a renter may cancel a pending hold
at any time, and a confirmed or delivery-scheduled booking before it starts; afterwards only
administrators can. A cancelled paid booking is refunded in full (Stage 11). Confirming a
booking creates its delivery, assigned to the vehicle owner (OPEN-3 default, Stage 12).
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.errors import AppError, NotFoundError, PermissionDeniedError
from app.models import (
    Booking,
    Delivery,
    DeliveryException,
    OwnerProfile,
    Payment,
    User,
    Vehicle,
    VehicleAvailabilityBlock,
)
from app.models.enums import BookingStatus, DeliveryStatus
from app.services import marketplace, notify_events
from app.services.audit import record_audit
from app.services.eligibility import evaluate_renter_eligibility
from app.services.pricing import calculate_quote
from app.services.vehicles import get_vehicle

S = BookingStatus
# BR-5.5: every allowed move. Anything else is rejected.
ALLOWED_TRANSITIONS: dict[BookingStatus, frozenset[BookingStatus]] = {
    S.PENDING_PAYMENT: frozenset({S.CONFIRMED, S.EXPIRED, S.CANCELLED}),
    S.CONFIRMED: frozenset({S.DELIVERY_SCHEDULED, S.CANCELLED}),
    S.DELIVERY_SCHEDULED: frozenset({S.IN_TRANSIT, S.CANCELLED}),
    # Back to DELIVERY_SCHEDULED when a failed delivery is re-attempted (Stage 12).
    S.IN_TRANSIT: frozenset({S.DELIVERED, S.DELIVERY_SCHEDULED, S.CANCELLED}),
    S.DELIVERED: frozenset({S.ACTIVE_RENTAL}),
    S.ACTIVE_RENTAL: frozenset({S.RETURN_PENDING}),
    S.RETURN_PENDING: frozenset({S.COMPLETED}),
    S.CANCELLED: frozenset(),
    S.EXPIRED: frozenset(),
    S.COMPLETED: frozenset(),
}
RENTER_CANCELLABLE = frozenset({S.PENDING_PAYMENT, S.CONFIRMED, S.DELIVERY_SCHEDULED})
ADMIN_CANCELLABLE = frozenset({S.PENDING_PAYMENT, S.CONFIRMED, S.DELIVERY_SCHEDULED, S.IN_TRANSIT})
_REFERENCE_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"  # no 0/O, 1/I/L, U


class InvalidTransitionError(AppError):
    status_code = 409
    code = "invalid_booking_transition"


class RenterNotEligibleError(AppError):
    status_code = 403
    code = "renter_not_eligible"


class VehicleUnavailableError(AppError):
    status_code = 409
    code = "vehicle_unavailable"


class BookingLimitError(AppError):
    status_code = 409
    code = "too_many_pending_bookings"


class HoldExpiredError(AppError):
    status_code = 409
    code = "booking_hold_expired"


class InvalidBookingPeriodError(AppError):
    status_code = 422
    code = "invalid_booking_period"


def _now() -> datetime:
    return datetime.now(UTC)


def transition(booking: Booking, target: BookingStatus) -> None:
    if target not in ALLOWED_TRANSITIONS[booking.status]:
        raise InvalidTransitionError(f"A {booking.status} booking cannot become {target}.")
    booking.status = target


def _new_reference() -> str:
    return "BK" + "".join(secrets.choice(_REFERENCE_ALPHABET) for _ in range(8))


# --- expiry ------------------------------------------------------------------------------------


def expire_stale_holds(
    session: Session, *, vehicle_id: uuid.UUID | None = None, now: datetime | None = None
) -> int:
    """Mark unpaid holds past their deadline EXPIRED (releases their dates). Returns the count.

    Called before availability checks and by `python -m app.cli expire-holds` (cron).
    The caller commits.
    """
    now = now or _now()
    statement = (
        update(Booking)
        .where(Booking.status == S.PENDING_PAYMENT, Booking.hold_expires_at <= now)
        .values(status=S.EXPIRED)
        .execution_options(synchronize_session="fetch")
    )
    if vehicle_id is not None:
        statement = statement.where(Booking.vehicle_id == vehicle_id)
    expired = session.scalars(statement.returning(Booking.id)).all()
    for booking_id in expired:
        notify_events.booking_expired(session, booking_id)
    return len(expired)


# --- creation ----------------------------------------------------------------------------------


def _validate_period(settings: Settings, start: datetime, end: datetime, now: datetime) -> None:
    if start.tzinfo is None or end.tzinfo is None:
        raise InvalidBookingPeriodError("Rental times must include a timezone.")
    if end <= start:
        raise InvalidBookingPeriodError("The rental must end after it starts.")
    if start < now + timedelta(minutes=settings.booking_min_lead_minutes):
        hours = settings.booking_min_lead_minutes / 60
        raise InvalidBookingPeriodError(f"Bookings must start at least {hours:g} hours from now.")
    if end - start > timedelta(days=settings.booking_max_days):
        raise InvalidBookingPeriodError(
            f"A rental can last at most {settings.booking_max_days} days."
        )


def create_booking(
    session: Session,
    settings: Settings,
    renter: User,
    *,
    vehicle_id: uuid.UUID,
    start_at: datetime,
    end_at: datetime,
    delivery_address: str,
) -> Booking:
    """Reserve a vehicle (PENDING_PAYMENT) at the backend-calculated official price."""
    now = _now()
    _validate_period(settings, start_at, end_at, now)

    eligibility = evaluate_renter_eligibility(
        session, settings, renter, rental_start=start_at, rental_end=end_at
    )
    if not eligibility.eligible:
        raise RenterNotEligibleError(
            "You cannot book yet. Some requirements are still outstanding.",
            details=[{"reason": reason} for reason in eligibility.reasons],
        )

    # Lock the vehicle row: serialises bookings with owner date blocks for this vehicle.
    get_vehicle(session, vehicle_id, for_update=True)
    vehicle, price = marketplace.get_listed(session, vehicle_id)  # 404 unless listed and priced
    if vehicle.owner.user_id == renter.id:
        raise PermissionDeniedError("You cannot book your own vehicle.")

    expire_stale_holds(session, vehicle_id=vehicle.id, now=now)
    pending = session.scalar(
        select(func.count())
        .select_from(Booking)
        .where(
            Booking.renter_id == renter.id,
            Booking.status == S.PENDING_PAYMENT,
            Booking.hold_expires_at > now,
        )
    )
    if pending >= settings.max_pending_bookings_per_renter:
        raise BookingLimitError("Finish or cancel your unpaid bookings before making another.")
    blocked = session.scalar(
        select(
            exists().where(
                VehicleAvailabilityBlock.vehicle_id == vehicle.id,
                VehicleAvailabilityBlock.start_at < end_at,
                VehicleAvailabilityBlock.end_at > start_at,
            )
        )
    )
    if blocked:
        raise VehicleUnavailableError("The vehicle is not available for these dates.")

    quote = calculate_quote(price, start_at, end_at)
    booking = Booking(
        reference=_new_reference(),
        renter_id=renter.id,
        vehicle_id=vehicle.id,
        vehicle_price_id=quote.vehicle_price_id,
        start_at=start_at,
        end_at=end_at,
        status=S.PENDING_PAYMENT,
        hold_expires_at=now + timedelta(minutes=settings.booking_hold_minutes),
        daily_rate=quote.daily_rate,
        rental_days=quote.rental_days,
        rental_amount=quote.rental_amount,
        delivery_fee=quote.delivery_fee,
        deposit_amount=quote.deposit_amount,
        total_amount=quote.total_amount,
        currency=quote.currency,
        delivery_address=delivery_address,
    )
    session.add(booking)
    try:
        session.flush()  # the exclusion constraint rejects overlaps here, even under concurrency
    except IntegrityError as exc:
        session.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", "") or ""
        if constraint == "ex_bookings_vehicle_period_overlap":
            raise VehicleUnavailableError("The vehicle is not available for these dates.") from exc
        raise
    record_audit(
        session,
        actor_id=renter.id,
        action="booking.created",
        entity_type="booking",
        entity_id=booking.id,
        changes={"vehicle_id": str(vehicle.id), "total_amount": str(booking.total_amount)},
    )
    session.commit()
    return get_booking(session, booking.id)


# --- queries -------------------------------------------------------------------------------------


def _booking_query():
    return select(Booking).options(
        selectinload(Booking.vehicle).selectinload(Vehicle.images),
        selectinload(Booking.vehicle).selectinload(Vehicle.owner).selectinload(OwnerProfile.user),
        selectinload(Booking.renter),
    )


def get_booking(session: Session, booking_id: uuid.UUID) -> Booking:
    booking = session.scalar(_booking_query().where(Booking.id == booking_id))
    if booking is None:
        raise NotFoundError("Booking not found.")
    return booking


def _refresh_expiry(session: Session, booking: Booking) -> Booking:
    """Show an unpaid hold as EXPIRED as soon as its deadline passes."""
    if booking.status == S.PENDING_PAYMENT and booking.hold_expires_at <= _now():
        expire_stale_holds(session, vehicle_id=booking.vehicle_id)
        session.commit()
        session.refresh(booking)
    return booking


def get_own_booking(session: Session, renter: User, booking_id: uuid.UUID) -> Booking:
    booking = get_booking(session, booking_id)
    if booking.renter_id != renter.id:
        raise NotFoundError("Booking not found.")  # never reveal other renters' bookings
    return _refresh_expiry(session, booking)


def list_own_bookings(
    session: Session, renter: User, *, status: BookingStatus | None, limit: int, offset: int
) -> list[Booking]:
    if expire_stale_holds(session):
        session.commit()
    query = _booking_query().where(Booking.renter_id == renter.id)
    if status is not None:
        query = query.where(Booking.status == status)
    return list(
        session.scalars(query.order_by(Booking.created_at.desc()).limit(limit).offset(offset))
    )


def list_bookings(
    session: Session,
    *,
    status: BookingStatus | None,
    vehicle_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> list[Booking]:
    if expire_stale_holds(session):
        session.commit()
    query = _booking_query()
    if status is not None:
        query = query.where(Booking.status == status)
    if vehicle_id is not None:
        query = query.where(Booking.vehicle_id == vehicle_id)
    return list(
        session.scalars(query.order_by(Booking.start_at.desc()).limit(limit).offset(offset))
    )


# --- state changes --------------------------------------------------------------------------------


def _locked(session: Session, booking_id: uuid.UUID) -> Booking:
    booking = session.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
    if booking is None:
        raise NotFoundError("Booking not found.")
    return booking


def cancel_as_renter(
    session: Session, renter: User, booking_id: uuid.UUID, reason: str | None
) -> Booking:
    booking = _locked(session, booking_id)
    if booking.renter_id != renter.id:
        raise NotFoundError("Booking not found.")
    if booking.status == S.PENDING_PAYMENT and booking.hold_expires_at <= _now():
        transition(booking, S.EXPIRED)
        session.commit()
        raise InvalidTransitionError("This booking has already expired.")
    if booking.status not in RENTER_CANCELLABLE:
        raise InvalidTransitionError(
            f"A {booking.status} booking cannot be cancelled by the renter."
        )
    if booking.status != S.PENDING_PAYMENT and booking.start_at <= _now():
        raise InvalidTransitionError("The rental has started; contact support to cancel.")
    return _cancel(session, booking, actor=renter, reason=reason or "Cancelled by renter")


def cancel_as_admin(session: Session, admin: User, booking_id: uuid.UUID, reason: str) -> Booking:
    booking = _locked(session, booking_id)
    if booking.status not in ADMIN_CANCELLABLE:
        raise InvalidTransitionError(f"A {booking.status} booking cannot be cancelled.")
    return _cancel(session, booking, actor=admin, reason=reason)


def _cancel(session: Session, booking: Booking, *, actor: User, reason: str) -> Booking:
    previous = booking.status
    transition(booking, S.CANCELLED)
    booking.cancelled_at = _now()
    booking.cancelled_by_id = actor.id
    booking.cancellation_reason = reason
    _cancel_delivery(session, booking, actor=actor, reason=reason)
    record_audit(
        session,
        actor_id=actor.id,
        action="booking.cancelled",
        entity_type="booking",
        entity_id=booking.id,
        changes={"status": {"from": previous, "to": "CANCELLED"}, "reason": reason},
    )
    paid = session.scalar(
        select(Payment.id)
        .where(Payment.booking_id == booking.id, Payment.paid_at.is_not(None))
        .limit(1)
    )
    notify_events.booking_cancelled(
        session, booking, by_admin=actor.id != booking.renter_id, refunded=paid is not None
    )
    session.commit()
    return get_booking(session, booking.id)


def _cancel_delivery(session: Session, booking: Booking, *, actor: User, reason: str) -> None:
    delivery = session.scalar(
        select(Delivery).where(Delivery.booking_id == booking.id).with_for_update()
    )
    if delivery is None or delivery.status in (DeliveryStatus.DELIVERED, DeliveryStatus.CANCELLED):
        return
    now = _now()
    delivery.status = DeliveryStatus.CANCELLED
    delivery.cancelled_at = now
    for exception in session.scalars(
        select(DeliveryException).where(
            DeliveryException.delivery_id == delivery.id, DeliveryException.resolved_at.is_(None)
        )
    ):
        exception.resolved_at = now
        exception.resolved_by_id = actor.id
        exception.resolution = f"Booking cancelled: {reason}"[:1000]


def confirm_booking(
    session: Session, booking_id: uuid.UUID, *, now: datetime | None = None
) -> Booking:
    """PENDING_PAYMENT -> CONFIRMED. Called by the payment stage once payment is verified."""
    now = now or _now()
    booking = _locked(session, booking_id)
    if booking.status == S.PENDING_PAYMENT and booking.hold_expires_at <= now:
        raise HoldExpiredError("The booking hold expired before payment completed.")
    transition(booking, S.CONFIRMED)
    booking.confirmed_at = now
    # Every paid booking gets one delivery, assigned to the vehicle owner (OPEN-3 default).
    owner_user_id = session.scalar(
        select(OwnerProfile.user_id)
        .join(Vehicle, Vehicle.owner_id == OwnerProfile.id)
        .where(Vehicle.id == booking.vehicle_id)
    )
    session.add(
        Delivery(
            booking_id=booking.id,
            assigned_to_id=owner_user_id,
            status=DeliveryStatus.PENDING_SCHEDULE,
            dropoff_address=booking.delivery_address or "",
        )
    )
    record_audit(
        session,
        actor_id=None,
        action="booking.confirmed",
        entity_type="booking",
        entity_id=booking.id,
        changes={"status": {"from": "PENDING_PAYMENT", "to": "CONFIRMED"}},
    )
    notify_events.booking_confirmed(session, booking)
    session.commit()
    return get_booking(session, booking.id)
