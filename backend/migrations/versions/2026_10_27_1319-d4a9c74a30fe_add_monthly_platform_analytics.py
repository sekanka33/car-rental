"""add monthly platform analytics snapshot

Revision ID: d4a9c74a30fe
Revises: b9840115d8b9
Create Date: 2026-10-27 13:19:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d4a9c74a30fe"
down_revision: str | Sequence[str] | None = "b9840115d8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "monthly_platform_analytics",
        sa.Column("month_start", sa.Date(), nullable=False),
        sa.Column("bookings_created", sa.Integer(), nullable=False),
        sa.Column(
            "bookings_by_current_status",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("cash_collected", sa.Numeric(12, 2), nullable=False),
        sa.Column("cash_refunded", sa.Numeric(12, 2), nullable=False),
        sa.Column("net_cash", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="ZAR", nullable=False),
        sa.Column(
            "refreshed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "EXTRACT(DAY FROM month_start) = 1",
            name=op.f("ck_monthly_platform_analytics_first_day_of_month"),
        ),
        sa.CheckConstraint(
            "bookings_created >= 0",
            name=op.f("ck_monthly_platform_analytics_bookings_created_non_negative"),
        ),
        sa.CheckConstraint(
            "cash_collected >= 0",
            name=op.f("ck_monthly_platform_analytics_cash_collected_non_negative"),
        ),
        sa.CheckConstraint(
            "cash_refunded >= 0",
            name=op.f("ck_monthly_platform_analytics_cash_refunded_non_negative"),
        ),
        sa.CheckConstraint(
            "currency = 'ZAR'",
            name=op.f("ck_monthly_platform_analytics_currency_zar"),
        ),
        sa.PrimaryKeyConstraint("month_start", name=op.f("pk_monthly_platform_analytics")),
    )


def downgrade() -> None:
    op.drop_table("monthly_platform_analytics")
