from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import AuditLog, Booking, Payment, PaymentEvent, Refund
from app.models.enums import BookingStatus, PaymentStatus
from app.services.payments import reconcile_pending
from tests.api_fixtures import Account
from tests.bookings.helpers import book, eligible_renter
from tests.conftest import requires_db
from tests.marketplace.factories import listed_vehicle
from tests.payments.fake_provider import FakePaymentProvider, signed

pytestmark = requires_db
WEBHOOK = "/api/v1/payments/webhooks/paystack"


@pytest.fixture
def alice(api: TestClient, db_session: Session) -> Account:
    return eligible_renter(api, db_session, "alice@example.com")


@pytest.fixture
def booking(api: TestClient, alice: Account, db_session: Session, storage) -> dict:
    vehicle = listed_vehicle(db_session, storage, daily_rate="650.00")
    response = book(api, alice, vehicle.id, days=3)  # total R2 100.00
    assert response.status_code == 201
    return response.json()


def start(api: TestClient, account: Account, booking_id: str):
    return api.post(f"/api/v1/bookings/{booking_id}/payments", headers=account.headers)


def refresh(api: TestClient, account: Account, payment_id: str):
    return api.post(f"/api/v1/payments/{payment_id}/refresh", headers=account.headers)


def actions(session: Session, entity_id: str) -> list[str]:
    return session.scalars(
        select(AuditLog.action).where(AuditLog.entity_id == entity_id).order_by(AuditLog.id)
    ).all()


# --- initiation ---------------------------------------------------------------------------------


def test_checkout_uses_the_booking_total(
    api, alice, booking, payment_provider: FakePaymentProvider
) -> None:
    response = start(api, alice, booking["id"])

    assert response.status_code == 201
    payment = response.json()
    assert (payment["status"], payment["amount"], payment["currency"]) == (
        "PENDING",
        "2100.00",
        "ZAR",
    )
    assert payment["checkout_url"] == f"https://checkout.test/{payment['reference']}"
    sent = payment_provider.checkouts[0]
    assert (sent["amount_cents"], sent["currency"], sent["email"]) == (
        210000,
        "ZAR",
        "alice@example.com",
    )
    assert sent["metadata"]["booking_id"] == booking["id"]


def test_starting_again_reuses_the_open_checkout(api, alice, booking, payment_provider) -> None:
    first = start(api, alice, booking["id"]).json()

    second = start(api, alice, booking["id"]).json()

    assert second["id"] == first["id"]
    assert len(payment_provider.checkouts) == 1  # never two live checkouts for one booking


def test_client_cannot_choose_the_amount(api, alice, booking, payment_provider) -> None:
    response = api.post(
        f"/api/v1/bookings/{booking['id']}/payments", headers=alice.headers, json={"amount": "1.00"}
    )

    assert response.json()["amount"] == "2100.00"
    assert payment_provider.checkouts[0]["amount_cents"] == 210000


