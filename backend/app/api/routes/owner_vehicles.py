"""Owner vehicle management: registration, photos, documents, review, availability."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile, status

from app.api.deps import AppSettings, DbSession, DocumentStorageDep, OwnerUser
from app.api.routes.customers import PRIVATE_FILE_HEADERS
from app.models.enums import VehicleDocumentType
from app.schemas.vehicles import (
    AvailabilityBlockCreate,
    AvailabilityBlockResponse,
    ListingAvailability,
    OwnerVehicleResponse,
    PhotoResponse,
    VehicleCreate,
    VehicleDocumentResponse,
    VehicleUpdate,
)
from app.services import vehicles

router = APIRouter(prefix="/owners/me/vehicles", tags=["owner: vehicles"])
VehicleId = uuid.UUID


def _read(upload: UploadFile, max_bytes: int) -> bytes:
    return upload.file.read(max_bytes + 1)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=OwnerVehicleResponse)
def register_vehicle(
    body: VehicleCreate, user: OwnerUser, session: DbSession
) -> OwnerVehicleResponse:
    """Create a vehicle as a DRAFT. Add photos and documents, then submit it for review."""
    return OwnerVehicleResponse.from_model(
        vehicles.create_vehicle(session, user, **body.model_dump())
    )


@router.get("", response_model=list[OwnerVehicleResponse])
def list_my_vehicles(user: OwnerUser, session: DbSession) -> list[OwnerVehicleResponse]:
    return [OwnerVehicleResponse.from_model(v) for v in vehicles.list_owned_vehicles(session, user)]


@router.get("/{vehicle_id}", response_model=OwnerVehicleResponse)
def read_my_vehicle(
    vehicle_id: VehicleId, user: OwnerUser, session: DbSession
) -> OwnerVehicleResponse:
    return OwnerVehicleResponse.from_model(vehicles.get_owned_vehicle(session, user, vehicle_id))


@router.patch("/{vehicle_id}", response_model=OwnerVehicleResponse)
def update_my_vehicle(
    vehicle_id: VehicleId, body: VehicleUpdate, user: OwnerUser, session: DbSession
) -> OwnerVehicleResponse:
    """Editing make, model, year, registration, VIN, transmission, fuel or seats on an
    approved vehicle sends it back for review."""
    changes = body.model_dump(exclude_unset=True)
    return OwnerVehicleResponse.from_model(
        vehicles.update_vehicle(session, user, vehicle_id, **changes)
    )


@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_vehicle(
    vehicle_id: VehicleId, user: OwnerUser, session: DbSession, storage: DocumentStorageDep
) -> None:
    vehicles.delete_vehicle(session, storage, user, vehicle_id)


@router.post("/{vehicle_id}/submit", response_model=OwnerVehicleResponse)
def submit_my_vehicle(
    vehicle_id: VehicleId, user: OwnerUser, session: DbSession
) -> OwnerVehicleResponse:
    return OwnerVehicleResponse.from_model(vehicles.submit_for_review(session, user, vehicle_id))


@router.post("/{vehicle_id}/withdraw", response_model=OwnerVehicleResponse)
def withdraw_my_vehicle(
    vehicle_id: VehicleId, user: OwnerUser, session: DbSession
) -> OwnerVehicleResponse:
    return OwnerVehicleResponse.from_model(vehicles.withdraw_from_review(session, user, vehicle_id))


@router.put("/{vehicle_id}/listing", response_model=OwnerVehicleResponse)
def set_listing(
    vehicle_id: VehicleId, body: ListingAvailability, user: OwnerUser, session: DbSession
) -> OwnerVehicleResponse:
    """Switch an approved vehicle between listed (APPROVED) and hidden (UNAVAILABLE)."""
    vehicle = vehicles.set_listing_availability(session, user, vehicle_id, available=body.available)
    return OwnerVehicleResponse.from_model(vehicle)


@router.post(
    "/{vehicle_id}/photos", status_code=status.HTTP_201_CREATED, response_model=PhotoResponse
)
def upload_photo(
    vehicle_id: VehicleId,
    user: OwnerUser,
    session: DbSession,
    settings: AppSettings,
    storage: DocumentStorageDep,
    photo: Annotated[UploadFile, File(description="JPEG, PNG or WebP")],
) -> PhotoResponse:
    image = vehicles.add_photo(
        session, settings, storage, user, vehicle_id, _read(photo, settings.max_document_bytes)
    )
    return PhotoResponse(
        id=image.id,
        content_type=image.content_type,
        size_bytes=image.size_bytes,
        sort_order=image.sort_order,
    )


@router.get("/{vehicle_id}/photos/{photo_id}", response_class=Response)
def view_photo(
    vehicle_id: VehicleId,
    photo_id: uuid.UUID,
    user: OwnerUser,
    session: DbSession,
    storage: DocumentStorageDep,
) -> Response:
    content_type, data = vehicles.read_vehicle_file(
        session,
        storage,
        viewer=user,
        vehicle_id=vehicle_id,
        file_id=photo_id,
        kind="photo",
        as_admin=False,
    )
    return Response(content=data, media_type=content_type, headers=PRIVATE_FILE_HEADERS)


@router.delete("/{vehicle_id}/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_photo(
    vehicle_id: VehicleId,
    photo_id: uuid.UUID,
    user: OwnerUser,
    session: DbSession,
    storage: DocumentStorageDep,
) -> None:
    vehicles.delete_photo(session, storage, user, vehicle_id, photo_id)


@router.post(
    "/{vehicle_id}/documents",
    status_code=status.HTTP_201_CREATED,
    response_model=VehicleDocumentResponse,
)
def upload_document(
    vehicle_id: VehicleId,
    user: OwnerUser,
    session: DbSession,
    settings: AppSettings,
    storage: DocumentStorageDep,
    document_type: Annotated[VehicleDocumentType, Form()],
    file: Annotated[UploadFile, File(description="JPEG, PNG or PDF")],
    expiry_date: Annotated[
        date | None, Form(description="Required for LICENCE_DISC and INSURANCE")
    ] = None,
) -> VehicleDocumentResponse:
    document = vehicles.add_document(
        session,
        settings,
        storage,
        user,
        vehicle_id,
        document_type=document_type,
        expiry_date=expiry_date,
        data=_read(file, settings.max_document_bytes),
    )
    return VehicleDocumentResponse(
        id=document.id,
        document_type=document.document_type,
        expiry_date=document.expiry_date,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        uploaded_at=document.created_at,
        is_current=True,
    )


@router.get("/{vehicle_id}/documents/{document_id}", response_class=Response)
def view_document(
    vehicle_id: VehicleId,
    document_id: uuid.UUID,
    user: OwnerUser,
    session: DbSession,
    storage: DocumentStorageDep,
) -> Response:
    content_type, data = vehicles.read_vehicle_file(
        session,
        storage,
        viewer=user,
        vehicle_id=vehicle_id,
        file_id=document_id,
        kind="document",
        as_admin=False,
    )
    return Response(content=data, media_type=content_type, headers=PRIVATE_FILE_HEADERS)


@router.get("/{vehicle_id}/availability-blocks", response_model=list[AvailabilityBlockResponse])
def list_blocks(
    vehicle_id: VehicleId, user: OwnerUser, session: DbSession
) -> list[AvailabilityBlockResponse]:
    return [
        AvailabilityBlockResponse(id=b.id, start_at=b.start_at, end_at=b.end_at, reason=b.reason)
        for b in vehicles.list_availability_blocks(session, user, vehicle_id)
    ]


@router.post(
    "/{vehicle_id}/availability-blocks",
    status_code=status.HTTP_201_CREATED,
    response_model=AvailabilityBlockResponse,
)
def add_block(
    vehicle_id: VehicleId, body: AvailabilityBlockCreate, user: OwnerUser, session: DbSession
) -> AvailabilityBlockResponse:
    """Block dates when the vehicle cannot be rented (rejected if they overlap a booking)."""
    block = vehicles.add_availability_block(
        session, user, vehicle_id, start_at=body.start_at, end_at=body.end_at, reason=body.reason
    )
    return AvailabilityBlockResponse(
        id=block.id, start_at=block.start_at, end_at=block.end_at, reason=block.reason
    )


@router.delete(
    "/{vehicle_id}/availability-blocks/{block_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_block(
    vehicle_id: VehicleId, block_id: uuid.UUID, user: OwnerUser, session: DbSession
) -> None:
    vehicles.delete_availability_block(session, user, vehicle_id, block_id)
