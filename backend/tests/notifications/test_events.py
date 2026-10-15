"""Which business events notify whom (FR-36), and that each event notifies once."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Booking, Delivery, Notification, OwnerProfile, Payment
from app.models.enums import BookingStatus, DeliveryStatus, PaymentStatus
from app.services import bookings as booking_service
from app.services import notifications, notify_events
from app.services import payments as payment_service
from tests.bookings.helpers import book
from tests.conftest import requires_db
from tests.notifications.conftest import deliveries, events, latest, user_id
from tests.tracking.conftest import HANDOVER, OWNER, post, set_off

pytestmark = requires_db
ALICE, OWNER_EMAIL = "alice@example.com", "owner@example.com"


def alice_name(session: Session) -> str:
    from app.models import User

    return session.scalar(select(User.full_name).where(User.email == ALICE)).split()[0]


def booking_of(session: Session, delivery_id: str) -> Booking:
    return session.get(Booking, session.get(Delivery, uuid.UUID(delivery_id)).booking_id)


# --- the outbox -------------------------------------------------------------------------------


def test_one_notification_per_event_with_a_delivery_per_channel(db_session, alice) -> None:
    uid = user_id(db_session, ALICE)
    first = notifications.notify(db_session, uid, "x.test", title="T", body="B", dedupe_key="x:1")
    again = notifications.notify(db_session, uid, "x.test", title="T", body="B", dedupe_key="x:1")

    assert (first, again) == (True, False)
    note = latest(db_session, ALICE, "x.test")
    assert set(deliveries(db_session, note)) == {"EMAIL", "PUSH"}


def test_nothing_is_sent_for_a_change_that_was_rolled_back(db_session, alice) -> None:
    uid = user_id(db_session, ALICE)
    savepoint = db_session.begin_nested()
    notifications.notify(db_session, uid, "x.rollback", title="T", body="B", dedupe_key="x:rb")
    savepoint.rollback()

    assert (
        db_session.scalar(
            select(func.count()).select_from(Notification).where(Notification.event == "x.rollback")
        )
        == 0
    )


# --- bookings and payments --------------------------------------------------------------------


def test_payment_confirms_and_tells_renter_and_owner(db_session, delivery_id) -> None:
    booking = booking_of(db_session, delivery_id)
    receipt = latest(db_session, ALICE, "booking.confirmed")

    assert receipt.essential and receipt.link == f"/bookings/{booking.id}"
    assert "R " in receipt.body and booking.reference in receipt.title
    assert events(db_session, OWNER_EMAIL) == ["booking.new"]
    assert latest(db_session, OWNER_EMAIL, "booking.new").essential is False


def test_expired_hold_is_notified_once(api, alice, owner, db_session, storage) -> None:
    from tests.marketplace.factories import listed_vehicle

    vehicle = listed_vehicle(db_session, storage)
    booking = book(api, alice, vehicle.id).json()
    later = datetime.now(UTC) + timedelta(hours=1)

    assert booking_service.expire_stale_holds(db_session, now=later) == 1
    assert booking_service.expire_stale_holds(db_session, now=later) == 0

    assert events(db_session, ALICE).count("booking.expired") == 1
    assert latest(db_session, ALICE, "booking.expired").link == f"/vehicles/{vehicle.id}"
    assert booking["status"] == "PENDING_PAYMENT"


def test_renter_cancelling_an_unpaid_hold_mentions_no_refund_and_spares_the_owner(
    api, alice, owner, db_session, storage
) -> None:
    from tests.marketplace.factories import listed_vehicle

    vehicle = listed_vehicle(db_session, storage)
    booking = book(api, alice, vehicle.id).json()
    post(api, alice, f"/api/v1/bookings/{booking['id']}/cancel")

    note = latest(db_session, ALICE, "booking.cancelled")
    assert note.essential and "refund" not in note.body and note.body.startswith("You cancelled")
    car_owner = db_session.scalar(
        select(OwnerProfile.user_id).where(OwnerProfile.id == vehicle.owner_id)
    )
    owner_events = db_session.scalars(
        select(Notification.event).where(Notification.user_id == car_owner)
    ).all()
    assert owner_events == []  # the owner never heard of this unpaid hold


def test_admin_cancelling_a_paid_booking_promises_a_refund_and_tells_the_owner(
    api, admin, delivery_id, db_session
) -> None:
    booking = booking_of(db_session, delivery_id)
    db_session.add(
        Payment(
            booking_id=booking.id,
            provider="paystack",
            provider_reference="r-1",
            amount=booking.total_amount,
            status=PaymentStatus.SUCCEEDED,
            paid_at=datetime.now(UTC),
        )
    )
    db_session.flush()

    post(api, admin, f"/api/v1/admin/bookings/{booking.id}/cancel", {"reason": "Car damaged"})

    note = latest(db_session, ALICE, "booking.cancelled")
    assert (
        "CarHire SA cancelled" in note.body
        and "Car damaged" in note.body
        and "full refund" in note.body
    )
    assert "booking.cancelled_owner" in events(db_session, OWNER_EMAIL)


def test_a_processed_refund_is_notified_once(
    api, admin, delivery_id, db_session, payment_provider
) -> None:
    booking = booking_of(db_session, delivery_id)
    payment = Payment(
        booking_id=booking.id,
        provider="paystack",
        provider_reference="r-2",
        amount=booking.total_amount,
        status=PaymentStatus.SUCCEEDED,
        paid_at=datetime.now(UTC),
    )
    db_session.add(payment)
    db_session.flush()
    response = post(
        api,
        admin,
        f"/api/v1/admin/payments/{payment.id}/refunds",
        {"amount": "100.00", "reason": "Goodwill"},
    )
    refund_id = uuid.UUID(response.json()["id"])
    provider_id = payment_provider.refund_requests[-1]["id"]
    assert "refund.processed" not in events(db_session, ALICE)  # still pending at Paystack

    payment_provider.refund_states[provider_id] = "processed"
    payment_service.refresh_refund(db_session, payment_provider, refund_id)
    payment_service.refresh_refund(db_session, payment_provider, refund_id)

    assert events(db_session, ALICE).count("refund.processed") == 1
    assert "R 100.00" in latest(db_session, ALICE, "refund.processed").title


# --- verification and vehicles ----------------------------------------------------------------


def test_verification_decisions_are_explained(api, admin, renter, db_session) -> None:
    from tests.verification.helpers import decide, set_dob, submit_id

    set_dob(api, renter.headers)
    submission = submit_id(api, renter.headers).json()
    decide(api, admin.headers, submission["id"], "REJECTED", note="The photo is blurry")

    note = latest(db_session, "renter@example.com", "verification.decided")
    assert note.title == "Your South African ID was not approved"
    assert "The photo is blurry" in note.body and note.link == "/verification"


def test_vehicle_review_tells_the_owner(api, admin, owner, db_session, storage) -> None:
    from sqlalchemy import select as sel

    from app.models import OwnerProfile, User
    from app.models.enums import VehicleStatus
    from tests.marketplace.factories import listed_vehicle

    vehicle = listed_vehicle(db_session, storage, status=VehicleStatus.PENDING_APPROVAL)
    vehicle.owner_id = db_session.scalar(
        sel(OwnerProfile.id)
        .join(User, User.id == OwnerProfile.user_id)
        .where(User.email == OWNER_EMAIL)
    )
    db_session.flush()
    post(
        api, admin, f"/api/v1/admin/vehicles/{vehicle.id}/reject", {"reason": "Blurry licence disc"}
    )

    note = latest(db_session, OWNER_EMAIL, "vehicle.rejected")
    assert "Blurry licence disc" in note.body and note.link == f"/owner/vehicles/{vehicle.id}"


# --- deliveries -------------------------------------------------------------------------------


def test_the_delivery_journey_notifies_each_step(
    api, alice, owner, delivery_id, db_session
) -> None:
    booking = booking_of(db_session, delivery_id)
    set_off(api, owner, delivery_id)  # schedule + start
    post(api, owner, f"{OWNER}/{delivery_id}/handover", HANDOVER)
    post(api, alice, f"/api/v1/bookings/{booking.id}/delivery/acknowledge")
    post(api, alice, f"/api/v1/bookings/{booking.id}/return-request")
    post(api, owner, f"{OWNER}/{delivery_id}/return", {**HANDOVER, "odometer_km": 41300})

    assert sorted(events(db_session, ALICE)) == sorted(
        [
            "booking.confirmed",
            "delivery.scheduled",
            "delivery.started",
            "delivery.handed_over",
            "return.recorded",
        ]
    )
    assert sorted(events(db_session, OWNER_EMAIL)) == ["booking.new", "return.requested"]
    first_name = alice_name(db_session)
    assert (
        latest(db_session, OWNER_EMAIL, "return.requested").title
        == f"{first_name} is ready to return the car"
    )
    assert latest(db_session, ALICE, "delivery.started").link == f"/bookings/{booking.id}"


def test_delays_and_stops_are_worded_differently(api, owner, delivery_id, db_session) -> None:
    set_off(api, owner, delivery_id)
    post(
        api,
        owner,
        f"{OWNER}/{delivery_id}/exceptions",
        {"kind": "DELAY", "notes": "Traffic on the N1"},
    )
    late = latest(db_session, ALICE, "delivery.problem")
    assert late.title == "Your delivery is running late" and "Traffic on the N1" in late.body

    post(
        api,
        owner,
        f"{OWNER}/{delivery_id}/exceptions",
        {"kind": "ADDRESS_PROBLEM", "notes": "Gate locked"},
    )
    assert events(db_session, ALICE).count("delivery.problem") == 2
    assert (
        latest(db_session, ALICE, "delivery.problem").title
        == "There is a problem with your delivery"
    )


def test_admin_reschedule_and_reassignment_tell_the_people_involved(
    api, admin, owner, delivery_id, db_session
) -> None:
    from tests.api_fixtures import register

    booking = booking_of(db_session, delivery_id)
    when = (booking.start_at - timedelta(hours=2)).isoformat()
    post(
        api,
        admin,
        f"/api/v1/admin/deliveries/{delivery_id}/reschedule",
        {"scheduled_for": when, "note": "Earlier"},
    )
    assert latest(db_session, ALICE, "delivery.scheduled").title == "New delivery time"
    assert "delivery.rescheduled" in events(db_session, OWNER_EMAIL)

    register(api, "helper@example.com", "OWNER")
    helper_id = user_id(db_session, "helper@example.com")
    post(api, admin, f"/api/v1/admin/deliveries/{delivery_id}/assign", {"user_id": str(helper_id)})
    assert events(db_session, "helper@example.com") == ["delivery.assigned"]


# --- reminders --------------------------------------------------------------------------------


def test_reminders_go_out_once_and_only_in_their_window(db_session, delivery_id) -> None:
    booking = booking_of(db_session, delivery_id)
    start = booking.start_at

    # Unscheduled 30 h before the start: remind the owner to confirm the time.
    counts = notify_events.queue_reminders(db_session, now=start - timedelta(hours=30))
    assert counts == {"return_reminders": 0, "schedule_reminders": 1}
    assert (
        notify_events.queue_reminders(db_session, now=start - timedelta(hours=29))[
            "schedule_reminders"
        ]
        == 0
    )
    assert notify_events.queue_reminders(db_session, now=start - timedelta(hours=40)) == {
        "return_reminders": 0,
        "schedule_reminders": 0,
    }

    # Once the time is confirmed, no more "confirm the time" reminders.
    delivery = db_session.get(Delivery, uuid.UUID(delivery_id))
    db_session.execute(
        Notification.__table__.delete().where(Notification.event == "reminder.schedule")
    )
    delivery.status, delivery.scheduled_for = DeliveryStatus.SCHEDULED, start
    db_session.flush()
    assert (
        notify_events.queue_reminders(db_session, now=start - timedelta(hours=30))[
            "schedule_reminders"
        ]
        == 0
    )

    # Rented: remind the renter in the last 24 h only.
    booking.status = BookingStatus.ACTIVE_RENTAL
    db_session.flush()
    assert (
        notify_events.queue_reminders(db_session, now=booking.end_at - timedelta(hours=30))[
            "return_reminders"
        ]
        == 0
    )
    assert (
        notify_events.queue_reminders(db_session, now=booking.end_at - timedelta(hours=20))[
            "return_reminders"
        ]
        == 1
    )
    assert (
        notify_events.queue_reminders(db_session, now=booking.end_at - timedelta(hours=2))[
            "return_reminders"
        ]
        == 0
    )
    assert "reminder.return" in events(db_session, ALICE)
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.event.like("reminder.%"))
        )
        == 1
    )
