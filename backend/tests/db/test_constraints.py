"""Database-level integrity rules (constraints, triggers, exact money)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Booking,
    CustomerProfile,
    Delivery,
    Payment,
    Role,
    User,
    UserRole,
    VehiclePrice,
)
from app.models.enums import (
    BookingStatus,
    PaymentStatus,
    RoleName,
    UserStatus,
    VerificationStatus,
)
from tests.conftest import requires_db
from tests.db.factories import (
    BASE_START,
    booking_values,
    create_booking,
    create_price,
    create_user,
    create_vehicle,
)

pytestmark = requires_db


def assert_rejected(
    session: Session, statement_or_obj, params: dict | None = None, error=IntegrityError
) -> None:
    """The write must fail; roll back to a savepoint so the test can continue."""
    with pytest.raises(error):
        with session.begin_nested():
            if isinstance(statement_or_obj, str):
                session.execute(text(statement_or_obj), params or {})
            else:
                session.add(statement_or_obj)
                session.flush()


# --- users and roles ------------------------------------------------------


def test_user_defaults(db_session: Session) -> None:
    user = create_user(db_session)
    db_session.refresh(user)

    assert user.status is UserStatus.ACTIVE
    assert user.id is not None and user.created_at is not None


def test_email_unique_case_insensitive(db_session: Session) -> None:
    create_user(db_session, email="Thandi@Example.com")

    assert_rejected(
        db_session, User(email="thandi@example.com", password_hash="x", full_name="Dup")
    )


def test_suspended_user_requires_timestamp(db_session: Session) -> None:
    assert_rejected(
        db_session,
        User(email="s@example.com", password_hash="x", full_name="S", status=UserStatus.SUSPENDED),
    )


def test_invalid_enum_value_rejected_by_database(db_session: Session) -> None:
    user = create_user(db_session)

    assert_rejected(
        db_session, "UPDATE users SET status = 'GOD_MODE' WHERE id = :id", {"id": user.id}
    )


def test_user_role_assignment_and_cascade(db_session: Session) -> None:
    user = create_user(db_session)
    renter = db_session.scalar(select(Role).where(Role.name == RoleName.RENTER))
    db_session.add(UserRole(user_id=user.id, role_id=renter.id))
    db_session.flush()
    db_session.refresh(user)

    assert [role.name for role in user.roles] == [RoleName.RENTER]
    assert_rejected(db_session, UserRole(user_id=user.id, role_id=renter.id))

    db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
    remaining = db_session.scalar(
        text("SELECT count(*) FROM user_roles WHERE user_id = :id"), {"id": user.id}
    )
    assert remaining == 0


def test_customer_profile_defaults_and_one_per_user(db_session: Session) -> None:
    user = create_user(db_session)
    profile = CustomerProfile(user_id=user.id)
    db_session.add(profile)
    db_session.flush()
    db_session.refresh(profile)

    assert profile.id_verification_status is VerificationStatus.NOT_SUBMITTED
    assert profile.licence_verification_status is VerificationStatus.NOT_SUBMITTED
    assert_rejected(db_session, CustomerProfile(user_id=user.id))


# --- vehicles and pricing -------------------------------------------------


def test_vehicle_registration_and_vin_are_validated_and_unique(db_session: Session) -> None:
    vehicle = create_vehicle(db_session, registration_number="CA123456")

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            create_vehicle(db_session, registration_number="CA123456")
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            create_vehicle(db_session, vin=vehicle.vin)
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            create_vehicle(db_session, registration_number="ca 123")
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            create_vehicle(db_session, vin="IOQ12345678901234")


def test_approved_vehicle_requires_approval_timestamp(db_session: Session) -> None:
    vehicle = create_vehicle(db_session)

    assert_rejected(
        db_session, "UPDATE vehicles SET status = 'APPROVED' WHERE id = :id", {"id": vehicle.id}
    )


def test_prices_are_stored_exactly(db_session: Session) -> None:
    price = create_price(db_session, create_vehicle(db_session), daily_rate=Decimal("1234567.89"))
    db_session.expire(price)

    stored = db_session.get(VehiclePrice, price.id)
    assert stored.daily_rate == Decimal("1234567.89")
    assert isinstance(stored.daily_rate, Decimal)
    assert stored.currency == "ZAR"


@pytest.mark.parametrize(
    "overrides",
    [
        {"daily_rate": Decimal("0.00")},
        {"daily_rate": Decimal("-10.00")},
        {"delivery_fee": Decimal("-1.00")},
        {"currency": "USD"},
    ],
    ids=["zero-rate", "negative-rate", "negative-fee", "non-zar"],
)
def test_invalid_prices_rejected(db_session: Session, overrides: dict) -> None:
    vehicle = create_vehicle(db_session)

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            create_price(db_session, vehicle, **overrides)


def test_price_history_is_append_only(db_session: Session) -> None:
    """Prices can never be edited or deleted, referenced by a booking or not."""
    referenced = create_price(db_session, create_vehicle(db_session))
    create_booking(db_session, referenced)
    unreferenced = create_price(db_session, create_vehicle(db_session))

    for price in (referenced, unreferenced):
        assert_rejected(
            db_session,
            "UPDATE vehicle_prices SET daily_rate = 1 WHERE id = :id",
            {"id": price.id},
            error=DBAPIError,
        )
        assert_rejected(
            db_session,
            "DELETE FROM vehicle_prices WHERE id = :id",
            {"id": price.id},
            error=DBAPIError,
        )


# --- bookings ---------------------------------------------------------------


def test_booking_snapshot_must_be_consistent(db_session: Session) -> None:
    price = create_price(db_session, create_vehicle(db_session))
    renter = create_user(db_session)

    wrong_total = booking_values(renter, price)
    wrong_total["total_amount"] = Decimal("1.00")
    assert_rejected(db_session, Booking(**wrong_total))

    wrong_rental = booking_values(renter, price)
    wrong_rental["rental_amount"] = price.daily_rate  # 1 day charged for 3 days
    wrong_rental["total_amount"] = price.daily_rate + price.delivery_fee
    assert_rejected(db_session, Booking(**wrong_rental))


def test_booking_period_must_be_positive(db_session: Session) -> None:
    price = create_price(db_session, create_vehicle(db_session))
    values = booking_values(create_user(db_session), price)
    values["end_at"] = values["start_at"]

    assert_rejected(db_session, Booking(**values))


def test_pending_payment_requires_hold_expiry(db_session: Session) -> None:
    price = create_price(db_session, create_vehicle(db_session))
    values = booking_values(create_user(db_session), price, status=BookingStatus.PENDING_PAYMENT)
    values["hold_expires_at"] = None

    assert_rejected(db_session, Booking(**values))


def test_overlapping_bookings_rejected(db_session: Session) -> None:
    price = create_price(db_session, create_vehicle(db_session))
    create_booking(db_session, price, start=BASE_START, days=3)

    overlapping = booking_values(
        create_user(db_session), price, start=BASE_START + timedelta(days=2), days=3
    )
    assert_rejected(db_session, Booking(**overlapping))

    pending_overlap = booking_values(
        create_user(db_session),
        price,
        start=BASE_START + timedelta(hours=1),
        days=1,
        status=BookingStatus.PENDING_PAYMENT,
    )
    assert_rejected(db_session, Booking(**pending_overlap))


def test_back_to_back_bookings_allowed(db_session: Session) -> None:
    price = create_price(db_session, create_vehicle(db_session))
    first = create_booking(db_session, price, start=BASE_START, days=3)

    second = create_booking(db_session, price, start=first.end_at, days=2)

    assert second.start_at == first.end_at


def test_same_dates_on_different_vehicles_allowed(db_session: Session) -> None:
    create_booking(db_session, create_price(db_session, create_vehicle(db_session)))
    create_booking(db_session, create_price(db_session, create_vehicle(db_session)))


@pytest.mark.parametrize(
    "released_status",
    [BookingStatus.CANCELLED, BookingStatus.EXPIRED, BookingStatus.COMPLETED],
)
def test_released_bookings_do_not_block_dates(
    db_session: Session, released_status: BookingStatus
) -> None:
    price = create_price(db_session, create_vehicle(db_session))
    old = create_booking(db_session, price, status=released_status)

    new = create_booking(db_session, price)

    assert (new.start_at, new.end_at) == (old.start_at, old.end_at)


def test_reactivating_a_cancelled_booking_into_a_conflict_is_rejected(
    db_session: Session,
) -> None:
    price = create_price(db_session, create_vehicle(db_session))
    cancelled = create_booking(db_session, price, status=BookingStatus.CANCELLED)
    create_booking(db_session, price)

    assert_rejected(
        db_session, "UPDATE bookings SET status = 'CONFIRMED' WHERE id = :id", {"id": cancelled.id}
    )


# --- payments, deliveries, audit -------------------------------------------


def _payment(booking: Booking, **overrides: object) -> Payment:
    values: dict[str, object] = {
        "booking_id": booking.id,
        "provider": "test-provider",
        "amount": booking.total_amount,
    }
    values.update(overrides)
    return Payment(**values)


def test_only_one_successful_payment_per_booking(db_session: Session) -> None:
    booking = create_booking(db_session, create_price(db_session, create_vehicle(db_session)))
    paid_at = BASE_START - timedelta(days=1)
    db_session.add(_payment(booking, status=PaymentStatus.SUCCEEDED, paid_at=paid_at))
    db_session.add(_payment(booking, status=PaymentStatus.FAILED))
    db_session.flush()

    assert_rejected(db_session, _payment(booking, status=PaymentStatus.SUCCEEDED, paid_at=paid_at))


def test_provider_reference_is_unique_per_provider(db_session: Session) -> None:
    booking = create_booking(db_session, create_price(db_session, create_vehicle(db_session)))
    db_session.add(_payment(booking, provider_reference="txn-1"))
    db_session.add(_payment(booking, provider="other-provider", provider_reference="txn-1"))
    db_session.flush()

    assert_rejected(db_session, _payment(booking, provider_reference="txn-1"))


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": Decimal("0.00")},
        {"currency": "EUR"},
        {"status": PaymentStatus.SUCCEEDED, "paid_at": None},
    ],
    ids=["zero-amount", "non-zar", "succeeded-without-paid-at"],
)
def test_invalid_payments_rejected(db_session: Session, overrides: dict) -> None:
    booking = create_booking(db_session, create_price(db_session, create_vehicle(db_session)))

    assert_rejected(db_session, _payment(booking, **overrides))


def test_one_delivery_per_booking_with_valid_coordinates(db_session: Session) -> None:
    booking = create_booking(db_session, create_price(db_session, create_vehicle(db_session)))
    db_session.add(
        Delivery(
            booking_id=booking.id,
            dropoff_address="1 Main Rd, Sandton",
            dropoff_latitude=Decimal("-26.107600"),
            dropoff_longitude=Decimal("28.056700"),
        )
    )
    db_session.flush()

    assert_rejected(db_session, Delivery(booking_id=booking.id, dropoff_address="Elsewhere"))
    other = create_booking(db_session, create_price(db_session, create_vehicle(db_session)))
    assert_rejected(
        db_session,
        Delivery(
            booking_id=other.id,
            dropoff_address="Nowhere",
            dropoff_latitude=Decimal("-95"),
            dropoff_longitude=Decimal("28"),
        ),
    )
    assert_rejected(
        db_session,
        Delivery(booking_id=other.id, dropoff_address="Half", dropoff_latitude=Decimal("-26")),
    )


def test_audit_log_is_append_only(db_session: Session) -> None:
    actor = create_user(db_session)
    entry = AuditLog(
        actor_user_id=actor.id,
        action="vehicle.approved",
        entity_type="vehicle",
        entity_id="abc",
        changes={"status": {"from": "PENDING_APPROVAL", "to": "APPROVED"}},
    )
    db_session.add(entry)
    db_session.flush()

    assert entry.id is not None
    assert_rejected(
        db_session,
        "UPDATE audit_logs SET action = 'x' WHERE id = :id",
        {"id": entry.id},
        error=DBAPIError,
    )
    assert_rejected(
        db_session, "DELETE FROM audit_logs WHERE id = :id", {"id": entry.id}, error=DBAPIError
    )
    assert db_session.get(AuditLog, entry.id).action == "vehicle.approved"


def test_user_with_audit_history_cannot_be_hard_deleted(db_session: Session) -> None:
    actor = create_user(db_session)
    db_session.add(
        AuditLog(actor_user_id=actor.id, action="user.login", entity_type="user", entity_id="x")
    )
    db_session.flush()

    assert_rejected(db_session, "DELETE FROM users WHERE id = :id", {"id": actor.id})
