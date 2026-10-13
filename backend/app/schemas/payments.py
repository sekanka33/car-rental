import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.models.enums import BookingStatus, PaymentStatus, RefundStatus
from app.schemas.auth import RequestModel


class RefundResponse(BaseModel):
    id: uuid.UUID
    amount: Decimal
    currency: str
    status: RefundStatus
    reason: str
    created_at: datetime
    processed_at: datetime | None


class PaymentResponse(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    reference: str
    provider: str
    status: PaymentStatus
    amount: Decimal
    currency: str
    checkout_url: str | None = Field(description="Open this to pay (only while PENDING)")
    paid_at: datetime | None
    failure_reason: str | None
    created_at: datetime
    refunds: list[RefundResponse]
    booking_status: BookingStatus | None = None

    @classmethod
    def from_model(cls, payment, booking_status=None) -> "PaymentResponse":
        return cls(
            id=payment.id,
            booking_id=payment.booking_id,
            reference=payment.provider_reference,
            provider=payment.provider,
            status=payment.status,
            amount=payment.amount,
            currency=payment.currency,
            checkout_url=payment.checkout_url if payment.status == PaymentStatus.PENDING else None,
            paid_at=payment.paid_at,
            failure_reason=payment.failure_reason,
            created_at=payment.created_at,
            refunds=[
                RefundResponse(
                    id=r.id,
                    amount=r.amount,
                    currency=r.currency,
                    status=r.status,
                    reason=r.reason,
                    created_at=r.created_at,
                    processed_at=r.processed_at,
                )
                for r in payment.refunds
            ],
            booking_status=booking_status,
        )


class RefundCreate(RequestModel):
    amount: Annotated[Decimal, Field(gt=0, max_digits=9, decimal_places=2)] | None = Field(
        default=None, description="Omit to refund everything not yet refunded"
    )
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class ReconcileResponse(BaseModel):
    payments_checked: int
    refunds_checked: int
