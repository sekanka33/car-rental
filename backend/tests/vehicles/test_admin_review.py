from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AuditLog, OwnerProfile, User, Vehicle, VehicleDocument
from app.models.enums import RoleName, UserStatus
from app.repositories.users import assign_role
from app.services.vehicles import publicly_listed_vehicles
from tests.api_fixtures import Account
from tests.conftest import requires_db
from tests.vehicles.helpers import (
    BASE,
    create_vehicle,
    in_days,
    make_ready,
    submitted_vehicle,
    upload_document,
)

pytestmark = requires_db
ADMIN = "/api/v1/admin/vehicles"


def approve(api: TestClient, admin: Account, vehicle_id: str):
    return api.post(f"{ADMIN}/{vehicle_id}/approve", headers=admin.headers)


def listed_ids(session: Session) -> set[str]:
    session.expire_all()
    return {str(v.id) for v in session.scalars(publicly_listed_vehicles())}


def test_review_queue_is_admin_only(
    api: TestClient, owner: Account, renter: Account, admin: Account, outbox
) -> None:
    vehicle = submitted_vehicle(api, owner.headers, outbox)

    for account in (owner, renter):
        assert api.get(ADMIN, headers=account.headers).status_code == 403
        assert approve(api, account, vehicle["id"]).status_code == 403

    queue = api.get(ADMIN, headers=admin.headers).json()
    assert [v["id"] for v in queue] == [vehicle["id"]]
    assert queue[0]["owner"]["email"] == "owner@example.com"
    assert queue[0]["compliance"]["ok"] is True


def test_approve(
    api: TestClient, owner: Account, admin: Account, outbox, db_session: Session
) -> None:
    vehicle = submitted_vehicle(api, owner.headers, outbox)

    response = approve(api, admin, vehicle["id"])

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "APPROVED" and body["approved_by_id"] is not None
    assert approve(api, admin, vehicle["id"]).status_code == 409
    actions = db_session.scalars(
        select(AuditLog.action).where(AuditLog.entity_id == vehicle["id"]).order_by(AuditLog.id)
    ).all()
    assert actions == ["vehicle.submitted", "vehicle.approved"]


def test_reject_then_fix_and_resubmit(
    api: TestClient, owner: Account, admin: Account, outbox
) -> None:
    vehicle = submitted_vehicle(api, owner.headers, outbox)
    url = f"{ADMIN}/{vehicle['id']}/reject"

    assert api.post(url, headers=admin.headers, json={}).status_code == 422
    rejected = api.post(url, headers=admin.headers, json={"reason": "Photos too dark"})
    assert rejected.json()["status"] == "REJECTED"

    mine = api.get(f"{BASE}/{vehicle['id']}", headers=owner.headers).json()
    assert mine["rejection_reason"] == "Photos too dark"
    resubmitted = api.post(f"{BASE}/{vehicle['id']}/submit", headers=owner.headers).json()
    assert resubmitted["status"] == "PENDING_APPROVAL" and resubmitted["rejection_reason"] is None


def test_admin_cannot_approve_own_vehicle(
    api: TestClient, admin: Account, db_session: Session, outbox
) -> None:
    admin_user = db_session.scalar(select(User).where(User.email == admin.email))
    assign_role(db_session, admin_user, RoleName.OWNER)
    db_session.add(OwnerProfile(user_id=admin_user.id))
    db_session.flush()
    # Administrators created by the CLI already have a verified email.
    vehicle = create_vehicle(api, admin.headers)
    make_ready(api, admin.headers, vehicle["id"])
    assert api.post(f"{BASE}/{vehicle['id']}/submit", headers=admin.headers).status_code == 200

    assert approve(api, admin, vehicle["id"]).status_code == 403


def test_cannot_approve_with_expired_documents_or_inactive_owner(
    api: TestClient, owner: Account, admin: Account, outbox, db_session: Session
) -> None:
    vehicle = submitted_vehicle(api, owner.headers, outbox)
    db_session.execute(
        update(VehicleDocument)
        .where(VehicleDocument.document_type == "LICENCE_DISC")
        .values(expiry_date=in_days(-1))
    )
    assert approve(api, admin, vehicle["id"]).status_code == 409

    db_session.execute(
        update(VehicleDocument)
        .where(VehicleDocument.document_type == "LICENCE_DISC")
        .values(expiry_date=in_days(100))
    )
    owner_user = db_session.scalar(select(User).where(User.email == owner.email))
    owner_user.status = UserStatus.DEACTIVATED
    db_session.flush()
    assert approve(api, admin, vehicle["id"]).status_code == 409


