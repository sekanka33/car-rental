"""Administrator-only access to persisted data-pipeline output."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.deps import AdminUser, DbSession
from app.models.enums import BookingStatus
from app.services import analytics

router = APIRouter(prefix="/admin/analytics", tags=["admin: analytics"])


class MonthlyAnalyticsItem(BaseModel):
    month: str = Field(description="South African calendar month, YYYY-MM")
    bookings_created: int
    bookings_by_current_status: dict[BookingStatus, int]
    cash_collected: Decimal
    cash_refunded: Decimal
    net_cash: Decimal
    currency: str
    refreshed_at: datetime


class MonthlyAnalyticsResponse(BaseModel):
    items: list[MonthlyAnalyticsItem]
    months_requested: int
    basis: str = (
        "Booking counts use booking creation month and current status at refresh time. "
        "Cash collected uses payment paid_at; cash refunded uses processed refund processed_at. "
        "Payments without paid_at and refunds not processed are excluded."
    )


@router.get("/monthly", response_model=MonthlyAnalyticsResponse)
def read_monthly_analytics(
    _: AdminUser,
    session: DbSession,
    months: Annotated[int, Query(ge=1, le=120)] = 12,
) -> MonthlyAnalyticsResponse:
    """Stored monthly pipeline output, oldest first; administrators only."""
    rows = analytics.list_monthly_analytics(session, months=months)
    return MonthlyAnalyticsResponse(
        months_requested=months,
        items=[
            MonthlyAnalyticsItem(
                month=row.month_start.strftime("%Y-%m"),
                bookings_created=row.bookings_created,
                bookings_by_current_status=row.bookings_by_current_status,
                cash_collected=row.cash_collected,
                cash_refunded=row.cash_refunded,
                net_cash=row.net_cash,
                currency=row.currency,
                refreshed_at=row.refreshed_at,
            )
            for row in rows
        ],
    )
