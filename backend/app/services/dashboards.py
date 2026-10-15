"""Read-only views for the renter and owner dashboards (FR-34).

Earnings (OPEN-1 default): the platform collects every payment as merchant of record and
settles owners outside the system, with no commission agreed yet. An owner's earnings are
therefore shown GROSS: money collected for bookings of their cars, minus refunds (pending or
processed). Each booking counts in the month its rental starts (Africa/Johannesburg).
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Booking, Delivery, Payment, User, Vehicle
from app.models.enums import BookingStatus, DeliveryStatus, VehicleDocumentType, VehicleStatus
from app.services import vehicles as vehicle_service
from app.services.bookings import expire_stale_holds
from app.services.payments import refunded_total
from app.services.verification import SA_TIMEZONE, today_in_south_africa

ZERO = Decimal("0.00")
S = BookingStatus
# Unpaid or lapsed holds are not the owner's business: only bookings that were paid for.
OWNER_VISIBLE = frozenset(set(S) - {S.PENDING_PAYMENT, S.EXPIRED})
UNDER_WAY = frozenset({S.IN_TRANSIT, S.DELIVERED, S.ACTIVE_RENTAL, S.RETURN_PENDING})
UPCOMING = frozenset({S.CONFIRMED, S.DELIVERY_SCHEDULED})
FINISHED = frozenset({S.COMPLETED, S.CANCELLED})
OwnerScope = Literal["upcoming", "active", "past", "all"]
EXPIRY_WARNING_DAYS = 30


def _now() -> datetime:
    return datetime.now(UTC)


# --- owner bookings --------------------------------------------------------------------------


def list_owner_bookings(
    session: Session, user: User, *, scope: OwnerScope, limit: int, offset: int
) -> list[Booking]:
    """Paid-for bookings of the owner's cars. `upcoming` and `active` run soonest first,
    `past` and `all` newest first."""
    owner = vehicle_service.get_owner_profile(session, user)
    query = (
        select(Booking)
        .join(Vehicle, Vehicle.id == Booking.vehicle_id)
        .options(selectinload(Booking.vehicle), selectinload(Booking.renter))
        .where(Vehicle.owner_id == owner.id, Booking.status.in_(OWNER_VISIBLE))
    )
    if scope == "upcoming":
        query = query.where(Booking.status.in_(UPCOMING)).order_by(Booking.start_at)
    elif scope == "active":
        query = query.where(Booking.status.in_(UNDER_WAY)).order_by(Booking.start_at)
    elif scope == "past":
        query = query.where(Booking.status.in_(FINISHED)).order_by(Booking.start_at.desc())
    else:
        query = query.order_by(Booking.start_at.desc())
    return list(session.scalars(query.limit(limit).offset(offset)))


def deliveries_by_booking(
    session: Session, booking_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[uuid.UUID, DeliveryStatus]]:
    """booking id -> (delivery id, delivery status)."""
    if not booking_ids:
        return {}
    rows = session.execute(
        select(Delivery.booking_id, Delivery.id, Delivery.status).where(
            Delivery.booking_id.in_(booking_ids)
        )
    )
    return {booking_id: (delivery_id, status) for booking_id, delivery_id, status in rows}


# --- owner earnings --------------------------------------------------------------------------


@dataclass
class EarningLine:
    booking: Booking
    collected: Decimal
    refunded: Decimal

    @property
    def net(self) -> Decimal:
        return self.collected - self.refunded

    @property
    def month(self) -> str:
        return self.booking.start_at.astimezone(SA_TIMEZONE).strftime("%Y-%m")


@dataclass
class MonthTotal:
    month: str
    collected: Decimal = ZERO
    refunded: Decimal = ZERO
    bookings: int = 0

    @property
    def net(self) -> Decimal:
        return self.collected - self.refunded


@dataclass
class Earnings:
    year: int
    lines: list[EarningLine]
    months: list[MonthTotal] = field(default_factory=list)

    @property
    def collected(self) -> Decimal:
        return sum((line.collected for line in self.lines), ZERO)

    @property
    def refunded(self) -> Decimal:
        return sum((line.refunded for line in self.lines), ZERO)

    @property
    def net(self) -> Decimal:
        return self.collected - self.refunded


def _sa_year_bounds(year: int) -> tuple[datetime, datetime]:
    start = datetime(year, 1, 1, tzinfo=SA_TIMEZONE)
    return start, datetime(year + 1, 1, 1, tzinfo=SA_TIMEZONE)


def owner_earnings(session: Session, user: User, *, year: int) -> Earnings:
    """Gross money collected for the owner's cars, per booking and per month of `year`."""
    owner = vehicle_service.get_owner_profile(session, user)
    start, end = _sa_year_bounds(year)
    payments = session.scalars(
        select(Payment)
        .join(Booking, Booking.id == Payment.booking_id)
        .join(Vehicle, Vehicle.id == Booking.vehicle_id)
        .options(
            selectinload(Payment.refunds),
            selectinload(Payment.booking).selectinload(Booking.vehicle),
        )
        .where(
            Vehicle.owner_id == owner.id,
            Payment.paid_at.is_not(None),  # money actually received
            Booking.start_at >= start,
            Booking.start_at < end,
        )
    )
    by_booking: dict[uuid.UUID, EarningLine] = {}
    for payment in payments:
        line = by_booking.setdefault(payment.booking_id, EarningLine(payment.booking, ZERO, ZERO))
        line.collected += payment.amount
        line.refunded += refunded_total(payment)
    lines = sorted(by_booking.values(), key=lambda line: line.booking.start_at, reverse=True)

    months: dict[str, MonthTotal] = {}
    for line in lines:
        total = months.setdefault(line.month, MonthTotal(line.month))
        total.collected += line.collected
        total.refunded += line.refunded
        total.bookings += 1
    return Earnings(year, lines, sorted(months.values(), key=lambda m: m.month))


