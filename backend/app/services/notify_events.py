"""What users are told, and when (FR-36). Each function queues notifications in the caller's
transaction through `notifications.notify`; the caller commits. Texts are short enough for a
push notification; the email repeats them with a link into the app. Times are SA time.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Booking, Delivery, DeliveryException, OwnerProfile, Refund, Vehicle
from app.models.enums import DeliveryExceptionKind
from app.services.notifications import notify

SA_TIMEZONE = ZoneInfo("Africa/Johannesburg")


def when(moment: datetime) -> str:
    """'Tue 20 Oct, 08:00' in South African time."""
    local = moment.astimezone(SA_TIMEZONE)
    return f"{local:%a} {local.day} {local:%b, %H:%M}"


def rand(amount: Decimal) -> str:
    whole, _, cents = f"{amount:.2f}".partition(".")
    return f"R {int(whole):,}".replace(",", " ") + f".{cents}"


def _car(vehicle: Vehicle) -> str:
    return f"{vehicle.make} {vehicle.model}"


def _owner_user_id(session: Session, vehicle: Vehicle) -> uuid.UUID:
    return session.scalar(select(OwnerProfile.user_id).where(OwnerProfile.id == vehicle.owner_id))


def _vehicle(session: Session, booking: Booking) -> Vehicle:
    return booking.vehicle or session.get(Vehicle, booking.vehicle_id)


# --- bookings and payments --------------------------------------------------------------------


def booking_confirmed(session: Session, booking: Booking) -> None:
    vehicle = _vehicle(session, booking)
    period = f"{when(booking.start_at)} to {when(booking.end_at)}"
    notify(
        session,
        booking.renter_id,
        "booking.confirmed",
        title=f"Booking confirmed: {booking.reference}",
        body=(
            f"We received your payment of {rand(booking.total_amount)}. Your {_car(vehicle)} is "
            f"booked from {period}. The owner will confirm the delivery time."
        ),
        link=f"/bookings/{booking.id}",
        dedupe_key=f"booking.confirmed:{booking.id}",
        essential=True,
    )
    notify(
        session,
        _owner_user_id(session, vehicle),
        "booking.new",
        title=f"New booking for your {_car(vehicle)}",
        body=f"Booked from {period} ({booking.reference}). Please confirm the delivery time.",
        link="/deliveries",
        dedupe_key=f"booking.new:{booking.id}",
    )


def booking_expired(session: Session, booking_id: uuid.UUID) -> None:
    booking = session.get(Booking, booking_id)
    vehicle = _vehicle(session, booking)
    notify(
        session,
        booking.renter_id,
        "booking.expired",
        title="Your booking hold has expired",
        body=(
            f"The {_car(vehicle)} was held for you but not paid in time, so the dates were released. "
            "You can book again if they are still free."
        ),
        link=f"/vehicles/{vehicle.id}",
        dedupe_key=f"booking.expired:{booking.id}",
    )


def booking_cancelled(
    session: Session, booking: Booking, *, by_admin: bool, refunded: bool
) -> None:
    vehicle = _vehicle(session, booking)
    refund_note = (
        f" A full refund of {rand(booking.total_amount)} is on its way to your card."
        if refunded
        else ""
    )
    who = "CarHire SA cancelled" if by_admin else "You cancelled"
    reason = (
        f" Reason: {booking.cancellation_reason}."
        if by_admin and booking.cancellation_reason
        else ""
    )
    notify(
        session,
        booking.renter_id,
        "booking.cancelled",
        title=f"Booking {booking.reference} cancelled",
        body=f"{who} your booking of the {_car(vehicle)}.{reason}{refund_note}",
        link=f"/bookings/{booking.id}",
        dedupe_key=f"booking.cancelled:{booking.id}",
        essential=True,
    )
    if booking.confirmed_at is not None:  # the owner only knew about paid bookings
        notify(
            session,
            _owner_user_id(session, vehicle),
            "booking.cancelled_owner",
            title=f"Booking of your {_car(vehicle)} cancelled",
            body=f"The booking {booking.reference} from {when(booking.start_at)} was cancelled. The dates are free again.",
            link="/owner/bookings",
            dedupe_key=f"booking.cancelled_owner:{booking.id}",
        )


def refund_processed(session: Session, refund: Refund, booking: Booking) -> None:
    notify(
        session,
        booking.renter_id,
        "refund.processed",
        title=f"Refund of {rand(refund.amount)} processed",
        body=(
            f"Your refund for booking {booking.reference} has been sent to your card. "
            "Banks can take 5 to 10 working days to show it."
        ),
        link="/payments",
        dedupe_key=f"refund.processed:{refund.id}",
        essential=True,
    )


# --- verification and vehicles ----------------------------------------------------------------

_DOCUMENT = {"SA_ID": "South African ID", "DRIVING_LICENCE": "driving licence"}


def verification_decided(
    session: Session,
    user_id: uuid.UUID,
    submission_id,
    document_type,
    decision: str,
    note: str | None,
) -> None:
    document = _DOCUMENT.get(str(document_type), "document")
    if decision == "APPROVED":
        title, body = f"Your {document} is verified", f"Your {document} has been approved."
    elif decision == "REJECTED":
        title, body = (
            f"Your {document} was not approved",
            f"Please upload it again. Reviewer's note: {note}",
        )
    else:
        title, body = f"More information needed for your {document}", f"Reviewer's note: {note}"
    notify(
        session,
        user_id,
        "verification.decided",
        title=title,
        body=body,
        link="/verification",
        dedupe_key=f"verification.decided:{submission_id}",
    )


def vehicle_reviewed(
    session: Session, vehicle: Vehicle, action: str, reason: str | None = None
) -> None:
    car = f"{_car(vehicle)} ({vehicle.registration_number})"
    texts = {
        "approved": (
            f"Your {_car(vehicle)} is approved",
            f"{car} is now listed. Renters can find and book it.",
        ),
        "rejected": (
            f"Your {_car(vehicle)} was not approved",
            f"{car}: {reason}. Fix this and submit it again.",
        ),
        "suspended": (
            f"Your {_car(vehicle)} has been suspended",
            f"{car} is no longer listed. Reason: {reason}. Contact support.",
        ),
        "reinstated": (
            f"Your {_car(vehicle)} is listed again",
            f"{car} has been reinstated and can be booked.",
        ),
    }
    title, body = texts[action]
    notify(
        session,
        _owner_user_id(session, vehicle),
        f"vehicle.{action}",
        title=title,
        body=body,
        link=f"/owner/vehicles/{vehicle.id}",
        dedupe_key=f"vehicle.{action}:{vehicle.id}:{uuid.uuid4()}",  # can happen more than once
    )


# --- deliveries ---------------------------------------------------------------------------------


def _renter_link(delivery: Delivery) -> str:
    return f"/bookings/{delivery.booking_id}"


def delivery_scheduled(session: Session, delivery: Delivery, *, by_admin: bool = False) -> None:
    booking = delivery.booking
    body = f"Your {_car(booking.vehicle)} will be delivered on {when(delivery.scheduled_for)} to {delivery.dropoff_address}."
    key = f"delivery.scheduled:{delivery.id}:{delivery.scheduled_for.isoformat()}"
    notify(
        session,
        booking.renter_id,
        "delivery.scheduled",
        title="Delivery time confirmed" if not by_admin else "New delivery time",
        body=body,
        link=_renter_link(delivery),
        dedupe_key=key,
    )
    if by_admin and delivery.assigned_to_id:
        notify(
            session,
            delivery.assigned_to_id,
            "delivery.rescheduled",
            title=f"Delivery {booking.reference} rescheduled",
            body=f"CarHire SA moved the delivery of the {_car(booking.vehicle)} to {when(delivery.scheduled_for)}.",
            link=f"/deliveries/{delivery.id}",
            dedupe_key=f"{key}:assignee",
        )


def delivery_started(session: Session, delivery: Delivery) -> None:
    notify(
        session,
        delivery.booking.renter_id,
        "delivery.started",
        title="Your car is on its way",
        body=f"The {_car(delivery.booking.vehicle)} is on its way. Follow it live in the app.",
        link=_renter_link(delivery),
        dedupe_key=f"delivery.started:{delivery.id}:{delivery.started_at.isoformat()}",
    )


def delivery_handed_over(session: Session, delivery: Delivery) -> None:
    notify(
        session,
        delivery.booking.renter_id,
        "delivery.handed_over",
        title="Please confirm you have the car",
        body="The handover has been recorded. Check the odometer, fuel and notes, then confirm receipt in the app.",
        link=_renter_link(delivery),
        dedupe_key=f"delivery.handed_over:{delivery.id}",
    )


def delivery_problem(session: Session, delivery: Delivery, issue: DeliveryException) -> None:
    if issue.kind == DeliveryExceptionKind.DELAY:
        title, body = "Your delivery is running late", f"Message from the owner: {issue.notes}"
    else:
        title = "There is a problem with your delivery"
        body = f"Message from the owner: {issue.notes} CarHire SA support will contact you to rearrange it."
    notify(
        session,
        delivery.booking.renter_id,
        "delivery.problem",
        title=title,
        body=body,
        link=_renter_link(delivery),
        dedupe_key=f"delivery.problem:{issue.id}",
    )


def delivery_reassigned(session: Session, delivery: Delivery) -> None:
    booking = delivery.booking
    notify(
        session,
        delivery.assigned_to_id,
        "delivery.assigned",
        title="You have a new delivery",
        body=f"Deliver the {_car(booking.vehicle)} for booking {booking.reference} (rental starts {when(booking.start_at)}).",
        link=f"/deliveries/{delivery.id}",
        dedupe_key=f"delivery.assigned:{delivery.id}:{delivery.assigned_to_id}:{uuid.uuid4()}",
    )


def return_requested(session: Session, delivery: Delivery) -> None:
    if delivery.assigned_to_id is None:
        return
    booking = delivery.booking
    notify(
        session,
        delivery.assigned_to_id,
        "return.requested",
        title=f"{booking.renter.full_name.split()[0]} is ready to return the car",
        body=f"Collect the {_car(booking.vehicle)} ({booking.reference}) and record the return in the app.",
        link=f"/deliveries/{delivery.id}",
        dedupe_key=f"return.requested:{booking.id}",
    )


def return_recorded(session: Session, delivery: Delivery) -> None:
    booking = delivery.booking
    notify(
        session,
        booking.renter_id,
        "return.recorded",
        title="Rental completed",
        body=f"The return of the {_car(booking.vehicle)} has been recorded. Thank you for renting with CarHire SA.",
        link=_renter_link(delivery),
        dedupe_key=f"return.recorded:{booking.id}",
    )


# --- reminders (run by `python -m app.cli send-reminders`) -------------------------------------


def return_reminder(session: Session, booking: Booking) -> bool:
    return notify(
        session,
        booking.renter_id,
        "reminder.return",
        title="Your rental ends soon",
        body=(
            f"Your rental of the {_car(_vehicle(session, booking))} ends {when(booking.end_at)}. "
            "Tap “I'm ready to return the car” when you are done."
        ),
        link=f"/bookings/{booking.id}",
        dedupe_key=f"reminder.return:{booking.id}",
    )


def schedule_reminder(session: Session, delivery: Delivery) -> bool:
    booking = delivery.booking
    return notify(
        session,
        delivery.assigned_to_id,
        "reminder.schedule",
        title="Confirm the delivery time",
        body=f"The rental of your {_car(booking.vehicle)} ({booking.reference}) starts {when(booking.start_at)}. Confirm when you will deliver.",
        link=f"/deliveries/{delivery.id}",
        dedupe_key=f"reminder.schedule:{delivery.id}",
    )


def queue_reminders(session: Session, *, now: datetime) -> dict[str, int]:
    """Return reminders 24 h before the rental ends; delivery-time reminders when a delivery is
    still unscheduled 36 h before the rental starts. Each is sent once (dedupe key)."""
    from datetime import timedelta

    from sqlalchemy.orm import selectinload

    from app.models.enums import BookingStatus, DeliveryStatus

    returns = session.scalars(
        select(Booking).where(
            Booking.status.in_([BookingStatus.DELIVERED, BookingStatus.ACTIVE_RENTAL]),
            Booking.end_at > now,
            Booking.end_at <= now + timedelta(hours=24),
        )
    )
    sent_returns = sum(return_reminder(session, b) for b in returns)
    unscheduled = session.scalars(
        select(Delivery)
        .join(Booking, Booking.id == Delivery.booking_id)
        .options(selectinload(Delivery.booking).selectinload(Booking.vehicle))
        .where(
            Delivery.status == DeliveryStatus.PENDING_SCHEDULE,
            Delivery.assigned_to_id.is_not(None),
            Booking.start_at > now,
            Booking.start_at <= now + timedelta(hours=36),
        )
    )
    sent_schedules = sum(schedule_reminder(session, d) for d in unscheduled)
    session.commit()
    return {"return_reminders": sent_returns, "schedule_reminders": sent_schedules}
