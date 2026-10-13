"""Two renters booking the same car at the same moment through the real service:
exactly one booking is created. Uses committed data (not the rollback-only session)."""

import threading
from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.integrations.storage import InMemoryDocumentStorage
from app.models import CustomerProfile
from app.models.enums import RoleName
from app.repositories.users import assign_role
from app.services.bookings import VehicleUnavailableError, create_booking
from tests.bookings.helpers import START, make_eligible
from tests.conftest import make_settings, requires_db
from tests.db.factories import create_user
from tests.marketplace.factories import listed_vehicle

pytestmark = requires_db


@pytest.fixture
def committed(migrated_engine: Engine) -> Iterator[tuple]:
    with Session(migrated_engine, expire_on_commit=False) as session:
        vehicle = listed_vehicle(session, InMemoryDocumentStorage())
        renters = []
        for n in range(2):
            user = create_user(session, email=f"racer{n}@example.com")
            assign_role(session, user, RoleName.RENTER)
            session.add(CustomerProfile(user_id=user.id))
            session.flush()
            renters.append(make_eligible(session, user.email))
        session.commit()
        ids = (vehicle.id, [r.id for r in renters])
    yield ids
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE bookings, vehicle_prices, vehicle_documents, vehicle_images, vehicles, "
                "owner_profiles, customer_profiles, user_roles, refresh_tokens, users CASCADE"
            )
        )


def test_simultaneous_bookings_for_the_same_dates(
    migrated_engine: Engine, committed: tuple
) -> None:
    vehicle_id, renter_ids = committed
    settings = make_settings()
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt(renter_id) -> None:
        with Session(migrated_engine) as session:
            from app.models import User

            renter = session.get(User, renter_id)
            barrier.wait()
            try:
                create_booking(
                    session,
                    settings,
                    renter,
                    vehicle_id=vehicle_id,
                    start_at=START,
                    end_at=START + timedelta(days=3),
                    delivery_address="1 Main Rd, Sandton",
                )
                result = "created"
            except VehicleUnavailableError:
                result = "unavailable"
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=attempt, args=(rid,)) for rid in renter_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(outcomes) == ["created", "unavailable"]
    with migrated_engine.connect() as connection:
        count = connection.scalar(
            text("SELECT count(*) FROM bookings WHERE vehicle_id = :v"), {"v": vehicle_id}
        )
    assert count == 1
