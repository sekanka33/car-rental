import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import AdminUser, DbSession, DocumentStorageDep
from app.api.routes.customers import PRIVATE_FILE_HEADERS
from app.models.enums import VehicleStatus
from app.schemas.vehicles import (
    AdminVehicleResponse,
    OfficialPriceCreate,
    OfficialPriceResponse,
    QuoteResponse,
    RejectVehicle,
    SuspendVehicle,
    VehicleOwnerSummary,
)
from app.services import pricing, vehicles

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
    status_filter: Annotated[
        VehicleStatus | None, Query(alias="status")
    ] = VehicleStatus.PENDING_APPROVAL,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AdminVehicleResponse]:
    """Review queue (oldest submission first). Defaults to vehicles awaiting approval."""
    return [
        _admin_view(v)
        for v in vehicles.list_for_review(session, status=status_filter, limit=limit, offset=offset)
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


@router.post("/{vehicle_id}/suspend", response_model=AdminVehicleResponse)
def suspend(
    vehicle_id: uuid.UUID, body: SuspendVehicle, admin: AdminUser, session: DbSession
) -> AdminVehicleResponse:
    """Remove a vehicle from the marketplace. Existing bookings are not cancelled automatically."""
    return _admin_view(
        vehicles.suspend_vehicle(session, admin=admin, vehicle_id=vehicle_id, reason=body.reason)
    )


@router.post("/{vehicle_id}/reinstate", response_model=AdminVehicleResponse)
def reinstate(vehicle_id: uuid.UUID, admin: AdminUser, session: DbSession) -> AdminVehicleResponse:
    return _admin_view(vehicles.reinstate_vehicle(session, admin=admin, vehicle_id=vehicle_id))


def _price_response(price, current_id) -> OfficialPriceResponse:
    return OfficialPriceResponse(
        id=price.id,
        daily_rate=price.daily_rate,
        delivery_fee=price.delivery_fee,
        deposit_amount=price.deposit_amount,
        currency=price.currency,
        effective_from=price.effective_from,
        change_reason=price.change_reason,
        created_by_id=price.created_by_id,
        created_at=price.created_at,
        is_current=price.id == current_id,
    )


@router.get("/{vehicle_id}/prices", response_model=list[OfficialPriceResponse])
def list_prices(
    vehicle_id: uuid.UUID, _: AdminUser, session: DbSession
) -> list[OfficialPriceResponse]:
    """Full official price history, newest first (including scheduled future prices)."""
    history = pricing.price_history(session, vehicle_id)
    current = pricing.current_price(session, vehicle_id)
    return [_price_response(p, current.id if current else None) for p in history]


@router.post(
    "/{vehicle_id}/prices",
    status_code=status.HTTP_201_CREATED,
    response_model=OfficialPriceResponse,
)
def set_price(
    vehicle_id: uuid.UUID, body: OfficialPriceCreate, admin: AdminUser, session: DbSession
) -> OfficialPriceResponse:
    """Set a new official price (ZAR, VAT-inclusive). Earlier prices are kept as history and
    existing bookings keep the price they were made at."""
    price = pricing.set_official_price(
        session,
        admin=admin,
        vehicle_id=vehicle_id,
        daily_rate=body.daily_rate,
        delivery_fee=body.delivery_fee,
        deposit_amount=body.deposit_amount,
        change_reason=body.change_reason,
        effective_from=body.effective_from,
    )
    current = pricing.current_price(session, vehicle_id)
    return _price_response(price, current.id if current else None)


@router.get("/{vehicle_id}/quote", response_model=QuoteResponse)
def quote(
    vehicle_id: uuid.UUID,
    _: AdminUser,
    session: DbSession,
    start_at: Annotated[datetime, Query()],
    end_at: Annotated[datetime, Query()],
) -> QuoteResponse:
    """Preview the price breakdown for a rental period at the current official price."""
    result = pricing.quote_for_vehicle(session, vehicle_id, start_at, end_at)
    return QuoteResponse(**result.__dict__)
