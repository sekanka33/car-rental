"""Full-refresh ETL for privacy-safe monthly platform aggregates."""

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, NoReturn

from sqlalchemy import Date, Numeric, String, cast, delete, func, literal, select, union_all
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Booking, MonthlyPlatformAnalytics, Payment, Refund
from app.models.enums import BookingStatus, PaymentStatus, RefundStatus
from app.services.verification import SA_TIMEZONE

logger = logging.getLogger(__name__)
ZERO = Decimal("0.00")
Source = Literal["booking", "payment", "refund"]
BOOKING_STATUSES = {member.value for member in BookingStatus}
PAYMENT_STATUSES = {member.value for member in PaymentStatus}
REFUND_STATUSES = {member.value for member in RefundStatus}


class PipelineDataQualityError(ValueError):
    """A source row violates a required quality rule; the entire refresh is rejected."""


@dataclass
class _MonthlyTotals:
    booking_status_counts: Counter[str] = field(default_factory=Counter)
    cash_collected: Decimal = ZERO
    cash_refunded: Decimal = ZERO


@dataclass(frozen=True)
class RefreshSummary:
    bookings_extracted: int
    payments_extracted: int
    refunds_extracted: int
    months_loaded: int


def _fail(source: Source, record_id: str, reason: str) -> NoReturn:
    raise PipelineDataQualityError(f"Invalid {source} record {record_id}: {reason}")


def _valid_amount(source: Source, record_id: str, amount: Decimal | None) -> Decimal:
    if amount is None or not amount.is_finite() or amount <= 0:
        _fail(source, record_id, "amount must be a finite positive value")
    return amount


def _source_rows():
    """A single UNION ALL statement gives all three source scans one MVCC snapshot.

    There are deliberately no joins: booking counts, payments, and refunds stay at their
    own source grain and cannot multiply one another's totals.
    """
    booking_rows = select(
        literal("booking", type_=String()).label("source"),
        cast(Booking.id, String).label("record_id"),
        cast(Booking.status, String).label("status"),
        cast(
            func.date_trunc("month", func.timezone(SA_TIMEZONE.key, Booking.created_at)),
            Date,
        ).label("month_start"),
        literal(None, type_=Numeric(12, 2)).label("amount"),
        literal(None, type_=String(3)).label("currency"),
    )
    payment_rows = select(
        literal("payment", type_=String()).label("source"),
        cast(Payment.id, String).label("record_id"),
        cast(Payment.status, String).label("status"),
        cast(
            func.date_trunc("month", func.timezone(SA_TIMEZONE.key, Payment.paid_at)),
            Date,
        ).label("month_start"),
        Payment.amount.label("amount"),
        Payment.currency.label("currency"),
    )
    refund_rows = select(
        literal("refund", type_=String()).label("source"),
        cast(Refund.id, String).label("record_id"),
        cast(Refund.status, String).label("status"),
        cast(
            func.date_trunc("month", func.timezone(SA_TIMEZONE.key, Refund.processed_at)),
            Date,
        ).label("month_start"),
        Refund.amount.label("amount"),
        Refund.currency.label("currency"),
    )
    return union_all(booking_rows, payment_rows, refund_rows)


def refresh_monthly_analytics(session: Session) -> RefreshSummary:
    """Extract, validate, transform, then atomically replace the monthly snapshot.

    The caller owns the transaction and must commit only after this function succeeds.
    The table contains derived information only; operational booking/payment records are
    never changed. Database primary and foreign keys provide source uniqueness/references.
    """
    monthly: dict[date, _MonthlyTotals] = defaultdict(_MonthlyTotals)
    bookings_extracted = 0
    payments_extracted = 0
    refunds_extracted = 0

    for source, record_id, status, month_start, amount, currency in session.execute(
        _source_rows()
    ).yield_per(1000):
        if source == "booking":
            bookings_extracted += 1
            if status not in BOOKING_STATUSES:
                _fail("booking", record_id, f"unknown booking status {status!r}")
            if month_start is None:
                _fail("booking", record_id, "created_at is required")
            monthly[month_start].booking_status_counts[status] += 1
            continue

        if source == "payment":
            payments_extracted += 1
            if status not in PAYMENT_STATUSES:
                _fail("payment", record_id, f"unknown payment status {status!r}")
            _valid_amount("payment", record_id, amount)
            if currency != "ZAR":
                _fail("payment", record_id, "currency must be ZAR")
            if status == PaymentStatus.SUCCEEDED.value and month_start is None:
                _fail("payment", record_id, "a succeeded payment requires paid_at")
            if month_start is not None:
                monthly[month_start].cash_collected += amount
            continue

        refunds_extracted += 1
        if status not in REFUND_STATUSES:
            _fail("refund", record_id, f"unknown refund status {status!r}")
        _valid_amount("refund", record_id, amount)
        if currency != "ZAR":
            _fail("refund", record_id, "currency must be ZAR")
        if status == RefundStatus.PROCESSED.value:
            if month_start is None:
                _fail("refund", record_id, "a processed refund requires processed_at")
            monthly[month_start].cash_refunded += amount

    values = []
    for month_start, totals in sorted(monthly.items()):
        status_counts = {
            member.value: totals.booking_status_counts[member.value] for member in BookingStatus
        }
        values.append(
            {
                "month_start": month_start,
                "bookings_created": sum(status_counts.values()),
                "bookings_by_current_status": status_counts,
                "cash_collected": totals.cash_collected,
                "cash_refunded": totals.cash_refunded,
                "net_cash": totals.cash_collected - totals.cash_refunded,
                "currency": "ZAR",
            }
        )

    if values:
        statement = insert(MonthlyPlatformAnalytics).values(values)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[MonthlyPlatformAnalytics.month_start],
                set_={
                    "bookings_created": statement.excluded.bookings_created,
                    "bookings_by_current_status": statement.excluded.bookings_by_current_status,
                    "cash_collected": statement.excluded.cash_collected,
                    "cash_refunded": statement.excluded.cash_refunded,
                    "net_cash": statement.excluded.net_cash,
                    "currency": statement.excluded.currency,
                    "refreshed_at": func.now(),
                },
            )
        )
        months = [item["month_start"] for item in values]
        session.execute(
            delete(MonthlyPlatformAnalytics).where(
                MonthlyPlatformAnalytics.month_start.not_in(months)
            )
        )
    else:
        session.execute(delete(MonthlyPlatformAnalytics))

    return RefreshSummary(
        bookings_extracted=bookings_extracted,
        payments_extracted=payments_extracted,
        refunds_extracted=refunds_extracted,
        months_loaded=len(values),
    )


def list_monthly_analytics(session: Session, *, months: int) -> list[MonthlyPlatformAnalytics]:
    """Read the latest N months of stored aggregates, including the current SA month."""
    current = datetime.now(SA_TIMEZONE).date().replace(day=1)
    month_index = current.year * 12 + current.month - 1 - (months - 1)
    first_month = date(month_index // 12, month_index % 12 + 1, 1)
    return list(
        session.scalars(
            select(MonthlyPlatformAnalytics)
            .where(MonthlyPlatformAnalytics.month_start >= first_month)
            .order_by(MonthlyPlatformAnalytics.month_start)
        )
    )
