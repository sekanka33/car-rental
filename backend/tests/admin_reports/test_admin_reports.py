"""Administrator aggregates, the audit log and user search (FR-35)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Booking, Delivery, DeliveryException, Payment, Refund, User
from app.models.enums import (
    BookingStatus,
    DeliveryExceptionKind,
    DeliveryStatus,
    PaymentStatus,
    RefundStatus,
    UserStatus,
    VehicleStatus,
)
from app.services import reports
from app.services.audit import record_audit
from app.services.verification import SA_TIMEZONE, today_in_south_africa
from tests.api_fixtures import Account, login, register
from tests.conftest import requires_db
from tests.db.factories import create_booking, create_price, create_user, create_vehicle
from tests.verification.helpers import set_dob, submit_id

pytestmark = requires_db
S = BookingStatus
ADMIN = "/api/v1/admin"
NOW = datetime.now(UTC)


def booking(session, status=S.CONFIRMED, days_ahead=5, **kw) -> Booking:
    vehicle = create_vehicle(session)
    return create_booking(
        session,
        create_price(session, vehicle),
        status=status,
        start=NOW + timedelta(days=days_ahead),
        **kw,
    )


def payment(session, b: Booking, amount: str, paid_at: datetime | None, *, ref: str) -> Payment:
    p = Payment(
        booking_id=b.id,
        provider="paystack",
        provider_reference=ref,
        amount=Decimal(amount),
        status=PaymentStatus.SUCCEEDED if paid_at else PaymentStatus.PENDING,
        paid_at=paid_at,
    )
    session.add(p)
    session.flush()
    return p


def refund(session, p: Payment, amount: str, status: RefundStatus, processed_at=None) -> None:
    session.add(
        Refund(
            payment_id=p.id,
            provider="paystack",
            amount=Decimal(amount),
            status=status,
            reason="Cancelled",
            processed_at=processed_at,
        )
    )
    session.flush()


def delivery(session, status: DeliveryStatus, **kw) -> Delivery:
    b = booking(session, days_ahead=30 + len(kw))
    assignee = create_user(session)
    values = (
        {"scheduled_for": NOW, "started_at": NOW}
        if status != DeliveryStatus.PENDING_SCHEDULE
        else {}
    )
    if status == DeliveryStatus.CANCELLED:
        values["cancelled_at"] = NOW
    d = Delivery(
        booking_id=b.id, assigned_to_id=assignee.id, status=status, dropoff_address="X", **values
    )
    session.add(d)
    session.flush()
    return d


def issue(session, d: Delivery, *, resolved: bool) -> None:
    reporter = create_user(session)
    session.add(
        DeliveryException(
            delivery_id=d.id,
            kind=DeliveryExceptionKind.DELAY,
            notes="Traffic",
            reported_by_id=reporter.id,
            resolved_at=NOW if resolved else None,
            resolved_by_id=reporter.id if resolved else None,
            resolution="Arrived" if resolved else None,
        )
    )
    session.flush()


@pytest.mark.parametrize("path", ["reports/overview", "reports/monthly", "audit-logs"])
def test_reports_are_for_administrators_only(api, renter, owner, path) -> None:
    assert api.get(f"{ADMIN}/{path}").status_code == 401
    assert api.get(f"{ADMIN}/{path}", headers=renter.headers).status_code == 403
    assert api.get(f"{ADMIN}/{path}", headers=owner.headers).status_code == 403


# --- overview --------------------------------------------------------------------------------


def test_overview_counts_work_queues(api, admin, renter, db_session: Session) -> None:
    set_dob(api, renter.headers)
    assert submit_id(api, renter.headers).status_code == 201  # one pending verification
    create_vehicle(db_session, status=VehicleStatus.PENDING_APPROVAL)
    create_vehicle(db_session, status=VehicleStatus.APPROVED, approved_at=NOW)
    delivery(db_session, DeliveryStatus.FAILED)
    issue(db_session, delivery(db_session, DeliveryStatus.SCHEDULED, a=1), resolved=False)
    issue(db_session, delivery(db_session, DeliveryStatus.EN_ROUTE, a=1, b=2), resolved=True)
    issue(db_session, delivery(db_session, DeliveryStatus.CANCELLED, a=1, b=2, c=3), resolved=False)
    booking(db_session, S.ACTIVE_RENTAL, days_ahead=-1)
    p = payment(
        db_session, booking(db_session, S.CANCELLED, days_ahead=60), "900.00", NOW, ref="r1"
    )
    refund(db_session, p, "100.00", RefundStatus.PENDING)
    refund(db_session, p, "50.00", RefundStatus.FAILED)
    suspended = create_user(db_session)
    suspended.status, suspended.suspended_at = UserStatus.SUSPENDED, NOW
    db_session.flush()

    body = api.get(f"{ADMIN}/reports/overview", headers=admin.headers).json()

    assert body["verifications_pending"] == 1
    assert body["vehicles_pending_approval"] == 1
    assert (
        body["deliveries_needing_attention"] == 2
    )  # failed + open exception (not resolved/cancelled)
    queue = api.get(f"{ADMIN}/deliveries?open_exceptions=true", headers=admin.headers).json()
    assert len(queue) == 2  # the list behind the tile shows the same deliveries
    assert (body["refunds_pending"], body["refunds_failed"]) == (1, 1)
    assert body["bookings_under_way"] == 1
    assert body["users_by_role"]["ADMIN"] == 1 and body["users_by_role"]["RENTER"] >= 1
    assert body["users_suspended"] == 1
    assert body["vehicles_by_status"]["APPROVED"] >= 1
    assert body["bookings_by_status"]["CANCELLED"] == 1


def test_overview_money_is_this_south_african_month(db_session: Session) -> None:
    today = date(2031, 3, 15)
    b = booking(db_session, days_ahead=90)
    this_month = payment(db_session, b, "1000.00", datetime(2031, 3, 2, tzinfo=UTC), ref="m1")
    # 28 Feb 22:30 UTC is already 1 March in South Africa.
    payment(
        db_session,
        booking(db_session, days_ahead=95),
        "300.00",
        datetime(2031, 2, 28, 22, 30, tzinfo=UTC),
        ref="m2",
    )
    payment(
        db_session,
        booking(db_session, days_ahead=100),
        "700.00",
        datetime(2031, 2, 28, 21, 30, tzinfo=UTC),
        ref="m3",
    )
    payment(db_session, booking(db_session, days_ahead=105), "999.00", None, ref="unpaid")
    refund(
        db_session, this_month, "250.00", RefundStatus.PROCESSED, datetime(2031, 3, 10, tzinfo=UTC)
    )
    refund(db_session, this_month, "100.00", RefundStatus.PENDING)
    # Failed at Paystack this month: not money returned.
    refund(db_session, this_month, "40.00", RefundStatus.FAILED, datetime(2031, 3, 11, tzinfo=UTC))
    # Next month (1 April in South Africa) does not count.
    payment(
        db_session,
        booking(db_session, days_ahead=110),
        "450.00",
        datetime(2031, 3, 31, 22, 30, tzinfo=UTC),
        ref="m4",
    )

    result = reports.overview(db_session, today=today)

    assert result.month == "2031-03"
    assert (result.month_collected, result.month_refunded) == (
        Decimal("1300.00"),
        Decimal("250.00"),
    )


# --- monthly ---------------------------------------------------------------------------------


def test_monthly_series_is_zero_filled_and_bucketed_in_sa_time(db_session: Session) -> None:
    today = date(2031, 3, 15)
    b = booking(db_session, days_ahead=90)
    b.confirmed_at = datetime(2031, 1, 31, 22, 30, tzinfo=UTC)  # 1 Feb in South Africa
    paid = payment(db_session, b, "1200.00", datetime(2031, 1, 31, 22, 30, tzinfo=UTC), ref="s1")
    refund(db_session, paid, "200.00", RefundStatus.PROCESSED, datetime(2031, 3, 1, 8, tzinfo=UTC))
    refund(db_session, paid, "999.00", RefundStatus.FAILED, datetime(2031, 3, 2, tzinfo=UTC))
    renter = create_user(db_session)
    renter.created_at = datetime(2031, 3, 3, tzinfo=UTC)
    db_session.flush()

    rows = reports.monthly(db_session, months=3, today=today)

    assert [r.month for r in rows] == ["2031-01", "2031-02", "2031-03"]
    jan, feb, mar = rows
    assert (jan.bookings_confirmed, jan.collected) == (0, Decimal("0.00"))
    assert (feb.bookings_confirmed, feb.collected, feb.net) == (
        1,
        Decimal("1200.00"),
        Decimal("1200.00"),
    )
    assert (mar.refunded, mar.net) == (Decimal("200.00"), Decimal("-200.00"))


def test_monthly_endpoint_spans_the_year_boundary(api, admin) -> None:
    rows = api.get(f"{ADMIN}/reports/monthly?months=14", headers=admin.headers).json()
    assert len(rows) == 14
    months = [r["month"] for r in rows]
    assert months == sorted(months) and months[-1] == today_in_south_africa().strftime("%Y-%m")
    assert api.get(f"{ADMIN}/reports/monthly?months=25", headers=admin.headers).status_code == 422


def test_month_helpers() -> None:
    assert reports._shift(2031, 1, -1) == (2030, 12)
    assert reports._shift(2030, 12, 1) == (2031, 1)
    assert reports._month_start(2031, 3).tzinfo == SA_TIMEZONE


# --- audit log -------------------------------------------------------------------------------


def test_audit_log_filters_and_actor(api, admin, db_session: Session) -> None:
    me = db_session.scalar(select(User).where(User.email == admin.email))
    record_audit(
        db_session,
        actor_id=me.id,
        action="vehicle.approved",
        entity_type="vehicle",
        entity_id="v-1",
    )
    record_audit(
        db_session,
        actor_id=me.id,
        action="vehicle.suspended",
        entity_type="vehicle",
        entity_id="v-2",
    )
    record_audit(
        db_session,
        actor_id=None,
        action="payment.succeeded",
        entity_type="payment",
        entity_id="p-1",
    )
    record_audit(
        db_session, actor_id=None, action="vehicle%", entity_type="vehicle", entity_id="v-3"
    )
    db_session.flush()

    def get(**params):
        return api.get(f"{ADMIN}/audit-logs", headers=admin.headers, params=params).json()

    vehicles = get(action="vehicle.")
    assert [i["entity_id"] for i in vehicles["items"]] == [
        "v-2",
        "v-1",
    ]  # newest first; % is literal
    assert vehicles["items"][0]["actor"]["email"] == admin.email
    system = get(entity_type="payment")
    assert system["total"] == 1 and system["items"][0]["actor"] is None
    assert get(entity_id="v-1")["items"][0]["action"] == "vehicle.approved"
    assert get(actor_user_id=str(me.id), action="vehicle")["total"] == 2  # not the system entry
    page = get(limit=1, offset=1, action="vehicle")
    assert len(page["items"]) == 1 and page["total"] == 3
    # A % typed by the administrator is a character, not a wildcard.
    assert [i["entity_id"] for i in get(action="vehicle%")["items"]] == ["v-3"]


# --- user search -----------------------------------------------------------------------------


@pytest.fixture
def people(api, db_session) -> dict[str, Account]:
    register(api, "lerato.owner@example.com", "OWNER", full_name="Lerato Khumalo")
    register(api, "sipho_r@example.com", "RENTER", full_name="Sipho Ndlovu")
    register(api, "sipho2@example.com", "RENTER", full_name="Sipho Zulu")
    register(api, "noor@example.com", "RENTER", full_name="Noor Patel")  # "oor" would match o_r
    user = db_session.scalar(select(User).where(User.email == "sipho2@example.com"))
    user.status, user.suspended_at = UserStatus.SUSPENDED, NOW
    db_session.flush()
    return {}


def test_users_can_be_searched_and_filtered(api, admin, people) -> None:
    def emails(**params):
        body = api.get(f"{ADMIN}/users", headers=admin.headers, params=params).json()
        return sorted(u["email"] for u in body["items"]), body["total"]

    assert emails(q="SIPHO") == (["sipho2@example.com", "sipho_r@example.com"], 2)
    assert emails(q="khumalo") == (["lerato.owner@example.com"], 1)
    assert emails(q="o_r") == (["sipho_r@example.com"], 1)  # "_" is literal, not a wildcard
    assert emails(role="OWNER") == (["lerato.owner@example.com"], 1)
    assert emails(q="sipho", status="SUSPENDED") == (["sipho2@example.com"], 1)
    assert api.get(f"{ADMIN}/users?role=DRIVER", headers=admin.headers).status_code == 422
    assert login(api, "sipho_r@example.com").access_token


def test_payments_can_be_filtered_by_refund_state(api, admin, db_session: Session) -> None:
    failed = payment(
        db_session, booking(db_session, S.CANCELLED, days_ahead=40), "500.00", NOW, ref="f1"
    )
    refund(db_session, failed, "500.00", RefundStatus.FAILED)
    fine = payment(
        db_session, booking(db_session, S.CANCELLED, days_ahead=50), "500.00", NOW, ref="f2"
    )
    refund(db_session, fine, "500.00", RefundStatus.PROCESSED, NOW)

    rows = api.get(f"{ADMIN}/payments?refund_status=FAILED", headers=admin.headers).json()

    assert [r["id"] for r in rows] == [str(failed.id)]


def test_deliveries_can_be_found_by_booking(api, admin, db_session: Session) -> None:
    wanted = delivery(db_session, DeliveryStatus.PENDING_SCHEDULE)
    delivery(db_session, DeliveryStatus.PENDING_SCHEDULE, a=1)

    rows = api.get(
        f"{ADMIN}/deliveries?booking_id={wanted.booking_id}", headers=admin.headers
    ).json()

    assert [r["id"] for r in rows] == [str(wanted.id)]
