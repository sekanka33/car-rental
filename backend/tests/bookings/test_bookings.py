import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AuditLog, Booking, OwnerProfile, User, VehicleAvailabilityBlock
from app.models.enums import BookingStatus, RoleName
from app.repositories.users import assign_role
from app.services.bookings import (
    HoldExpiredError,
    InvalidTransitionError,
    confirm_booking,
    expire_stale_holds,
)
from tests.api_fixtures import Account, register
from tests.bookings.helpers import START, URL, book, eligible_renter
from tests.conftest import requires_db
from tests.db.factories import create_user
from tests.marketplace.factories import add_price, listed_vehicle

pytestmark = requires_db


@pytest.fixture
def vehicle(db_session: Session, storage):
    return listed_vehicle(db_session, storage, daily_rate="650.00")


@pytest.fixture
def alice(api: TestClient, db_session: Session) -> Account:
    return eligible_renter(api, db_session, "alice@example.com")


@pytest.fixture
def bob(api: TestClient, db_session: Session) -> Account:
    return eligible_renter(api, db_session, "bob@example.com")


def expire(session: Session, booking_id: str) -> None:
    session.execute(
        update(Booking)
        .where(Booking.id == booking_id)
        .values(hold_expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )


# --- creation ------------------------------------------------------------------------------------


def test_eligible_renter_creates_a_pending_booking(
    api: TestClient, alice: Account, vehicle, db_session: Session
) -> None:
    response = book(api, alice, vehicle.id, days=3)

    assert response.status_code == 201, response.text
    booking = response.json()
    assert booking["status"] == "PENDING_PAYMENT"
    assert re.fullmatch(r"BK[A-Z2-9]{8}", booking["reference"])
    assert booking["price"] == {
        "daily_rate": "650.00",
        "rental_days": 3,
        "rental_amount": "1950.00",
        "delivery_fee": "150.00",
        "deposit_amount": "2000.00",
        "total_amount": "2100.00",
        "currency": "ZAR",
    }
    hold = datetime.fromisoformat(booking["hold_expires_at"]) - datetime.now(UTC)
    assert timedelta(minutes=14) < hold <= timedelta(minutes=15)
    assert booking["vehicle"]["make"] == vehicle.make
    stored = db_session.get(Booking, booking["id"])
    assert stored.vehicle_price_id == vehicle.prices[0].id
    audit = db_session.scalar(select(AuditLog).where(AuditLog.entity_id == booking["id"]))
    assert audit.action == "booking.created"


@pytest.mark.parametrize(
    "extra",
    [{"total_amount": "1.00"}, {"daily_rate": "1.00"}, {"status": "CONFIRMED"}, {"renter_id": "x"}],
    ids=["total", "rate", "status", "renter"],
)
def test_client_cannot_set_price_status_or_renter(
    api: TestClient, alice: Account, vehicle, extra: dict
) -> None:
    assert book(api, alice, vehicle.id, **extra).status_code == 422


def test_booking_uses_the_current_official_price(
    api: TestClient, alice: Account, vehicle, db_session: Session
) -> None:
    add_price(
        db_session, vehicle, "700.00", effective_from=datetime.now(UTC) - timedelta(seconds=1)
    )
    add_price(db_session, vehicle, "999.00", effective_from=datetime.now(UTC) + timedelta(days=1))

    price = book(api, alice, vehicle.id, days=2).json()["price"]

    assert (price["daily_rate"], price["total_amount"]) == ("700.00", "1550.00")


def test_ineligible_renter_is_told_why(api: TestClient, vehicle) -> None:
    register(api, "newbie@example.com", "RENTER")
    from tests.api_fixtures import login

    newbie = login(api, "newbie@example.com")

    response = book(api, newbie, vehicle.id)

    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "renter_not_eligible"
    assert [d["reason"] for d in error["details"]] == [
        "EMAIL_NOT_VERIFIED",
        "DATE_OF_BIRTH_MISSING",
        "ID_NOT_APPROVED",
        "LICENCE_NOT_APPROVED",
    ]


def test_licence_must_outlast_the_rental(api: TestClient, db_session: Session, vehicle) -> None:
    short = eligible_renter(api, db_session, "short@example.com", licence_days=8)

    response = book(api, short, vehicle.id, days=5)

    assert response.status_code == 403
    assert response.json()["error"]["details"] == [{"reason": "LICENCE_EXPIRES_BEFORE_RENTAL_ENDS"}]


def test_only_renters_can_book(api: TestClient, owner: Account, vehicle) -> None:
    assert book(api, owner, vehicle.id).status_code == 403
    assert api.post(URL, json={}).status_code == 401


def test_unlisted_or_unknown_vehicle_is_404(
    api: TestClient, alice: Account, db_session: Session, storage
) -> None:
    hidden = listed_vehicle(db_session, storage, daily_rate=None)

    assert book(api, alice, hidden.id).status_code == 404
    assert book(api, alice, "00000000-0000-0000-0000-000000000000").status_code == 404


def test_cannot_book_own_vehicle(
    api: TestClient, alice: Account, vehicle, db_session: Session
) -> None:
    user = db_session.scalar(select(User).where(User.email == alice.email))
    assign_role(db_session, user, RoleName.OWNER)
    owner_profile = OwnerProfile(user_id=user.id)
    db_session.add(owner_profile)
    db_session.flush()
    vehicle.owner_id = owner_profile.id
    db_session.flush()
    db_session.expire_all()

    assert book(api, alice, vehicle.id).status_code == 403


@pytest.mark.parametrize(
    ("start", "days"),
    [
        (datetime.now(UTC) + timedelta(minutes=30), 1),  # inside the 2-hour lead time
        (datetime.now(UTC) - timedelta(days=1), 2),  # in the past
        (START, 31),  # longer than 30 days
        (START, 0),  # zero length
    ],
    ids=["lead-time", "past", "too-long", "zero-length"],
)
def test_invalid_periods(
    api: TestClient, alice: Account, vehicle, start: datetime, days: int
) -> None:
    assert book(api, alice, vehicle.id, start=start, days=days).status_code == 422


def test_naive_datetimes_rejected(api: TestClient, alice: Account, vehicle) -> None:
    assert book(api, alice, vehicle.id, start=START.replace(tzinfo=None)).status_code == 422


# --- availability -------------------------------------------------------------------------------


def test_overlapping_booking_is_rejected_back_to_back_allowed(
    api: TestClient, alice: Account, bob: Account, vehicle
) -> None:
    assert book(api, alice, vehicle.id, start=START, days=3).status_code == 201

    clash = book(api, bob, vehicle.id, start=START + timedelta(days=2), days=2)
    assert clash.status_code == 409
    assert clash.json()["error"]["code"] == "vehicle_unavailable"
    assert book(api, bob, vehicle.id, start=START + timedelta(days=3), days=2).status_code == 201


def test_owner_blocked_dates_are_unavailable(
    api: TestClient, alice: Account, vehicle, db_session: Session
) -> None:
    db_session.add(
        VehicleAvailabilityBlock(
            vehicle_id=vehicle.id,
            start_at=START + timedelta(days=1),
            end_at=START + timedelta(days=2),
            created_by_id=create_user(db_session).id,
        )
    )
    db_session.flush()

    assert book(api, alice, vehicle.id, start=START, days=3).status_code == 409


def test_expired_hold_releases_the_dates(
    api: TestClient, alice: Account, bob: Account, vehicle, db_session: Session
) -> None:
    first = book(api, alice, vehicle.id).json()
    expire(db_session, first["id"])

    second = book(api, bob, vehicle.id)

    assert second.status_code == 201
    assert api.get(f"{URL}/{first['id']}", headers=alice.headers).json()["status"] == "EXPIRED"


def test_expired_hold_not_shown_as_unavailable_in_marketplace(
    api: TestClient, alice: Account, vehicle, db_session: Session
) -> None:
    first = book(api, alice, vehicle.id).json()
    period = {"start_at": START.isoformat(), "end_at": (START + timedelta(days=3)).isoformat()}
    assert (
        api.get(f"/api/v1/vehicles/{vehicle.id}/quote", params=period).json()["available"] is False
    )

    expire(db_session, first["id"])

    assert (
        api.get(f"/api/v1/vehicles/{vehicle.id}/quote", params=period).json()["available"] is True
    )
    assert api.get(f"/api/v1/vehicles/{vehicle.id}/availability").json()["unavailable"] == []


def test_pending_booking_limit(
    api: TestClient, alice: Account, db_session: Session, storage
) -> None:
    cars = [listed_vehicle(db_session, storage) for _ in range(3)]

    assert book(api, alice, cars[0].id).status_code == 201
    assert book(api, alice, cars[1].id).status_code == 201
    third = book(api, alice, cars[2].id)
    assert third.status_code == 409
    assert third.json()["error"]["code"] == "too_many_pending_bookings"


# --- history ---------------------------------------------------------------------------


def test_history_is_private(
    api: TestClient, alice: Account, bob: Account, admin: Account, vehicle
) -> None:
    first = book(api, alice, vehicle.id, start=START).json()
    second = book(api, alice, vehicle.id, start=START + timedelta(days=10)).json()

    mine = api.get(URL, headers=alice.headers).json()
    assert [b["id"] for b in mine] == [second["id"], first["id"]]  # newest first
    assert api.get(URL, headers=bob.headers).json() == []
    assert api.get(f"{URL}/{first['id']}", headers=bob.headers).status_code == 404
    assert api.get(URL, headers=alice.headers, params={"status": "CANCELLED"}).json() == []

    everything = api.get("/api/v1/admin/bookings", headers=admin.headers).json()
    assert {b["id"] for b in everything} == {first["id"], second["id"]}
    assert everything[0]["renter"]["email"] == "alice@example.com"
    assert api.get("/api/v1/admin/bookings", headers=alice.headers).status_code == 403


# --- cancellation and confirmation ---------------------------------------------------------


def test_renter_cancels_pending_booking_and_dates_are_released(
    api: TestClient, alice: Account, bob: Account, vehicle, db_session: Session
) -> None:
    booking = book(api, alice, vehicle.id).json()

    response = api.post(
        f"{URL}/{booking['id']}/cancel", headers=alice.headers, json={"reason": "Plans changed"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CANCELLED" and body["cancellation_reason"] == "Plans changed"
    assert body["cancelled_at"] is not None and body["hold_expires_at"] is None
    assert (
        api.post(f"{URL}/{booking['id']}/cancel", headers=alice.headers, json={}).status_code == 409
    )
    assert (
        api.post(f"{URL}/{booking['id']}/cancel", headers=bob.headers, json={}).status_code == 404
    )
    assert book(api, bob, vehicle.id).status_code == 201
    actions = db_session.scalars(
        select(AuditLog.action).where(AuditLog.entity_id == booking["id"]).order_by(AuditLog.id)
    ).all()
    assert actions == ["booking.created", "booking.cancelled"]


def test_expired_booking_cannot_be_cancelled(
    api: TestClient, alice: Account, vehicle, db_session: Session
) -> None:
    booking = book(api, alice, vehicle.id).json()
    expire(db_session, booking["id"])

    response = api.post(f"{URL}/{booking['id']}/cancel", headers=alice.headers, json={})

    assert response.status_code == 409
    assert db_session.get(Booking, booking["id"]).status == BookingStatus.EXPIRED


def test_confirmed_booking_cancellation_rules(
    api: TestClient, alice: Account, admin: Account, vehicle, db_session: Session
) -> None:
    booking = book(api, alice, vehicle.id).json()
    confirm_booking(db_session, booking["id"])
    assert api.get(f"{URL}/{booking['id']}", headers=alice.headers).json()["status"] == "CONFIRMED"

    # Once the rental has started the renter can no longer cancel; an administrator can.
    db_session.execute(
        update(Booking)
        .where(Booking.id == booking["id"])
        .values(
            start_at=datetime.now(UTC) - timedelta(hours=1),
            end_at=datetime.now(UTC) + timedelta(days=2),
        )
    )
    assert (
        api.post(f"{URL}/{booking['id']}/cancel", headers=alice.headers, json={}).status_code == 409
    )
    admin_url = f"/api/v1/admin/bookings/{booking['id']}/cancel"
    assert api.post(admin_url, headers=admin.headers, json={}).status_code == 422
    assert api.post(admin_url, headers=alice.headers, json={"reason": "x" * 5}).status_code == 403
    cancelled = api.post(
        admin_url, headers=admin.headers, json={"reason": "Vehicle damaged"}
    ).json()
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["cancelled_by_id"] == str(
        db_session.scalar(select(User.id).where(User.email == admin.email))
    )


def test_confirm_booking_rules(
    api: TestClient, alice: Account, vehicle, db_session: Session
) -> None:
    booking = book(api, alice, vehicle.id).json()

    confirmed = confirm_booking(db_session, booking["id"])
    assert confirmed.status == BookingStatus.CONFIRMED and confirmed.confirmed_at is not None
    with pytest.raises(InvalidTransitionError):
        confirm_booking(db_session, booking["id"])

    late = book(api, alice, vehicle.id, start=START + timedelta(days=10)).json()
    expire(db_session, late["id"])
    with pytest.raises(HoldExpiredError):
        confirm_booking(db_session, late["id"])


def test_expire_stale_holds_counts(
    api: TestClient, alice: Account, vehicle, db_session: Session
) -> None:
    first = book(api, alice, vehicle.id).json()
    book(api, alice, vehicle.id, start=START + timedelta(days=10))
    expire(db_session, first["id"])

    assert expire_stale_holds(db_session) == 1
    assert expire_stale_holds(db_session) == 0


def test_booking_amounts_are_exact_decimals(
    api: TestClient, alice: Account, db_session: Session, storage
) -> None:
    car = listed_vehicle(db_session, storage, daily_rate="333.33")

    booking = book(api, alice, car.id, days=3).json()

    assert booking["price"]["rental_amount"] == "999.99"
    assert db_session.get(Booking, booking["id"]).total_amount == Decimal("1149.99")
