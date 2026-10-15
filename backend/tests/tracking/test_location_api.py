"""Location updates (BR-7.2, 7.4, 7.5) and ETA."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import Delivery, DeliveryLocationUpdate
from app.services.tracking import purge_old_locations, tracking_payload
from tests.api_fixtures import login, register
from tests.conftest import make_settings, requires_db
from tests.tracking.conftest import HANDOVER, OWNER, fix, post, set_off

pytestmark = requires_db


def share(api, account, delivery_id, body=None):
    return post(api, account, f"{OWNER}/{delivery_id}/location", body or fix())


def age_last_update(session, seconds: int = 30) -> None:
    """Pretend the previous update arrived a while ago (bypasses the rate limit)."""
    last = session.scalars(
        select(DeliveryLocationUpdate).order_by(DeliveryLocationUpdate.received_at.desc())
    ).first()
    last.received_at -= timedelta(seconds=seconds)
    delivery = session.get(Delivery, last.delivery_id)
    if (
        delivery.started_at and delivery.started_at > last.received_at
    ):  # keep the update inside the current trip
        delivery.started_at = last.received_at - timedelta(seconds=1)
    session.flush()


def payload(session, delivery_id):
    session.expire_all()
    return tracking_payload(session, session.get(Delivery, delivery_id))


def test_location_only_while_on_the_way(api, owner, delivery_id, db_session) -> None:
    assert share(api, owner, delivery_id).status_code == 409  # not scheduled
    post(api, owner, f"{OWNER}/{delivery_id}/schedule")
    assert share(api, owner, delivery_id).status_code == 409  # scheduled, not started
    post(api, owner, f"{OWNER}/{delivery_id}/start")

    assert share(api, owner, delivery_id).status_code == 204
    assert payload(db_session, delivery_id)["location"]["latitude"] == -33.915

    post(api, owner, f"{OWNER}/{delivery_id}/handover", HANDOVER)
    age_last_update(db_session)
    late = share(api, owner, delivery_id)
    assert late.status_code == 409 and late.json()["error"]["code"] == "tracking_not_active"
    assert payload(db_session, delivery_id)["location"] is None  # sharing stopped


def test_only_the_assigned_person_can_share(api, alice, owner, delivery_id) -> None:
    set_off(api, owner, delivery_id)
    register(api, "other-owner@example.com", "OWNER")
    other = login(api, "other-owner@example.com")

    assert share(api, other, delivery_id).status_code == 404
    assert share(api, alice, delivery_id).status_code == 403


@pytest.mark.parametrize(
    "body",
    [
        fix(latitude=91),
        fix(longitude=-181),
        fix(heading=360),
        fix(speed_mps=-1),
        fix(recorded_at="2030-01-01T08:00:00"),  # no timezone
        fix(recorded_at=(datetime.now(UTC) + timedelta(minutes=5)).isoformat()),
        fix(recorded_at=(datetime.now(UTC) - timedelta(minutes=11)).isoformat()),
        {**fix(), "user_id": "someone-else"},
    ],
)
def test_location_input_is_validated(api, owner, delivery_id, body) -> None:
    set_off(api, owner, delivery_id)
    assert share(api, owner, delivery_id, body).status_code == 422


def test_phone_precision_is_rounded(api, owner, delivery_id, db_session) -> None:
    set_off(api, owner, delivery_id)

    response = share(
        api, owner, delivery_id, fix(latitude=-33.91512345678, longitude=18.3901, heading=271.66)
    )

    assert response.status_code == 204
    stored = db_session.scalar(select(DeliveryLocationUpdate))
    assert (str(stored.latitude), str(stored.heading)) == ("-33.915123", "271.7")


def test_updates_are_rate_limited(api, owner, delivery_id, db_session) -> None:
    set_off(api, owner, delivery_id)
    assert share(api, owner, delivery_id).status_code == 204

    too_soon = share(api, owner, delivery_id)

    assert too_soon.status_code == 429
    assert too_soon.json()["error"]["code"] == "location_too_frequent"
    age_last_update(db_session, seconds=6)
    assert share(api, owner, delivery_id).status_code == 204


def test_latest_fix_wins_and_old_trip_is_hidden(api, owner, admin, delivery_id, db_session):
    set_off(api, owner, delivery_id)
    share(api, owner, delivery_id, fix(latitude=-33.90))
    age_last_update(db_session)
    earlier = (datetime.now(UTC) - timedelta(minutes=2)).isoformat()
    share(api, owner, delivery_id, fix(latitude=-33.80, recorded_at=earlier))  # arrives late
    assert payload(db_session, delivery_id)["location"]["latitude"] == -33.90

    post(
        api,
        owner,
        f"{OWNER}/{delivery_id}/exceptions",
        {"kind": "VEHICLE_PROBLEM", "notes": "Flat tyre"},
    )
    delivery = db_session.get(Delivery, delivery_id)
    post(
        api,
        admin,
        f"/api/v1/admin/deliveries/{delivery_id}/reschedule",
        {
            "scheduled_for": (delivery.scheduled_for + timedelta(hours=2)).isoformat(),
            "note": "New attempt",
        },
    )
    age_last_update(db_session, seconds=120)
    post(api, owner, f"{OWNER}/{delivery_id}/start")
    assert payload(db_session, delivery_id)["location"] is None  # nothing from the failed trip


# --- ETA ----------------------------------------------------------------------------------


def test_eta_geocodes_once_and_limits_route_calls(
    api, owner, delivery_id, db_session, maps_provider
) -> None:
    set_off(api, owner, delivery_id)
    share(api, owner, delivery_id)

    view = payload(db_session, delivery_id)
    assert view["eta"]["seconds"] == 600 and view["eta"]["distance_m"] == 4200
    assert maps_provider.geocodes == ["12 Long Street, Cape Town"]
    assert len(maps_provider.routes) == 1

    age_last_update(db_session)
    share(api, owner, delivery_id)
    assert len(maps_provider.routes) == 1  # within ETA_REFRESH_SECONDS

    delivery = db_session.get(Delivery, delivery_id)
    delivery.eta_computed_at -= timedelta(seconds=61)
    age_last_update(db_session)
    share(api, owner, delivery_id, fix(latitude=-33.92))
    assert len(maps_provider.routes) == 2
    assert float(maps_provider.routes[-1][0].latitude) == -33.92
    assert maps_provider.geocodes == ["12 Long Street, Cape Town"]  # still only once


def test_no_eta_when_the_address_cannot_be_found(
    api, owner, delivery_id, db_session, maps_provider
) -> None:
    maps_provider.dropoff = None
    set_off(api, owner, delivery_id)
    share(api, owner, delivery_id)
    age_last_update(db_session)
    share(api, owner, delivery_id)

    assert payload(db_session, delivery_id)["eta"] is None
    assert len(maps_provider.geocodes) == 1  # not retried on every update
    assert maps_provider.routes == []


def test_failed_route_clears_the_eta(api, owner, delivery_id, db_session, maps_provider) -> None:
    set_off(api, owner, delivery_id)
    share(api, owner, delivery_id)
    maps_provider.estimate = None
    db_session.get(Delivery, delivery_id).eta_computed_at -= timedelta(seconds=61)
    age_last_update(db_session)

    share(api, owner, delivery_id)

    assert payload(db_session, delivery_id)["eta"] is None


# --- retention ----------------------------------------------------------------------------


def test_purge_keeps_recent_and_en_route_history(api, owner, delivery_id, db_session) -> None:
    set_off(api, owner, delivery_id)
    share(api, owner, delivery_id)
    settings = make_settings()
    later = datetime.now(UTC) + timedelta(days=settings.location_retention_days + 1)

    assert purge_old_locations(db_session, settings, now=later) == 0  # still on its way

    post(api, owner, f"{OWNER}/{delivery_id}/handover", HANDOVER)
    assert purge_old_locations(db_session, settings) == 0  # recent
    assert purge_old_locations(db_session, settings, now=later) == 1
    assert db_session.scalar(select(func.count()).select_from(DeliveryLocationUpdate)) == 0
