"""Payments: checkout initiation, verification, booking confirmation, refunds, webhooks.

Rules (BR-6):
- Only the backend starts a payment, for the booking's stored total (never a client amount).
- A payment becomes SUCCEEDED only after the backend itself verifies the charge with the
  provider and the amount, currency and reference match. Webhook contents are never
  trusted: a verified webhook only triggers that verification.
- Provider notifications are stored once (unique event key); re-deliveries are no-ops.
- Money received for a booking that can no longer be confirmed (hold expired, booking
  cancelled, or already paid) is refunded automatically.
- No real money moves unless a live key is configured AND ALLOW_LIVE_PAYMENTS is true.
"""

import hashlib
import json
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.errors import AppError, NotFoundError
from app.integrations.payments import PaymentProvider, PaymentProviderError
from app.models import Booking, Payment, PaymentEvent, Refund, User
from app.models.enums import BookingStatus, PaymentStatus, RefundStatus
from app.services import bookings as booking_service
from app.services import notify_events
from app.services.audit import record_audit

logger = logging.getLogger(__name__)
CENTS = Decimal(100)


class PaymentsUnavailableError(AppError):
    status_code = 503
    code = "payments_unavailable"


class PaymentProviderFailedError(AppError):
    status_code = 502
    code = "payment_provider_error"


class PaymentNotAllowedError(AppError):
    status_code = 409
    code = "payment_not_allowed"


class RefundNotAllowedError(AppError):
    status_code = 409
    code = "refund_not_allowed"


class InvalidWebhookSignatureError(AppError):
    status_code = 401
    code = "invalid_signature"


def _now() -> datetime:
    return datetime.now(UTC)


def to_cents(amount: Decimal) -> int:
    cents = amount * CENTS
    if cents != cents.to_integral_value():
        raise ValueError(f"Amount has more than 2 decimals: {amount}")
    return int(cents)


def from_cents(cents: int) -> Decimal:
    return (Decimal(cents) / CENTS).quantize(Decimal("0.01"))


def _require(provider: PaymentProvider | None) -> PaymentProvider:
    if provider is None:
        raise PaymentsUnavailableError("Online payment is not available right now.")
    return provider


def _callback_url(settings: Settings, payment_id: uuid.UUID) -> str | None:
    """Where checkout returns the customer; carries the payment id so the app can verify it."""
    if not settings.payment_callback_url:
        return None
    separator = "&" if "?" in settings.payment_callback_url else "?"
    return f"{settings.payment_callback_url}{separator}payment_id={payment_id}"


def _new_reference() -> str:
    return "PAY" + secrets.token_hex(10).upper()


# --- initiation --------------------------------------------------------------------------------


def start_checkout(
    session: Session,
    settings: Settings,
    provider: PaymentProvider | None,
    renter: User,
    booking_id: uuid.UUID,
) -> Payment:
    """Create (or reuse) a provider checkout for the renter's unpaid booking."""
    provider = _require(provider)
    booking = session.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
    if booking is None or booking.renter_id != renter.id:
        raise NotFoundError("Booking not found.")
    now = _now()
    if booking.status == BookingStatus.PENDING_PAYMENT and booking.hold_expires_at <= now:
        booking_service.transition(booking, BookingStatus.EXPIRED)
        session.commit()
        raise PaymentNotAllowedError("This booking's hold has expired. Please book again.")
    if booking.status != BookingStatus.PENDING_PAYMENT:
        raise PaymentNotAllowedError(f"A {booking.status} booking cannot be paid.")

    open_payment = session.scalar(
        select(Payment).where(
            Payment.booking_id == booking.id,
            Payment.status == PaymentStatus.PENDING,
            Payment.checkout_url.is_not(None),
        )
    )
    if open_payment is not None:
        return open_payment  # one checkout per booking at a time (no double charging)

    payment = Payment(
        booking_id=booking.id,
        provider=provider.name,
        provider_reference=_new_reference(),
        amount=booking.total_amount,
        currency=booking.currency,
        status=PaymentStatus.PENDING,
        initiated_by_id=renter.id,
    )
    session.add(payment)
    session.flush()
    try:
        checkout = provider.create_checkout(
            email=renter.email,
            amount_cents=to_cents(booking.total_amount),
            currency=booking.currency,
            reference=payment.provider_reference,
            callback_url=_callback_url(settings, payment.id),
            metadata={
                "booking_id": str(booking.id),
                "booking_reference": booking.reference,
                "payment_id": str(payment.id),
            },
        )
    except PaymentProviderError as exc:
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = str(exc)[:500]
        session.commit()
        raise PaymentProviderFailedError(
            "The payment provider is unavailable. Please try again."
        ) from exc
    payment.checkout_url = checkout.checkout_url
    record_audit(
        session,
        actor_id=renter.id,
        action="payment.initiated",
        entity_type="payment",
        entity_id=payment.id,
        changes={
            "booking_id": str(booking.id),
            "amount": str(payment.amount),
            "reference": payment.provider_reference,
        },
    )
    session.commit()
    return payment


