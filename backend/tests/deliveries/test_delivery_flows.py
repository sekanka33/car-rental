"""Deliveries through the API: owner delivers (OPEN-3 default), renter acknowledges, admin
resolves exceptions (BR-7)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Booking, Delivery, HandoverRecord, OwnerProfile, User
from app.models.enums import BookingStatus, UserStatus
from app.services import bookings as booking_service
from tests.api_fixtures import Account, login, register
from tests.bookings.helpers import book, eligible_renter
from tests.conftest import requires_db
from tests.marketplace.factories import PHOTO, listed_vehicle

pytestmark = requires_db
OWNER = "/api/v1/owners/me/deliveries"
ADMIN = "/api/v1/admin/deliveries"
HANDOVER = {"odometer_km": 41200, "fuel_level": "FULL", "condition_notes": "Clean, no damage"}


def owner_profile(session: Session, email: str) -> OwnerProfile:
    user = session.scalar(select(User).where(User.email == email))
    return session.scalar(select(OwnerProfile).where(OwnerProfile.user_id == user.id))


@pytest.fixture
def alice(api: TestClient, db_session: Session) -> Account:
    return eligible_renter(api, db_session, "alice@example.com")


@pytest.fixture
def unpaid(api, alice, owner, db_session, storage) -> dict:
    vehicle = listed_vehicle(db_session, storage)
    vehicle.owner_id = owner_profile(db_session, owner.email).id  # the logged-in owner's car
    db_session.flush()
    response = book(api, alice, vehicle.id)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def booking(unpaid, db_session) -> dict:
    booking_service.confirm_booking(db_session, uuid.UUID(unpaid["id"]))  # payment verified
    return unpaid


@pytest.fixture
def delivery_id(booking, db_session) -> str:
    return str(db_session.scalar(select(Delivery.id).where(Delivery.booking_id == booking["id"])))


def booking_status(session: Session, booking_id: str) -> BookingStatus:
    session.expire_all()
    return session.get(Booking, booking_id).status


def audit_actions(session: Session, delivery_id: str) -> list[str]:
    return session.scalars(
        select(AuditLog.action).where(AuditLog.entity_id == delivery_id).order_by(AuditLog.id)
    ).all()


def post(api: TestClient, account: Account, url: str, json: dict | None = None):
    return api.post(url, headers=account.headers, json=json if json is not None else {})


def deliver(api, owner, delivery_id) -> None:
    """Schedule, set off and hand over: the happy path up to DELIVERED."""
    for step, body in (("schedule", {}), ("start", None), ("handover", HANDOVER)):
        response = post(api, owner, f"{OWNER}/{delivery_id}/{step}", body)
        assert response.status_code == 200, response.text


def photo(api, owner, delivery_id, kind="HANDOVER", data=PHOTO):
    return api.post(
        f"{OWNER}/{delivery_id}/records/{kind}/photos",
        headers=owner.headers,
        files={"photo": ("p.jpg", data, "image/jpeg")},
    )


# --- creation and visibility ------------------------------------------------------------


def test_paid_booking_gets_a_delivery_assigned_to_the_owner(
    api, alice, owner, unpaid, db_session
) -> None:
    mine = f"/api/v1/bookings/{unpaid['id']}/delivery"
    assert api.get(mine, headers=alice.headers).status_code == 404  # not paid yet

    booking_service.confirm_booking(db_session, uuid.UUID(unpaid["id"]))

    renter_view = api.get(mine, headers=alice.headers).json()
    assert renter_view["status"] == "PENDING_SCHEDULE"
    assert renter_view["dropoff_address"] == "12 Long Street, Cape Town"
    assert renter_view["delivery_person_first_name"] == "Test"
    assert "renter" not in renter_view and "registration_number" not in renter_view

    [owner_view] = api.get(OWNER, headers=owner.headers).json()
    assert owner_view["booking_reference"] == unpaid["reference"]
    assert owner_view["renter"]["full_name"] == "Test Person"
    assert owner_view["registration_number"].endswith("GP")


def test_deliveries_are_private(api, alice, owner, delivery_id, booking, db_session) -> None:
    register(api, "other-owner@example.com", "OWNER")
    other_owner = login(api, "other-owner@example.com")
    bob = eligible_renter(api, db_session, "bob@example.com")

    assert api.get(f"{OWNER}/{delivery_id}", headers=other_owner.headers).status_code == 404
    assert post(api, other_owner, f"{OWNER}/{delivery_id}/start").status_code == 404
    assert api.get(OWNER, headers=other_owner.headers).json() == []
    assert (
        api.get(f"/api/v1/bookings/{booking['id']}/delivery", headers=bob.headers).status_code
        == 404
    )
    assert api.get(OWNER, headers=alice.headers).status_code == 403  # renters are not owners
    assert api.get(ADMIN, headers=owner.headers).status_code == 403


# --- scheduling -------------------------------------------------------------------------------


def test_scheduling_rules(api, owner, booking, delivery_id, db_session) -> None:
    url = f"{OWNER}/{delivery_id}/schedule"
    start = datetime.fromisoformat(booking["start_at"])

    for too_early_or_late in (start - timedelta(hours=25), start + timedelta(minutes=1)):
        response = post(api, owner, url, {"scheduled_for": too_early_or_late.isoformat()})
        assert response.status_code == 422, too_early_or_late
    naive = post(api, owner, url, {"scheduled_for": "2030-01-01T08:00:00"})
    assert naive.status_code == 422
    assert booking_status(db_session, booking["id"]) == BookingStatus.CONFIRMED

    first = post(api, owner, url).json()  # defaults to the rental start
    assert first["status"] == "SCHEDULED"
    assert datetime.fromisoformat(first["scheduled_for"]) == start
    assert booking_status(db_session, booking["id"]) == BookingStatus.DELIVERY_SCHEDULED

    earlier = (start - timedelta(hours=2)).isoformat()
    moved = post(api, owner, url, {"scheduled_for": earlier}).json()
    assert datetime.fromisoformat(moved["scheduled_for"]) == start - timedelta(hours=2)
    assert audit_actions(db_session, delivery_id) == ["delivery.scheduled", "delivery.rescheduled"]


def test_steps_must_happen_in_order(api, alice, owner, booking, delivery_id) -> None:
    base = f"{OWNER}/{delivery_id}"
    assert post(api, owner, f"{base}/start").status_code == 409  # not scheduled
    assert post(api, owner, f"{base}/handover", HANDOVER).status_code == 409
    assert post(api, owner, f"{base}/return", HANDOVER).status_code == 409
    ack = f"/api/v1/bookings/{booking['id']}/delivery/acknowledge"
    assert post(api, alice, ack).status_code == 409

    post(api, owner, f"{base}/schedule")
    assert post(api, owner, f"{base}/handover", HANDOVER).status_code == 409  # not en route
    post(api, owner, f"{base}/start")
    assert post(api, owner, f"{base}/schedule").status_code == 409  # already on the way
    assert post(api, owner, f"{base}/handover", HANDOVER).status_code == 200
    assert post(api, owner, f"{base}/handover", HANDOVER).status_code == 409  # only once


# --- full journey ----------------------------------------------------------------------------


def test_delivery_handover_and_return(api, alice, owner, booking, delivery_id, db_session) -> None:
    base = f"{OWNER}/{delivery_id}"
    post(api, owner, f"{base}/schedule")
    assert post(api, owner, f"{base}/start").json()["booking_status"] == "IN_TRANSIT"
    handed = post(api, owner, f"{base}/handover", HANDOVER).json()
    assert (handed["status"], handed["booking_status"]) == ("DELIVERED", "DELIVERED")
    assert handed["handover"]["odometer_km"] == 41200

    uploaded = photo(api, owner, delivery_id)
    assert uploaded.status_code == 201
    mine = f"/api/v1/bookings/{booking['id']}/delivery"
    renter_view = api.get(mine, headers=alice.headers).json()
    [renter_photo] = renter_view["handover"]["photos"]
    image = api.get(renter_photo["url"], headers=alice.headers)
    assert image.status_code == 200 and image.content == PHOTO
    assert image.headers["cache-control"] == "no-store"

    acknowledged = post(api, alice, f"{mine}/acknowledge", {"notes": "Small scratch on boot"})
    assert acknowledged.json()["booking_status"] == "ACTIVE_RENTAL"
    assert acknowledged.json()["handover"]["renter_notes"] == "Small scratch on boot"
    assert photo(api, owner, delivery_id).status_code == 422  # handover photos now closed

    assert post(api, alice, f"/api/v1/bookings/{booking['id']}/return-request").status_code == 200
    assert booking_status(db_session, booking["id"]) == BookingStatus.RETURN_PENDING

    lower = post(api, owner, f"{base}/return", {**HANDOVER, "odometer_km": 41000})
    assert lower.status_code == 422  # cannot go backwards
    returned = post(api, owner, f"{base}/return", {**HANDOVER, "odometer_km": 41530}).json()
    assert returned["booking_status"] == "COMPLETED"
    assert returned["return_record"]["odometer_km"] == 41530
    assert photo(api, owner, delivery_id, "RETURN").status_code == 201
    assert api.get(OWNER, headers=owner.headers).json() == []  # nothing left to do
    assert len(api.get(f"{OWNER}?active=false", headers=owner.headers).json()) == 1

    assert audit_actions(db_session, delivery_id) == [
        "delivery.scheduled",
        "delivery.started",
        "delivery.delivered",
        "delivery.photo_added",
        "delivery.handover_acknowledged",
        "delivery.return_requested",
        "delivery.returned",
        "delivery.photo_added",
    ]


def test_owner_can_record_a_return_the_renter_never_acknowledged(
    api, owner, booking, delivery_id, db_session
) -> None:
    deliver(api, owner, delivery_id)

    returned = post(api, owner, f"{OWNER}/{delivery_id}/return", HANDOVER)

    assert returned.json()["booking_status"] == "COMPLETED"
    assert returned.json()["handover"]["renter_acknowledged_at"] is None
    entry = db_session.scalar(select(AuditLog).where(AuditLog.action == "delivery.returned"))
    assert entry.changes["renter_acknowledged_handover"] is False
    assert entry.changes["distance_km"] == 0


def test_return_photos_close_after_two_hours(api, owner, delivery_id, db_session) -> None:
    deliver(api, owner, delivery_id)
    post(api, owner, f"{OWNER}/{delivery_id}/return", HANDOVER)
    record = db_session.scalar(select(HandoverRecord).where(HandoverRecord.kind == "RETURN"))
    record.recorded_at -= timedelta(hours=3)
    db_session.flush()

    assert photo(api, owner, delivery_id, "RETURN").status_code == 422


def test_photo_rules(api, owner, delivery_id) -> None:
    assert photo(api, owner, delivery_id).status_code == 422  # no handover record yet
    deliver(api, owner, delivery_id)
    assert photo(api, owner, delivery_id, data=b"%PDF-not a photo").status_code == 422
    for _ in range(10):
        assert photo(api, owner, delivery_id).status_code == 201
    assert photo(api, owner, delivery_id).status_code == 422  # at most 10


@pytest.mark.parametrize(
    "body",
    [
        {**HANDOVER, "odometer_km": -1},
        {**HANDOVER, "fuel_level": "SEVENTY_PERCENT"},
        {**HANDOVER, "recorded_by_id": str(uuid.uuid4())},
        {"fuel_level": "FULL"},
    ],
)
def test_handover_input_is_validated(api, owner, delivery_id, body) -> None:
    post(api, owner, f"{OWNER}/{delivery_id}/schedule")
    post(api, owner, f"{OWNER}/{delivery_id}/start")
    assert post(api, owner, f"{OWNER}/{delivery_id}/handover", body).status_code == 422


# --- exceptions and administrator resolution ---------------------------------------------


def test_delay_is_recorded_without_stopping_the_delivery(
    api, alice, owner, admin, booking, delivery_id
) -> None:
    post(api, owner, f"{OWNER}/{delivery_id}/schedule")
    delayed = post(
        api,
        owner,
        f"{OWNER}/{delivery_id}/exceptions",
        {"kind": "DELAY", "notes": "Traffic on the N2, 30 minutes late"},
    ).json()

    assert delayed["status"] == "SCHEDULED"
    renter_view = api.get(
        f"/api/v1/bookings/{booking['id']}/delivery", headers=alice.headers
    ).json()
    assert renter_view["exceptions"][0]["notes"] == "Traffic on the N2, 30 minutes late"

    [flagged] = api.get(f"{ADMIN}?open_exceptions=true", headers=admin.headers).json()
    exception_id = flagged["exceptions"][0]["id"]
    resolved = post(
        api, admin, f"{ADMIN}/{delivery_id}/exceptions/{exception_id}/resolve", {"note": "Noted"}
    )
    assert resolved.json()["has_open_exception"] is False
    again = post(
        api, admin, f"{ADMIN}/{delivery_id}/exceptions/{exception_id}/resolve", {"note": "Again"}
    )
    assert again.status_code == 409


def test_failed_delivery_is_rescheduled_by_an_administrator(
    api, owner, admin, booking, delivery_id, db_session
) -> None:
    base = f"{OWNER}/{delivery_id}"
    post(api, owner, f"{base}/schedule")
    post(api, owner, f"{base}/start")
    failed = post(
        api,
        owner,
        f"{base}/exceptions",
        {"kind": "RENTER_UNAVAILABLE", "notes": "Nobody at the address, phone off"},
    ).json()
    assert failed["status"] == "FAILED"
    assert booking_status(db_session, booking["id"]) == BookingStatus.IN_TRANSIT
    assert post(api, owner, f"{base}/handover", HANDOVER).status_code == 409
    exception_id = failed["exceptions"][0]["id"]
    resolve = f"{ADMIN}/{delivery_id}/exceptions/{exception_id}/resolve"
    assert post(api, admin, resolve, {"note": "Handled"}).status_code == 409  # must reschedule

    end = datetime.fromisoformat(booking["end_at"])
    beyond = post(
        api,
        admin,
        f"{ADMIN}/{delivery_id}/reschedule",
        {"scheduled_for": end.isoformat(), "note": "Try again"},
    )
    assert beyond.status_code == 422
    new_time = datetime.fromisoformat(booking["start_at"]) + timedelta(hours=4)
    rescheduled = post(
        api,
        admin,
        f"{ADMIN}/{delivery_id}/reschedule",
        {"scheduled_for": new_time.isoformat(), "note": "Renter confirmed by phone"},
    ).json()
    assert rescheduled["status"] == "SCHEDULED"
    assert rescheduled["has_open_exception"] is False
    assert rescheduled["exceptions"][0]["resolution"] == "Renter confirmed by phone"
    assert booking_status(db_session, booking["id"]) == BookingStatus.DELIVERY_SCHEDULED

    deliver_again = [
        post(api, owner, f"{base}/{step}", body)
        for step, body in (("start", None), ("handover", HANDOVER))
    ]
    assert [r.status_code for r in deliver_again] == [200, 200]


def test_administrator_can_cancel_a_failed_delivery_in_transit(
    api, owner, admin, booking, delivery_id, db_session
) -> None:
    post(api, owner, f"{OWNER}/{delivery_id}/schedule")
    post(api, owner, f"{OWNER}/{delivery_id}/start")
    post(
        api,
        owner,
        f"{OWNER}/{delivery_id}/exceptions",
        {"kind": "VEHICLE_PROBLEM", "notes": "Flat tyre, no spare"},
    )

    cancelled = post(
        api, admin, f"/api/v1/admin/bookings/{booking['id']}/cancel", {"reason": "Car broke down"}
    )

    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    view = api.get(f"{ADMIN}/{delivery_id}", headers=admin.headers).json()
    assert view["status"] == "CANCELLED"
    assert view["exceptions"][0]["resolution"] == "Booking cancelled: Car broke down"
    assert post(api, owner, f"{OWNER}/{delivery_id}/schedule").status_code == 409


def test_renter_can_cancel_a_scheduled_delivery_before_the_start(
    api, alice, owner, booking, delivery_id
) -> None:
    post(api, owner, f"{OWNER}/{delivery_id}/schedule")

    cancelled = post(api, alice, f"/api/v1/bookings/{booking['id']}/cancel")

    assert cancelled.json()["status"] == "CANCELLED"
    assert api.get(f"{OWNER}/{delivery_id}", headers=owner.headers).json()["status"] == "CANCELLED"


def test_renter_cannot_cancel_once_the_car_is_on_its_way(
    api, alice, owner, booking, delivery_id
) -> None:
    post(api, owner, f"{OWNER}/{delivery_id}/schedule")
    post(api, owner, f"{OWNER}/{delivery_id}/start")

    assert post(api, alice, f"/api/v1/bookings/{booking['id']}/cancel").status_code == 409


@pytest.mark.parametrize("kind", ["DELAY", "OTHER"])
def test_exceptions_only_on_active_deliveries(api, owner, delivery_id, kind) -> None:
    deliver(api, owner, delivery_id)
    late = post(
        api, owner, f"{OWNER}/{delivery_id}/exceptions", {"kind": kind, "notes": "Too late"}
    )
    assert late.status_code == 409


# --- reassignment -----------------------------------------------------------------------------


def test_reassignment_to_another_active_owner(
    api, alice, owner, admin, delivery_id, db_session
) -> None:
    url = f"{ADMIN}/{delivery_id}/assign"
    renter_id = db_session.scalar(select(User.id).where(User.email == alice.email))
    assert post(api, admin, url, {"user_id": str(renter_id)}).status_code == 422
    assert post(api, admin, url, {"user_id": str(uuid.uuid4())}).status_code == 422

    register(api, "driver-owner@example.com", "OWNER")
    helper = login(api, "driver-owner@example.com")
    helper_user = db_session.scalar(select(User).where(User.email == helper.email))
    helper_user.status = UserStatus.SUSPENDED
    helper_user.suspended_at = datetime.now(UTC)
    db_session.flush()
    assert post(api, admin, url, {"user_id": str(helper_user.id)}).status_code == 422
    helper_user.status = UserStatus.ACTIVE
    helper_user.suspended_at = None
    db_session.flush()

    moved = post(api, admin, url, {"user_id": str(helper_user.id)})

    assert moved.json()["assigned_to_id"] == str(helper_user.id)
    assert api.get(f"{OWNER}/{delivery_id}", headers=owner.headers).status_code == 404
    assert api.get(f"{OWNER}/{delivery_id}", headers=helper.headers).status_code == 200
    assert "delivery.reassigned" in audit_actions(db_session, delivery_id)
