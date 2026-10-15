"""Deliveries: scheduling, the delivery status machine, handover and return records,
exceptions, reassignment, and the booking status changes they drive (BR-7).

OPEN-3 default: the vehicle owner delivers. A delivery is created, assigned to the owner,
when payment confirms the booking (`bookings.confirm_booking`). Administrators can reassign
it to another active owner account and resolve exceptions.

Delivery                          Booking
PENDING_SCHEDULE ─schedule─►      CONFIRMED ─► DELIVERY_SCHEDULED
SCHEDULED ─start─► EN_ROUTE       DELIVERY_SCHEDULED ─► IN_TRANSIT
EN_ROUTE ─handover─► DELIVERED    IN_TRANSIT ─► DELIVERED ─(renter acknowledges)─► ACTIVE_RENTAL
(any active) ─exception─► FAILED  (unchanged until an administrator reschedules or cancels)
FAILED ─admin reschedule─► SCHEDULED   IN_TRANSIT ─► DELIVERY_SCHEDULED
return recorded                   ACTIVE_RENTAL ─► RETURN_PENDING ─► COMPLETED
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError, NotFoundError
from app.integrations.storage import DocumentStorage
from app.models import (
    Booking,
    Delivery,
    DeliveryException,
    HandoverPhoto,
    HandoverRecord,
    OwnerProfile,
    User,
    Vehicle,
)
from app.models.enums import (
    BookingStatus,
    DeliveryExceptionKind,
    DeliveryStatus,
    FuelLevel,
    HandoverKind,
    RoleName,
    UserStatus,
)
from app.services.audit import record_audit
from app.services.bookings import transition as booking_transition
from app.services.uploads import PHOTO_TYPES, check_upload

D = DeliveryStatus
B = BookingStatus
ALLOWED_TRANSITIONS: dict[DeliveryStatus, frozenset[DeliveryStatus]] = {
    D.PENDING_SCHEDULE: frozenset({D.SCHEDULED, D.FAILED, D.CANCELLED}),
    D.SCHEDULED: frozenset({D.EN_ROUTE, D.FAILED, D.CANCELLED}),
    D.EN_ROUTE: frozenset({D.DELIVERED, D.FAILED, D.CANCELLED}),
    D.FAILED: frozenset({D.SCHEDULED, D.CANCELLED}),
    D.DELIVERED: frozenset(),
    D.CANCELLED: frozenset(),
}
ACTIVE = frozenset({D.PENDING_SCHEDULE, D.SCHEDULED, D.EN_ROUTE})
# The delivery person may schedule up to this long before the rental starts (never after).
EARLIEST_BEFORE_START = timedelta(hours=24)
MAX_PHOTOS_PER_RECORD = 10
RETURN_PHOTO_WINDOW = timedelta(hours=2)


class InvalidDeliveryTransitionError(AppError):
    status_code = 409
    code = "invalid_delivery_transition"


class InvalidScheduleError(AppError):
    status_code = 422
    code = "invalid_delivery_schedule"


class InvalidHandoverError(AppError):
    status_code = 422
    code = "invalid_handover"


class InvalidAssigneeError(AppError):
    status_code = 422
    code = "invalid_delivery_assignee"


def _now() -> datetime:
    return datetime.now(UTC)


def transition(delivery: Delivery, target: DeliveryStatus) -> None:
    if target not in ALLOWED_TRANSITIONS[delivery.status]:
        raise InvalidDeliveryTransitionError(
            f"A {delivery.status} delivery cannot become {target}."
        )
    delivery.status = target


def _audit(session: Session, actor: User, action: str, delivery: Delivery, **changes) -> None:
    record_audit(
        session,
        actor_id=actor.id,
        action=f"delivery.{action}",
        entity_type="delivery",
        entity_id=delivery.id,
        changes={"booking_id": str(delivery.booking_id), **changes},
    )


# --- queries -------------------------------------------------------------------------------------


def _delivery_query():
    return select(Delivery).options(
        selectinload(Delivery.booking).selectinload(Booking.vehicle).selectinload(Vehicle.images),
        selectinload(Delivery.booking).selectinload(Booking.renter),
        selectinload(Delivery.assigned_to),
        selectinload(Delivery.records).selectinload(HandoverRecord.photos),
        selectinload(Delivery.exceptions),
    )


def get_delivery(session: Session, delivery_id: uuid.UUID) -> Delivery:
    delivery = session.scalar(
        _delivery_query()
        .where(Delivery.id == delivery_id)
        .execution_options(populate_existing=True)
    )
    if delivery is None:
        raise NotFoundError("Delivery not found.")
    return delivery


def get_assigned_delivery(session: Session, user: User, delivery_id: uuid.UUID) -> Delivery:
    delivery = get_delivery(session, delivery_id)
    if delivery.assigned_to_id != user.id:
        raise NotFoundError("Delivery not found.")  # never reveal other people's deliveries
    return delivery


def get_booking_delivery(session: Session, renter: User, booking_id: uuid.UUID) -> Delivery:
    delivery = session.scalar(
        _delivery_query()
        .join(Delivery.booking)
        .where(Delivery.booking_id == booking_id, Booking.renter_id == renter.id)
        .execution_options(populate_existing=True)
    )
    if delivery is None:
        raise NotFoundError("This booking has no delivery yet.")
    return delivery


def list_assigned(session: Session, user: User, *, active_only: bool) -> list[Delivery]:
    query = _delivery_query().where(Delivery.assigned_to_id == user.id)
    if active_only:
        # Still to deliver, or delivered and not yet returned.
        query = query.join(Delivery.booking).where(
            Booking.status.in_(
                (
                    B.CONFIRMED,
                    B.DELIVERY_SCHEDULED,
                    B.IN_TRANSIT,
                    B.DELIVERED,
                    B.ACTIVE_RENTAL,
                    B.RETURN_PENDING,
                )
            )
        )
    return list(session.scalars(query.order_by(Delivery.created_at)))


def list_deliveries(
    session: Session,
    *,
    status: DeliveryStatus | None,
    open_exceptions: bool,
    limit: int,
    offset: int,
    booking_id: uuid.UUID | None = None,
) -> list[Delivery]:
    query = _delivery_query()
    if booking_id is not None:
        query = query.where(Delivery.booking_id == booking_id)
    if status is not None:
        query = query.where(Delivery.status == status)
    if open_exceptions:
        # Needs an administrator: stopped (FAILED), or a reported problem is still open. The
        # admin overview counts the same set (app/services/reports.py).
        query = query.where(
            Delivery.status != DeliveryStatus.CANCELLED,
            or_(
                Delivery.status == DeliveryStatus.FAILED,
                exists().where(
                    DeliveryException.delivery_id == Delivery.id,
                    DeliveryException.resolved_at.is_(None),
                ),
            ),
        )
    return list(
        session.scalars(query.order_by(Delivery.created_at.desc()).limit(limit).offset(offset))
    )


# --- delivery person actions -----------------------------------------------------------------


def _locked(session: Session, delivery_id: uuid.UUID) -> Delivery:
    delivery = session.scalar(select(Delivery).where(Delivery.id == delivery_id).with_for_update())
    if delivery is None:
        raise NotFoundError("Delivery not found.")
    return delivery


def _locked_assigned(session: Session, user: User, delivery_id: uuid.UUID) -> Delivery:
    delivery = _locked(session, delivery_id)
    if delivery.assigned_to_id != user.id:
        raise NotFoundError("Delivery not found.")
    return delivery


def _locked_booking(session: Session, delivery: Delivery) -> Booking:
    return session.scalar(
        select(Booking).where(Booking.id == delivery.booking_id).with_for_update()
    )


def schedule(
    session: Session, user: User, delivery_id: uuid.UUID, scheduled_for: datetime | None
) -> Delivery:
    """Set (or change) the delivery time. Defaults to the rental start."""
    delivery = _locked_assigned(session, user, delivery_id)
    booking = _locked_booking(session, delivery)
    when = scheduled_for or booking.start_at
    now = _now()
    if when.tzinfo is None:
        raise InvalidScheduleError("The delivery time must include a timezone.")
    if when <= now:
        raise InvalidScheduleError("The delivery time must be in the future.")
    if when > booking.start_at or when < booking.start_at - EARLIEST_BEFORE_START:
        raise InvalidScheduleError(
            "Deliver at most 24 hours before the rental starts, and no later than its start. "
            "Contact support if the car cannot arrive in time."
        )
    if delivery.status == D.PENDING_SCHEDULE:
        transition(delivery, D.SCHEDULED)
        booking_transition(booking, B.DELIVERY_SCHEDULED)
    elif delivery.status != D.SCHEDULED:
        raise InvalidDeliveryTransitionError(f"A {delivery.status} delivery cannot be rescheduled.")
    previous = delivery.scheduled_for
    delivery.scheduled_for = when
    _audit(
        session,
        user,
        "scheduled" if previous is None else "rescheduled",
        delivery,
        scheduled_for=when.isoformat(),
        previous=previous.isoformat() if previous else None,
    )
    session.commit()
    return get_delivery(session, delivery.id)


def start(session: Session, user: User, delivery_id: uuid.UUID) -> Delivery:
    """The delivery person sets off with the vehicle."""
    delivery = _locked_assigned(session, user, delivery_id)
    booking = _locked_booking(session, delivery)
    transition(delivery, D.EN_ROUTE)
    booking_transition(booking, B.IN_TRANSIT)
    delivery.started_at = _now()
    _audit(session, user, "started", delivery)
    session.commit()
    return get_delivery(session, delivery.id)


def _new_record(
    session: Session,
    delivery: Delivery,
    user: User,
    kind: HandoverKind,
    *,
    odometer_km: int,
    fuel_level: FuelLevel,
    condition_notes: str | None,
) -> HandoverRecord:
    record = HandoverRecord(
        delivery_id=delivery.id,
        kind=kind,
        recorded_by_id=user.id,
        recorded_at=_now(),
        odometer_km=odometer_km,
        fuel_level=fuel_level,
        condition_notes=condition_notes,
    )
    session.add(record)
    session.flush()
    return record


def complete_handover(
    session: Session,
    user: User,
    delivery_id: uuid.UUID,
    *,
    odometer_km: int,
    fuel_level: FuelLevel,
    condition_notes: str | None,
) -> Delivery:
    """The vehicle is with the renter: record its condition. The renter then acknowledges."""
    delivery = _locked_assigned(session, user, delivery_id)
    booking = _locked_booking(session, delivery)
    transition(delivery, D.DELIVERED)
    booking_transition(booking, B.DELIVERED)
    delivery.delivered_at = _now()
    _new_record(
        session,
        delivery,
        user,
        HandoverKind.HANDOVER,
        odometer_km=odometer_km,
        fuel_level=fuel_level,
        condition_notes=condition_notes,
    )
    _audit(session, user, "delivered", delivery, odometer_km=odometer_km, fuel=fuel_level.value)
    session.commit()
    return get_delivery(session, delivery.id)


def record_return(
    session: Session,
    user: User,
    delivery_id: uuid.UUID,
    *,
    odometer_km: int,
    fuel_level: FuelLevel,
    condition_notes: str | None,
) -> Delivery:
    """The vehicle is back with its owner: record its condition and complete the booking."""
    delivery = _locked_assigned(session, user, delivery_id)
    booking = _locked_booking(session, delivery)
    if booking.status not in (B.DELIVERED, B.ACTIVE_RENTAL, B.RETURN_PENDING):
        raise InvalidDeliveryTransitionError(f"A {booking.status} booking cannot be returned.")
    handover = session.scalar(
        select(HandoverRecord).where(
            HandoverRecord.delivery_id == delivery.id,
            HandoverRecord.kind == HandoverKind.HANDOVER,
        )
    )
    if odometer_km < handover.odometer_km:
        raise InvalidHandoverError(
            f"The odometer cannot be lower than at handover ({handover.odometer_km} km)."
        )
    # Walk the booking through each state so the state machine stays the single authority.
    acknowledged = booking.status != B.DELIVERED
    if booking.status == B.DELIVERED:
        booking_transition(booking, B.ACTIVE_RENTAL)
    if booking.status == B.ACTIVE_RENTAL:
        booking_transition(booking, B.RETURN_PENDING)
    booking_transition(booking, B.COMPLETED)
    _new_record(
        session,
        delivery,
        user,
        HandoverKind.RETURN,
        odometer_km=odometer_km,
        fuel_level=fuel_level,
        condition_notes=condition_notes,
    )
    _audit(
        session,
        user,
        "returned",
        delivery,
        odometer_km=odometer_km,
        distance_km=odometer_km - handover.odometer_km,
        fuel=fuel_level.value,
        renter_acknowledged_handover=acknowledged,
    )
    session.commit()
    return get_delivery(session, delivery.id)


def report_exception(
    session: Session,
    user: User,
    delivery_id: uuid.UUID,
    *,
    kind: DeliveryExceptionKind,
    notes: str,
) -> Delivery:
    """A delay is only recorded; any other problem stops the delivery for an administrator."""
    delivery = _locked_assigned(session, user, delivery_id)
    if delivery.status not in ACTIVE:
        raise InvalidDeliveryTransitionError(
            f"Problems can only be reported on an active delivery, not a {delivery.status} one."
        )
    if kind != DeliveryExceptionKind.DELAY:
        transition(delivery, D.FAILED)
    session.add(
        DeliveryException(delivery_id=delivery.id, kind=kind, notes=notes, reported_by_id=user.id)
    )
    _audit(session, user, "exception_reported", delivery, kind=kind.value, notes=notes)
    session.commit()
    return get_delivery(session, delivery.id)


def add_photo(
    session: Session,
    storage: DocumentStorage,
    user: User,
    delivery_id: uuid.UUID,
    kind: HandoverKind,
    data: bytes,
    *,
    max_bytes: int,
) -> HandoverPhoto:
    """Photos are accepted only while the record is fresh, so they cannot be added later
    to support a damage claim: handover photos until the renter acknowledges, return
    photos for two hours after the return."""
    delivery = _locked_assigned(session, user, delivery_id)
    record = session.scalar(
        select(HandoverRecord)
        .options(selectinload(HandoverRecord.photos))
        .where(HandoverRecord.delivery_id == delivery.id, HandoverRecord.kind == kind)
        .with_for_update()
    )
    if record is None:
        raise InvalidHandoverError(f"Record the {kind.value.lower()} before adding photos.")
    if kind == HandoverKind.HANDOVER and record.renter_acknowledged_at is not None:
        raise InvalidHandoverError("The renter has acknowledged the handover; photos are closed.")
    if kind == HandoverKind.RETURN and _now() > record.recorded_at + RETURN_PHOTO_WINDOW:
        raise InvalidHandoverError("Return photos can only be added within 2 hours.")
    if len(record.photos) >= MAX_PHOTOS_PER_RECORD:
        raise InvalidHandoverError(f"At most {MAX_PHOTOS_PER_RECORD} photos per record.")
    upload = check_upload(data, allowed=PHOTO_TYPES, max_bytes=max_bytes)
    photo = HandoverPhoto(
        record_id=record.id,
        storage_key=storage.save(upload.data),
        content_type=upload.content_type,
        size_bytes=upload.size_bytes,
        sha256=upload.sha256,
        uploaded_by_id=user.id,
    )
    session.add(photo)
    session.flush()
    _audit(session, user, "photo_added", delivery, record=kind.value, photo_id=str(photo.id))
    session.commit()
    return photo


def read_photo(
    session: Session, storage: DocumentStorage, delivery: Delivery, photo_id: uuid.UUID
) -> tuple[str, bytes]:
    """Callers must already have checked access to `delivery`."""
    photo = next(
        (p for r in delivery.records for p in r.photos if p.id == photo_id),
        None,
    )
    if photo is None:
        raise NotFoundError("Photo not found.")
    return photo.content_type, storage.read(photo.storage_key)


# --- renter actions ------------------------------------------------------------------------


def acknowledge_handover(
    session: Session, renter: User, booking_id: uuid.UUID, notes: str | None
) -> Delivery:
    """The renter confirms they have the car (and may note anything they disagree with).
    The rental is then active."""
    delivery = get_booking_delivery(session, renter, booking_id)
    booking = _locked_booking(session, delivery)
    record = session.scalar(
        select(HandoverRecord)
        .where(
            HandoverRecord.delivery_id == delivery.id,
            HandoverRecord.kind == HandoverKind.HANDOVER,
        )
        .with_for_update()
    )
    if booking.status != B.DELIVERED or record is None:
        raise InvalidDeliveryTransitionError("There is no handover waiting for you to confirm.")
    booking_transition(booking, B.ACTIVE_RENTAL)
    record.renter_acknowledged_at = _now()
    record.renter_notes = notes
    _audit(session, renter, "handover_acknowledged", delivery, renter_notes=notes)
    session.commit()
    return get_delivery(session, delivery.id)


def request_return(session: Session, renter: User, booking_id: uuid.UUID) -> Delivery:
    """The renter is ready to hand the car back (early or at the end of the rental)."""
    delivery = get_booking_delivery(session, renter, booking_id)
    booking = _locked_booking(session, delivery)
    if booking.status != B.ACTIVE_RENTAL:
        raise InvalidDeliveryTransitionError(f"A {booking.status} booking cannot be returned.")
    booking_transition(booking, B.RETURN_PENDING)
    _audit(session, renter, "return_requested", delivery)
    session.commit()
    return get_delivery(session, delivery.id)


# --- administrator actions -------------------------------------------------------------


def reassign(session: Session, admin: User, delivery_id: uuid.UUID, user_id: uuid.UUID) -> Delivery:
    """Hand an unfinished delivery to another active owner account."""
    delivery = _locked(session, delivery_id)
    if delivery.status in (D.DELIVERED, D.CANCELLED):
        raise InvalidDeliveryTransitionError(f"A {delivery.status} delivery cannot be reassigned.")
    assignee = session.get(User, user_id)
    if (
        assignee is None
        or assignee.status != UserStatus.ACTIVE
        or RoleName.OWNER not in {role.name for role in assignee.roles}
        or session.scalar(select(OwnerProfile.id).where(OwnerProfile.user_id == assignee.id))
        is None
    ):
        raise InvalidAssigneeError("Deliveries can only be assigned to an active owner account.")
    previous = delivery.assigned_to_id
    delivery.assigned_to_id = assignee.id
    _audit(
        session,
        admin,
        "reassigned",
        delivery,
        assigned_to={"from": str(previous) if previous else None, "to": str(assignee.id)},
    )
    session.commit()
    return get_delivery(session, delivery.id)


def admin_reschedule(
    session: Session, admin: User, delivery_id: uuid.UUID, scheduled_for: datetime, note: str
) -> Delivery:
    """Resolve open exceptions and set a new delivery time (any time before the rental ends)."""
    delivery = _locked(session, delivery_id)
    booking = _locked_booking(session, delivery)
    now = _now()
    if scheduled_for <= now or scheduled_for >= booking.end_at:
        raise InvalidScheduleError("Choose a future time before the rental ends.")
    if delivery.status in (D.PENDING_SCHEDULE, D.FAILED):
        transition(delivery, D.SCHEDULED)
    elif delivery.status != D.SCHEDULED:
        raise InvalidDeliveryTransitionError(f"A {delivery.status} delivery cannot be rescheduled.")
    if booking.status in (B.CONFIRMED, B.IN_TRANSIT):
        booking_transition(booking, B.DELIVERY_SCHEDULED)
    delivery.scheduled_for = scheduled_for
    delivery.started_at = None
    resolved = _resolve_open(session, delivery, admin, note, now)
    _audit(
        session,
        admin,
        "rescheduled_by_admin",
        delivery,
        scheduled_for=scheduled_for.isoformat(),
        note=note,
        resolved_exceptions=resolved,
    )
    session.commit()
    return get_delivery(session, delivery.id)


def resolve_exception(
    session: Session, admin: User, delivery_id: uuid.UUID, exception_id: uuid.UUID, note: str
) -> Delivery:
    """Close an exception that needs no change to the delivery (e.g. a delay)."""
    delivery = _locked(session, delivery_id)
    exception = session.scalar(
        select(DeliveryException)
        .where(DeliveryException.id == exception_id, DeliveryException.delivery_id == delivery.id)
        .with_for_update()
    )
    if exception is None:
        raise NotFoundError("Exception not found.")
    if exception.resolved_at is not None:
        raise InvalidDeliveryTransitionError("This exception is already resolved.")
    if delivery.status == D.FAILED:
        raise InvalidDeliveryTransitionError(
            "The delivery is stopped: reschedule it or cancel the booking instead."
        )
    exception.resolved_at = _now()
    exception.resolved_by_id = admin.id
    exception.resolution = note
    _audit(session, admin, "exception_resolved", delivery, exception_id=str(exception.id))
    session.commit()
    return get_delivery(session, delivery.id)


def _resolve_open(
    session: Session, delivery: Delivery, admin: User, note: str, now: datetime
) -> int:
    open_exceptions = session.scalars(
        select(DeliveryException).where(
            DeliveryException.delivery_id == delivery.id, DeliveryException.resolved_at.is_(None)
        )
    ).all()
    for exception in open_exceptions:
        exception.resolved_at = now
        exception.resolved_by_id = admin.id
        exception.resolution = note
    return len(open_exceptions)
