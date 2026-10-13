"""Official pricing, price calculation, booking price preservation and vehicle suspension."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Booking, OwnerProfile, User, Vehicle, VehiclePrice
from app.models.enums import RoleName
from app.repositories.users import assign_role
from app.services.pricing import (
    PricingError,
    billable_days,
    calculate_quote,
    current_price,
    to_money,
)
from app.services.vehicles import publicly_listed_vehicles
from tests.api_fixtures import Account
from tests.conftest import requires_db
from tests.db.factories import booking_values, create_user
from tests.vehicles.helpers import BASE, create_vehicle, submitted_vehicle

ADMIN = "/api/v1/admin/vehicles"
T0 = datetime(2030, 3, 1, 9, 0, tzinfo=UTC)


def price_row(daily="650.00", delivery="150.00", deposit="2000.00") -> VehiclePrice:
    return VehiclePrice(
        id=uuid.uuid4(),
        daily_rate=Decimal(daily),
        delivery_fee=Decimal(delivery),
        deposit_amount=Decimal(deposit),
        currency="ZAR",
    )


# --- calculation (no database) ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("duration", "days"),
    [
        (timedelta(minutes=1), 1),
        (timedelta(hours=24), 1),
        (timedelta(hours=24, seconds=1), 2),
        (timedelta(days=3), 3),
        (timedelta(days=3, hours=1), 4),
        (timedelta(days=30), 30),
    ],
)
def test_each_started_24_hours_is_a_billable_day(duration: timedelta, days: int) -> None:
    assert billable_days(T0, T0 + duration) == days


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (T0, T0),
        (T0, T0 - timedelta(hours=1)),
        (T0.replace(tzinfo=None), T0.replace(tzinfo=None) + timedelta(days=1)),
    ],
    ids=["zero-length", "negative", "naive"],
)
def test_invalid_periods_rejected(start: datetime, end: datetime) -> None:
    with pytest.raises(PricingError):
        billable_days(start, end)


def test_quote_breakdown_is_exact() -> None:
    quote = calculate_quote(price_row(), T0, T0 + timedelta(days=3))

    assert quote.rental_days == 3
    assert quote.daily_rate == Decimal("650.00")
    assert quote.rental_amount == Decimal("1950.00")
    assert quote.delivery_fee == Decimal("150.00")
    assert quote.deposit_amount == Decimal("2000.00")
    assert quote.total_amount == Decimal("2100.00")  # deposit is held separately
    assert quote.currency == "ZAR"
    assert all(
        isinstance(v, Decimal)
        for v in (quote.daily_rate, quote.rental_amount, quote.total_amount, quote.deposit_amount)
    )


def test_amounts_never_drift_like_floats() -> None:
    quote = calculate_quote(price_row(daily="0.10", delivery="0.20"), T0, T0 + timedelta(days=3))

    assert quote.rental_amount == Decimal("0.30")  # 0.1 * 3 is 0.30000000000000004 as a float
    assert quote.total_amount == Decimal("0.50")


@pytest.mark.parametrize(
    ("raw", "rounded"),
    [("2.675", "2.68"), ("0.005", "0.01"), ("0.004", "0.00"), ("1999.995", "2000.00")],
)
def test_rounding_is_half_up_to_cents(raw: str, rounded: str) -> None:
    assert to_money(Decimal(raw)) == Decimal(rounded)


# --- API ----------------------------------------------------------------------------------------


def approved_vehicle(api: TestClient, owner: Account, admin: Account, outbox) -> dict:
    vehicle = submitted_vehicle(api, owner.headers, outbox)
    assert api.post(f"{ADMIN}/{vehicle['id']}/approve", headers=admin.headers).status_code == 200
    return vehicle


def set_price(api: TestClient, headers: dict, vehicle_id: str, **body):
    payload = {
        "daily_rate": "650.00",
        "delivery_fee": "150.00",
        "deposit_amount": "2000.00",
        "change_reason": "Launch",
    }
    payload.update(body)
    return api.post(f"{ADMIN}/{vehicle_id}/prices", headers=headers, json=payload)


@requires_db
def test_admin_sets_official_price(api: TestClient, owner: Account, admin: Account, outbox) -> None:
    vehicle = approved_vehicle(api, owner, admin, outbox)

    response = set_price(api, admin.headers, vehicle["id"])

    assert response.status_code == 201
    price = response.json()
    assert (price["daily_rate"], price["delivery_fee"], price["deposit_amount"]) == (
        "650.00",
        "150.00",
        "2000.00",
    )
    assert price["currency"] == "ZAR" and price["is_current"] is True
    mine = api.get(f"{BASE}/{vehicle['id']}", headers=owner.headers).json()
    assert mine["current_price"]["daily_rate"] == "650.00"  # owners can see, not set


@requires_db
@pytest.mark.parametrize("who", ["owner", "renter"])
def test_only_admins_can_set_or_view_price_history(
    api: TestClient,
    request: pytest.FixtureRequest,
    owner: Account,
    admin: Account,
    outbox,
    who: str,
) -> None:
    vehicle = approved_vehicle(api, owner, admin, outbox)
    account: Account = request.getfixturevalue(who)

    assert set_price(api, account.headers, vehicle["id"]).status_code == 403
    assert api.get(f"{ADMIN}/{vehicle['id']}/prices", headers=account.headers).status_code == 403
    assert api.get(f"{BASE}/{vehicle['id']}", headers=owner.headers).json()["current_price"] is None


@requires_db
@pytest.mark.parametrize(
    "fields",
    [{"daily_rate": "1.00"}, {"current_price": {"daily_rate": "1.00"}}, {"deposit_amount": "0"}],
    ids=["daily_rate", "current_price", "deposit"],
)
def test_owner_cannot_smuggle_prices_through_vehicle_endpoints(
    api: TestClient, owner: Account, fields: dict
) -> None:
    vehicle = create_vehicle(api, owner.headers)

    assert (
        api.patch(f"{BASE}/{vehicle['id']}", headers=owner.headers, json=fields).status_code == 422
    )


@requires_db
@pytest.mark.parametrize(
    "body",
    [
        {"daily_rate": "650.555"},
        {"daily_rate": "0"},
        {"daily_rate": "-100.00"},
        {"daily_rate": "abc"},
        {"daily_rate": "100000.01"},
        {"delivery_fee": "-1"},
        {"change_reason": ""},
        {"effective_from": (datetime.now(UTC) - timedelta(days=1)).isoformat()},
        {"effective_from": "2031-01-01T00:00:00"},
        {"currency": "USD"},
    ],
    ids=[
        "three-decimals",
        "zero",
        "negative",
        "not-a-number",
        "too-large",
        "negative-fee",
        "no-reason",
        "backdated",
        "naive-datetime",
        "currency",
    ],
)
def test_invalid_prices_rejected(
    api: TestClient, owner: Account, admin: Account, outbox, body: dict
) -> None:
    vehicle = approved_vehicle(api, owner, admin, outbox)

    response = set_price(api, admin.headers, vehicle["id"], **body)

    assert response.status_code == 422, response.text
    assert api.get(f"{ADMIN}/{vehicle['id']}/prices", headers=admin.headers).json() == []


@requires_db
def test_price_changes_are_audited_with_old_and_new_values(
    api: TestClient, owner: Account, admin: Account, outbox, db_session: Session
) -> None:
    vehicle = approved_vehicle(api, owner, admin, outbox)
    set_price(api, admin.headers, vehicle["id"])
    set_price(api, admin.headers, vehicle["id"], daily_rate="720.00", change_reason="Peak season")

    entries = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "vehicle.price_set").order_by(AuditLog.id)
    ).all()
    admin_id = db_session.scalar(select(User.id).where(User.email == admin.email))
    assert [e.actor_user_id for e in entries] == [admin_id, admin_id]
    assert entries[0].changes["old"] is None
    assert entries[1].changes["old"]["daily_rate"] == "650.00"
    assert entries[1].changes["new"]["daily_rate"] == "720.00"
    assert entries[1].changes["reason"] == "Peak season"
    history = api.get(f"{ADMIN}/{vehicle['id']}/prices", headers=admin.headers).json()
    assert [(p["daily_rate"], p["is_current"]) for p in history] == [
        ("720.00", True),
        ("650.00", False),
    ]
    assert all(p["created_by_id"] == str(admin_id) for p in history)


@requires_db
def test_scheduled_price_does_not_apply_early(
    api: TestClient, owner: Account, admin: Account, outbox, db_session: Session
) -> None:
    vehicle = approved_vehicle(api, owner, admin, outbox)
    set_price(api, admin.headers, vehicle["id"])
    later = datetime.now(UTC) + timedelta(days=7)

    scheduled = set_price(
        api, admin.headers, vehicle["id"], daily_rate="800.00", effective_from=later.isoformat()
    )

    assert scheduled.status_code == 201 and scheduled.json()["is_current"] is False
    assert current_price(db_session, vehicle["id"]).daily_rate == Decimal("650.00")
    assert current_price(
        db_session, vehicle["id"], at=later + timedelta(seconds=1)
    ).daily_rate == Decimal("800.00")
    duplicate = set_price(api, admin.headers, vehicle["id"], effective_from=later.isoformat())
    assert duplicate.status_code == 422


@requires_db
def test_existing_bookings_keep_their_agreed_price(
    api: TestClient, owner: Account, admin: Account, outbox, db_session: Session
) -> None:
    vehicle = approved_vehicle(api, owner, admin, outbox)
    set_price(api, admin.headers, vehicle["id"])
    agreed = current_price(db_session, vehicle["id"])
    booking = Booking(**booking_values(create_user(db_session), agreed, start=T0, days=3))
    db_session.add(booking)
    db_session.flush()

    set_price(api, admin.headers, vehicle["id"], daily_rate="999.00", delivery_fee="300.00")

    db_session.expire_all()
    stored = db_session.get(Booking, booking.id)
    assert (stored.daily_rate, stored.rental_amount, stored.total_amount) == (
        Decimal("650.00"),
        Decimal("1950.00"),
        Decimal("2100.00"),
    )
    assert db_session.get(VehiclePrice, agreed.id).daily_rate == Decimal("650.00")
    new_quote = api.get(
        f"{ADMIN}/{vehicle['id']}/quote",
        headers=admin.headers,
        params={"start_at": T0.isoformat(), "end_at": (T0 + timedelta(days=3)).isoformat()},
    ).json()
    assert (new_quote["rental_amount"], new_quote["total_amount"]) == ("2997.00", "3297.00")


@requires_db
def test_quote_requires_a_price(api: TestClient, owner: Account, admin: Account, outbox) -> None:
    vehicle = approved_vehicle(api, owner, admin, outbox)
    params = {"start_at": T0.isoformat(), "end_at": (T0 + timedelta(days=3, hours=1)).isoformat()}

    assert (
        api.get(f"{ADMIN}/{vehicle['id']}/quote", headers=admin.headers, params=params).status_code
        == 409
    )
    set_price(api, admin.headers, vehicle["id"])
    quote = api.get(f"{ADMIN}/{vehicle['id']}/quote", headers=admin.headers, params=params).json()
    assert (quote["rental_days"], quote["rental_amount"], quote["total_amount"]) == (
        4,
        "2600.00",
        "2750.00",
    )


@requires_db
def test_admin_cannot_price_own_vehicle(
    api: TestClient, admin: Account, db_session: Session
) -> None:
    admin_user = db_session.scalar(select(User).where(User.email == admin.email))
    assign_role(db_session, admin_user, RoleName.OWNER)
    db_session.add(OwnerProfile(user_id=admin_user.id))
    db_session.flush()
    vehicle = create_vehicle(api, admin.headers)

    assert set_price(api, admin.headers, vehicle["id"]).status_code == 403


# --- suspension ----------------------------------------------------------------------------------


def listed(session: Session) -> set[str]:
    session.expire_all()
    return {str(v.id) for v in session.scalars(publicly_listed_vehicles())}


@requires_db
def test_suspend_and_reinstate(
    api: TestClient, owner: Account, admin: Account, outbox, db_session: Session
) -> None:
    vehicle = approved_vehicle(api, owner, admin, outbox)
    set_price(api, admin.headers, vehicle["id"])
    assert listed(db_session) == {vehicle["id"]}

    assert (
        api.post(f"{ADMIN}/{vehicle['id']}/suspend", headers=admin.headers, json={}).status_code
        == 422
    )
    suspended = api.post(
        f"{ADMIN}/{vehicle['id']}/suspend",
        headers=admin.headers,
        json={"reason": "Insurance query"},
    ).json()

    assert suspended["status"] == "SUSPENDED"
    assert listed(db_session) == set()
    mine = api.get(f"{BASE}/{vehicle['id']}", headers=owner.headers).json()
    assert mine["suspension_reason"] == "Insurance query"
    assert (
        api.patch(
            f"{BASE}/{vehicle['id']}", headers=owner.headers, json={"colour": "Red"}
        ).status_code
        == 409
    )
    assert (
        api.put(
            f"{BASE}/{vehicle['id']}/listing", headers=owner.headers, json={"available": True}
        ).status_code
        == 409
    )
    assert (
        api.post(
            f"{ADMIN}/{vehicle['id']}/suspend", headers=admin.headers, json={"reason": "Again"}
        ).status_code
        == 409
    )

    reinstated = api.post(f"{ADMIN}/{vehicle['id']}/reinstate", headers=admin.headers).json()
    assert reinstated["status"] == "APPROVED" and reinstated["suspension_reason"] is None
    assert listed(db_session) == {vehicle["id"]}
    assert api.post(f"{ADMIN}/{vehicle['id']}/reinstate", headers=admin.headers).status_code == 409
    actions = db_session.scalars(
        select(AuditLog.action).where(AuditLog.entity_id == vehicle["id"]).order_by(AuditLog.id)
    ).all()
    assert actions[-2:] == ["vehicle.suspended", "vehicle.reinstated"]


@requires_db
def test_suspension_rules(
    api: TestClient, owner: Account, renter: Account, admin: Account, outbox
) -> None:
    draft = create_vehicle(api, owner.headers)
    assert (
        api.post(
            f"{ADMIN}/{draft['id']}/suspend", headers=admin.headers, json={"reason": "x" * 5}
        ).status_code
        == 409
    )

    vehicle = approved_vehicle(api, owner, admin, outbox)
    for account in (owner, renter):
        response = api.post(
            f"{ADMIN}/{vehicle['id']}/suspend", headers=account.headers, json={"reason": "Nope"}
        )
        assert response.status_code == 403
    assert (
        api.post(
            f"{ADMIN}/{uuid.uuid4()}/suspend", headers=admin.headers, json={"reason": "Ghost"}
        ).status_code
        == 404
    )


@requires_db
def test_suspending_unapproved_vehicle_reinstates_to_draft(
    api: TestClient, owner: Account, admin: Account, outbox, db_session: Session
) -> None:
    pending = submitted_vehicle(api, owner.headers, outbox)

    api.post(
        f"{ADMIN}/{pending['id']}/suspend", headers=admin.headers, json={"reason": "Fraud check"}
    )
    reinstated = api.post(f"{ADMIN}/{pending['id']}/reinstate", headers=admin.headers).json()

    assert reinstated["status"] == "DRAFT"
    assert db_session.get(Vehicle, pending["id"]).approved_at is None


@requires_db
def test_vehicle_with_only_a_future_price_is_not_listed_yet(
    api: TestClient, owner: Account, admin: Account, outbox, db_session: Session
) -> None:
    vehicle = approved_vehicle(api, owner, admin, outbox)
    next_week = datetime.now(UTC) + timedelta(days=7)

    set_price(api, admin.headers, vehicle["id"], effective_from=next_week.isoformat())

    assert listed(db_session) == set()
    assert api.get(f"{BASE}/{vehicle['id']}", headers=owner.headers).json()["current_price"] is None
    set_price(api, admin.headers, vehicle["id"])  # a price effective now
    assert listed(db_session) == {vehicle["id"]}