def test_document_views(
    api: TestClient, owner: Account, admin: Account, outbox, db_session: Session
) -> None:
    vehicle = submitted_vehicle(api, owner.headers, outbox)
    document = vehicle["documents"][0]
    photo = vehicle["photos"][0]

    assert (
        api.get(
            f"{ADMIN}/{vehicle['id']}/documents/{document['id']}", headers=admin.headers
        ).status_code
        == 200
    )
    assert (
        api.get(f"{ADMIN}/{vehicle['id']}/photos/{photo['id']}", headers=admin.headers).status_code
        == 200
    )
    assert (
        api.get(
            f"{ADMIN}/{vehicle['id']}/documents/{document['id']}", headers=owner.headers
        ).status_code
        == 403
    )
    actions = db_session.scalars(
        select(AuditLog.action).where(AuditLog.entity_id == vehicle["id"])
    ).all()
    assert actions.count("vehicle.document_viewed") == 1  # photo views are not audited


def test_material_change_sends_approved_vehicle_back_to_review(
    api: TestClient, owner: Account, admin: Account, outbox
) -> None:
    vehicle = submitted_vehicle(api, owner.headers, outbox)
    approve(api, admin, vehicle["id"])
    url = f"{BASE}/{vehicle['id']}"

    cosmetic = api.patch(
        url, headers=owner.headers, json={"description": "Now with roof racks", "colour": "Silver"}
    )
    assert cosmetic.json()["status"] == "APPROVED"

    material = api.patch(url, headers=owner.headers, json={"seats": 7})
    assert material.json()["status"] == "PENDING_APPROVAL"
    assert material.json()["approved_at"] is None


def test_new_registration_certificate_requires_review_but_renewals_do_not(
    api: TestClient, owner: Account, admin: Account, outbox
) -> None:
    vehicle = submitted_vehicle(api, owner.headers, outbox)
    approve(api, admin, vehicle["id"])
    url = f"{BASE}/{vehicle['id']}"

    upload_document(api, owner.headers, vehicle["id"], "LICENCE_DISC", in_days(500))
    assert api.get(url, headers=owner.headers).json()["status"] == "APPROVED"

    upload_document(api, owner.headers, vehicle["id"], "REGISTRATION_CERTIFICATE")
    assert api.get(url, headers=owner.headers).json()["status"] == "PENDING_APPROVAL"


def test_listing_toggle(api: TestClient, owner: Account, admin: Account, outbox) -> None:
    vehicle = submitted_vehicle(api, owner.headers, outbox)
    url = f"{BASE}/{vehicle['id']}/listing"

    assert (
        api.put(url, headers=owner.headers, json={"available": False}).status_code == 409
    )  # not approved yet
    approve(api, admin, vehicle["id"])
    assert (
        api.put(url, headers=owner.headers, json={"available": False}).json()["status"]
        == "UNAVAILABLE"
    )
    assert (
        api.put(url, headers=owner.headers, json={"available": True}).json()["status"] == "APPROVED"
    )
    assert api.delete(f"{BASE}/{vehicle['id']}", headers=owner.headers).status_code == 409


def test_only_approved_compliant_vehicles_of_active_owners_are_publicly_listed(
    api: TestClient, owner: Account, admin: Account, outbox, db_session: Session
) -> None:
    draft = create_vehicle(api, owner.headers)
    vehicle = submitted_vehicle(api, owner.headers, outbox)
    assert listed_ids(db_session) == set()  # draft and pending are hidden

    approve(api, admin, vehicle["id"])
    assert listed_ids(db_session) == set()  # approved but not priced yet
    priced = api.post(
        f"{ADMIN}/{vehicle['id']}/prices",
        headers=admin.headers,
        json={"daily_rate": "650.00", "change_reason": "Launch price"},
    )
    assert priced.status_code == 201
    assert listed_ids(db_session) == {vehicle["id"]}
    assert draft["id"] not in listed_ids(db_session)

    api.put(f"{BASE}/{vehicle['id']}/listing", headers=owner.headers, json={"available": False})
    assert listed_ids(db_session) == set()
    api.put(f"{BASE}/{vehicle['id']}/listing", headers=owner.headers, json={"available": True})

    # The newest insurance document counts: an expired renewal hides the vehicle...
    newest = VehicleDocument(
        **{
            c: getattr(
                db_session.scalar(
                    select(VehicleDocument).where(VehicleDocument.document_type == "INSURANCE")
                ),
                c,
            )
            for c in (
                "vehicle_id",
                "document_type",
                "content_type",
                "size_bytes",
                "sha256",
                "uploaded_by_id",
            )
        },
        storage_key="0" * 32,
        expiry_date=in_days(-1),
        created_at=datetime.now(UTC) + timedelta(seconds=1),
    )
    db_session.add(newest)
    db_session.flush()
    assert listed_ids(db_session) == set()
    newest.expiry_date = in_days(10)
    db_session.flush()
    assert listed_ids(db_session) == {vehicle["id"]}

    # ...and a suspended owner hides it too.
    owner_user = db_session.scalar(select(User).where(User.email == owner.email))
    owner_user.status = UserStatus.SUSPENDED
    owner_user.suspended_at = datetime.now(UTC)
    db_session.flush()
    assert listed_ids(db_session) == set()
    assert db_session.get(Vehicle, vehicle["id"]).status == "APPROVED"
