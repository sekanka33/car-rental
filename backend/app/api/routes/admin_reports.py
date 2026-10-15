"""Administrator dashboard: platform aggregates and the audit log (FR-35). Read-only."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.deps import AdminUser, DbSession
from app.models.enums import BookingStatus, RoleName, VehicleStatus
from app.services import reports

router = APIRouter(prefix="/admin", tags=["admin: reports"])


class OverviewResponse(BaseModel):
    verifications_pending: int
    vehicles_pending_approval: int
    deliveries_needing_attention: int = Field(description="Failed, or with an open exception")
    refunds_pending: int
    refunds_failed: int
    notifications_failed: int = Field(description="Emails or pushes that could not be sent")
    bookings_upcoming: int
    bookings_under_way: int
    users_by_role: dict[RoleName, int]
    users_suspended: int
    vehicles_by_status: dict[VehicleStatus, int]
    bookings_by_status: dict[BookingStatus, int]
    month: str = Field(description="Current month, YYYY-MM (South African time)")
    month_collected: Decimal = Field(description="Payments received this month")
    month_refunded: Decimal = Field(description="Refunds processed this month")
    currency: str = "ZAR"


class MonthResponse(BaseModel):
    month: str
    bookings_confirmed: int
    collected: Decimal
    refunded: Decimal
    net: Decimal
    new_renters: int
    new_owners: int


class AuditActor(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str


class AuditLogResponse(BaseModel):
    id: int
    created_at: datetime
    action: str
    entity_type: str
    entity_id: str
    actor: AuditActor | None = Field(description="None for system actions (e.g. webhooks)")
    changes: dict[str, Any] | None


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int
    limit: int
    offset: int


@router.get("/reports/overview", response_model=OverviewResponse)
def read_overview(_: AdminUser, session: DbSession) -> OverviewResponse:
    """Work queues, platform counts and this month's money (cash basis)."""
    result = reports.overview(session)
    return OverviewResponse(**result.__dict__)


@router.get("/reports/monthly", response_model=list[MonthResponse])
def read_monthly(
    _: AdminUser,
    session: DbSession,
    months: Annotated[int, Query(ge=1, le=reports.MAX_MONTHS)] = 12,
) -> list[MonthResponse]:
    """The last `months` months, oldest first, zero-filled: confirmed bookings, money received
    and refunded (cash basis), and new renter and owner accounts."""
    return [
        MonthResponse(**row.__dict__, net=row.net)
        for row in reports.monthly(session, months=months)
    ]


@router.get("/audit-logs", response_model=AuditLogListResponse)
def list_audit_logs(
    _: AdminUser,
    session: DbSession,
    entity_type: Annotated[str | None, Query(max_length=50)] = None,
    entity_id: Annotated[str | None, Query(max_length=64)] = None,
    actor_user_id: uuid.UUID | None = None,
    action: Annotated[
        str | None, Query(max_length=100, description="Prefix, e.g. 'vehicle.'")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditLogListResponse:
    """Sensitive actions, newest first. Entries never contain secrets or full ID numbers."""
    rows, total = reports.list_audit_logs(
        session,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        action=action,
        limit=limit,
        offset=offset,
    )
    return AuditLogListResponse(
        items=[
            AuditLogResponse(
                id=log.id,
                created_at=log.created_at,
                action=log.action,
                entity_type=log.entity_type,
                entity_id=log.entity_id,
                actor=AuditActor(id=user.id, full_name=user.full_name, email=user.email)
                if user
                else None,
                changes=log.changes,
            )
            for log, user in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
