"""Concurrent booking attempts for the same vehicle and dates: exactly one may succeed.

Uses real, separately committed transactions on two connections (not the rollback-only
db_session fixture), then cleans up the rows it created.

These are raw inserts with no row lock, so PostgreSQL may reject the loser in one of two
ways: an exclusion violation, or (when both inserts check each other's uncommitted rows
at the same instant) a deadlock abort. Either way exactly one booking is stored. The real
booking service locks the vehicle row first, so it serialises instead of deadlocking
(see tests/bookings/test_booking_concurrency.py).
"""

import threading
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.models import Booking
from app.models.enums import BookingStatus
from tests.conftest import requires_db
from tests.db.factories import booking_values, create_price, create_user, create_vehicle

pytestmark = requires_db


@pytest.fixture
def committed_price(migrated_engine: Engine) -> Iterator[tuple]:
    with Session(migrated_engine, expire_on_commit=False) as session:
        price = create_price(session, create_vehicle(session))
        renters = [create_user(session), create_user(session)]
        session.commit()
    yield price, renters
    with migrated_engine.begin() as connection:
        connection.execute(
            text("TRUNCATE bookings, vehicle_prices, vehicles, owner_profiles, users CASCADE")
        )


def test_concurrent_overlapping_bookings_only_one_succeeds(
    migrated_engine: Engine, committed_price: tuple
) -> None:
    price, renters = committed_price
    barrier = threading.Barrier(len(renters))
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt(renter) -> None:
        with Session(migrated_engine) as session:
            session.add(
                Booking(**booking_values(renter, price, status=BookingStatus.PENDING_PAYMENT))
            )
            barrier.wait()  # both transactions insert at (nearly) the same moment
            try:
                session.commit()
                result = "committed"
            except IntegrityError as exc:
                session.rollback()
                result = f"rejected:{exc.orig.diag.constraint_name}"
            except OperationalError as exc:  # deadlock detected while checking the constraint
                session.rollback()
                result = f"rejected:{type(exc.orig).__name__}"
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=attempt, args=(renter,)) for renter in renters]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(outcomes)[0] == "committed"
    assert sorted(outcomes)[1] in (
        "rejected:ex_bookings_vehicle_period_overlap",
        "rejected:DeadlockDetected",
    )
    with migrated_engine.connect() as connection:
        stored = connection.scalar(
            text("SELECT count(*) FROM bookings WHERE vehicle_id = :id"), {"id": price.vehicle_id}
        )
    assert stored == 1
