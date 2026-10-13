import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import AdminUser, DbSession, DocumentStorageDep
from app.api.routes.customers import PRIVATE_FILE_HEADERS
from app.models.enums import VehicleStatus
from app.schemas.vehicles import AdminVehicleResponse, RejectVehicle, VehicleOwnerSummary
from app.services import vehicles

router = APIRouter(prefix="/admin/vehicles", tags=["admin: vehicles"])


def _admin_view(vehicle) -> AdminVehicleResponse:
    return AdminVehicleResponse.from_model(
        vehicle,
        owner=VehicleOwnerSummary(
            user_id=vehicle.owner.user.id,
            full_name=vehicle.owner.user.full_name,
            email=vehicle.owner.user.email,
            business_name=vehicle.owner.business_name,
        ),
        approved_by_id=vehicle.approved_by_id,
    )


@router.get("", response_model=list[AdminVehicleResponse])
def list_vehicles(
    _: AdminUser,
    session: DbSession,
    status: VehicleStatus | None = VehicleStatus.PENDING_APPROVAL,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AdminVehicleResponse]:
    """Review queue (oldest submission first). Defaults to vehicles awaiting approval."""
    return [
        _admin_view(v)
        for v in vehicles.list_for_review(session, status=status, limit=limit, offset=offset)
    ]


@router.get("/{vehicle_id}", response_model=AdminVehicleResponse)
def read_vehicle(vehicle_id: uuid.UUID, _: AdminUser, session: DbSession) -> AdminVehicleResponse:
    return _admin_view(vehicles.get_vehicle(session, vehicle_id))


@router.get("/{vehicle_id}/photos/{photo_id}", response_class=Response)
def view_photo(
    vehicle_id: uuid.UUID,
    photo_id: uuid.UUID,
    admin: AdminUser,
    session: DbSession,
    storage: DocumentStorageDep,
) -> Response:
    content_type, data = vehicles.read_vehicle_file(
        session,
        storage,
        viewer=admin,
        vehicle_id=vehicle_id,
        file_id=photo_id,
        kind="photo",
        as_admin=True,
    )
    return Response(content=data, media_type=content_type, headers=PRIVATE_FILE_HEADERS)


@router.get("/{vehicle_id}/documents/{document_id}", response_class=Response)
def view_document(
    vehicle_id: uuid.UUID,
    document_id: uuid.UUID,
    admin: AdminUser,
    session: DbSession,
    storage: DocumentStorageDep,
) -> Response:
    """Every administrator view of a vehicle document is recorded in the audit log."""
    content_type, data = vehicles.read_vehicle_file(
        session,
        storage,
        viewer=admin,
        vehicle_id=vehicle_id,
        file_id=document_id,
        kind="document",
        as_admin=True,
    )
    return Response(content=data, media_type=content_type, headers=PRIVATE_FILE_HEADERS)


@router.post("/{vehicle_id}/approve", response_model=AdminVehicleResponse)
def approve(vehicle_id: uuid.UUID, admin: AdminUser, session: DbSession) -> AdminVehicleResponse:
    """Approve a vehicle for listing. It appears in the marketplace only once it also has an
    official price (Stage 08)."""
    return _admin_view(vehicles.approve_vehicle(session, reviewer=admin, vehicle_id=vehicle_id))


@router.post("/{vehicle_id}/reject", response_model=AdminVehicleResponse)
def reject(
    vehicle_id: uuid.UUID, body: RejectVehicle, admin: AdminUser, session: DbSession
) -> AdminVehicleResponse:
    return _admin_view(
        vehicles.reject_vehicle(session, reviewer=admin, vehicle_id=vehicle_id, reason=body.reason)
    )
