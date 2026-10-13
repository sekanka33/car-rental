from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.integrations.storage import InMemoryDocumentStorage
from app.models import AuditLog, Vehicle, VehicleDocument
from tests.api_fixtures import Account, login, register
from tests.conftest import requires_db
from tests.db.factories import create_booking, create_price
from tests.vehicles.helpers import (
    BASE,
    WEBP,
    create_vehicle,
    in_days,
    make_ready,
    submitted_vehicle,
    unique_vin,
    upload_document,
    upload_photo,
    vehicle_body,
    verify_owner_email,
)
from tests.verification.helpers import JPEG, PDF, PNG

pytestmark = requires_db


def second_owner(api: TestClient) -> Account:
    register(api, "owner2@example.com", "OWNER")
    return login(api, "owner2@example.com")


# --- owner profile --------------------------------------------------------------------


def test_owner_profile_update(api: TestClient, owner: Account, renter: Account) -> None:
    url = "/api/v1/owners/me/profile"
    response = api.patch(
        url,
        headers=owner.headers,
        json={"business_name": "Sipho's Cars", "city": "Durban", "province": "KwaZulu-Natal"},
    )

    assert response.status_code == 200
    assert response.json()["province"] == "KwaZulu-Natal"
    assert api.patch(url, headers=owner.headers, json={"province": "Atlantis"}).status_code == 422
    assert api.patch(url, headers=renter.headers, json={"city": "Durban"}).status_code == 403


# --- registration ---------------------------------------------------------------------


def test_register_vehicle_as_draft(api: TestClient, owner: Account) -> None:
    vin = unique_vin()

    vehicle = create_vehicle(api, owner.headers, registration_number="ca 123-456", vin=vin.lower())

    assert vehicle["status"] == "DRAFT"
    assert vehicle["registration_number"] == "CA123456"
    assert vehicle["vin"] == vin
    assert vehicle["photos"] == [] and vehicle["documents"] == []
    assert vehicle["compliance"] == {
        "ok": False,
        "missing": ["REGISTRATION_CERTIFICATE", "LICENCE_DISC", "INSURANCE"],
        "expired": [],
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"daily_rate": "1.00"},
        {"status": "APPROVED"},
        {"owner_id": "00000000-0000-0000-0000-000000000000"},
        {"approved_at": "2026-01-01T00:00:00Z"},
    ],
    ids=["price", "status", "owner_id", "approved_at"],
)
def test_owner_cannot_set_price_status_or_ownership(
    api: TestClient, owner: Account, overrides: dict
) -> None:
    assert api.post(BASE, headers=owner.headers, json=vehicle_body(**overrides)).status_code == 422


@pytest.mark.parametrize(
    "overrides",
    [
        {"vin": "IOQ12345678901234"},
        {"vin": "SHORT"},
        {"year": 1975},
        {"year": datetime.now(UTC).year + 3},
        {"seats": 1},
        {"province": "Atlantis"},
        {"registration_number": "!!"},
        {"transmission": "CVT"},
    ],
    ids=[
        "vin-letters",
        "vin-length",
        "too-old",
        "future-year",
        "one-seat",
        "province",
        "registration",
        "transmission",
    ],
)
def test_invalid_vehicle_details_rejected(api: TestClient, owner: Account, overrides: dict) -> None:
    assert api.post(BASE, headers=owner.headers, json=vehicle_body(**overrides)).status_code == 422


def test_registration_and_vin_are_unique_across_owners(api: TestClient, owner: Account) -> None:
    first = create_vehicle(api, owner.headers, registration_number="GP 777 ZA")
    other = second_owner(api)

    same_reg = api.post(
        BASE, headers=other.headers, json=vehicle_body(registration_number="gp777za")
    )
    same_vin = api.post(BASE, headers=other.headers, json=vehicle_body(vin=first["vin"]))

    assert same_reg.status_code == same_vin.status_code == 409
    assert same_reg.json()["error"]["code"] == "vehicle_already_registered"


def test_only_owners_can_register_vehicles(api: TestClient, renter: Account) -> None:
    assert api.post(BASE, headers=renter.headers, json=vehicle_body()).status_code == 403
    assert api.post(BASE, json=vehicle_body()).status_code == 401