# --- owner summary ----------------------------------------------------------------------------


@dataclass
class ExpiringDocument:
    vehicle: Vehicle
    document_type: VehicleDocumentType
    expiry_date: date


@dataclass
class OwnerSummary:
    vehicles_by_status: dict[VehicleStatus, int]
    upcoming_bookings: int
    active_rentals: int
    deliveries_to_do: int
    returns_to_record: int
    month_net: Decimal
    year_net: Decimal
    expiring_documents: list[ExpiringDocument]
    next_booking: Booking | None


def owner_summary(session: Session, user: User) -> OwnerSummary:
    owner = vehicle_service.get_owner_profile(session, user)
    if expire_stale_holds(session):
        session.commit()
    vehicles = vehicle_service.list_owned_vehicles(session, user)
    by_status = {status: 0 for status in VehicleStatus}
    for vehicle in vehicles:
        by_status[vehicle.status] += 1

    owned = select(Vehicle.id).where(Vehicle.owner_id == owner.id)
    counts = dict(
        session.execute(
            select(Booking.status, func.count())
            .where(Booking.vehicle_id.in_(owned))
            .group_by(Booking.status)
        ).all()
    )
    upcoming = sum(counts.get(s, 0) for s in UPCOMING)
    active = sum(counts.get(s, 0) for s in UNDER_WAY)

    # What the owner has to do: deliveries assigned to them that are not finished, and
    # handed-over cars whose return has not been recorded yet.
    deliveries_to_do = session.scalar(
        select(func.count())
        .select_from(Delivery)
        .where(
            Delivery.assigned_to_id == user.id,
            Delivery.status.in_(
                [DeliveryStatus.PENDING_SCHEDULE, DeliveryStatus.SCHEDULED, DeliveryStatus.EN_ROUTE]
            ),
        )
    )
    returns_to_record = session.scalar(
        select(func.count())
        .select_from(Delivery)
        .join(Booking, Booking.id == Delivery.booking_id)
        .where(
            Delivery.assigned_to_id == user.id,
            Delivery.status == DeliveryStatus.DELIVERED,
            Booking.status.in_([S.DELIVERED, S.ACTIVE_RENTAL, S.RETURN_PENDING]),
        )
    )

    today = today_in_south_africa()
    earnings = owner_earnings(session, user, year=today.year)
    this_month = today.strftime("%Y-%m")
    month_net = next((m.net for m in earnings.months if m.month == this_month), ZERO)

    warn_until = today + timedelta(days=EXPIRY_WARNING_DAYS)
    expiring = [
        ExpiringDocument(vehicle, doc_type, document.expiry_date)
        for vehicle in vehicles
        if vehicle.status in (VehicleStatus.APPROVED, VehicleStatus.UNAVAILABLE)
        for doc_type, document in vehicle_service.current_documents(vehicle).items()
        if document.expiry_date is not None and document.expiry_date <= warn_until
    ]
    expiring.sort(key=lambda e: e.expiry_date)

    next_booking = session.scalar(
        select(Booking)
        .options(selectinload(Booking.vehicle), selectinload(Booking.renter))
        .where(
            Booking.vehicle_id.in_(owned),
            or_(
                Booking.status.in_(UNDER_WAY),
                and_(Booking.status.in_(UPCOMING), Booking.end_at > _now()),
            ),
        )
        .order_by(Booking.start_at)
        .limit(1)
    )
    return OwnerSummary(
        vehicles_by_status=by_status,
        upcoming_bookings=upcoming,
        active_rentals=active,
        deliveries_to_do=deliveries_to_do or 0,
        returns_to_record=returns_to_record or 0,
        month_net=month_net,
        year_net=earnings.net,
        expiring_documents=expiring,
        next_booking=next_booking,
    )


# --- renter payments ---------------------------------------------------------------------------


def list_renter_payments(
    session: Session, renter: User, *, limit: int, offset: int
) -> list[Payment]:
    """Every payment attempt the renter made, newest first, with refunds."""
    return list(
        session.scalars(
            select(Payment)
            .join(Booking, Booking.id == Payment.booking_id)
            .options(
                selectinload(Payment.refunds),
                selectinload(Payment.booking).selectinload(Booking.vehicle),
            )
            .where(Booking.renter_id == renter.id)
            .order_by(Payment.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )
