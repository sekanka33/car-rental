from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import Date, Numeric, String, func, literal, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Booking, MonthlyPlatformAnalytics, Payment, Refund
from app.models.enums import BookingStatus, PaymentStatus, RefundStatus
from app.services import analytics
from app.services.analytics import PipelineDataQualityError, refresh_monthly_analytics
from app.services.verification import SA_TIMEZONE
from tests.api_fixtures import Account
from tests.conftest import requires_db
from tests.db.factories import create_booking, create_price, create_vehicle

pytestmark = requires_db


def _create_payment(
    session: Session,
    booking: Booking,
    *,
    status: PaymentStatus,
    amount: str,
    paid_at: datetime | None,
    reference: str,
) -> Payment:
    payment = Payment(
        booking_id=booking.id,
        provider="test",
        provider_reference=reference,
        amount=Decimal(amount),
        status=status,
        paid_at=paid_at,
    )
    session.add(payment)
    session.flush()
    return payment


def _current_month_timestamp() -> datetime:
    today = datetime.now(SA_TIMEZONE).date()
    return datetime(today.year, today.month, 1, 0, 30, tzinfo=SA_TIMEZONE)


def test_refresh_is_repeatable_and_keeps_source_grains_separate(db_session: Session) -> None:
    now = datetime.now(UTC)
    created_at = _current_month_timestamp()
    price = create_price(db_session, create_vehicle(db_session))
    completed = create_booking(
        db_session, price, status=BookingStatus.COMPLETED, start=now + timedelta(days=30)
    )
    completed.created_at = created_at
    cancelled = create_booking(
        db_session, price, status=BookingStatus.CANCELLED, start=now + timedelta(days=40)
    )
    cancelled.created_at = created_at

    succeeded = _create_payment(
        db_session,
        completed,
        status=PaymentStatus.SUCCEEDED,
        amount="1000.00",
        paid_at=now,
        reference="paid-once",
    )
    _create_payment(
        db_session,
        cancelled,
        status=PaymentStatus.PENDING,
        amount="700.00",
        paid_at=None,
        reference="not-paid",
    )
    db_session.add_all(
        [
            Refund(
                payment_id=succeeded.id,
                provider="test",
                amount=Decimal("250.00"),
                status=RefundStatus.PROCESSED,
                reason="Test refund",
                processed_at=now,
            ),
            Refund(
                payment_id=succeeded.id,
                provider="test",
                amount=Decimal("50.00"),
                status=RefundStatus.PENDING,
                reason="Awaiting provider",
            ),
        ]
    )
    db_session.flush()

    first = refresh_monthly_analytics(db_session)
    db_session.flush()
    second = refresh_monthly_analytics(db_session)
    db_session.flush()
    rows = list(db_session.scalars(select(MonthlyPlatformAnalytics)))

    assert first == second
    assert first.bookings_extracted == 2
    assert first.payments_extracted == 2
    assert first.refunds_extracted == 2
    assert first.months_loaded == 1
    assert len(rows) == 1
    row = rows[0]
    assert row.month_start == created_at.date().replace(day=1)
    assert row.bookings_created == 2
    assert row.bookings_by_current_status["COMPLETED"] == 1
    assert row.bookings_by_current_status["CANCELLED"] == 1
    assert row.bookings_created == db_session.scalar(select(func.count()).select_from(Booking))
    expected_collected = db_session.scalar(
        select(func.sum(Payment.amount)).where(Payment.paid_at.is_not(None))
    )
    expected_refunded = db_session.scalar(
        select(func.sum(Refund.amount)).where(Refund.status == RefundStatus.PROCESSED)
    )
    assert row.cash_collected == expected_collected == Decimal("1000.00")
    assert row.cash_refunded == expected_refunded == Decimal("250.00")
    assert row.net_cash == row.cash_collected - row.cash_refunded == Decimal("750.00")


def test_timezone_month_boundary_uses_south_african_calendar(db_session: Session) -> None:
    now = datetime.now(SA_TIMEZONE).date()
    price = create_price(db_session, create_vehicle(db_session))
    booking = create_booking(
        db_session,
        price,
        status=BookingStatus.CONFIRMED,
        start=datetime.now(UTC) + timedelta(days=30),
    )
    booking.created_at = datetime(now.year, now.month, 1, 0, 30, tzinfo=SA_TIMEZONE).astimezone(UTC)
    db_session.flush()

    refresh_monthly_analytics(db_session)
    row = db_session.scalar(select(MonthlyPlatformAnalytics))

    assert row is not None
    assert row.month_start == now.replace(day=1)


def test_empty_source_replaces_snapshot_with_empty_result(db_session: Session) -> None:
    result = refresh_monthly_analytics(db_session)
    db_session.flush()

    assert result.bookings_extracted == 0
    assert result.payments_extracted == 0
    assert result.refunds_extracted == 0
    assert result.months_loaded == 0
    assert db_session.scalar(select(func.count()).select_from(MonthlyPlatformAnalytics)) == 0