def test_payment_rules(api, alice, owner, booking, db_session) -> None:
    bob = eligible_renter(api, db_session, "bob@example.com")
    assert start(api, bob, booking["id"]).status_code == 404
    assert start(api, owner, booking["id"]).status_code == 403
    assert api.post(f"/api/v1/bookings/{booking['id']}/payments").status_code == 401

    db_session.execute(
        update(Booking)
        .where(Booking.id == booking["id"])
        .values(hold_expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    expired = start(api, alice, booking["id"])
    assert expired.status_code == 409
    assert db_session.get(Booking, booking["id"]).status == BookingStatus.EXPIRED


def test_cancelled_booking_cannot_be_paid(api, alice, booking) -> None:
    api.post(f"/api/v1/bookings/{booking['id']}/cancel", headers=alice.headers, json={})

    assert start(api, alice, booking["id"]).status_code == 409


def test_provider_outage(api, alice, booking, payment_provider, db_session) -> None:
    payment_provider.fail_next = "create_checkout"

    response = start(api, alice, booking["id"])

    assert response.status_code == 502
    assert db_session.scalar(select(Payment.status)) == PaymentStatus.FAILED
    assert start(api, alice, booking["id"]).status_code == 201  # can retry


@pytest.mark.parametrize("payment_provider", [None], indirect=False)
def test_payments_unavailable_without_provider(api, alice, booking) -> None:
    assert start(api, alice, booking["id"]).status_code == 503


# --- verification ---------------------------------------------------------------------------------


def test_only_a_verified_payment_confirms_the_booking(
    api, alice, booking, payment_provider, db_session
) -> None:
    payment = start(api, alice, booking["id"]).json()

    pending = refresh(api, alice, payment["id"]).json()
    assert (pending["status"], pending["booking_status"]) == ("PENDING", "PENDING_PAYMENT")

    payment_provider.set_charge(payment["reference"], "success", 210000)
    paid = refresh(api, alice, payment["id"]).json()

    assert (paid["status"], paid["booking_status"]) == ("SUCCEEDED", "CONFIRMED")
    assert paid["paid_at"] is not None and paid["checkout_url"] is None
    assert actions(db_session, payment["id"]) == ["payment.initiated", "payment.succeeded"]
    assert "booking.confirmed" in actions(db_session, booking["id"])
    assert refresh(api, alice, payment["id"]).json()["status"] == "SUCCEEDED"  # idempotent


def test_failed_payment_allows_a_new_attempt(api, alice, booking, payment_provider) -> None:
    payment = start(api, alice, booking["id"]).json()
    payment_provider.set_charge(payment["reference"], "failed", 210000)

    failed = refresh(api, alice, payment["id"]).json()

    assert (failed["status"], failed["booking_status"]) == ("FAILED", "PENDING_PAYMENT")
    assert failed["failure_reason"] == "Declined"
    retry = start(api, alice, booking["id"]).json()
    assert retry["id"] != payment["id"] and retry["status"] == "PENDING"


@pytest.mark.parametrize(
    ("amount_cents", "currency"),
    [(100, "ZAR"), (210000, "USD"), (210001, "ZAR")],
    ids=["underpaid", "wrong-currency", "off-by-a-cent"],
)
def test_mismatched_payment_is_flagged_not_confirmed(
    api, alice, booking, payment_provider, db_session, amount_cents, currency
) -> None:
    payment = start(api, alice, booking["id"]).json()
    payment_provider.set_charge(payment["reference"], "success", amount_cents, currency)

    result = refresh(api, alice, payment["id"]).json()

    assert result["status"] == "FAILED" and "mismatch" in result["failure_reason"]
    assert result["booking_status"] == "PENDING_PAYMENT"
    assert "payment.mismatch" in actions(db_session, payment["id"])


def test_payment_after_hold_expired_is_refunded(
    api, alice, booking, payment_provider, db_session
) -> None:
    payment = start(api, alice, booking["id"]).json()
    db_session.execute(
        update(Booking)
        .where(Booking.id == booking["id"])
        .values(hold_expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    payment_provider.set_charge(payment["reference"], "success", 210000)

    result = refresh(api, alice, payment["id"]).json()

    assert result["status"] == "REFUND_PENDING"
    assert result["booking_status"] == "PENDING_PAYMENT"  # never confirmed
    assert [(r["amount"], r["status"]) for r in result["refunds"]] == [("2100.00", "PENDING")]
    assert payment_provider.refund_requests[0]["amount_cents"] == 210000


def test_second_successful_payment_for_same_booking_is_refunded(
    api, alice, booking, payment_provider, db_session
) -> None:
    first = start(api, alice, booking["id"]).json()
    # A second checkout that slipped through (e.g. an old link) also gets paid.
    second = Payment(
        booking_id=booking["id"],
        provider="paystack",
        provider_reference="PAYDUPLICATE",
        amount=Decimal("2100.00"),
        status=PaymentStatus.PENDING,
    )
    db_session.add(second)
    db_session.flush()
    payment_provider.set_charge(first["reference"], "success", 210000)
    payment_provider.set_charge("PAYDUPLICATE", "success", 210000)

    assert refresh(api, alice, first["id"]).json()["status"] == "SUCCEEDED"
    duplicate = refresh(api, alice, str(second.id)).json()

    assert duplicate["status"] == "REFUND_PENDING"
    assert duplicate["refunds"][0]["reason"] == "Duplicate payment"
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Payment)
            .where(Payment.status == PaymentStatus.SUCCEEDED)
        )
        == 1
    )


def test_provider_unreachable_during_verify_leaves_payment_pending(
    api, alice, booking, payment_provider
) -> None:
    payment = start(api, alice, booking["id"]).json()
    payment_provider.fail_next = "verify_charge"

    assert refresh(api, alice, payment["id"]).json()["status"] == "PENDING"


# --- webhooks -------------------------------------------------------------------------


def test_signed_webhook_triggers_verification(
    api, alice, booking, payment_provider, db_session
) -> None:
    payment = start(api, alice, booking["id"]).json()
    payment_provider.set_charge(payment["reference"], "success", 210000)
    body, headers = signed(
        {
            "event": "charge.success",
            "data": {
                "reference": payment["reference"],
                "amount": 210000,
                "customer": {"email": "alice@example.com"},
                "authorization": {"last4": "4081"},
            },
        }
    )

    response = api.post(WEBHOOK, content=body, headers=headers)

    assert response.status_code == 200
    assert db_session.get(Booking, booking["id"]).status == BookingStatus.CONFIRMED
    event = db_session.scalar(select(PaymentEvent))
    assert (event.event_type, event.reference, event.outcome) == (
        "charge.success",
        payment["reference"],
        "payment SUCCEEDED",
    )
    assert (
        "customer" not in event.payload["data"] and "authorization" not in event.payload["data"]
    )  # POPIA


def test_webhook_payload_is_never_trusted(
    api, alice, booking, payment_provider, db_session
) -> None:
    """A correctly signed 'success' event is still checked with the provider, which says failed."""
    payment = start(api, alice, booking["id"]).json()
    payment_provider.set_charge(payment["reference"], "failed", 210000)
    body, headers = signed(
        {
            "event": "charge.success",
            "data": {"reference": payment["reference"], "status": "success"},
        }
    )

    api.post(WEBHOOK, content=body, headers=headers)

    assert db_session.get(Booking, booking["id"]).status == BookingStatus.PENDING_PAYMENT
    assert db_session.get(Payment, payment["id"]).status == PaymentStatus.FAILED


def test_repeated_webhook_is_processed_once(
    api, alice, booking, payment_provider, db_session
) -> None:
    payment = start(api, alice, booking["id"]).json()
    payment_provider.set_charge(payment["reference"], "success", 210000)
    body, headers = signed({"event": "charge.success", "data": {"reference": payment["reference"]}})

    for _ in range(3):
        assert api.post(WEBHOOK, content=body, headers=headers).status_code == 200

    assert db_session.scalar(select(func.count()).select_from(PaymentEvent)) == 1
    assert actions(db_session, payment["id"]).count("payment.succeeded") == 1
    assert actions(db_session, booking["id"]).count("booking.confirmed") == 1


@pytest.mark.parametrize("variant", ["no-signature", "wrong-secret", "tampered-body"])
def test_unsigned_or_forged_webhooks_are_rejected(
    api, alice, booking, payment_provider, db_session, variant
) -> None:
    payment = start(api, alice, booking["id"]).json()
    payment_provider.set_charge(payment["reference"], "success", 210000)
    body, headers = signed(
        {"event": "charge.success", "data": {"reference": payment["reference"]}},
        secret="sk_test_attacker" if variant == "wrong-secret" else "sk_test_fake_provider_secret",
    )
    if variant == "no-signature":
        headers.pop("x-paystack-signature")
    if variant == "tampered-body":
        body = body.replace(b"charge.success", b"charge.successX")

    response = api.post(WEBHOOK, content=body, headers=headers)

    assert response.status_code == 401
    assert db_session.scalar(select(func.count()).select_from(PaymentEvent)) == 0
    assert db_session.get(Booking, booking["id"]).status == BookingStatus.PENDING_PAYMENT


def test_webhook_for_unknown_reference_is_acknowledged(api, payment_provider, db_session) -> None:
    body, headers = signed({"event": "charge.success", "data": {"reference": "NOT-OURS"}})

    assert api.post(WEBHOOK, content=body, headers=headers).status_code == 200
    assert db_session.scalar(select(PaymentEvent.outcome)) == "unknown reference"


# --- refunds --------------------------------------------------------------------------


def paid_booking(api, alice, booking, payment_provider) -> dict:
    payment = start(api, alice, booking["id"]).json()
    payment_provider.set_charge(payment["reference"], "success", 210000)
    return refresh(api, alice, payment["id"]).json()


def test_admin_partial_then_full_refund(
    api, alice, admin, booking, payment_provider, db_session
) -> None:
    payment = paid_booking(api, alice, booking, payment_provider)
    url = f"/api/v1/admin/payments/{payment['id']}/refunds"

    partial = api.post(
        url, headers=admin.headers, json={"amount": "500.00", "reason": "Late delivery"}
    )
    assert partial.status_code == 201 and partial.json()["status"] == "PENDING"
    assert (
        api.post(
            url, headers=admin.headers, json={"amount": "1600.01", "reason": "Too much"}
        ).status_code
        == 409
    )

    payment_provider.refund_states["rf-1"] = "processed"
    body, headers = signed(
        {
            "event": "refund.processed",
            "data": {"id": "rf-1", "transaction_reference": payment["reference"]},
        }
    )
    api.post(WEBHOOK, content=body, headers=headers)
    db_session.expire_all()
    assert db_session.get(Payment, payment["id"]).status == PaymentStatus.PARTIALLY_REFUNDED

    rest = api.post(url, headers=admin.headers, json={"reason": "Goodwill"}).json()
    assert rest["amount"] == "1600.00"
    payment_provider.refund_states["rf-2"] = "processed"
    reconcile_pending(db_session, payment_provider)
    db_session.expire_all()
    assert db_session.get(Payment, payment["id"]).status == PaymentStatus.REFUNDED
    assert api.post(url, headers=admin.headers, json={"reason": "Again"}).status_code == 409


def test_refund_webhook_without_a_known_refund_id_rechecks_pending_refunds(
    api, alice, admin, booking, payment_provider, db_session
) -> None:
    payment = paid_booking(api, alice, booking, payment_provider)
    api.post(
        f"/api/v1/admin/payments/{payment['id']}/refunds",
        headers=admin.headers,
        json={"reason": "Goodwill"},
    )
    payment_provider.refund_states["rf-1"] = "processed"
    body, headers = signed(
        {
            "event": "refund.processed",
            "data": {"refund_reference": "unknown", "transaction_reference": payment["reference"]},
        }
    )

    assert api.post(WEBHOOK, content=body, headers=headers).status_code == 200

    db_session.expire_all()
    assert db_session.get(Payment, payment["id"]).status == PaymentStatus.REFUNDED
    event = db_session.scalar(
        select(PaymentEvent).where(PaymentEvent.event_type == "refund.processed")
    )
    assert event.outcome == "refunds rechecked: 1"


def test_refund_rules(api, alice, admin, booking, payment_provider, db_session) -> None:
    pending = start(api, alice, booking["id"]).json()
    url = f"/api/v1/admin/payments/{pending['id']}/refunds"
    assert (
        api.post(url, headers=admin.headers, json={"reason": "Nope"}).status_code == 409
    )  # not paid
    assert api.post(url, headers=alice.headers, json={"reason": "Mine"}).status_code == 403

    payment_provider.set_charge(pending["reference"], "success", 210000)
    refresh(api, alice, pending["id"])
    payment_provider.fail_next = "create_refund"
    failed = api.post(url, headers=admin.headers, json={"reason": "Provider down"}).json()
    assert failed["status"] == "FAILED"
    assert db_session.get(Refund, failed["id"]).failure_reason.startswith("simulated")


def test_cancelling_a_paid_booking_refunds_it(
    api, alice, booking, payment_provider, db_session
) -> None:
    payment = paid_booking(api, alice, booking, payment_provider)

    cancelled = api.post(
        f"/api/v1/bookings/{booking['id']}/cancel",
        headers=alice.headers,
        json={"reason": "Trip off"},
    )

    assert cancelled.json()["status"] == "CANCELLED"
    refund = db_session.scalar(select(Refund).where(Refund.payment_id == payment["id"]))
    assert (refund.amount, refund.reason) == (Decimal("2100.00"), "Booking cancelled: Trip off")
    assert payment_provider.refund_requests[0]["reference"] == payment["reference"]


def test_admin_cancellation_of_paid_booking_refunds_it(
    api, alice, admin, booking, payment_provider, db_session
) -> None:
    payment = paid_booking(api, alice, booking, payment_provider)

    api.post(
        f"/api/v1/admin/bookings/{booking['id']}/cancel",
        headers=admin.headers,
        json={"reason": "Vehicle damaged"},
    )

    assert (
        db_session.scalar(select(Refund.reason).where(Refund.payment_id == payment["id"]))
        == "Booking cancelled: Vehicle damaged"
    )


def test_reconcile_pending_catches_missed_webhooks(
    api, alice, booking, payment_provider, db_session
) -> None:
    payment = start(api, alice, booking["id"]).json()
    payment_provider.set_charge(payment["reference"], "success", 210000)
    db_session.execute(update(Payment).values(created_at=datetime.now(UTC) - timedelta(minutes=5)))

    counts = reconcile_pending(db_session, payment_provider)

    assert counts["payments_checked"] == 1
    assert db_session.get(Booking, booking["id"]).status == BookingStatus.CONFIRMED


def test_admin_payment_list(api, alice, admin, booking, payment_provider) -> None:
    payment = paid_booking(api, alice, booking, payment_provider)

    listed = api.get("/api/v1/admin/payments", headers=admin.headers).json()

    assert [(p["id"], p["status"], p["booking_status"]) for p in listed] == [
        (payment["id"], "SUCCEEDED", "CONFIRMED")
    ]
    assert api.get("/api/v1/admin/payments", headers=alice.headers).status_code == 403


def test_payments_are_private_to_their_renter(
    api, alice, booking, payment_provider, db_session
) -> None:
    payment = start(api, alice, booking["id"]).json()
    bob = eligible_renter(api, db_session, "bob@example.com")

    assert refresh(api, bob, payment["id"]).status_code == 404
    assert (
        api.get(f"/api/v1/bookings/{booking['id']}/payments", headers=bob.headers).status_code
        == 404
    )
    assert [
        p["id"]
        for p in api.get(f"/api/v1/bookings/{booking['id']}/payments", headers=alice.headers).json()
    ] == [payment["id"]]


def test_checkout_returns_to_a_url_carrying_the_payment_id(
    db_session, outbox, storage, payment_provider
) -> None:
    from app.db.session import get_db
    from app.main import create_app
    from tests.api_fixtures import login, register
    from tests.bookings.helpers import make_eligible
    from tests.conftest import make_settings

    app = create_app(
        make_settings(payment_callback_url="http://localhost:8081/payments/return"),
        email_sender=outbox,
        document_storage=storage,
        payment_provider=payment_provider,
    )
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as client:
        register(client, "carol@example.com")
        make_eligible(db_session, "carol@example.com")
        carol = login(client, "carol@example.com")
        vehicle = listed_vehicle(db_session, storage)
        booking_id = book(client, carol, vehicle.id).json()["id"]
        payment = start(client, carol, booking_id).json()

    assert payment_provider.checkouts[0]["callback_url"] == (
        f"http://localhost:8081/payments/return?payment_id={payment['id']}"
    )
