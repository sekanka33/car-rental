from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import CURRENCY_ZAR, Base, Money


class MonthlyPlatformAnalytics(Base):
    """Replaceable, derived monthly aggregates populated by the analytics refresh command."""

    __tablename__ = "monthly_platform_analytics"
    __table_args__ = (
        CheckConstraint("EXTRACT(DAY FROM month_start) = 1", name="first_day_of_month"),
        CheckConstraint("bookings_created >= 0", name="bookings_created_non_negative"),
        CheckConstraint("cash_collected >= 0", name="cash_collected_non_negative"),
        CheckConstraint("cash_refunded >= 0", name="cash_refunded_non_negative"),
        CheckConstraint(f"currency = '{CURRENCY_ZAR}'", name="currency_zar"),
    )

    month_start: Mapped[date] = mapped_column(Date, primary_key=True)
    bookings_created: Mapped[int] = mapped_column(Integer)
    bookings_by_current_status: Mapped[dict[str, int]] = mapped_column(JSONB)
    cash_collected: Mapped[Decimal] = mapped_column(Money)
    cash_refunded: Mapped[Decimal] = mapped_column(Money)
    net_cash: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(
        String(3), default=CURRENCY_ZAR, server_default=CURRENCY_ZAR
    )
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
