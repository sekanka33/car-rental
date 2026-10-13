"""Official rental pricing (administrator-controlled) and rental price calculation.

All amounts are exact `Decimal` rand values (ZAR, VAT-inclusive until OPEN-6 is decided).
Prices are append-only: setting a price adds a row; the current price is the row with the
latest `effective_from` that is not in the future. Bookings copy the calculated breakdown,
so later price changes never alter an existing booking (BR-4.6).
"""

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, PermissionDeniedError
from app.db.base import CURRENCY_ZAR
from app.models import User, VehiclePrice
from app.services.audit import record_audit
from app.services.vehicles import get_vehicle

CENT = Decimal("0.01")
BILLING_PERIOD = timedelta(hours=24)


class PricingError(AppError):
    status_code = 422
    code = "invalid_price"


class NoActivePriceError(AppError):
    status_code = 409
    code = "no_active_price"


def to_money(value: Decimal) -> Decimal:
    """Round half up to cents (BR-4.5)."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PriceQuote:
    vehicle_price_id: uuid.UUID
    daily_rate: Decimal
    rental_days: int
    rental_amount: Decimal
    delivery_fee: Decimal
    deposit_amount: Decimal
    total_amount: Decimal  # rental + delivery; the deposit is held separately
    currency: str = CURRENCY_ZAR


def billable_days(start: datetime, end: datetime) -> int:
    """Each started 24-hour period is one billable day (BR-4.4)."""
    if start.tzinfo is None or end.tzinfo is None:
        raise PricingError("Rental times must include a timezone.")
    if end <= start:
        raise PricingError("The rental must end after it starts.")
    return math.ceil((end - start) / BILLING_PERIOD)


def calculate_quote(price: VehiclePrice, start: datetime, end: datetime) -> PriceQuote:
    """Price breakdown for a rental, from an official price row only."""
    days = billable_days(start, end)
    rental = to_money(price.daily_rate * days)
    delivery = to_money(price.delivery_fee)
    return PriceQuote(
        vehicle_price_id=price.id,
        daily_rate=to_money(price.daily_rate),
        rental_days=days,
        rental_amount=rental,
        delivery_fee=delivery,
        deposit_amount=to_money(price.deposit_amount),
        total_amount=rental + delivery,
    )


def current_price(
    session: Session, vehicle_id: uuid.UUID, at: datetime | None = None
) -> VehiclePrice | None:
    at = at or datetime.now(UTC)
    return session.scalar(
        select(VehiclePrice)
        .where(VehiclePrice.vehicle_id == vehicle_id, VehiclePrice.effective_from <= at)
        .order_by(VehiclePrice.effective_from.desc())
        .limit(1)
    )


def require_current_price(
    session: Session, vehicle_id: uuid.UUID, at: datetime | None = None
) -> VehiclePrice:
    price = current_price(session, vehicle_id, at)
    if price is None:
        raise NoActivePriceError("This vehicle does not have an official price yet.")
    return price


def price_history(session: Session, vehicle_id: uuid.UUID) -> list[VehiclePrice]:
    get_vehicle(session, vehicle_id)  # 404 for unknown vehicles
    return list(
        session.scalars(
            select(VehiclePrice)
            .where(VehiclePrice.vehicle_id == vehicle_id)
            .order_by(VehiclePrice.effective_from.desc())
        )
    )


def _price_snapshot(price: VehiclePrice | None) -> dict[str, str] | None:
    if price is None:
        return None
    return {
        "daily_rate": str(price.daily_rate),
        "delivery_fee": str(price.delivery_fee),
        "deposit_amount": str(price.deposit_amount),
    }


def set_official_price(
    session: Session,
    *,
    admin: User,
    vehicle_id: uuid.UUID,
    daily_rate: Decimal,
    delivery_fee: Decimal,
    deposit_amount: Decimal,
    change_reason: str,
    effective_from: datetime | None = None,
) -> VehiclePrice:
    """Add a new official price (never edits an old one). Audited with old and new values."""
    vehicle = get_vehicle(session, vehicle_id, for_update=True)
    if vehicle.owner.user_id == admin.id:
        raise PermissionDeniedError("You cannot set the price of your own vehicle.")
    now = datetime.now(UTC)
    effective = effective_from or now
    if effective < now - timedelta(minutes=1):
        raise PricingError("Prices cannot be backdated; effective_from must be now or later.")

    previous = current_price(session, vehicle.id, now)
    price = VehiclePrice(
        vehicle_id=vehicle.id,
        daily_rate=to_money(daily_rate),
        delivery_fee=to_money(delivery_fee),
        deposit_amount=to_money(deposit_amount),
        currency=CURRENCY_ZAR,
        effective_from=effective,
        created_by_id=admin.id,
        change_reason=change_reason,
    )
    session.add(price)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise PricingError(
            "A price already takes effect at exactly this time for this vehicle."
        ) from exc
    record_audit(
        session,
        actor_id=admin.id,
        action="vehicle.price_set",
        entity_type="vehicle",
        entity_id=vehicle.id,
        changes={
            "price_id": str(price.id),
            "old": _price_snapshot(previous),
            "new": _price_snapshot(price),
            "effective_from": effective.isoformat(),
            "reason": change_reason,
        },
    )
    session.commit()
    return price


def quote_for_vehicle(
    session: Session, vehicle_id: uuid.UUID, start: datetime, end: datetime
) -> PriceQuote:
    """Quote using the official price in force now. Raises if the vehicle has no price."""
    get_vehicle(session, vehicle_id)  # 404 for unknown vehicles
    return calculate_quote(require_current_price(session, vehicle_id), start, end)
