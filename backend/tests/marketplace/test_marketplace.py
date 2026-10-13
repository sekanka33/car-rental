from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations.storage import InMemoryDocumentStorage
from app.models import OwnerProfile, User, VehicleAvailabilityBlock, VehicleDocument
from app.models.enums import BookingStatus, FuelType, Transmission, UserStatus, VehicleStatus
from tests.conftest import requires_db
from tests.db.factories import booking_values, create_user
from tests.marketplace.factories import PHOTO, add_price, listed_vehicle

pytestmark = requires_db
URL = "/api/v1/vehicles"
SOON = datetime.now(UTC).replace(microsecond=0) + timedelta(days=10)


def ids(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


# --- visibility ----------------------------------------------------------------------------


def test_only_listed_vehicles_are_visible(
    api: TestClient, db_session: Session, storage: InMemoryDocumentStorage
) -> None:
    listed = listed_vehicle(db_session, storage)
    hidden = [
        listed_vehicle(db_session, storage, status=status)
        for status in (
            VehicleStatus.DRAFT,
            VehicleStatus.PENDING_APPROVAL,
            VehicleStatus.REJECTED,
            VehicleStatus.UNAVAILABLE,
            VehicleStatus.SUSPENDED,
        )
    ]
    hidden.append(listed_vehicle(db_session, storage, daily_rate=None))  # no price
    expired = listed_vehicle(db_session, storage)
    for doc in db_session.query(VehicleDocument).filter_by(
        vehicle_id=expired.id, document_type="INSURANCE"
    ):
        db_session.execute(
            VehicleDocument.__table__.update()
            .where(VehicleDocument.id == doc.id)
            .values(expiry_date=datetime.now(UTC).date() - timedelta(days=1))
        )
    hidden.append(expired)
    inactive = listed_vehicle(db_session, storage)
    owner_user = db_session.get(User, db_session.get(OwnerProfile, inactive.owner_id).user_id)
    owner_user.status = UserStatus.SUSPENDED
    owner_user.suspended_at = datetime.now(UTC)
    hidden.append(inactive)
    db_session.flush()

    assert ids(api.get(URL)) == [str(listed.id)]
    for vehicle in hidden:
        assert api.get(f"{URL}/{vehicle.id}").status_code == 404
        photo = vehicle.images[0] if vehicle.images else None
        if photo:
            assert api.get(f"{URL}/{vehicle.id}/photos/{photo.id}").status_code == 404
        assert api.get(f"{URL}/{vehicle.id}/availability").status_code == 404


def test_public_data_is_privacy_limited(api: TestClient, db_session: Session, storage) -> None:
    vehicle = listed_vehicle(
        db_session, storage, owner_name="Lerato Mokoena", city="Pretoria", province="Gauteng"
    )

    response = api.get(f"{URL}/{vehicle.id}")

    body = response.json()
    assert body["owner"] == {"first_name": "Lerato", "city": "Pretoria", "province": "Gauteng"}
    for secret in (vehicle.vin, vehicle.registration_number, "Mokoena", "@example.com"):
        assert secret not in response.text
    assert not {"vin", "registration_number", "owner_id", "status", "documents"} & body.keys()


def test_price_is_the_official_price_in_effect(
    api: TestClient, db_session: Session, storage
) -> None:
    vehicle = listed_vehicle(db_session, storage, daily_rate="650.00")
    add_price(db_session, vehicle, "800.00", effective_from=datetime.now(UTC) + timedelta(days=5))

    price = api.get(f"{URL}/{vehicle.id}").json()["price"]
    assert price == {
        "daily_rate": "650.00",
        "delivery_fee": "150.00",
        "deposit_amount": "2000.00",
        "currency": "ZAR",
    }

    add_price(
        db_session, vehicle, "700.00", effective_from=datetime.now(UTC) - timedelta(minutes=1)
    )
    assert api.get(f"{URL}/{vehicle.id}").json()["price"]["daily_rate"] == "700.00"
    assert api.get(URL).json()["items"][0]["price"]["daily_rate"] == "700.00"


def test_unknown_vehicle_is_404(api: TestClient) -> None:
    assert api.get(f"{URL}/00000000-0000-0000-0000-000000000000").status_code == 404
    assert api.get(f"{URL}/not-a-uuid").status_code == 422


# --- search, filters, sort, pagination --------------------------------------------------------


@pytest.fixture
def fleet(db_session: Session, storage):
    return {
        "polo": listed_vehicle(
            db_session,
            storage,
            make="Volkswagen",
            model="Polo Vivo",
            city="Cape Town",
            province="Western Cape",
            transmission=Transmission.MANUAL,
            daily_rate="480.00",
            seats=5,
        ),
        "hilux": listed_vehicle(
            db_session,
            storage,
            make="Toyota",
            model="Hilux",
            city="Durban",
            province="KwaZulu-Natal",
            fuel_type=FuelType.DIESEL,
            daily_rate="1150.00",
            seats=5,
        ),
        "fortuner": listed_vehicle(
            db_session,
            storage,
            make="Toyota",
            model="Fortuner",
            city="Johannesburg",
            province="Gauteng",
            daily_rate="1400.00",
            seats=7,
        ),
    }


def names(response) -> list[str]:
    return [item["model"] for item in response.json()["items"]]


def test_search_text(api: TestClient, fleet) -> None:
    assert names(api.get(URL, params={"q": "toyota"})) == ["Hilux", "Fortuner"]
    assert names(api.get(URL, params={"q": "POLO"})) == ["Polo Vivo"]
    assert names(api.get(URL, params={"q": "durban"})) == ["Hilux"]
    assert names(api.get(URL, params={"q": "toyota fort"})) == ["Fortuner"]
    assert names(api.get(URL, params={"q": "%"})) == []  # wildcards are literal
    assert names(api.get(URL, params={"q": "_"})) == []


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"transmission": "MANUAL"}, ["Polo Vivo"]),
        ({"fuel_type": "DIESEL"}, ["Hilux"]),
        ({"province": "Gauteng"}, ["Fortuner"]),
        ({"city": "cape town"}, ["Polo Vivo"]),
        ({"min_seats": 7}, ["Fortuner"]),
        ({"max_daily_rate": "1150.00"}, ["Polo Vivo", "Hilux"]),
        ({"min_daily_rate": "500", "max_daily_rate": "1200"}, ["Hilux"]),
        ({"sort": "price_desc"}, ["Fortuner", "Hilux", "Polo Vivo"]),
        ({"q": "toyota", "min_seats": 6}, ["Fortuner"]),
    ],
)
def test_filters_and_sorting(api: TestClient, fleet, params: dict, expected: list[str]) -> None:
    assert names(api.get(URL, params=params)) == expected


