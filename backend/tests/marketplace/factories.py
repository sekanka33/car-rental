"""Build marketplace-ready vehicles directly in the database (test data only)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.integrations.storage import InMemoryDocumentStorage
from app.models import OwnerProfile, VehicleDocument, VehicleImage, VehiclePrice
from app.models.enums import VehicleDocumentType, VehicleStatus
from app.services.verification import today_in_south_africa
from tests.db.factories import create_user, create_vehicle
from tests.verification.helpers import JPEG

PHOTO = JPEG


def listed_vehicle(
    session: Session,
    storage: InMemoryDocumentStorage,
    *,
    owner_name: str = "Lerato Mokoena",
    daily_rate: str = "650.00",
    photos: int = 2,
    status: VehicleStatus = VehicleStatus.APPROVED,
    **vehicle_fields,
):
    owner_user = create_user(session, full_name=owner_name)
    owner = OwnerProfile(user_id=owner_user.id)
    session.add(owner)
    session.flush()
    vehicle = create_vehicle(session, owner_id=owner.id, **vehicle_fields)
    now = datetime.now(UTC)
    vehicle.status = status
    vehicle.approved_at = now - timedelta(days=1)
    if status == VehicleStatus.SUSPENDED:
        vehicle.suspended_at = now
    for doc_type, expiry in (
        (VehicleDocumentType.REGISTRATION_CERTIFICATE, None),
        (VehicleDocumentType.LICENCE_DISC, today_in_south_africa() + timedelta(days=200)),
        (VehicleDocumentType.INSURANCE, today_in_south_africa() + timedelta(days=300)),
    ):
        session.add(
            VehicleDocument(
                vehicle_id=vehicle.id,
                document_type=doc_type,
                expiry_date=expiry,
                storage_key=storage.save(b"%PDF-doc"),
                content_type="application/pdf",
                size_bytes=8,
                sha256="0" * 64,
                uploaded_by_id=owner_user.id,
                created_at=now - timedelta(days=2),
            )
        )
    for order in range(photos):
        session.add(
            VehicleImage(
                vehicle_id=vehicle.id,
                storage_key=storage.save(PHOTO + bytes([order])),
                content_type="image/jpeg",
                size_bytes=len(PHOTO) + 1,
                sha256="0" * 64,
                sort_order=order,
            )
        )
    if daily_rate is not None:
        add_price(session, vehicle, daily_rate, effective_from=now - timedelta(hours=1))
    session.flush()
    session.refresh(vehicle)
    return vehicle


def add_price(
    session: Session, vehicle, daily_rate: str, *, effective_from: datetime
) -> VehiclePrice:
    price = VehiclePrice(
        vehicle_id=vehicle.id,
        daily_rate=Decimal(daily_rate),
        delivery_fee=Decimal("150.00"),
        deposit_amount=Decimal("2000.00"),
        effective_from=effective_from,
        created_by_id=create_user(session).id,
    )
    session.add(price)
    session.flush()
    return price
