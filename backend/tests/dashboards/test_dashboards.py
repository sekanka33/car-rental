"""Owner bookings, earnings and summary; renter payment history (FR-34)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Booking,
    Delivery,
    OwnerProfile,
    Payment,
    Refund,
    User,
    Vehicle,
    VehicleDocument,
    VehiclePrice,
)
from app.models.enums import (
    BookingStatus,
    DeliveryStatus,
    PaymentStatus,
    RefundStatus,
    VehicleDocumentType,
    VehicleStatus,
)
from app.services.verification import today_in_south_africa
from tests.api_fixtures import Account, login, register
from tests.conftest import requires_db
from tests.db.factories import create_booking, create_user
from tests.marketplace.factories import listed_vehicle

pytestmark = requires_db
S = BookingStatus
OWNER = "/api/v1/owners/me"
NOW = datetime.now(UTC)


def user_of(session: Session, account: Account) -> User:
    return session.scalar(select(User).where(User.email == account.email))


def car_of(session: Session, storage, account: Account, **fields) -> Vehicle:
    """An approved, listed car belonging to the logged-in owner."""
    vehicle = listed_vehicle(session, storage, **fields)
    vehicle.owner_id = session.scalar(
        select(OwnerProfile.id).where(OwnerProfile.user_id == user_of(session, account).id)
    )
    session.flush()
    return vehicle


def booking_of(session, vehicle, status=S.CONFIRMED, start=NOW + timedelta(days=5), **kw):
    price = session.scalar(select(VehiclePrice).where(VehiclePrice.vehicle_id == vehicle.id))
    renter = kw.pop("renter", None) or create_user(session, full_name="Naledi Dlamini")
    return create_booking(session, price, status=status, start=start, renter=renter, **kw)


def paid(session, booking: Booking, amount=None, *, refunds=(), ref=None) -> Payment:
    payment = Payment(
        booking_id=booking.id,
        provider="paystack",
        provider_reference=ref or f"ref-{booking.reference}",
        amount=amount or booking.total_amount,
        status=PaymentStatus.SUCCEEDED,
        paid_at=NOW,
    )
    session.add(payment)
    session.flush()
    for value, state in refunds:
        session.add(
            Refund(
                payment_id=payment.id,
                provider="paystack",
                amount=Decimal(value),
                status=state,
                reason="Cancelled",
                processed_at=NOW if state == RefundStatus.PROCESSED else None,
            )
        )
    if refunds:
        payment.status = PaymentStatus.PARTIALLY_REFUNDED
    session.flush()
    return payment


@pytest.fixture
def other_owner(api) -> Account:
    register(api, "other-owner@example.com", "OWNER")
    return login(api, "other-owner@example.com")


# --- owner bookings ---------------------------------------------------------------------------


def test_owner_sees_only_paid_bookings_of_own_cars(
    api, owner, other_owner, db_session, storage
) -> None:
    mine = car_of(db_session, storage, owner)
    theirs = car_of(db_session, storage, other_owner)
    confirmed = booking_of(db_session, mine)
    booking_of(db_session, mine, S.PENDING_PAYMENT, start=NOW + timedelta(days=20))
    booking_of(db_session, mine, S.EXPIRED, start=NOW + timedelta(days=30))
    booking_of(db_session, theirs)

    rows = api.get(f"{OWNER}/bookings?scope=all", headers=owner.headers).json()

    assert [r["id"] for r in rows] == [str(confirmed.id)]
    row = rows[0]
    assert row["renter_first_name"] == "Naledi"
    assert row["vehicle"]["registration_number"] == mine.registration_number
    assert "email" not in str(row) and "phone" not in str(row)  # contact details stay private


def test_owner_booking_scopes(api, owner, db_session, storage) -> None:
    car = car_of(db_session, storage, owner)
    later = booking_of(db_session, car, S.DELIVERY_SCHEDULED, start=NOW + timedelta(days=9))
    sooner = booking_of(db_session, car, S.CONFIRMED, start=NOW + timedelta(days=2))
    rented = booking_of(db_session, car, S.ACTIVE_RENTAL, start=NOW - timedelta(days=1))
    done = booking_of(db_session, car, S.COMPLETED, start=NOW - timedelta(days=20))
    cancelled = booking_of(db_session, car, S.CANCELLED, start=NOW - timedelta(days=10))

    def ids(scope):
        return [
            r["id"]
            for r in api.get(f"{OWNER}/bookings?scope={scope}", headers=owner.headers).json()
        ]

    assert ids("upcoming") == [str(sooner.id), str(later.id)]  # soonest first
    assert ids("active") == [str(rented.id)]
    assert ids("past") == [str(cancelled.id), str(done.id)]  # newest first
    assert api.get(f"{OWNER}/bookings?scope=nonsense", headers=owner.headers).status_code == 422


def test_owner_booking_links_its_delivery(api, owner, db_session, storage) -> None:
    car = car_of(db_session, storage, owner)
    booking = booking_of(db_session, car)
    delivery = Delivery(
        booking_id=booking.id,
        assigned_to_id=user_of(db_session, owner).id,
        status=DeliveryStatus.PENDING_SCHEDULE,
        dropoff_address="12 Long Street, Cape Town",
    )
    db_session.add(delivery)
    db_session.flush()

    row = api.get(f"{OWNER}/bookings", headers=owner.headers).json()[0]

    assert (row["delivery_id"], row["delivery_status"]) == (str(delivery.id), "PENDING_SCHEDULE")


@pytest.mark.parametrize("path", ["bookings", "earnings", "dashboard"])
def test_owner_views_need_an_owner(api, renter, path) -> None:
    assert api.get(f"{OWNER}/{path}").status_code == 401
    assert api.get(f"{OWNER}/{path}", headers=renter.headers).status_code == 403


# --- earnings ---------------------------------------------------------------------------------


def test_earnings_are_gross_collected_minus_refunds_by_rental_month(
    api, owner, other_owner, db_session, storage
) -> None:
    year = today_in_south_africa().year + 1
    car = car_of(db_session, storage, owner)
    # 31 Jan 23:30 UTC is already 1 Feb in South Africa: counts in February.
    feb = booking_of(db_session, car, S.COMPLETED, start=datetime(year, 1, 31, 23, 30, tzinfo=UTC))
    paid(db_session, feb, Decimal("2100.00"))
    march = booking_of(db_session, car, S.CANCELLED, start=datetime(year, 3, 10, 8, tzinfo=UTC))
    paid(
        db_session,
        march,
        Decimal("1500.00"),
        refunds=[
            ("1000.00", RefundStatus.PROCESSED),
            ("200.00", RefundStatus.PENDING),
            ("300.00", RefundStatus.FAILED),
        ],
    )
    unpaid = booking_of(db_session, car, S.CONFIRMED, start=datetime(year, 3, 20, tzinfo=UTC))
    db_session.add(
        Payment(
            booking_id=unpaid.id,
            provider="paystack",
            provider_reference="never-paid",
            amount=Decimal("900.00"),
            status=PaymentStatus.FAILED,
        )
    )
    other_year = booking_of(
        db_session, car, S.COMPLETED, start=datetime(year + 1, 1, 5, tzinfo=UTC)
    )
    paid(db_session, other_year)
    paid(
        db_session,
        booking_of(
            db_session,
            car_of(db_session, storage, other_owner),
            start=datetime(year, 2, 3, tzinfo=UTC),
        ),
    )

    body = api.get(f"{OWNER}/earnings?year={year}", headers=owner.headers).json()

    assert (body["collected"], body["refunded"], body["net"]) == ("3600.00", "1200.00", "2400.00")
    assert body["months"] == [
        {
            "month": f"{year}-02",
            "bookings": 1,
            "collected": "2100.00",
            "refunded": "0.00",
            "net": "2100.00",
        },
        {
            "month": f"{year}-03",
            "bookings": 1,
            "collected": "1500.00",
            "refunded": "1200.00",
            "net": "300.00",
        },
    ]
    assert [b["reference"] for b in body["bookings"]] == [march.reference, feb.reference]
    assert "commission" in body["basis"]


def test_earnings_default_to_this_year_and_validate(api, owner) -> None:
    body = api.get(f"{OWNER}/earnings", headers=owner.headers).json()
    assert body["year"] == today_in_south_africa().year and body["bookings"] == []
    assert api.get(f"{OWNER}/earnings?year=1999", headers=owner.headers).status_code == 422


# --- summary ----------------------------------------------------------------------------------


def test_owner_dashboard_summary(api, owner, db_session, storage) -> None:
    me = user_of(db_session, owner)
    car = car_of(db_session, storage, owner)
    car_of(db_session, storage, owner, status=VehicleStatus.PENDING_APPROVAL)
    soon = booking_of(db_session, car, S.CONFIRMED, start=NOW + timedelta(days=1))
    paid(db_session, soon)
    booking_of(db_session, car, S.DELIVERY_SCHEDULED, start=NOW + timedelta(days=10))
    rented = booking_of(db_session, car, S.ACTIVE_RENTAL, start=NOW - timedelta(days=2))
    # Reassigned by an administrator to someone else: not this owner's job any more.
    handed_off = booking_of(db_session, car, S.CONFIRMED, start=NOW + timedelta(days=5))
    helper = create_user(db_session, full_name="Helper Driver")
    db_session.add_all(
        [
            Delivery(
                booking_id=soon.id,
                assigned_to_id=me.id,
                status=DeliveryStatus.PENDING_SCHEDULE,
                dropoff_address="A",
            ),
            Delivery(
                booking_id=handed_off.id,
                assigned_to_id=helper.id,
                status=DeliveryStatus.PENDING_SCHEDULE,
                dropoff_address="C",
            ),
            Delivery(
                booking_id=rented.id,
                assigned_to_id=me.id,
                status=DeliveryStatus.DELIVERED,
                dropoff_address="B",
                scheduled_for=NOW,
                started_at=NOW,
                delivered_at=NOW,
            ),
        ]
    )
    disc = db_session.scalar(
        select(VehicleDocument).where(
            VehicleDocument.vehicle_id == car.id,
            VehicleDocument.document_type == VehicleDocumentType.LICENCE_DISC,
        )
    )
    disc.expiry_date = today_in_south_africa() + timedelta(days=12)
    db_session.flush()

    body = api.get(f"{OWNER}/dashboard", headers=owner.headers).json()

    assert body["vehicles_by_status"]["APPROVED"] == 1
    assert body["vehicles_by_status"]["PENDING_APPROVAL"] == 1
    assert (body["upcoming_bookings"], body["active_rentals"]) == (3, 1)
    assert (body["deliveries_to_do"], body["returns_to_record"]) == (1, 1)
    assert body["next_booking"]["id"] == str(rented.id)  # under way comes first
    assert [(d["document_type"], d["expired"]) for d in body["expiring_documents"]] == [
        ("LICENCE_DISC", False)
    ]
    this_month = today_in_south_africa().strftime("%Y-%m")
    expected = soon.total_amount if soon.start_at.strftime("%Y-%m") == this_month else Decimal("0")
    assert Decimal(body["month_net"]) == expected


def test_empty_owner_dashboard(api, owner) -> None:
    body = api.get(f"{OWNER}/dashboard", headers=owner.headers).json()
    assert body["next_booking"] is None and body["expiring_documents"] == []
    assert set(body["vehicles_by_status"].values()) == {0}
    assert body["year_net"] == "0.00"


# --- renter payments --------------------------------------------------------------------------


def test_renter_sees_own_payments_with_refunds(api, renter, owner, db_session, storage) -> None:
    me = user_of(db_session, renter)
    car = car_of(db_session, storage, owner)
    mine = booking_of(db_session, car, S.CANCELLED, renter=me)
    paid(db_session, mine, refunds=[("500.00", RefundStatus.PROCESSED)])
    paid(db_session, booking_of(db_session, car, start=NOW + timedelta(days=40)))  # someone else

    rows = api.get("/api/v1/customers/me/payments", headers=renter.headers).json()

    assert len(rows) == 1
    assert rows[0]["booking_reference"] == mine.reference
    assert rows[0]["vehicle"] == f"{car.make} {car.model}"
    assert rows[0]["refunds"][0]["amount"] == "500.00"
    assert api.get("/api/v1/customers/me/payments", headers=owner.headers).status_code == 403