def test_owners_only_see_their_own_vehicles(api: TestClient, owner: Account) -> None:
    mine = create_vehicle(api, owner.headers)
    other = second_owner(api)
    url = f"{BASE}/{mine['id']}"

    assert api.get(BASE, headers=other.headers).json() == []
    assert api.get(url, headers=other.headers).status_code == 404
    assert api.patch(url, headers=other.headers, json={"colour": "Red"}).status_code == 404
    assert api.delete(url, headers=other.headers).status_code == 404
    assert upload_photo(api, other.headers, mine["id"]).status_code == 404
    assert [v["id"] for v in api.get(BASE, headers=owner.headers).json()] == [mine["id"]]


# --- photos and documents ------------------------------------------------------------------


def test_photos(api: TestClient, owner: Account, storage: InMemoryDocumentStorage) -> None:
    vehicle = create_vehicle(api, owner.headers)

    ids = [
        upload_photo(api, owner.headers, vehicle["id"], data).json()["id"]
        for data in (JPEG, PNG, WEBP)
    ]

    photos = api.get(f"{BASE}/{vehicle['id']}", headers=owner.headers).json()["photos"]
    assert [p["content_type"] for p in photos] == ["image/jpeg", "image/png", "image/webp"]
    assert [p["sort_order"] for p in photos] == [0, 1, 2]
    view = api.get(f"{BASE}/{vehicle['id']}/photos/{ids[1]}", headers=owner.headers)
    assert view.content == PNG and view.headers["cache-control"] == "no-store"
    assert (
        api.delete(f"{BASE}/{vehicle['id']}/photos/{ids[0]}", headers=owner.headers).status_code
        == 204
    )
    assert len(storage.files) == 2


@pytest.mark.parametrize("data", [PDF, b"MZ\x90\x00 exe", b""], ids=["pdf", "exe", "empty"])
def test_photo_type_checked_by_content(api: TestClient, owner: Account, data: bytes) -> None:
    vehicle = create_vehicle(api, owner.headers)

    assert upload_photo(api, owner.headers, vehicle["id"], data).status_code == 422


def test_photo_limit(api: TestClient, owner: Account) -> None:
    vehicle = create_vehicle(api, owner.headers)
    for _ in range(12):
        assert upload_photo(api, owner.headers, vehicle["id"]).status_code == 201

    assert upload_photo(api, owner.headers, vehicle["id"]).status_code == 409


def test_documents_need_expiry_where_relevant_and_renewals_supersede(
    api: TestClient, owner: Account
) -> None:
    vehicle = create_vehicle(api, owner.headers)
    vid = vehicle["id"]

    assert upload_document(api, owner.headers, vid, "LICENCE_DISC").status_code == 422
    assert upload_document(api, owner.headers, vid, "INSURANCE", in_days(0)).status_code == 422
    assert upload_document(api, owner.headers, vid, "ROADWORTHY_CERTIFICATE").status_code == 201
    old = upload_document(api, owner.headers, vid, "LICENCE_DISC", in_days(30)).json()
    new = upload_document(api, owner.headers, vid, "LICENCE_DISC", in_days(395)).json()

    docs = {
        d["id"]: d["is_current"]
        for d in api.get(f"{BASE}/{vid}", headers=owner.headers).json()["documents"]
    }
    assert docs[old["id"]] is False and docs[new["id"]] is True
    assert (
        upload_document(
            api, owner.headers, vid, "INSURANCE", in_days(30), data=b"<html>"
        ).status_code
        == 422
    )


# --- submission workflow -----------------------------------------------------------------------


def test_submit_requires_photos_documents_and_verified_email(
    api: TestClient, owner: Account, outbox
) -> None:
    vehicle = create_vehicle(api, owner.headers)

    response = api.post(f"{BASE}/{vehicle['id']}/submit", headers=owner.headers)

    assert response.status_code == 409
    message = response.json()["error"]["message"]
    for needed in (
        "verified email",
        "at least 3 photos",
        "REGISTRATION_CERTIFICATE",
        "LICENCE_DISC",
        "INSURANCE",
    ):
        assert needed in message


