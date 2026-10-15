"""Platform-wide aggregates for the administrator dashboard (FR-35). Read-only.

Money here is on a cash basis: a payment counts in the month it was received (`paid_at`), a
refund in the month it was processed. (Owner earnings, by contrast, count by rental start.)
Months are calendar months in South African time.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Booking,
    Delivery,
    DeliveryException,
    Payment,
    Refund,
    Role,
    User,
    UserRole,
    Vehicle,
    VerificationSubmission,
)
from app.models.enums import (
    BookingStatus,
    DeliveryStatus,
    RefundStatus,
    RoleName,
    SubmissionStatus,
    UserStatus,
    VehicleStatus,
)
from app.services.verification import SA_TIMEZONE, today_in_south_africa

ZERO = Decimal("0.00")
S = BookingStatus
UNDER_WAY = (S.IN_TRANSIT, S.DELIVERED, S.ACTIVE_RENTAL, S.RETURN_PENDING)
UPCOMING = (S.CONFIRMED, S.DELIVERY_SCHEDULED)
MAX_MONTHS = 24


def _sa_month(column):
    """'YYYY-MM' of a timestamp column in South African time."""
    return func.to_char(func.timezone(SA_TIMEZONE.key, column), "YYYY-MM")


def _month_start(year: int, month: int) -> datetime:
    return datetime(year, month, 1, tzinfo=SA_TIMEZONE)


def _shift(year: int, month: int, by: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + by
    return index // 12, index % 12 + 1


def _counts(session: Session, query: Select) -> dict:
    return {key: count for key, count in session.execute(query).all()}


# --- overview ----------------------------------------------------------------------------------


@dataclass
class Overview:
    verifications_pending: int
    vehicles_pending_approval: int
    deliveries_needing_attention: int
    refunds_pending: int
    refunds_failed: int
    bookings_upcoming: int
    bookings_under_way: int
    users_by_role: dict[RoleName, int]
    users_suspended: int
    vehicles_by_status: dict[VehicleStatus, int]
    bookings_by_status: dict[BookingStatus, int]
    month: str
    month_collected: Decimal
    month_refunded: Decimal


def overview(session: Session, *, today: date | None = None) -> Overview:
    today = today or today_in_south_africa()
    month_start = _month_start(today.year, today.month)
    next_start = _month_start(*_shift(today.year, today.month, 1))

    vehicles = _counts(session, select(Vehicle.status, func.count()).group_by(Vehicle.status))
    bookings = _counts(session, select(Booking.status, func.count()).group_by(Booking.status))
    roles = _counts(
        session,
        select(Role.name, func.count())
        .join(UserRole, UserRole.role_id == Role.id)
        .group_by(Role.name),
    )
    refunds = _counts(session, select(Refund.status, func.count()).group_by(Refund.status))
    open_exception = (
        select(DeliveryException.id)
        .where(
            DeliveryException.delivery_id == Delivery.id,
            DeliveryException.resolved_at.is_(None),
        )
        .exists()
    )
    attention = session.scalar(
        select(func.count())
        .select_from(Delivery)
        .where(
            Delivery.status.not_in([DeliveryStatus.CANCELLED]),
            or_(Delivery.status == DeliveryStatus.FAILED, open_exception),
        )
    )
    collected = session.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.paid_at >= month_start, Payment.paid_at < next_start
        )
    )
    refunded = session.scalar(
        select(func.coalesce(func.sum(Refund.amount), 0)).where(
            Refund.status == RefundStatus.PROCESSED,
            Refund.processed_at >= month_start,
            Refund.processed_at < next_start,
        )
    )
    return Overview(
        verifications_pending=session.scalar(
            select(func.count())
            .select_from(VerificationSubmission)
            .where(VerificationSubmission.status == SubmissionStatus.PENDING)
        )
        or 0,
        vehicles_pending_approval=vehicles.get(VehicleStatus.PENDING_APPROVAL, 0),
        deliveries_needing_attention=attention or 0,
        refunds_pending=refunds.get(RefundStatus.PENDING, 0),
        refunds_failed=refunds.get(RefundStatus.FAILED, 0),
        bookings_upcoming=sum(bookings.get(s, 0) for s in UPCOMING),
        bookings_under_way=sum(bookings.get(s, 0) for s in UNDER_WAY),
        users_by_role={role: roles.get(role, 0) for role in RoleName},
        users_suspended=session.scalar(
            select(func.count()).select_from(User).where(User.status == UserStatus.SUSPENDED)
        )
        or 0,
        vehicles_by_status={status: vehicles.get(status, 0) for status in VehicleStatus},
        bookings_by_status={status: bookings.get(status, 0) for status in BookingStatus},
        month=today.strftime("%Y-%m"),
        month_collected=Decimal(collected).quantize(ZERO),
        month_refunded=Decimal(refunded).quantize(ZERO),
    )


# --- monthly series ----------------------------------------------------------------------------


@dataclass
class MonthRow:
    month: str
    bookings_confirmed: int = 0
    collected: Decimal = ZERO
    refunded: Decimal = ZERO
    new_renters: int = 0
    new_owners: int = 0

    @property
    def net(self) -> Decimal:
        return self.collected - self.refunded


def monthly(session: Session, *, months: int = 12, today: date | None = None) -> list[MonthRow]:
    """The last `months` calendar months (oldest first), including the current one. Months
    without activity are included with zeros, so charts have no gaps."""
    today = today or today_in_south_africa()
    months = max(1, min(months, MAX_MONTHS))
    first = _shift(today.year, today.month, -(months - 1))
    since = _month_start(*first)
    rows = {
        f"{y:04d}-{m:02d}": MonthRow(f"{y:04d}-{m:02d}")
        for y, m in (_shift(*first, i) for i in range(months))
    }

    def each(query, apply):
        for month, value in session.execute(query).all():
            if month in rows:
                apply(rows[month], value)

    confirmed = _sa_month(Booking.confirmed_at)
    each(
        select(confirmed, func.count()).where(Booking.confirmed_at >= since).group_by(confirmed),
        lambda row, v: setattr(row, "bookings_confirmed", v),
    )
    paid = _sa_month(Payment.paid_at)
    each(
        select(paid, func.sum(Payment.amount)).where(Payment.paid_at >= since).group_by(paid),
        lambda row, v: setattr(row, "collected", Decimal(v).quantize(ZERO)),
    )
    processed = _sa_month(Refund.processed_at)
    each(
        select(processed, func.sum(Refund.amount))
        .where(Refund.status == RefundStatus.PROCESSED, Refund.processed_at >= since)
        .group_by(processed),
        lambda row, v: setattr(row, "refunded", Decimal(v).quantize(ZERO)),
    )
    for role, attribute in ((RoleName.RENTER, "new_renters"), (RoleName.OWNER, "new_owners")):
        created = _sa_month(User.created_at)
        each(
            select(created, func.count())
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.name == role, User.created_at >= since)
            .group_by(created),
            lambda row, v, a=attribute: setattr(row, a, v),
        )
    return list(rows.values())


# --- audit log ---------------------------------------------------------------------------------


def list_audit_logs(
    session: Session,
    *,
    entity_type: str | None,
    entity_id: str | None,
    actor_user_id,
    action: str | None,
    limit: int,
    offset: int,
) -> tuple[list[tuple[AuditLog, User | None]], int]:
    """Newest first, with the acting user (None for system actions). `action` matches a prefix,
    e.g. "delivery." for every delivery action."""
    conditions = []
    if entity_type:
        conditions.append(AuditLog.entity_type == entity_type)
    if entity_id:
        conditions.append(AuditLog.entity_id == entity_id)
    if actor_user_id:
        conditions.append(AuditLog.actor_user_id == actor_user_id)
    if action:
        conditions.append(AuditLog.action.startswith(action, autoescape=True))
    total = session.scalar(select(func.count()).select_from(AuditLog).where(*conditions)) or 0
    rows = session.execute(
        select(AuditLog, User)
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        .where(*conditions)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [(log, user) for log, user in rows], total