@pytest.mark.parametrize(
    "params",
    [
        {"province": "Atlantis"},
        {"transmission": "CVT"},
        {"min_daily_rate": "-1"},
        {"limit": 500},
        {"sort": "random"},
    ],
)
def test_invalid_filters_rejected(api: TestClient, params: dict) -> None:
    assert api.get(URL, params=params).status_code == 422


def test_pagination(api: TestClient, fleet) -> None:
    page = api.get(URL, params={"limit": 2, "offset": 0}).json()
    rest = api.get(URL, params={"limit": 2, "offset": 2}).json()

    assert page["total"] == rest["total"] == 3
    assert [i["model"] for i in page["items"]] == ["Polo Vivo", "Hilux"]
    assert [i["model"] for i in rest["items"]] == ["Fortuner"]


def test_availability_filter(api: TestClient, fleet, db_session: Session) -> None:
    from app.models import Booking

    price = fleet["hilux"].prices[0]
    db_session.add(Booking(**booking_values(create_user(db_session), price, start=SOON, days=3)))
    db_session.add(
        VehicleAvailabilityBlock(
            vehicle_id=fleet["polo"].id,
            start_at=SOON + timedelta(days=1),
            end_at=SOON + timedelta(days=2),
            created_by_id=create_user(db_session).id,
        )
    )
    db_session.flush()
    window = {
        "available_from": (SOON + timedelta(hours=12)).isoformat(),
        "available_to": (SOON + timedelta(days=2)).isoformat(),
    }

    assert names(api.get(URL, params=window)) == ["Fortuner"]
    later = {
        "available_from": (SOON + timedelta(days=5)).isoformat(),
        "available_to": (SOON + timedelta(days=6)).isoformat(),
    }
    assert len(names(api.get(URL, params=later))) == 3
    assert api.get(URL, params={"available_from": SOON.isoformat()}).status_code == 422


# --- details, photos, availability, quote -------------------------------------------------------


def test_details_and_public_photos(api: TestClient, db_session: Session, storage) -> None:
    vehicle = listed_vehicle(db_session, storage, photos=3, description="Spotless")
    other = listed_vehicle(db_session, storage)

    detail = api.get(f"{URL}/{vehicle.id}").json()
    assert detail["description"] == "Spotless" and detail["photo_count"] == 3
    assert detail["primary_photo_url"] == detail["photos"][0]["url"]

    photo = api.get(detail["photos"][1]["url"])
    assert photo.status_code == 200 and photo.content == PHOTO + bytes([1])
    assert photo.headers["cache-control"] == "public, max-age=300"
    assert photo.headers["content-type"] == "image/jpeg"
    # A photo id only works with its own vehicle.
    assert api.get(f"{URL}/{other.id}/photos/{detail['photos'][1]['id']}").status_code == 404


def test_availability_lists_merged_periods_without_details(
    api: TestClient, db_session: Session, storage
) -> None:
    from app.models import Booking

    vehicle = listed_vehicle(db_session, storage)
    db_session.add(
        Booking(**booking_values(create_user(db_session), vehicle.prices[0], start=SOON, days=2))
    )
    db_session.add(
        VehicleAvailabilityBlock(
            vehicle_id=vehicle.id,
            start_at=SOON + timedelta(days=1),
            end_at=SOON + timedelta(days=4),
            reason="Family holiday",
            created_by_id=create_user(db_session).id,
        )
    )
    db_session.add(
        Booking(
            **booking_values(
                create_user(db_session),
                vehicle.prices[0],
                start=SOON + timedelta(days=20),
                days=1,
                status=BookingStatus.CANCELLED,
            )
        )
    )
    db_session.flush()

    response = api.get(f"{URL}/{vehicle.id}/availability")

    assert response.status_code == 200
    periods = response.json()["unavailable"]
    assert len(periods) == 1  # overlapping booking + block merged; cancelled booking ignored
    assert datetime.fromisoformat(periods[0]["start_at"]) == SOON
    assert datetime.fromisoformat(periods[0]["end_at"]) == SOON + timedelta(days=4)
    assert "Family holiday" not in response.text
    too_wide = {"start_at": SOON.isoformat(), "end_at": (SOON + timedelta(days=200)).isoformat()}
    assert api.get(f"{URL}/{vehicle.id}/availability", params=too_wide).status_code == 422


def test_quote(api: TestClient, db_session: Session, storage) -> None:
    from app.models import Booking

    vehicle = listed_vehicle(db_session, storage, daily_rate="650.00")
    free = {"start_at": SOON.isoformat(), "end_at": (SOON + timedelta(days=3, hours=1)).isoformat()}

    quote = api.get(f"{URL}/{vehicle.id}/quote", params=free).json()
    assert quote == {
        "available": True,
        "rental_days": 4,
        "daily_rate": "650.00",
        "rental_amount": "2600.00",
        "delivery_fee": "150.00",
        "deposit_amount": "2000.00",
        "total_amount": "2750.00",
        "currency": "ZAR",
    }

    db_session.add(
        Booking(
            **booking_values(
                create_user(db_session), vehicle.prices[0], start=SOON + timedelta(days=1), days=1
            )
        )
    )
    db_session.flush()
    assert api.get(f"{URL}/{vehicle.id}/quote", params=free).json()["available"] is False


@pytest.mark.parametrize(
    "period",
    [
        (timedelta(days=-2), timedelta(days=-1)),
        (timedelta(days=1), timedelta(days=95)),
        (timedelta(days=2), timedelta(days=1)),
    ],
    ids=["past", "longer-than-90-days", "end-before-start"],
)
def test_quote_period_validation(api: TestClient, db_session: Session, storage, period) -> None:
    vehicle = listed_vehicle(db_session, storage)
    now = datetime.now(UTC)
    params = {"start_at": (now + period[0]).isoformat(), "end_at": (now + period[1]).isoformat()}

    assert api.get(f"{URL}/{vehicle.id}/quote", params=params).status_code == 422
    naive = {
        "start_at": SOON.replace(tzinfo=None).isoformat(),
        "end_at": (SOON + timedelta(days=1)).isoformat(),
    }
    assert api.get(f"{URL}/{vehicle.id}/quote", params=naive).status_code == 422


@pytest.mark.parametrize(
    "released", [BookingStatus.CANCELLED, BookingStatus.EXPIRED, BookingStatus.COMPLETED]
)
def test_released_bookings_do_not_block_search_or_quotes(
    api: TestClient, db_session: Session, storage, released: BookingStatus
) -> None:
    from app.models import Booking

    vehicle = listed_vehicle(db_session, storage)
    db_session.add(
        Booking(
            **booking_values(
                create_user(db_session), vehicle.prices[0], start=SOON, days=2, status=released
            )
        )
    )
    db_session.flush()
    period = {"start_at": SOON.isoformat(), "end_at": (SOON + timedelta(days=2)).isoformat()}
    window = {"available_from": period["start_at"], "available_to": period["end_at"]}

    assert api.get(f"{URL}/{vehicle.id}/quote", params=period).json()["available"] is True
    assert ids(api.get(URL, params=window)) == [str(vehicle.id)]
