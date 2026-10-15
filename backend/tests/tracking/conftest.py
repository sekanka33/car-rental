import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.maps import LatLng, RouteEstimate
from app.models import Delivery, OwnerProfile, User
from app.services import bookings as booking_service
from tests.api_fixtures import *  # noqa: F403  (shared API fixtures)
from tests.api_fixtures import Account
from tests.bookings.helpers import book, eligible_renter
from tests.marketplace.factories import listed_vehicle

OWNER = "/api/v1/owners/me/deliveries"
HANDOVER = {"odometer_km": 41200, "fuel_level": "FULL"}
DROPOFF = LatLng(Decimal("-33.924870"), Decimal("18.424055"))


class FakeMaps:
    """Scriptable maps provider that counts calls (each Routes call costs money)."""

    def __init__(self) -> None:
        self.geocodes: list[str] = []
        self.routes: list[tuple[LatLng, LatLng]] = []
        self.dropoff: LatLng | None = DROPOFF
        self.estimate: RouteEstimate | None = RouteEstimate(600, 4200)

    def geocode(self, address: str) -> LatLng | None:
        self.geocodes.append(address)
        return self.dropoff

    def route(self, origin: LatLng, destination: LatLng) -> RouteEstimate | None:
        self.routes.append((origin, destination))
        return self.estimate


@pytest.fixture
def maps_provider() -> FakeMaps:
    return FakeMaps()


@pytest.fixture
def alice(api: TestClient, db_session: Session) -> Account:
    return eligible_renter(api, db_session, "alice@example.com")


@pytest.fixture
def delivery_id(api, alice, owner, db_session, storage) -> str:
    """A paid booking for the logged-in owner's car; its delivery is not yet scheduled."""
    vehicle = listed_vehicle(db_session, storage)
    user = db_session.scalar(select(User).where(User.email == owner.email))
    vehicle.owner_id = db_session.scalar(
        select(OwnerProfile.id).where(OwnerProfile.user_id == user.id)
    )
    db_session.flush()
    booking = book(api, alice, vehicle.id).json()
    booking_service.confirm_booking(db_session, uuid.UUID(booking["id"]))
    return str(db_session.scalar(select(Delivery.id).where(Delivery.booking_id == booking["id"])))


def post(api: TestClient, account: Account, url: str, json: dict | None = None):
    return api.post(url, headers=account.headers, json=json if json is not None else {})


def set_off(api: TestClient, owner: Account, delivery_id: str) -> None:
    for step in ("schedule", "start"):
        assert post(api, owner, f"{OWNER}/{delivery_id}/{step}").status_code == 200


def fix(latitude: float = -33.915, longitude: float = 18.39, **extra) -> dict:
    return {
        "latitude": latitude,
        "longitude": longitude,
        "accuracy_m": 8.3,
        "recorded_at": datetime.now(UTC).isoformat(),
        **extra,
    }
