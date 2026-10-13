import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import AdminUser, DbSession, PaymentProviderDep
from app.models import Payment
from app.models.enums import PaymentStatus
from app.schemas.payments import PaymentResponse, ReconcileResponse, RefundCreate, RefundResponse
from app.services import payments

router = APIRouter(prefix="/admin/payments", tags=["admin: payments"])


@router.get("", response_model=list[PaymentResponse])
def list_payments(
    _: AdminUser,
    session: DbSession,
    status_filter: Annotated[PaymentStatus | None, Query(alias="status")] = None,
    booking_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PaymentResponse]:
    query = select(Payment).options(selectinload(Payment.refunds), selectinload(Payment.booking))
    if status_filter is not None:
        query = query.where(Payment.status == status_filter)
    if booking_id is not None:
        query = query.where(Payment.booking_id == booking_id)
    rows = session.scalars(
        query.order_by(Payment.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return [PaymentResponse.from_model(p, booking_status=p.booking.status) for p in rows]


@router.post(
    "/{payment_id}/refunds", status_code=status.HTTP_201_CREATED, response_model=RefundResponse
)
def refund(
    payment_id: uuid.UUID,
    body: RefundCreate,
    admin: AdminUser,
    session: DbSession,
    provider: PaymentProviderDep,
) -> RefundResponse:
    """Refund all or part of a payment through the provider (audited)."""
    created = payments.refund_payment(
        session,
        provider,
        admin=admin,
        payment_id=payment_id,
        amount=body.amount,
        reason=body.reason,
    )
    return RefundResponse(
        id=created.id,
        amount=created.amount,
        currency=created.currency,
        status=created.status,
        reason=created.reason,
        created_at=created.created_at,
        processed_at=created.processed_at,
    )


@router.post("/reconcile", response_model=ReconcileResponse)
def reconcile(_: AdminUser, session: DbSession, provider: PaymentProviderDep) -> ReconcileResponse:
    """Re-check pending payments and refunds with the provider now."""
    counts = payments.reconcile_pending(session, payments._require(provider))
    return ReconcileResponse(**counts)
