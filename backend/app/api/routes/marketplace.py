"""Public marketplace endpoints (no login required)."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import DbSession, DocumentStorageDep
from app.core.config import Settings
from app.models import Vehicle, VehiclePrice
from app.models.enums import FuelType, Province, Transmission
from app.schemas.marketplace import (
    AvailabilityResponse,
    MarketplaceQuote,
    MarketplaceSearchResponse,
    MarketplaceVehicle,
    MarketplaceVehicleDetail,
    PublicOwner,
    PublicPhoto,
    PublicPrice,
    UnavailablePeriod,
)
from app.services import marketplace
from app.services.marketplace import SearchFilters, SortOrder

router = APIRouter(prefix="/vehicles", tags=["marketplace"])
API_PREFIX = Settings.model_fields["api_v1_prefix"].default


def _photo_url(vehicle_id: uuid.UUID, photo_id: uuid.UUID) -> str:
    return f"{API_PREFIX}/vehicles/{vehicle_id}/photos/{photo_id}"


def _summary_fields(vehicle: Vehicle, price: VehiclePrice) -> dict:
    owner_user = vehicle.owner.user
    primary = vehicle.images[0] if vehicle.images else None
    return {
        "id": vehicle.id,
        "make": vehicle.make,
        "model": vehicle.model,
        "year": vehicle.year,
        "transmission": vehicle.transmission,
        "fuel_type": vehicle.fuel_type,
        "seats": vehicle.seats,
        "colour": vehicle.colour,
        "city": vehicle.city,
        "province": vehicle.province,
        "price": PublicPrice(
            daily_rate=price.daily_rate,
            delivery_fee=price.delivery_fee,
            deposit_amount=price.deposit_amount,
            currency=price.currency,
        ),
        # Privacy: first name and the vehicle's area only.
        "owner": PublicOwner(
            first_name=owner_user.full_name.split()[0],
            city=vehicle.city,
            province=vehicle.province,
        ),
        "primary_photo_url": _photo_url(vehicle.id, primary.id) if primary else None,
        "photo_count": len(vehicle.images),
    }


@router.get("", response_model=MarketplaceSearchResponse)
def search_vehicles(
    session: DbSession,
    q: Annotated[str | None, Query(max_length=60, description="Make, model or city")] = None,
    city: Annotated[str | None, Query(max_length=100)] = None,
    province: Province | None = None,
    transmission: Transmission | None = None,
    fuel_type: FuelType | None = None,
    min_seats: Annotated[int | None, Query(ge=1, le=16)] = None,
    min_daily_rate: Annotated[Decimal | None, Query(ge=0, decimal_places=2)] = None,
    max_daily_rate: Annotated[Decimal | None, Query(ge=0, decimal_places=2)] = None,
    available_from: datetime | None = None,
    available_to: datetime | None = None,
    sort: SortOrder = "price_asc",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MarketplaceSearchResponse:
    """Approved, priced vehicles only. Prices are official ZAR amounts (VAT-inclusive)."""
    filters = SearchFilters(
        q=q or None,
        city=city or None,
        province=province,
        transmission=transmission,
        fuel_type=fuel_type,
        min_seats=min_seats,
        min_daily_rate=min_daily_rate,
        max_daily_rate=max_daily_rate,
        available_from=available_from,
        available_to=available_to,
        sort=sort,
    )
    rows, total = marketplace.search(session, filters, limit=limit, offset=offset)
    return MarketplaceSearchResponse(
        items=[MarketplaceVehicle(**_summary_fields(v, p)) for v, p in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{vehicle_id}", response_model=MarketplaceVehicleDetail)
def read_vehicle(vehicle_id: uuid.UUID, session: DbSession) -> MarketplaceVehicleDetail:
    vehicle, price = marketplace.get_listed(session, vehicle_id)
    return MarketplaceVehicleDetail(
        **_summary_fields(vehicle, price),
        description=vehicle.description,
        photos=[PublicPhoto(id=i.id, url=_photo_url(vehicle.id, i.id)) for i in vehicle.images],
    )


@router.get("/{vehicle_id}/photos/{photo_id}", response_class=Response)
def read_photo(
    vehicle_id: uuid.UUID, photo_id: uuid.UUID, session: DbSession, storage: DocumentStorageDep
) -> Response:
    """Photos are public only while the vehicle is listed."""
    content_type, data = marketplace.read_public_photo(session, storage, vehicle_id, photo_id)
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=300", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/{vehicle_id}/availability", response_model=AvailabilityResponse)
def read_availability(
    vehicle_id: uuid.UUID,
    session: DbSession,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> AvailabilityResponse:
    """Booked or blocked periods (default window: the next 60 days)."""
    start = start_at or datetime.now(UTC)
    end = end_at or start + timedelta(days=60)
    periods = marketplace.unavailable_periods(session, vehicle_id, start, end)
    return AvailabilityResponse(
        window_start=start,
        window_end=end,
        unavailable=[UnavailablePeriod(start_at=p.start_at, end_at=p.end_at) for p in periods],
    )


@router.get("/{vehicle_id}/quote", response_model=MarketplaceQuote)
def read_quote(
    vehicle_id: uuid.UUID,
    session: DbSession,
    start_at: Annotated[datetime, Query()],
    end_at: Annotated[datetime, Query()],
) -> MarketplaceQuote:
    """Official price for the period and whether the vehicle is free. Not a booking."""
    result, available = marketplace.quote(session, vehicle_id, start_at, end_at)
    return MarketplaceQuote(
        available=available,
        rental_days=result.rental_days,
        daily_rate=result.daily_rate,
        rental_amount=result.rental_amount,
        delivery_fee=result.delivery_fee,
        deposit_amount=result.deposit_amount,
        total_amount=result.total_amount,
        currency=result.currency,
    )
