"""The delivery person's side (OPEN-3 default: the vehicle owner delivers)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Query, Response, UploadFile, status

from app.api.deps import (
    AppSettings,
    DbSession,
    DocumentStorageDep,
    MapsProviderDep,
    OwnerUser,
    TrackingHubDep,
)
from app.api.routes.customers import PRIVATE_FILE_HEADERS
from app.models.enums import HandoverKind
from app.schemas.deliveries import (
    AssignedDeliveryResponse,
    ExceptionCreate,
    HandoverCreate,
    HandoverPhotoResponse,
    LocationUpdate,
    ScheduleDelivery,
)
from app.services import deliveries, tracking

router = APIRouter(prefix="/owners/me/deliveries", tags=["owner: deliveries"])


@router.get("", response_model=list[AssignedDeliveryResponse])
def list_my_deliveries(
    user: OwnerUser,
    session: DbSession,
    active: Annotated[bool, Query(description="Only deliveries and returns still to do")] = True,
) -> list[AssignedDeliveryResponse]:
    return [
        AssignedDeliveryResponse.for_assignee(d)
        for d in deliveries.list_assigned(session, user, active_only=active)
    ]


@router.get("/{delivery_id}", response_model=AssignedDeliveryResponse)
def read_my_delivery(
    delivery_id: uuid.UUID, user: OwnerUser, session: DbSession
) -> AssignedDeliveryResponse:
    return AssignedDeliveryResponse.for_assignee(
        deliveries.get_assigned_delivery(session, user, delivery_id)
    )


@router.post("/{delivery_id}/schedule", response_model=AssignedDeliveryResponse)
def schedule_delivery(
    delivery_id: uuid.UUID,
    body: ScheduleDelivery,
    user: OwnerUser,
    session: DbSession,
    hub: TrackingHubDep,
) -> AssignedDeliveryResponse:
    """Confirm (or change) the delivery time: within 24 hours before the rental start."""
    delivery = deliveries.schedule(session, user, delivery_id, body.scheduled_for)
    tracking.publish(hub, session, delivery.id, "status")
    return AssignedDeliveryResponse.for_assignee(delivery)


@router.post("/{delivery_id}/start", response_model=AssignedDeliveryResponse)
def start_delivery(
    delivery_id: uuid.UUID, user: OwnerUser, session: DbSession, hub: TrackingHubDep
) -> AssignedDeliveryResponse:
    delivery = deliveries.start(session, user, delivery_id)
    tracking.publish(hub, session, delivery.id, "status")
    return AssignedDeliveryResponse.for_assignee(delivery)


@router.post("/{delivery_id}/handover", response_model=AssignedDeliveryResponse)
def complete_handover(
    delivery_id: uuid.UUID,
    body: HandoverCreate,
    user: OwnerUser,
    session: DbSession,
    hub: TrackingHubDep,
) -> AssignedDeliveryResponse:
    """The car is with the renter: record odometer, fuel and condition."""
    delivery = deliveries.complete_handover(session, user, delivery_id, **body.model_dump())
    tracking.publish(hub, session, delivery.id, "status")
    return AssignedDeliveryResponse.for_assignee(delivery)


@router.post("/{delivery_id}/return", response_model=AssignedDeliveryResponse)
def record_return(
    delivery_id: uuid.UUID,
    body: HandoverCreate,
    user: OwnerUser,
    session: DbSession,
    hub: TrackingHubDep,
) -> AssignedDeliveryResponse:
    """The car is back: record its condition. Completes the booking."""
    delivery = deliveries.record_return(session, user, delivery_id, **body.model_dump())
    tracking.publish(hub, session, delivery.id, "status")
    return AssignedDeliveryResponse.for_assignee(delivery)


@router.post("/{delivery_id}/exceptions", response_model=AssignedDeliveryResponse)
def report_exception(
    delivery_id: uuid.UUID,
    body: ExceptionCreate,
    user: OwnerUser,
    session: DbSession,
    hub: TrackingHubDep,
) -> AssignedDeliveryResponse:
    """Report a problem. DELAY is informational; anything else stops the delivery until an
    administrator reschedules it or cancels the booking. The renter sees the notes."""
    delivery = deliveries.report_exception(
        session, user, delivery_id, kind=body.kind, notes=body.notes
    )
    tracking.publish(hub, session, delivery.id, "status")
    return AssignedDeliveryResponse.for_assignee(delivery)


@router.post(
    "/{delivery_id}/records/{kind}/photos",
    status_code=status.HTTP_201_CREATED,
    response_model=HandoverPhotoResponse,
)
def upload_record_photo(
    delivery_id: uuid.UUID,
    kind: HandoverKind,
    user: OwnerUser,
    session: DbSession,
    settings: AppSettings,
    storage: DocumentStorageDep,
    photo: Annotated[UploadFile, File(description="JPEG, PNG or WebP")],
) -> HandoverPhotoResponse:
    data = photo.file.read(settings.max_document_bytes + 1)
    created = deliveries.add_photo(
        session, storage, user, delivery_id, kind, data, max_bytes=settings.max_document_bytes
    )
    return HandoverPhotoResponse(
        id=created.id,
        url=f"/api/v1/owners/me/deliveries/{delivery_id}/photos/{created.id}",
        content_type=created.content_type,
        created_at=created.created_at,
    )


@router.get("/{delivery_id}/photos/{photo_id}", response_class=Response)
def read_record_photo(
    delivery_id: uuid.UUID,
    photo_id: uuid.UUID,
    user: OwnerUser,
    session: DbSession,
    storage: DocumentStorageDep,
) -> Response:
    delivery = deliveries.get_assigned_delivery(session, user, delivery_id)
    content_type, data = deliveries.read_photo(session, storage, delivery, photo_id)
    return Response(content=data, media_type=content_type, headers=PRIVATE_FILE_HEADERS)


@router.post("/{delivery_id}/location", status_code=status.HTTP_204_NO_CONTENT)
def share_location(
    delivery_id: uuid.UUID,
    body: LocationUpdate,
    user: OwnerUser,
    session: DbSession,
    settings: AppSettings,
    maps: MapsProviderDep,
    hub: TrackingHubDep,
) -> Response:
    """Send the current position while the car is on its way (409 otherwise). At most one
    update every LOCATION_MIN_INTERVAL_SECONDS (429). The renter sees the latest position."""
    delivery = tracking.record_location(
        session, settings, maps, user, delivery_id, **body.model_dump()
    )
    tracking.publish(hub, session, delivery.id, "location")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
