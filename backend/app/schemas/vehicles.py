import re
import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.models.enums import FuelType, Province, Transmission, VehicleDocumentType, VehicleStatus
from app.schemas.auth import RequestModel
from app.services.verification import today_in_south_africa

Text60 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Text80 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
City = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
Colour = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=40)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]

_VIN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
_REGISTRATION = re.compile(r"^[A-Z0-9]{2,20}$")


def _normalise_registration(value: str) -> str:
    cleaned = re.sub(r"[\s-]", "", value).upper()
    if not _REGISTRATION.match(cleaned):
        raise ValueError("registration number must be 2-20 letters or digits, e.g. CA 123-456")
    return cleaned


def _normalise_vin(value: str) -> str:
    cleaned = re.sub(r"\s", "", value).upper()
    if not _VIN.match(cleaned):
        raise ValueError("VIN must be 17 characters (letters I, O and Q are not used)")
    return cleaned


def _check_year(value: int) -> int:
    latest = today_in_south_africa().year + 1
    if not 1981 <= value <= latest:
        raise ValueError(f"year must be between 1981 and {latest}")
    return value


class OwnerProfileUpdate(RequestModel):
    business_name: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None
    ) = None
    city: City | None = None
    province: Province | None = None


class VehicleCreate(RequestModel):
    """No price or status fields: prices are set by administrators, status by the workflow."""

    make: Text60
    model: Text80
    year: int
    registration_number: str
    vin: str
    colour: Colour | None = None
    transmission: Transmission
    fuel_type: FuelType
    seats: int = Field(ge=2, le=16)
    city: City
    province: Province
    description: Description | None = None

    _registration = field_validator("registration_number")(
        classmethod(lambda cls, v: _normalise_registration(v))
    )
    _vin = field_validator("vin")(classmethod(lambda cls, v: _normalise_vin(v)))
    _year = field_validator("year")(classmethod(lambda cls, v: _check_year(v)))


class VehicleUpdate(RequestModel):
    make: Text60 | None = None
    model: Text80 | None = None
    year: int | None = None
    registration_number: str | None = None
    vin: str | None = None
    colour: Colour | None = None
    transmission: Transmission | None = None
    fuel_type: FuelType | None = None
    seats: int | None = Field(default=None, ge=2, le=16)
    city: City | None = None
    province: Province | None = None
    description: Description | None = None

    _registration = field_validator("registration_number")(
        classmethod(lambda cls, v: None if v is None else _normalise_registration(v))
    )
    _vin = field_validator("vin")(
        classmethod(lambda cls, v: None if v is None else _normalise_vin(v))
    )
    _year = field_validator("year")(
        classmethod(lambda cls, v: None if v is None else _check_year(v))
    )


class ListingAvailability(RequestModel):
    available: bool


class AvailabilityBlockCreate(RequestModel):
    start_at: datetime
    end_at: datetime
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None

    @field_validator("start_at", "end_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("must include a timezone")
        return value


class RejectVehicle(RequestModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class PhotoResponse(BaseModel):
    id: uuid.UUID
    content_type: str
    size_bytes: int
    sort_order: int


class VehicleDocumentResponse(BaseModel):
    id: uuid.UUID
    document_type: VehicleDocumentType
    expiry_date: date | None
    content_type: str
    size_bytes: int
    uploaded_at: datetime
    is_current: bool


class ComplianceResponse(BaseModel):
    ok: bool
    missing: list[str]
    expired: list[str]


class AvailabilityBlockResponse(BaseModel):
    id: uuid.UUID
    start_at: datetime
    end_at: datetime
    reason: str | None


class OwnerVehicleResponse(BaseModel):
    id: uuid.UUID
    make: str
    model: str
    year: int
    registration_number: str
    vin: str
    colour: str | None
    transmission: Transmission
    fuel_type: FuelType
    seats: int
    city: str
    province: str
    description: str | None
    status: VehicleStatus
    rejection_reason: str | None
    submitted_at: datetime | None
    approved_at: datetime | None
    created_at: datetime
    photos: list[PhotoResponse]
    documents: list[VehicleDocumentResponse]
    compliance: ComplianceResponse

    @classmethod
    def from_model(cls, vehicle, **extra) -> "OwnerVehicleResponse":
        from app.services.vehicles import compliance, current_documents

        current_ids = {d.id for d in current_documents(vehicle).values()}
        status = compliance(vehicle)
        return cls(
            **{
                name: getattr(vehicle, name)
                for name in (
                    "id",
                    "make",
                    "model",
                    "year",
                    "registration_number",
                    "vin",
                    "colour",
                    "transmission",
                    "fuel_type",
                    "seats",
                    "city",
                    "province",
                    "description",
                    "status",
                    "rejection_reason",
                    "submitted_at",
                    "approved_at",
                    "created_at",
                )
            },
            photos=[
                PhotoResponse(
                    id=i.id,
                    content_type=i.content_type,
                    size_bytes=i.size_bytes,
                    sort_order=i.sort_order,
                )
                for i in vehicle.images
            ],
            documents=[
                VehicleDocumentResponse(
                    id=d.id,
                    document_type=d.document_type,
                    expiry_date=d.expiry_date,
                    content_type=d.content_type,
                    size_bytes=d.size_bytes,
                    uploaded_at=d.created_at,
                    is_current=d.id in current_ids,
                )
                for d in vehicle.documents
            ],
            compliance=ComplianceResponse(
                ok=status.ok, missing=status.missing, expired=status.expired
            ),
            **extra,
        )


class VehicleOwnerSummary(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str
    business_name: str | None


class AdminVehicleResponse(OwnerVehicleResponse):
    owner: VehicleOwnerSummary
    approved_by_id: uuid.UUID | None
