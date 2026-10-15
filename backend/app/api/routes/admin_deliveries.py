import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import AdminUser, DbSession, DocumentStorageDep, TrackingHubDep
from app.api.routes.customers import PRIVATE_FILE_HEADERS
from app.models.enums import DeliveryStatus
from app.schemas.deliveries import (
    AdminDeliveryResponse,
    AdminReassign,
    AdminReschedule,
    ResolveException,
)
from app.services import deliveries, tracking

router = APIRouter(prefix="/admin/deliveries", tags=["admin: deliveries"])


@router.get("", response_model=list[AdminDeliveryResponse])
def list_deliveries(
    _: AdminUser,
    session: DbSession,
    status_filter: Annotated[DeliveryStatus | None, Query(alias="status")] = None,
    open_exceptions: Annotated[bool, Query(description="Only those needing attention")] = False,
    booking_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AdminDeliveryResponse]:
    return [
        AdminDeliveryResponse.for_admin(d)
        for d in deliveries.list_deliveries(
            session,
            status=status_filter,
            open_exceptions=open_exceptions,
            booking_id=booking_id,
            limit=limit,
            offset=offset,
        )
    ]


@router.get("/{delivery_id}", response_model=AdminDeliveryResponse)
def read_delivery(
    delivery_id: uuid.UUID, _: AdminUser, session: DbSession
) -> AdminDeliveryResponse:
    return AdminDeliveryResponse.for_admin(deliveries.get_delivery(session, delivery_id))


@router.post("/{delivery_id}/assign", response_model=AdminDeliveryResponse)
def reassign(
    delivery_id: uuid.UUID,
    body: AdminReassign,
    admin: AdminUser,
    session: DbSession,
    hub: TrackingHubDep,
) -> AdminDeliveryResponse:
    """Hand the delivery to another active owner account (audited). The previous assignee's
    live view is closed."""
    delivery = deliveries.reassign(session, admin, delivery_id, body.user_id)
    tracking.publish(hub, session, delivery.id, "status")
    return AdminDeliveryResponse.for_admin(delivery)


@router.post("/{delivery_id}/reschedule", response_model=AdminDeliveryResponse)
def reschedule(
    delivery_id: uuid.UUID,
    body: AdminReschedule,
    admin: AdminUser,
    session: DbSession,
    hub: TrackingHubDep,
) -> AdminDeliveryResponse:
    """Set a new delivery time (e.g. after a failed attempt); resolves open exceptions.
    To give up instead, cancel the booking (`POST /admin/bookings/{id}/cancel`); it is
    refunded."""
    delivery = deliveries.admin_reschedule(
        session, admin, delivery_id, body.scheduled_for, body.note
    )
    tracking.publish(hub, session, delivery.id, "status")
    return AdminDeliveryResponse.for_admin(delivery)


@router.post(
    "/{delivery_id}/exceptions/{exception_id}/resolve", response_model=AdminDeliveryResponse
)
def resolve_exception(
    delivery_id: uuid.UUID,
    exception_id: uuid.UUID,
    body: ResolveException,
    admin: AdminUser,
    session: DbSession,
) -> AdminDeliveryResponse:
    return AdminDeliveryResponse.for_admin(
        deliveries.resolve_exception(session, admin, delivery_id, exception_id, body.note)
    )


@router.get("/{delivery_id}/photos/{photo_id}", response_class=Response)
def read_photo(
    delivery_id: uuid.UUID,
    photo_id: uuid.UUID,
    _: AdminUser,
    session: DbSession,
    storage: DocumentStorageDep,
) -> Response:
    delivery = deliveries.get_delivery(session, delivery_id)
    content_type, data = deliveries.read_photo(session, storage, delivery, photo_id)
    return Response(content=data, media_type=content_type, headers=PRIVATE_FILE_HEADERS)
