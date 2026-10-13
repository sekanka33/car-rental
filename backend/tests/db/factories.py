"""Helpers that insert valid rows for database tests (test data only)."""

import itertools
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Booking, OwnerProfile, User, Vehicle, VehiclePrice
from app.models.enums import BookingStatus, FuelType, Transmission

_counter = itertools.count(1)
VIN_CHARS = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"


def _next() -> int:
    return next(_counter)


def unique_vin() -> str:
    n = uuid.uuid4().int
    return "".join(VIN_CHARS[(n >> (5 * i)) % len(VIN_CHARS)] for i in range(17))


def create_user(session: Session, **overrides: object) -> User:
    n = _next()
    values: dict[str, object] = {
        "email": f"user{n}-{uuid.uuid4().hex[:6]}@example.com",
        "password_hash": "not-a-real-hash",
        "full_name": f"Test User {n}",
    }
    values.update(overrides)
    user = User(**values)
    session.add(user)
    session.flush()
    return user


def create_vehicle(session: Session, **overrides: object) -> Vehicle:
    owner = OwnerProfile(user_id=create_user(session).id)
    session.add(owner)
    session.flush()
    n = _next()
    values: dict[str, object] = {
        "owner_id": owner.id,
        "make": "Toyota",
        "model": "Corolla",
        "year": 2022,
        "registration_number": f"TST{n:04d}GP",
        "vin": unique_vin(),
        "transmission": Transmission.AUTOMATIC,
        "fuel_type": FuelType.PETROL,
        "seats": 5,
        "city": "Johannesburg",
        "province": "Gauteng",
    }
    values.update(overrides)
    vehicle = Vehicle(**values)
    session.add(vehicle)
    session.flush()
    return vehicle


def create_price(session: Session, vehicle: Vehicle, **overrides: object) -> VehiclePrice:
    admin = create_user(session)
    values: dict[str, object] = {
        "vehicle_id": vehicle.id,
        "daily_rate": Decimal("650.00"),
        "delivery_fee": Decimal("150.00"),
        "deposit_amount": Decimal("2000.00"),
        "created_by_id": admin.id,
    }
    values.update(overrides)
    price = VehiclePrice(**values)
    session.add(price)
    session.flush()
    return price


BASE_START = datetime(2030, 1, 10, 9, 0, tzinfo=UTC)


def booking_values(
    renter: User,
    price: VehiclePrice,
    start: datetime = BASE_START,
    days: int = 3,
    status: BookingStatus = BookingStatus.CONFIRMED,
) -> dict[str, object]:
    rental_amount = price.daily_rate * days
    return {
        "reference": f"BK{_next():06d}{uuid.uuid4().hex[:4].upper()}",
        "renter_id": renter.id,
        "vehicle_id": price.vehicle_id,
        "vehicle_price_id": price.id,
        "start_at": start,
        "end_at": start + timedelta(days=days),
        "status": status,
        "hold_expires_at": datetime.now(UTC) + timedelta(minutes=15)
        if status == BookingStatus.PENDING_PAYMENT
        else None,
        "cancelled_at": start - timedelta(days=1) if status == BookingStatus.CANCELLED else None,
        "daily_rate": price.daily_rate,
        "rental_days": days,
        "rental_amount": rental_amount,
        "delivery_fee": price.delivery_fee,
        "deposit_amount": price.deposit_amount,
        "total_amount": rental_amount + price.delivery_fee,
    }


def create_booking(session: Session, price: VehiclePrice, **kwargs: object) -> Booking:
    renter = kwargs.pop("renter", None) or create_user(session)
    booking = Booking(**booking_values(renter, price, **kwargs))  # type: ignore[arg-type]
    session.add(booking)
    session.flush()
    return booking
