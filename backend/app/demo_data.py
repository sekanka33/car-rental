"""DEVELOPMENT-ONLY demo marketplace data. Never runs outside APP_ENV=development.

Creates clearly marked demo accounts (demo-*@example.com, random unknown passwords),
approved vehicles with generated placeholder photos and documents, and official prices
set through the normal pricing service (so they are audited like real prices).
"""

import secrets
import struct
import zlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Environment, Settings
from app.core.security import hash_password
from app.integrations.storage import DocumentStorage
from app.models import OwnerProfile, User, Vehicle, VehicleDocument, VehicleImage
from app.models.enums import FuelType, RoleName, Transmission, VehicleDocumentType, VehicleStatus
from app.repositories.users import assign_role
from app.services.audit import record_audit
from app.services.pricing import set_official_price
from app.services.verification import today_in_south_africa

DEMO_ADMIN_EMAIL = "demo-admin@example.com"

DEMO_VEHICLES = [
    # owner, make, model, year, gearbox, fuel, seats, city, province, daily rate, photo colour
    (
        "Thabo",
        "Toyota",
        "Corolla Cross",
        2023,
        Transmission.AUTOMATIC,
        FuelType.PETROL,
        5,
        "Johannesburg",
        "Gauteng",
        "750.00",
        (31, 111, 235),
    ),
    (
        "Aisha",
        "Volkswagen",
        "Polo Vivo",
        2022,
        Transmission.MANUAL,
        FuelType.PETROL,
        5,
        "Cape Town",
        "Western Cape",
        "480.00",
        (220, 38, 38),
    ),
    (
        "Sipho",
        "Toyota",
        "Hilux 2.4 GD-6",
        2021,
        Transmission.MANUAL,
        FuelType.DIESEL,
        5,
        "Durban",
        "KwaZulu-Natal",
        "1150.00",
        (71, 85, 105),
    ),
    (
        "Lerato",
        "Suzuki",
        "Swift",
        2024,
        Transmission.AUTOMATIC,
        FuelType.PETROL,
        5,
        "Pretoria",
        "Gauteng",
        "420.00",
        (234, 179, 8),
    ),
    (
        "Johan",
        "Hyundai",
        "Grand i10",
        2023,
        Transmission.MANUAL,
        FuelType.PETROL,
        5,
        "Gqeberha",
        "Eastern Cape",
        "390.00",
        (22, 163, 74),
    ),
    (
        "Naledi",
        "Ford",
        "Ranger XLT",
        2024,
        Transmission.AUTOMATIC,
        FuelType.DIESEL,
        5,
        "Bloemfontein",
        "Free State",
        "1450.00",
        (15, 23, 42),
    ),
]


class DemoDataRefusedError(Exception):
    pass


def placeholder_png(rgb: tuple[int, int, int], width: int = 320, height: int = 200) -> bytes:
    """A plain gradient PNG (no external libraries) so demo photos are obviously placeholders."""
    rows = bytearray()
    for y in range(height):
        shade = 0.6 + 0.4 * y / height
        pixel = bytes(min(255, int(c * shade)) for c in rgb)
        rows += b"\x00" + pixel * width

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(rows)))
        + chunk(b"IEND", b"")
    )


def _demo_user(session: Session, email: str, full_name: str, role: RoleName) -> User:
    user = User(
        email=email,
        full_name=full_name,
        password_hash=hash_password(secrets.token_urlsafe(32)),  # unknown: cannot log in
        email_verified_at=datetime.now(UTC),
    )
    session.add(user)
    session.flush()
    assign_role(session, user, role)
    return user


def seed_demo_data(session: Session, settings: Settings, storage: DocumentStorage) -> int:
    """Create the demo marketplace. Returns the number of vehicles created (0 if present)."""
    if settings.app_env != Environment.DEVELOPMENT:
        raise DemoDataRefusedError("Demo data can only be created when APP_ENV=development.")
    if session.scalar(select(User).where(User.email == DEMO_ADMIN_EMAIL)):
        return 0

    admin = _demo_user(session, DEMO_ADMIN_EMAIL, "Demo Administrator", RoleName.ADMIN)
    today = today_in_south_africa()
    now = datetime.now(UTC)
    created: list[tuple[Vehicle, str]] = []
    for index, (
        first,
        make,
        model,
        year,
        gearbox,
        fuel,
        seats,
        city,
        province,
        rate,
        rgb,
    ) in enumerate(DEMO_VEHICLES):
        owner_user = _demo_user(
            session, f"demo-owner-{index + 1}@example.com", f"{first} Demo", RoleName.OWNER
        )
        owner = OwnerProfile(user_id=owner_user.id, city=city, province=province)
        session.add(owner)
        session.flush()
        vehicle = Vehicle(
            owner_id=owner.id,
            make=make,
            model=model,
            year=year,
            registration_number=f"DEMO{index + 1:03d}GP",
            vin=f"DEMXVN{index + 1:011d}",  # 17 chars; VINs never use the letters I, O or Q
            colour=None,
            transmission=gearbox,
            fuel_type=fuel,
            seats=seats,
            city=city,
            province=province,
            description=f"DEMO LISTING — development data only. {make} {model} in {city}.",
            status=VehicleStatus.APPROVED,
            submitted_at=now,
            approved_at=now,
            approved_by_id=admin.id,
        )
        session.add(vehicle)
        session.flush()
        for order in range(3):
            shade = tuple(min(255, c + 30 * order) for c in rgb)
            data = placeholder_png(shade)
            session.add(
                VehicleImage(
                    vehicle_id=vehicle.id,
                    storage_key=storage.save(data),
                    content_type="image/png",
                    size_bytes=len(data),
                    sha256="0" * 64,
                    sort_order=order,
                )
            )
        for doc_type, expiry in (
            (VehicleDocumentType.REGISTRATION_CERTIFICATE, None),
            (VehicleDocumentType.LICENCE_DISC, today + timedelta(days=300)),
            (VehicleDocumentType.INSURANCE, today + timedelta(days=330)),
        ):
            data = b"%PDF-1.4\n% DEMO DOCUMENT - not a real document\n"
            session.add(
                VehicleDocument(
                    vehicle_id=vehicle.id,
                    document_type=doc_type,
                    expiry_date=expiry,
                    storage_key=storage.save(data),
                    content_type="application/pdf",
                    size_bytes=len(data),
                    sha256="0" * 64,
                    uploaded_by_id=owner_user.id,
                    created_at=now,
                )
            )
        created.append((vehicle, rate))
    record_audit(
        session,
        actor_id=admin.id,
        action="demo.seeded",
        entity_type="system",
        entity_id="demo-data",
        changes={"vehicles": len(created)},
    )
    session.commit()
    for vehicle, rate in created:
        set_official_price(
            session,
            admin=admin,
            vehicle_id=vehicle.id,
            daily_rate=Decimal(rate),
            delivery_fee=Decimal("150.00"),
            deposit_amount=Decimal("2000.00"),
            change_reason="Demo data",
        )
    return len(created)
