import itertools
import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.services.verification import today_in_south_africa
from tests.verification.helpers import JPEG, PDF, PNG

WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 200
BASE = "/api/v1/owners/me/vehicles"
_n = itertools.count(1)
VIN_CHARS = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"


def unique_vin() -> str:
    n = uuid.uuid4().int
    return "".join(VIN_CHARS[(n >> (5 * i)) % len(VIN_CHARS)] for i in range(17))


def vehicle_body(**overrides) -> dict:
    values = {
        "make": "Toyota",
        "model": "Corolla Cross",
        "year": 2023,
        "registration_number": f"ca {next(_n):03d}-456",
        "vin": unique_vin().lower(),
        "colour": "White",
        "transmission": "AUTOMATIC",
        "fuel_type": "PETROL",
        "seats": 5,
        "city": "Cape Town",
        "province": "Western Cape",
        "description": "Clean and reliable.",
    }
    values.update(overrides)
    return values


def in_days(days: int) -> date:
    return today_in_south_africa() + timedelta(days=days)


def create_vehicle(api: TestClient, headers: dict, **overrides) -> dict:
    response = api.post(BASE, headers=headers, json=vehicle_body(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def upload_photo(api: TestClient, headers: dict, vehicle_id: str, data: bytes = JPEG):
    return api.post(
        f"{BASE}/{vehicle_id}/photos",
        headers=headers,
        files={"photo": ("car.jpg", data, "image/jpeg")},
    )


def upload_document(
    api: TestClient,
    headers: dict,
    vehicle_id: str,
    document_type: str,
    expiry: date | None = None,
    data: bytes = PDF,
):
    form = {"document_type": document_type}
    if expiry is not None:
        form["expiry_date"] = expiry.isoformat()
    return api.post(
        f"{BASE}/{vehicle_id}/documents",
        headers=headers,
        data=form,
        files={"file": ("doc.pdf", data, "application/pdf")},
    )


def make_ready(api: TestClient, headers: dict, vehicle_id: str, photos: int = 3) -> None:
    for data in [JPEG, PNG, WEBP, JPEG][:photos]:
        assert upload_photo(api, headers, vehicle_id, data).status_code == 201
    assert upload_document(api, headers, vehicle_id, "REGISTRATION_CERTIFICATE").status_code == 201
    assert (
        upload_document(api, headers, vehicle_id, "LICENCE_DISC", in_days(200)).status_code == 201
    )
    assert upload_document(api, headers, vehicle_id, "INSURANCE", in_days(300)).status_code == 201


def verify_owner_email(api: TestClient, outbox, email: str = "owner@example.com") -> None:
    message = [m for m in outbox.outbox if m.to == email][-1]
    token = message.body.split("token=")[1].split()[0]
    assert api.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200


def submitted_vehicle(api: TestClient, owner_headers: dict, outbox) -> dict:
    verify_owner_email(api, outbox)
    vehicle = create_vehicle(api, owner_headers)
    make_ready(api, owner_headers, vehicle["id"])
    response = api.post(f"{BASE}/{vehicle['id']}/submit", headers=owner_headers)
    assert response.status_code == 200, response.text
    return response.json()
