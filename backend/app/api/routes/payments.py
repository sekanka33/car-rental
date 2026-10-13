import uuid

from fastapi import APIRouter, Request, status
from starlette.concurrency import run_in_threadpool

from app.api.deps import DbSession, PaymentProviderDep, RenterUser
from app.core.errors import NotFoundError
from app.models import Booking
from app.schemas.payments import PaymentResponse
from app.services import payments

router = APIRouter(tags=["payments"])


@router.post(
    "/bookings/{booking_id}/payments",
    status_code=status.HTTP_201_CREATED,
    response_model=PaymentResponse,
)
def start_payment(
    booking_id: uuid.UUID,
    user: RenterUser,
    session: DbSession,
    request: Request,
    provider: PaymentProviderDep,
) -> PaymentResponse:
    """Start (or resume) checkout for an unpaid booking. The amount is the booking's stored
    total; open `checkout_url` to pay. The booking is confirmed only after the backend
    verifies the payment with the provider."""
    payment = payments.start_checkout(
        session, request.app.state.settings, provider, user, booking_id
    )
    return PaymentResponse.from_model(payment)


@router.get("/bookings/{booking_id}/payments", response_model=list[PaymentResponse])
def list_payments(
    booking_id: uuid.UUID, user: RenterUser, session: DbSession
) -> list[PaymentResponse]:
    booking = session.get(Booking, booking_id)
    if booking is None or booking.renter_id != user.id:
        raise NotFoundError("Booking not found.")
    return [
        PaymentResponse.from_model(p) for p in payments.list_booking_payments(session, booking_id)
    ]


@router.post("/payments/{payment_id}/refresh", response_model=PaymentResponse)
def refresh_payment(
    payment_id: uuid.UUID, user: RenterUser, session: DbSession, provider: PaymentProviderDep
) -> PaymentResponse:
    """Check the payment with the provider now (e.g. after returning from checkout)."""
    payment = payments.refresh_own_payment(session, provider, user, payment_id)
    return PaymentResponse.from_model(payment, booking_status=payment.booking.status)


@router.post("/payments/webhooks/paystack", include_in_schema=True)
async def paystack_webhook(
    request: Request, session: DbSession, provider: PaymentProviderDep
) -> dict[str, str]:
    """Paystack notifications. Authenticated by HMAC-SHA512 signature, de-duplicated, and
    then verified with Paystack's API; the payload itself is never trusted."""
    raw = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    await run_in_threadpool(payments.handle_webhook, session, provider, raw, headers)
    return {"status": "ok"}
