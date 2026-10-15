"""Live delivery tracking (BR-7.2–7.5): location updates from the assigned delivery person
while the delivery is EN_ROUTE, ETA through the maps provider, who may watch, and retention.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, NotFoundError
from app.core.realtime import TrackingHub
from app.integrations.maps import LatLng, MapsProvider
from app.models import Booking, Delivery, DeliveryLocationUpdate, User
from app.models.enums import DeliveryStatus, RoleName

logger = logging.getLogger(__name__)
# Deliveries that can still change: watchers stay connected while one of these.
WATCHABLE = frozenset(
    {DeliveryStatus.PENDING_SCHEDULE, DeliveryStatus.SCHEDULED, DeliveryStatus.EN_ROUTE}
)


class TrackingNotActiveError(AppError):
    status_code = 409
    code = "tracking_not_active"


class LocationTooFrequentError(AppError):
    status_code = 429
    code = "location_too_frequent"


class InvalidLocationError(AppError):
    status_code = 422
    code = "invalid_location"


def _now() -> datetime:
    return datetime.now(UTC)


# --- location updates -------------------------------------------------------------------------


def record_location(
    session: Session,
    settings: Settings,
    maps: MapsProvider | None,
    user: User,
    delivery_id: uuid.UUID,
    *,
    latitude: Decimal,
    longitude: Decimal,
    accuracy_m: Decimal | None,
    heading: Decimal | None,
    speed_mps: Decimal | None,
    recorded_at: datetime,
) -> Delivery:
    delivery = session.scalar(select(Delivery).where(Delivery.id == delivery_id).with_for_update())
    if delivery is None or delivery.assigned_to_id != user.id:
        raise NotFoundError("Delivery not found.")
    if delivery.status != DeliveryStatus.EN_ROUTE:
        raise TrackingNotActiveError("Location is only shared while the car is on its way.")
    now = _now()
    if recorded_at > now + timedelta(minutes=1):
        raise InvalidLocationError("The location time is in the future; check the phone clock.")
    if recorded_at < now - timedelta(seconds=settings.location_max_age_seconds):
        raise InvalidLocationError("This location is too old to show.")
    last = session.scalar(
        select(DeliveryLocationUpdate.received_at)
        .where(DeliveryLocationUpdate.delivery_id == delivery.id)
        .order_by(DeliveryLocationUpdate.received_at.desc())
        .limit(1)
    )
    if last is not None and now - last < timedelta(seconds=settings.location_min_interval_seconds):
        raise LocationTooFrequentError(
            f"Send at most one location every {settings.location_min_interval_seconds} seconds."
        )
    session.add(
        DeliveryLocationUpdate(
            delivery_id=delivery.id,
            user_id=user.id,
            latitude=latitude,
            longitude=longitude,
            accuracy_m=accuracy_m,
            heading=heading,
            speed_mps=speed_mps,
            recorded_at=recorded_at,
            received_at=now,
        )
    )
    if maps is not None:
        _refresh_eta(settings, maps, delivery, LatLng(latitude, longitude), now)
    session.commit()
    return delivery


def _refresh_eta(
    settings: Settings, maps: MapsProvider, delivery: Delivery, here: LatLng, now: datetime
) -> None:
    """Geocode the drop-off once, then ask for a driving ETA at most every
    ETA_REFRESH_SECONDS (each Routes call is billed)."""
    if delivery.dropoff_latitude is None and delivery.geocode_attempted_at is None:
        delivery.geocode_attempted_at = now
        found = maps.geocode(delivery.dropoff_address)
        if found is not None:
            delivery.dropoff_latitude, delivery.dropoff_longitude = found.latitude, found.longitude
    if delivery.dropoff_latitude is None:
        return
    fresh = delivery.eta_computed_at is not None and (
        now - delivery.eta_computed_at < timedelta(seconds=settings.eta_refresh_seconds)
    )
    if fresh and delivery.eta_computed_at >= delivery.started_at:
        return
    estimate = maps.route(here, LatLng(delivery.dropoff_latitude, delivery.dropoff_longitude))
    delivery.eta_computed_at = now
    delivery.eta_seconds = estimate.duration_seconds if estimate else None
    delivery.eta_distance_m = estimate.distance_meters if estimate else None


# --- what watchers see ---------------------------------------------------------------------


def latest_location(session: Session, delivery: Delivery) -> DeliveryLocationUpdate | None:
    """The newest fix of the current trip (none from an earlier, failed attempt)."""
    if delivery.status != DeliveryStatus.EN_ROUTE or delivery.started_at is None:
        return None
    return session.scalar(
        select(DeliveryLocationUpdate)
        .where(
            DeliveryLocationUpdate.delivery_id == delivery.id,
            DeliveryLocationUpdate.received_at >= delivery.started_at,
        )
        .order_by(DeliveryLocationUpdate.recorded_at.desc())
        .limit(1)
    )


def _num(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def tracking_payload(session: Session, delivery: Delivery) -> dict[str, Any]:
    """The live view, identical for every authorised watcher (JSON-ready)."""
    booking_status = session.scalar(select(Booking.status).where(Booking.id == delivery.booking_id))
    location = latest_location(session, delivery)
    eta = None
    if (
        delivery.status == DeliveryStatus.EN_ROUTE
        and delivery.eta_seconds is not None
        and delivery.eta_computed_at is not None
        and delivery.started_at is not None
        and delivery.eta_computed_at >= delivery.started_at
    ):
        eta = {
            "seconds": delivery.eta_seconds,
            "distance_m": delivery.eta_distance_m,
            "computed_at": delivery.eta_computed_at.isoformat(),
            "arrives_at": (
                delivery.eta_computed_at + timedelta(seconds=delivery.eta_seconds)
            ).isoformat(),
        }
    return {
        "delivery_id": str(delivery.id),
        "status": delivery.status.value,
        "booking_status": booking_status.value,
        "scheduled_for": delivery.scheduled_for.isoformat() if delivery.scheduled_for else None,
        "tracking_active": delivery.status == DeliveryStatus.EN_ROUTE,
        "location": None
        if location is None
        else {
            "latitude": _num(location.latitude),
            "longitude": _num(location.longitude),
            "accuracy_m": _num(location.accuracy_m),
            "heading": _num(location.heading),
            "speed_mps": _num(location.speed_mps),
            "recorded_at": location.recorded_at.isoformat(),
            "received_at": location.received_at.isoformat(),
        },
        "eta": eta,
    }


def find_watchable(session: Session, user: User, delivery_id: uuid.UUID) -> Delivery | None:
    """The delivery if `user` may watch it: its renter, the assigned person, or an admin."""
    delivery = session.scalar(
        select(Delivery).where(Delivery.id == delivery_id).execution_options(populate_existing=True)
    )
    if delivery is None:
        return None
    if RoleName.ADMIN in {role.name for role in user.roles} or delivery.assigned_to_id == user.id:
        return delivery
    renter_id = session.scalar(select(Booking.renter_id).where(Booking.id == delivery.booking_id))
    return delivery if renter_id == user.id else None


def publish(hub: TrackingHub, session: Session, delivery_id: uuid.UUID, kind: str) -> None:
    """Tell live watchers about a change (`kind` is "location" or "status")."""
    delivery = session.scalar(
        select(Delivery).where(Delivery.id == delivery_id).execution_options(populate_existing=True)
    )
    if delivery is not None:
        hub.publish(delivery.id, {"type": kind, **tracking_payload(session, delivery)})


def publish_for_booking(hub: TrackingHub, session: Session, booking_id: uuid.UUID) -> None:
    """After a booking change (e.g. cancellation) that also changed its delivery."""
    delivery_id = session.scalar(select(Delivery.id).where(Delivery.booking_id == booking_id))
    if delivery_id is not None:
        publish(hub, session, delivery_id, "status")


# --- retention -------------------------------------------------------------------------------


def purge_old_locations(
    session: Session, settings: Settings, *, now: datetime | None = None
) -> int:
    """Delete location history older than LOCATION_RETENTION_DAYS (BR-7.5), never from a
    delivery that is still on its way."""
    cutoff = (now or _now()) - timedelta(days=settings.location_retention_days)
    en_route = select(Delivery.id).where(Delivery.status == DeliveryStatus.EN_ROUTE)
    result = session.execute(
        delete(DeliveryLocationUpdate).where(
            DeliveryLocationUpdate.received_at < cutoff,
            DeliveryLocationUpdate.delivery_id.not_in(en_route),
        )
    )
    session.commit()
    return result.rowcount