def test_submit_for_review(api: TestClient, owner: Account, outbox, db_session: Session) -> None:
    vehicle = submitted_vehicle(api, owner.headers, outbox)

    assert vehicle["status"] == "PENDING_APPROVAL"
    assert vehicle["submitted_at"] is not None
    assert vehicle["compliance"]["ok"] is True
    actions = db_session.scalars(
        select(AuditLog.action).where(AuditLog.entity_id == vehicle["id"])
    ).all()
    assert actions == ["vehicle.submitted"]


def test_expired_document_blocks_submission(
    api: TestClient, owner: Account, outbox, db_session: Session
) -> None:
    verify_owner_email(api, outbox)
    vehicle = create_vehicle(api, owner.headers)
    make_ready(api, owner.headers, vehicle["id"])
    db_session.execute(
        update(VehicleDocument)
        .where(VehicleDocument.document_type == "INSURANCE")
        .values(expiry_date=in_days(-1))
    )

    response = api.post(f"{BASE}/{vehicle['id']}/submit", headers=owner.headers)
    assert response.status_code == 409
    assert "valid (unexpired) INSURANCE" in response.json()["error"]["message"]


def test_no_edits_while_under_review_but_withdraw_allowed(
    api: TestClient, owner: Account, outbox
) -> None:
    vehicle = submitted_vehicle(api, owner.headers, outbox)
    url = f"{BASE}/{vehicle['id']}"

    assert api.patch(url, headers=owner.headers, json={"colour": "Blue"}).status_code == 409
    assert api.post(f"{url}/submit", headers=owner.headers).status_code == 409
    withdrawn = api.post(f"{url}/withdraw", headers=owner.headers).json()
    assert withdrawn["status"] == "DRAFT"
    assert api.patch(url, headers=owner.headers, json={"colour": "Blue"}).json()["colour"] == "Blue"


def test_delete_draft_removes_files(
    api: TestClient, owner: Account, storage: InMemoryDocumentStorage
) -> None:
    vehicle = create_vehicle(api, owner.headers)
    make_ready(api, owner.headers, vehicle["id"])
    assert len(storage.files) == 6

    assert api.delete(f"{BASE}/{vehicle['id']}", headers=owner.headers).status_code == 204

    assert storage.files == {}
    assert api.get(f"{BASE}/{vehicle['id']}", headers=owner.headers).status_code == 404


# --- availability blocks --------------------------------------------------------------------------


def test_availability_blocks(api: TestClient, owner: Account, db_session: Session) -> None:
    vehicle = create_vehicle(api, owner.headers)
    url = f"{BASE}/{vehicle['id']}/availability-blocks"
    start = datetime.now(UTC) + timedelta(days=10)

    block = api.post(
        url,
        headers=owner.headers,
        json={
            "start_at": start.isoformat(),
            "end_at": (start + timedelta(days=2)).isoformat(),
            "reason": "Service",
        },
    )
    assert block.status_code == 201
    assert [b["id"] for b in api.get(url, headers=owner.headers).json()] == [block.json()["id"]]

    bad = [
        {"start_at": start.isoformat(), "end_at": start.isoformat()},
        {
            "start_at": (start - timedelta(days=30)).isoformat(),
            "end_at": (start - timedelta(days=20)).isoformat(),
        },
    ]
    for body in bad:
        assert api.post(url, headers=owner.headers, json=body).status_code == 409
    naive = {
        "start_at": start.replace(tzinfo=None).isoformat(),
        "end_at": (start + timedelta(days=1)).isoformat(),
    }
    assert api.post(url, headers=owner.headers, json=naive).status_code == 422

    assert api.delete(f"{url}/{block.json()['id']}", headers=owner.headers).status_code == 204
    assert api.get(url, headers=owner.headers).json() == []


def test_block_cannot_cover_an_existing_booking(
    api: TestClient, owner: Account, db_session: Session
) -> None:
    vehicle = create_vehicle(api, owner.headers)
    model = db_session.get(Vehicle, vehicle["id"])
    start = datetime.now(UTC) + timedelta(days=20)
    create_booking(db_session, create_price(db_session, model), start=start, days=3)

    response = api.post(
        f"{BASE}/{vehicle['id']}/availability-blocks",
        headers=owner.headers,
        json={
            "start_at": (start + timedelta(days=1)).isoformat(),
            "end_at": (start + timedelta(days=5)).isoformat(),
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "availability_conflict"