def test_invalid_source_does_not_replace_existing_snapshot(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    month = _current_month_timestamp().date().replace(day=1)
    db_session.add(
        MonthlyPlatformAnalytics(
            month_start=month,
            bookings_created=3,
            bookings_by_current_status={"CONFIRMED": 3},
            cash_collected=Decimal("900.00"),
            cash_refunded=Decimal("0.00"),
            net_cash=Decimal("900.00"),
            currency="ZAR",
        )
    )
    db_session.flush()
    invalid_row = select(
        literal("payment", type_=String()).label("source"),
        literal("invalid-payment", type_=String()).label("record_id"),
        literal("SUCCEEDED", type_=String()).label("status"),
        literal(None, type_=Date()).label("month_start"),
        literal(Decimal("0.00"), type_=Numeric(12, 2)).label("amount"),
        literal("ZAR", type_=String(3)).label("currency"),
    )
    monkeypatch.setattr(analytics, "_source_rows", lambda: invalid_row)

    with pytest.raises(PipelineDataQualityError, match="finite positive value"):
        refresh_monthly_analytics(db_session)

    stored = db_session.get(MonthlyPlatformAnalytics, month)
    assert stored is not None
    assert stored.cash_collected == Decimal("900.00")


@pytest.mark.parametrize("amount", [None, Decimal("0.00"), Decimal("-1.00"), Decimal("NaN")])
def test_invalid_money_is_rejected(amount: Decimal | None) -> None:
    with pytest.raises(PipelineDataQualityError, match="finite positive value"):
        analytics._valid_amount("payment", "record-1", amount)


def test_monthly_endpoint_is_admin_only_and_reads_pipeline_output(
    api, admin: Account, renter: Account, db_session: Session
) -> None:
    path = "/api/v1/admin/analytics/monthly"
    assert api.get(path).status_code == 401
    assert api.get(path, headers=renter.headers).status_code == 403

    booking = create_booking(
        db_session,
        create_price(db_session, create_vehicle(db_session)),
        status=BookingStatus.CONFIRMED,
        start=datetime.now(UTC) + timedelta(days=30),
    )
    booking.created_at = _current_month_timestamp()
    db_session.flush()
    paid_at = datetime.now(UTC)
    payment = _create_payment(
        db_session,
        booking,
        status=PaymentStatus.SUCCEEDED,
        amount="1000.00",
        paid_at=paid_at,
        reference="api-paid-once",
    )
    db_session.add(
        Refund(
            payment_id=payment.id,
            provider="test",
            amount=Decimal("250.00"),
            status=RefundStatus.PROCESSED,
            reason="Test refund",
            processed_at=paid_at,
        )
    )
    db_session.flush()
    refresh_monthly_analytics(db_session)
    db_session.flush()
    stored = db_session.scalar(select(MonthlyPlatformAnalytics))
    assert stored is not None, "refresh should persist one monthly aggregate"
    assert analytics.list_monthly_analytics(db_session, months=12) == [stored]

    response = api.get(path, headers=admin.headers)

    assert response.status_code == 200
    body = response.json()
    assert body["months_requested"] == 12
    assert len(body["items"]) == 1
    assert body["items"][0]["bookings_created"] == 1
    assert body["items"][0]["bookings_by_current_status"]["CONFIRMED"] == 1
    assert body["items"][0]["cash_collected"] == "1000.00"
    assert body["items"][0]["cash_refunded"] == "250.00"
    assert body["items"][0]["net_cash"] == "750.00"
    assert body["items"][0]["currency"] == "ZAR"
    assert body["basis"] == (
        "Booking counts use booking creation month and current status at refresh time. "
        "Cash collected uses payment paid_at; cash refunded uses processed refund processed_at. "
        "Payments without paid_at and refunds not processed are excluded."
    )


def test_monthly_endpoint_rejects_out_of_range_months(api, admin: Account) -> None:
    response = api.get(
        "/api/v1/admin/analytics/monthly?months=121",
        headers=admin.headers,
    )

    assert response.status_code == 422


def test_monthly_endpoint_returns_an_empty_list_without_snapshot_rows(api, admin: Account) -> None:
    response = api.get("/api/v1/admin/analytics/monthly", headers=admin.headers)

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_database_errors_are_not_reported_as_empty_analytics(
    api, admin: Account, monkeypatch: pytest.MonkeyPatch
) -> None:
    def database_failure(*args, **kwargs):
        raise SQLAlchemyError("analytics database unavailable")

    monkeypatch.setattr(analytics, "list_monthly_analytics", database_failure)

    response = api.get("/api/v1/admin/analytics/monthly", headers=admin.headers)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_server_error"