# --- verification and booking confirmation ------------------------------------------------------


def reconcile(session: Session, provider: PaymentProvider, payment_id: uuid.UUID) -> Payment:
    """Ask the provider for the true state of a payment and apply it. Safe to call repeatedly."""
    payment = session.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if payment is None:
        raise NotFoundError("Payment not found.")
    if payment.status != PaymentStatus.PENDING:
        return payment  # already final: nothing to do (idempotent)
    try:
        result = provider.verify_charge(payment.provider_reference)
    except PaymentProviderError as exc:
        logger.warning("Could not verify payment %s: %s", payment.id, exc)
        return payment
    payment.last_verified_at = _now()

    if result.status == "pending":
        session.commit()
        return payment
    if result.status == "failed":
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = result.gateway_response or "Payment was not completed."
        record_audit(
            session,
            actor_id=None,
            action="payment.failed",
            entity_type="payment",
            entity_id=payment.id,
            changes={"gateway_response": payment.failure_reason},
        )
        session.commit()
        return payment

    # The provider says the money was taken. Check it is exactly what we asked for.
    expected = to_cents(payment.amount)
    if (
        result.reference != payment.provider_reference
        or result.amount_cents != expected
        or result.currency != payment.currency
    ):
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = "Verification mismatch: needs administrator review."
        payment.provider_transaction_id = result.transaction_id
        record_audit(
            session,
            actor_id=None,
            action="payment.mismatch",
            entity_type="payment",
            entity_id=payment.id,
            changes={
                "expected_cents": expected,
                "received_cents": result.amount_cents,
                "currency": result.currency,
                "reference": result.reference,
            },
        )
        logger.error("Payment %s verification mismatch; flagged for review", payment.id)
        session.commit()
        return payment

    payment.provider_transaction_id = result.transaction_id
    payment.paid_at = _now()
    booking = session.scalar(
        select(Booking).where(Booking.id == payment.booking_id).with_for_update()
    )
    already_paid = session.scalar(
        select(func.count())
        .select_from(Payment)
        .where(Payment.booking_id == booking.id, Payment.status == PaymentStatus.SUCCEEDED)
    )
    hold_valid = (
        booking.status == BookingStatus.PENDING_PAYMENT
        and booking.hold_expires_at > payment.paid_at
    )
    if already_paid or not hold_valid:
        # BR-6.5: money we cannot apply to the booking is returned automatically.
        payment.status = PaymentStatus.REFUND_PENDING
        reason = (
            "Duplicate payment"
            if already_paid
            else f"Payment received after the booking became {_late_state(booking)}"
        )
        record_audit(
            session,
            actor_id=None,
            action="payment.unapplied",
            entity_type="payment",
            entity_id=payment.id,
            changes={"booking_status": booking.status.value, "reason": reason},
        )
        session.commit()
        _issue_refund(session, provider, payment, amount=payment.amount, reason=reason, actor=None)
        return payment

    payment.status = PaymentStatus.SUCCEEDED
    record_audit(
        session,
        actor_id=None,
        action="payment.succeeded",
        entity_type="payment",
        entity_id=payment.id,
        changes={"amount": str(payment.amount), "transaction_id": result.transaction_id},
    )
    session.flush()
    booking_service.confirm_booking(session, booking.id, now=payment.paid_at)  # commits
    return payment


def _late_state(booking: Booking) -> str:
    if booking.status == BookingStatus.PENDING_PAYMENT:
        return "EXPIRED (hold elapsed)"
    return booking.status.value


def get_own_payment(session: Session, renter: User, payment_id: uuid.UUID) -> Payment:
    payment = session.scalar(
        select(Payment)
        .options(selectinload(Payment.booking), selectinload(Payment.refunds))
        .where(Payment.id == payment_id)
    )
    if payment is None or payment.booking.renter_id != renter.id:
        raise NotFoundError("Payment not found.")
    return payment


def refresh_own_payment(
    session: Session, provider: PaymentProvider | None, renter: User, payment_id: uuid.UUID
) -> Payment:
    """Renter returned from checkout: check with the provider now instead of waiting."""
    get_own_payment(session, renter, payment_id)
    reconcile(session, _require(provider), payment_id)
    session.expire_all()
    return get_own_payment(session, renter, payment_id)


def list_booking_payments(session: Session, booking_id: uuid.UUID) -> list[Payment]:
    return list(
        session.scalars(
            select(Payment)
            .options(selectinload(Payment.refunds))
            .where(Payment.booking_id == booking_id)
            .order_by(Payment.created_at)
        )
    )


