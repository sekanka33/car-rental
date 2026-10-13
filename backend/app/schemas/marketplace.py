"""Public marketplace responses. Deliberately minimal: no VIN, registration number,
owner surname, contact details, documents or anything about other renters."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import FuelType, Transmission


class PublicPrice(BaseModel):
    daily_rate: Decimal
    delivery_fee: Decimal
    deposit_amount: Decimal
    currency: str


class PublicOwner(BaseModel):
    first_name: str
    city: str
    province: str


class PublicPhoto(BaseModel):
    id: uuid.UUID
    url: str


class MarketplaceVehicle(BaseModel):
    id: uuid.UUID
    make: str
    model: str
    year: int
    transmission: Transmission
    fuel_type: FuelType
    seats: int
    colour: str | None
    city: str
    province: str
    price: PublicPrice
    owner: PublicOwner
    primary_photo_url: str | None
    photo_count: int


class MarketplaceVehicleDetail(MarketplaceVehicle):
    description: str | None
    photos: list[PublicPhoto]


class MarketplaceSearchResponse(BaseModel):
    items: list[MarketplaceVehicle]
    total: int
    limit: int
    offset: int


class UnavailablePeriod(BaseModel):
    start_at: datetime
    end_at: datetime


class AvailabilityResponse(BaseModel):
    window_start: datetime
    window_end: datetime
    unavailable: list[UnavailablePeriod]


class MarketplaceQuote(BaseModel):
    available: bool
    rental_days: int
    daily_rate: Decimal
    rental_amount: Decimal
    delivery_fee: Decimal
    deposit_amount: Decimal
    total_amount: Decimal
    currency: str
