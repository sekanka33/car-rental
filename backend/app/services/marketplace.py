"""Public marketplace: search, details, photos, availability and quotes.

Everything here starts from `publicly_listed_vehicles()`, so a vehicle that is not
approved, compliant, priced and owned by an active account is invisible (404).
Prices always come from the official price in effect now.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import Select, and_, exists, func, not_, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from app.core.errors import AppError, NotFoundError
from app.integrations.storage import DocumentStorage
from app.models import Booking, OwnerProfile, Vehicle, VehicleAvailabilityBlock, VehiclePrice
from app.models.enums import BLOCKING_BOOKING_STATUSES, FuelType, Province, Transmission
from app.services.pricing import PriceQuote, calculate_quote
from app.services.vehicles import publicly_listed_vehicles

MAX_WINDOW = timedelta(days=180)
MAX_RENTAL = timedelta(days=90)
SortOrder = Literal["price_asc", "price_desc", "newest"]


class InvalidPeriodError(AppError):
    status_code = 422
    code = "invalid_period"


@dataclass(frozen=True)
class SearchFilters:
    q: str | None = None
    city: str | None = None
    province: Province | None = None
    transmission: Transmission | None = None
    fuel_type: FuelType | None = None
    min_seats: int | None = None
    min_daily_rate: Decimal | None = None
    max_daily_rate: Decimal | None = None
    available_from: datetime | None = None
    available_to: datetime | None = None
    sort: SortOrder = "price_asc"


@dataclass(frozen=True, order=True)
class Period:
    start_at: datetime
    end_at: datetime


def _now() -> datetime:
    return datetime.now(UTC)


def _listed_with_price(now: datetime) -> tuple[Select, type[VehiclePrice]]:
    """Listed vehicles joined to the official price currently in effect."""
    latest = (
        select(VehiclePrice.vehicle_id, func.max(VehiclePrice.effective_from).label("effective"))
        .where(VehiclePrice.effective_from <= now)
        .group_by(VehiclePrice.vehicle_id)
        .subquery()
    )
    price = aliased(VehiclePrice)
    query = (
        publicly_listed_vehicles()
        .join(latest, latest.c.vehicle_id == Vehicle.id)
        .join(
            price,
            and_(
                price.vehicle_id == latest.c.vehicle_id, price.effective_from == latest.c.effective
            ),
        )
        .add_columns(price)
        .options(
            selectinload(Vehicle.images),
            selectinload(Vehicle.owner).selectinload(OwnerProfile.user),
        )
    )
    return query, price


def _overlaps(start: datetime, end: datetime):
    """Conditions: a reserving booking or an owner block overlaps [start, end)."""
    booked = exists().where(
        Booking.vehicle_id == Vehicle.id,
        Booking.status.in_(BLOCKING_BOOKING_STATUSES),
        Booking.start_at < end,
        Booking.end_at > start,
    )
    blocked = exists().where(
        VehicleAvailabilityBlock.vehicle_id == Vehicle.id,
        VehicleAvailabilityBlock.start_at < end,
        VehicleAvailabilityBlock.end_at > start,
    )
    return or_(booked, blocked)


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def validate_period(
    start: datetime, end: datetime, *, limit: timedelta, allow_past: bool = False
) -> None:
    if start.tzinfo is None or end.tzinfo is None:
        raise InvalidPeriodError("Dates must include a timezone.")
    if end <= start:
        raise InvalidPeriodError("The end must be after the start.")
    if end - start > limit:
        raise InvalidPeriodError(f"The period can be at most {limit.days} days.")
    if not allow_past and start < _now() - timedelta(minutes=5):
        raise InvalidPeriodError("The start must not be in the past.")


def search(
    session: Session, filters: SearchFilters, *, limit: int, offset: int
) -> tuple[list[tuple[Vehicle, VehiclePrice]], int]:
    now = _now()
    query, price = _listed_with_price(now)
    conditions = []
    if filters.q:
        pattern = f"%{_escape_like(filters.q.strip())}%"
        conditions.append(
            or_(
                Vehicle.make.ilike(pattern, escape="\\"),
                Vehicle.model.ilike(pattern, escape="\\"),
                Vehicle.city.ilike(pattern, escape="\\"),
                func.concat(Vehicle.make, " ", Vehicle.model).ilike(pattern, escape="\\"),
            )
        )
    if filters.city:
        conditions.append(func.lower(Vehicle.city) == filters.city.strip().lower())
    if filters.province:
        conditions.append(Vehicle.province == filters.province.value)
    if filters.transmission:
        conditions.append(Vehicle.transmission == filters.transmission)
    if filters.fuel_type:
        conditions.append(Vehicle.fuel_type == filters.fuel_type)
    if filters.min_seats:
        conditions.append(Vehicle.seats >= filters.min_seats)
    if filters.min_daily_rate is not None:
        conditions.append(price.daily_rate >= filters.min_daily_rate)
    if filters.max_daily_rate is not None:
        conditions.append(price.daily_rate <= filters.max_daily_rate)
    if filters.available_from or filters.available_to:
        if not (filters.available_from and filters.available_to):
            raise InvalidPeriodError("Give both available_from and available_to.")
        validate_period(filters.available_from, filters.available_to, limit=MAX_RENTAL)
        conditions.append(not_(_overlaps(filters.available_from, filters.available_to)))
    if conditions:
        query = query.where(*conditions)

    total = session.scalar(
        select(func.count()).select_from(query.with_only_columns(Vehicle.id).subquery())
    )
    order = {
        "price_asc": (price.daily_rate.asc(), Vehicle.id),
        "price_desc": (price.daily_rate.desc(), Vehicle.id),
        "newest": (Vehicle.approved_at.desc(), Vehicle.id),
    }[filters.sort]
    rows = session.execute(query.order_by(*order).limit(limit).offset(offset)).all()
    return [(row[0], row[1]) for row in rows], total or 0


def get_listed(session: Session, vehicle_id: uuid.UUID) -> tuple[Vehicle, VehiclePrice]:
    query, _ = _listed_with_price(_now())
    row = session.execute(query.where(Vehicle.id == vehicle_id)).first()
    if row is None:
        raise NotFoundError("Vehicle not found.")
    return row[0], row[1]


def read_public_photo(
    session: Session, storage: DocumentStorage, vehicle_id: uuid.UUID, photo_id: uuid.UUID
) -> tuple[str, bytes]:
    vehicle, _ = get_listed(session, vehicle_id)
    image = next((i for i in vehicle.images if i.id == photo_id), None)
    if image is None:
        raise NotFoundError("Photo not found.")
    return image.content_type, storage.read(image.storage_key)


def unavailable_periods(
    session: Session, vehicle_id: uuid.UUID, start: datetime, end: datetime
) -> list[Period]:
    """Booked or blocked periods overlapping the window (no reasons, no renter details)."""
    validate_period(start, end, limit=MAX_WINDOW, allow_past=True)
    get_listed(session, vehicle_id)
    bookings = session.execute(
        select(Booking.start_at, Booking.end_at).where(
            Booking.vehicle_id == vehicle_id,
            Booking.status.in_(BLOCKING_BOOKING_STATUSES),
            Booking.start_at < end,
            Booking.end_at > start,
        )
    ).all()
    blocks = session.execute(
        select(VehicleAvailabilityBlock.start_at, VehicleAvailabilityBlock.end_at).where(
            VehicleAvailabilityBlock.vehicle_id == vehicle_id,
            VehicleAvailabilityBlock.start_at < end,
            VehicleAvailabilityBlock.end_at > start,
        )
    ).all()
    return _merge(sorted(Period(s, e) for s, e in [*bookings, *blocks]))


def _merge(periods: list[Period]) -> list[Period]:
    merged: list[Period] = []
    for period in periods:
        if merged and period.start_at <= merged[-1].end_at:
            last = merged[-1]
            merged[-1] = Period(last.start_at, max(last.end_at, period.end_at))
        else:
            merged.append(period)
    return merged


def quote(
    session: Session, vehicle_id: uuid.UUID, start: datetime, end: datetime
) -> tuple[PriceQuote, bool]:
    """Price for the period at the official price, and whether the vehicle is free then."""
    validate_period(start, end, limit=MAX_RENTAL)
    _, price = get_listed(session, vehicle_id)
    taken = session.scalar(select(_overlaps(start, end)).where(Vehicle.id == vehicle_id))
    return calculate_quote(price, start, end), not taken