# --- refunds --------------------------------------------------------------------------------------


def refunded_total(payment: Payment) -> Decimal:
    return sum(
        (r.amount for r in payment.refunds if r.status != RefundStatus.FAILED), Decimal("0.00")
    )


def _issue_refund(
    session: Session,
    provider: PaymentProvider,
    payment: Payment,
    *,
    amount: Decimal,
    reason: str,
    actor: User | None,
) -> Refund:
    refund = Refund(
        payment_id=payment.id,
        provider=payment.provider,
        amount=amount,
        currency=payment.currency,
        status=RefundStatus.PENDING,
        reason=reason[:500],
        requested_by_id=actor.id if actor else None,
    )
    payment.refunds.append(refund)  # keep the loaded collection consistent (status maths)
    session.flush()
    try:
        result = provider.create_refund(
            reference=payment.provider_reference, amount_cents=to_cents(amount), note=reason
        )
        refund.provider_refund_id = result.refund_id
        _apply_refund_state(session, payment, refund, result.status)
    except PaymentProviderError as exc:
        refund.status = RefundStatus.FAILED
        refund.failure_reason = str(exc)[:500]
        logger.error("Refund for payment %s failed to start: %s", payment.id, exc)
    record_audit(
        session,
        actor_id=actor.id if actor else None,
        action="refund.requested",
        entity_type="payment",
        entity_id=payment.id,
        changes={
            "refund_id": str(refund.id),
            "amount": str(amount),
            "reason": reason,
            "status": refund.status.value,
        },
    )
    session.commit()
    return refund


def _apply_refund_state(session: Session, payment: Payment, refund: Refund, state: str) -> None:
    if state == "processed":
        refund.status = RefundStatus.PROCESSED
        refund.processed_at = refund.processed_at or _now()
        notify_events.refund_processed(session, refund, payment.booking)  # once per refund
    elif state == "failed":
        refund.status = RefundStatus.FAILED
    session_total = sum(
        (r.amount for r in payment.refunds if r.status == RefundStatus.PROCESSED), Decimal("0.00")
    )
    if session_total >= payment.amount:
        payment.status = PaymentStatus.REFUNDED
    elif session_total > 0 and payment.status == PaymentStatus.SUCCEEDED:
        payment.status = PaymentStatus.PARTIALLY_REFUNDED


def refund_payment(
    session: Session,
    provider: PaymentProvider | None,
    *,
    admin: User,
    payment_id: uuid.UUID,
    amount: Decimal | None,
    reason: str,
) -> Refund:
    provider = _require(provider)
    payment = session.scalar(
        select(Payment)
        .options(selectinload(Payment.refunds))
        .where(Payment.id == payment_id)
        .with_for_update()
    )
    if payment is None:
        raise NotFoundError("Payment not found.")
    if payment.status not in (
        PaymentStatus.SUCCEEDED,
        PaymentStatus.PARTIALLY_REFUNDED,
        PaymentStatus.REFUND_PENDING,
    ):
        raise RefundNotAllowedError(f"A {payment.status} payment cannot be refunded.")
    remaining = payment.amount - refunded_total(payment)
    amount = amount if amount is not None else remaining
    if amount <= 0 or amount > remaining:
        raise RefundNotAllowedError(
            f"The refund must be between R0.01 and the remaining R{remaining}."
        )
    return _issue_refund(session, provider, payment, amount=amount, reason=reason, actor=admin)


def refund_cancelled_booking(
    session: Session,
    provider: PaymentProvider | None,
    booking: Booking,
    *,
    actor: User,
    reason: str,
) -> Refund | None:
    """Default policy (OPEN-2 undecided): a cancelled paid booking is refunded in full."""
    payment = session.scalar(
        select(Payment)
        .options(selectinload(Payment.refunds))
        .where(Payment.booking_id == booking.id, Payment.status == PaymentStatus.SUCCEEDED)
    )
    if payment is None:
        return None
    if provider is None:
        logger.error("Booking %s cancelled with a payment but no provider configured", booking.id)
        return None
    remaining = payment.amount - refunded_total(payment)
    if remaining <= 0:
        return None
    return _issue_refund(
        session,
        provider,
        payment,
        amount=remaining,
        reason=f"Booking cancelled: {reason}",
        actor=actor,
    )


def refresh_refund(session: Session, provider: PaymentProvider, refund_id: uuid.UUID) -> Refund:
    refund = session.scalar(
        select(Refund)
        .options(selectinload(Refund.payment).selectinload(Payment.refunds))
        .where(Refund.id == refund_id)
    )
    if refund is None or refund.provider_refund_id is None or refund.status != RefundStatus.PENDING:
        return refund
    try:
        result = provider.fetch_refund(refund.provider_refund_id)
    except PaymentProviderError as exc:
        logger.warning("Could not fetch refund %s: %s", refund.id, exc)
        return refund
    _apply_refund_state(session, refund.payment, refund, result.status)
    if refund.status != RefundStatus.PENDING:
        record_audit(
            session,
            actor_id=None,
            action=f"refund.{refund.status.value.lower()}",
            entity_type="payment",
            entity_id=refund.payment_id,
            changes={"refund_id": str(refund.id), "amount": str(refund.amount)},
        )
    session.commit()
    return refund


# --- webhooks -------------------------------------------------------------------------


def handle_webhook(
    session: Session, provider: PaymentProvider | None, raw_body: bytes, headers: dict[str, str]
) -> str:
    """Authenticate, de-duplicate and process a provider notification. Returns an outcome label."""
    provider = _require(provider)
    if not provider.verify_webhook(raw_body, headers):
        logger.warning("Rejected %s webhook with an invalid signature", provider.name)
        raise InvalidWebhookSignatureError("Invalid signature.")
    try:
        body = json.loads(raw_body)
    except ValueError as exc:
        raise InvalidWebhookSignatureError("Malformed payload.") from exc
    event_type = str(body.get("event", "unknown"))[:80]
    data = body.get("data") or {}
    reference = data.get("reference") or data.get("transaction_reference")
    if not reference and isinstance(data.get("transaction"), dict):
        reference = data["transaction"].get("reference")

    event = PaymentEvent(
        provider=provider.name,
        event_key=hashlib.sha256(raw_body).hexdigest(),
        event_type=event_type,
        reference=str(reference)[:255] if reference else None,
        payload=_safe_payload(body),
    )
    session.add(event)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        return "duplicate"  # already received: acknowledge without processing again

    outcome = "ignored"
    payment = (
        session.scalar(
            select(Payment).where(
                Payment.provider == provider.name, Payment.provider_reference == reference
            )
        )
        if reference
        else None
    )
    if event_type.startswith("charge.") and payment is not None:
        session.commit()
        reconcile(session, provider, payment.id)
        outcome = f"payment {session.get(Payment, payment.id).status.value}"
    elif event_type.startswith("refund.") and payment is not None:
        # Match the refund by its provider id; if the event does not carry one we know,
        # re-check every pending refund of the payment instead.
        refund_id = str(data.get("id") or "")
        pending_ids = session.scalars(
            select(Refund.id).where(
                Refund.payment_id == payment.id,
                Refund.status == RefundStatus.PENDING,
                Refund.provider_refund_id.is_not(None),
            )
        ).all()
        matched = session.scalar(
            select(Refund.id).where(
                Refund.provider == provider.name, Refund.provider_refund_id == refund_id
            )
        )
        session.commit()
        for target in [matched] if matched is not None else pending_ids:
            refresh_refund(session, provider, target)
        if matched is not None:
            outcome = f"refund {session.get(Refund, matched).status.value}"
        else:
            outcome = f"refunds rechecked: {len(pending_ids)}"
    elif reference and payment is None:
        outcome = "unknown reference"
    stored = session.get(PaymentEvent, event.id)
    stored.processed_at = _now()
    stored.outcome = outcome
    session.commit()
    return outcome


def _safe_payload(body: dict) -> dict:
    """Keep what is useful for reconciliation; drop card and customer details (POPIA)."""
    data = body.get("data") or {}
    keep = (
        "id",
        "reference",
        "status",
        "amount",
        "currency",
        "paid_at",
        "gateway_response",
        "channel",
        "transaction_reference",
    )
    return {"event": body.get("event"), "data": {k: data.get(k) for k in keep if k in data}}


# --- reconciliation -------------------------------------------------------------------


def reconcile_pending(
    session: Session, provider: PaymentProvider, *, older_than: timedelta = timedelta(minutes=2)
) -> dict[str, int]:
    """Re-check payments still PENDING and refunds still PENDING with the provider (cron)."""
    cutoff = _now() - older_than
    payment_ids = session.scalars(
        select(Payment.id).where(
            Payment.status == PaymentStatus.PENDING, Payment.created_at <= cutoff
        )
    ).all()
    refund_ids = session.scalars(
        select(Refund.id).where(
            Refund.status == RefundStatus.PENDING, Refund.provider_refund_id.is_not(None)
        )
    ).all()
    counts = {"payments_checked": len(payment_ids), "refunds_checked": len(refund_ids)}
    for payment_id in payment_ids:
        reconcile(session, provider, payment_id)
    for refund_id in refund_ids:
        refresh_refund(session, provider, refund_id)
    return counts
