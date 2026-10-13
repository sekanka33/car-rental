import logging
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.integrations.storage import InMemoryDocumentStorage
from app.main import create_app
from app.models import AuditLog, CustomerProfile, User
from app.models.enums import RoleName
from app.repositories.users import assign_role
from tests.api_fixtures import Account, login, register
from tests.conftest import make_settings, requires_db
from tests.verification.helpers import (
    DOB,
    JPEG,
    PDF,
    decide,
    future_date,
    make_sa_id,
    set_dob,
    submit_id,
    submit_licence,
)

pytestmark = requires_db
DOCS = "/api/v1/customers/me/documents"


def profile(session: Session, email: str) -> CustomerProfile:
    user_id = session.scalar(select(User.id).where(User.email == email))
    session.expire_all()
    return session.scalar(select(CustomerProfile).where(CustomerProfile.user_id == user_id))


# --- date of birth -------------------------------------------------------------------


def test_date_of_birth_rules(api: TestClient, renter: Account) -> None:
    from app.services.verification import today_in_south_africa

    today = today_in_south_africa()
    turns_18_today = today.replace(year=today.year - 18)
    turns_18_tomorrow = turns_18_today + timedelta(days=1)

    assert set_dob(api, renter.headers, turns_18_tomorrow).status_code == 422
    assert set_dob(api, renter.headers, today + timedelta(days=1)).status_code == 422
    response = set_dob(api, renter.headers, turns_18_today)
    assert response.status_code == 200
    assert response.json()["date_of_birth"] == turns_18_today.isoformat()
    assert response.json()["minimum_age"] == 18


def test_profile_endpoints_are_for_renters_only(api: TestClient, owner: Account) -> None:
    assert api.get("/api/v1/customers/me/profile", headers=owner.headers).status_code == 403
    assert set_dob(api, owner.headers).status_code == 403


def test_date_of_birth_locked_once_id_is_submitted(api: TestClient, renter: Account) -> None:
    set_dob(api, renter.headers)
    assert submit_id(api, renter.headers).status_code == 201

    response = set_dob(api, renter.headers, date(1990, 1, 1))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "profile_locked"


# --- submission ----------------------------------------------------------------------


def test_id_submission_is_stored_privately_and_pending(
    api: TestClient,
    renter: Account,
    db_session: Session,
    storage: InMemoryDocumentStorage,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    set_dob(api, renter.headers)
    id_number = make_sa_id(DOB)

    response = submit_id(api, renter.headers, id_number)

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "PENDING"
    assert data["document_number_masked"].endswith(id_number[-3:])
    assert id_number not in response.text
    assert [f["side"] for f in data["files"]] == ["FRONT"]
    assert data["files"][0]["content_type"] == "image/jpeg"
    assert profile(db_session, renter.email).id_verification_status == "PENDING"
    assert list(storage.files.values()) == [JPEG]
    # The full ID number is stored nowhere: not in any table, not in the logs.
    dump = (
        db_session.execute(text("SELECT row_to_json(s)::text FROM verification_submissions s"))
        .scalars()
        .all()
    )
    assert dump and all(id_number not in row for row in dump)
    assert id_number not in caplog.text


def test_id_requires_date_of_birth_first(api: TestClient, renter: Account) -> None:
    response = submit_id(api, renter.headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "profile_incomplete"


@pytest.mark.parametrize(
    ("id_number", "reason"),
    [
        (make_sa_id(date(1990, 1, 1)), "does not match your date of birth"),
        (make_sa_id(DOB)[:-1] + str((int(make_sa_id(DOB)[-1]) + 1) % 10), "check digit"),
    ],
    ids=["dob-mismatch", "bad-check-digit"],
)
def test_invalid_id_numbers_rejected(
    api: TestClient, renter: Account, storage: InMemoryDocumentStorage, id_number: str, reason: str
) -> None:
    set_dob(api, renter.headers)

    response = submit_id(api, renter.headers, id_number)

    assert response.status_code == 422
    assert reason in response.json()["error"]["message"]
    assert storage.files == {}
    assert id_number not in response.text


@pytest.mark.parametrize(
    "content",
    [b"MZ\x90\x00 fake executable", b"<html>not an image</html>", b""],
    ids=["exe-disguised-as-jpeg", "html", "empty"],
)
def test_file_type_is_checked_by_content_not_by_name(
    api: TestClient, renter: Account, storage: InMemoryDocumentStorage, content: bytes
) -> None:
    set_dob(api, renter.headers)

    response = submit_id(api, renter.headers, front=content)

    assert response.status_code == 422
    assert storage.files == {}


def test_oversized_file_rejected(db_session: Session, outbox) -> None:
    storage = InMemoryDocumentStorage()
    app = create_app(
        make_settings(max_document_bytes=100 * 1024), email_sender=outbox, document_storage=storage
    )
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app, raise_server_exceptions=False) as api:
        register(api, "big@example.com")
        account = login(api, "big@example.com")
        set_dob(api, account.headers)

        response = submit_id(api, account.headers, front=JPEG[:4] + b"\x00" * (100 * 1024))

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "document_too_large"
    assert storage.files == {}


def test_front_side_is_required(api: TestClient, renter: Account) -> None:
    set_dob(api, renter.headers)

    response = api.post(
        DOCS,
        headers=renter.headers,
        data={"document_type": "SA_ID", "document_number": make_sa_id(DOB)},
    )
    assert response.status_code == 422


def test_resubmission_supersedes_pending(
    api: TestClient, renter: Account, db_session: Session
) -> None:
    set_dob(api, renter.headers)
    first = submit_id(api, renter.headers).json()

    second = submit_id(api, renter.headers).json()

    statuses = {s["id"]: s["status"] for s in api.get(DOCS, headers=renter.headers).json()}
    assert statuses == {first["id"]: "SUPERSEDED", second["id"]: "PENDING"}


def test_licence_submission(api: TestClient, renter: Account, db_session: Session) -> None:
    response = submit_licence(api, renter.headers, back=PDF)

    assert response.status_code == 201
    assert sorted(f["side"] for f in response.json()["files"]) == ["BACK", "FRONT"]
    assert response.json()["licence_codes"] == "B"
    assert profile(db_session, renter.email).licence_verification_status == "PENDING"


def test_expired_licence_rejected(api: TestClient, renter: Account) -> None:
    from app.services.verification import today_in_south_africa

    response = submit_licence(api, renter.headers, expiry=today_in_south_africa())
    assert response.status_code == 422


# --- review --------------------------------------------------------------------------


def test_review_queue_is_admin_only(
    api: TestClient, renter: Account, owner: Account, admin: Account
) -> None:
    set_dob(api, renter.headers)
    submission = submit_id(api, renter.headers).json()

    for account in (renter, owner):
        assert api.get("/api/v1/admin/verifications", headers=account.headers).status_code == 403
        assert decide(api, account.headers, submission["id"], "APPROVED").status_code == 403

    queue = api.get("/api/v1/admin/verifications", headers=admin.headers).json()
    assert [item["id"] for item in queue] == [submission["id"]]
    assert queue[0]["submitter"]["email"] == renter.email
    assert queue[0]["submitter"]["date_of_birth"] == DOB.isoformat()


def test_customer_cannot_change_their_own_verification_status(
    api: TestClient, renter: Account
) -> None:
    set_dob(api, renter.headers)
    submission = submit_id(api, renter.headers).json()

    assert decide(api, renter.headers, submission["id"], "APPROVED").status_code == 403
    tampered = api.put(
        "/api/v1/customers/me/profile/date-of-birth",
        headers=renter.headers,
        json={"date_of_birth": DOB.isoformat(), "id_verification_status": "APPROVED"},
    )
    assert tampered.status_code == 422


def test_approve_id(api: TestClient, renter: Account, admin: Account, db_session: Session) -> None:
    set_dob(api, renter.headers)
    submission = submit_id(api, renter.headers).json()

    response = decide(api, admin.headers, submission["id"], "APPROVED")

    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"
    assert profile(db_session, renter.email).id_verification_status == "APPROVED"
    audit = db_session.scalar(select(AuditLog).where(AuditLog.entity_id == submission["id"]))
    assert audit.action == "verification.approved"
    assert decide(api, admin.headers, submission["id"], "REJECTED", note="again").status_code == 409


def test_reject_requires_note_and_shows_it_to_customer(
    api: TestClient, renter: Account, admin: Account, db_session: Session
) -> None:
    set_dob(api, renter.headers)
    submission = submit_id(api, renter.headers).json()

    assert decide(api, admin.headers, submission["id"], "REJECTED").status_code == 422
    response = decide(api, admin.headers, submission["id"], "REJECTED", note="Photo is blurred")

    assert response.status_code == 200
    mine = api.get(DOCS, headers=renter.headers).json()[0]
    assert (mine["status"], mine["review_note"]) == ("REJECTED", "Photo is blurred")
    assert profile(db_session, renter.email).id_verification_status == "REJECTED"


def test_more_information_then_resubmit(
    api: TestClient, renter: Account, admin: Account, db_session: Session
) -> None:
    set_dob(api, renter.headers)
    first = submit_id(api, renter.headers).json()
    decide(api, admin.headers, first["id"], "REQUIRES_MORE_INFORMATION", note="Upload the back too")
    assert profile(db_session, renter.email).id_verification_status == "REQUIRES_MORE_INFORMATION"

    assert submit_id(api, renter.headers).status_code == 201
    assert profile(db_session, renter.email).id_verification_status == "PENDING"


def test_licence_approval_records_confirmed_expiry(
    api: TestClient, renter: Account, admin: Account, db_session: Session
) -> None:
    submission = submit_licence(api, renter.headers, expiry=future_date(400)).json()
    corrected = future_date(500)

    decide(
        api, admin.headers, submission["id"], "APPROVED", licence_expiry_date=corrected.isoformat()
    )

    customer = profile(db_session, renter.email)
    assert customer.licence_verification_status == "APPROVED"
    assert customer.licence_expiry_date == corrected


def test_cannot_approve_licence_that_expired_while_waiting(
    api: TestClient, renter: Account, admin: Account
) -> None:
    from app.services.verification import today_in_south_africa

    submission = submit_licence(api, renter.headers).json()

    response = decide(
        api,
        admin.headers,
        submission["id"],
        "APPROVED",
        licence_expiry_date=today_in_south_africa().isoformat(),
    )
    assert response.status_code == 409


def test_admin_cannot_review_own_documents(
    api: TestClient, admin: Account, db_session: Session
) -> None:
    admin_user = db_session.scalar(select(User).where(User.email == admin.email))
    assign_role(db_session, admin_user, RoleName.RENTER)
    db_session.add(CustomerProfile(user_id=admin_user.id, date_of_birth=DOB))
    db_session.flush()
    submission = submit_id(api, admin.headers).json()

    response = decide(api, admin.headers, submission["id"], "APPROVED")
    assert response.status_code == 403


def _second_renter(api: TestClient, email: str) -> Account:
    register(api, email)
    account = login(api, email)
    set_dob(api, account.headers)
    return account


def test_same_id_cannot_be_verified_on_two_accounts(
    api: TestClient, renter: Account, admin: Account
) -> None:
    set_dob(api, renter.headers)
    decide(api, admin.headers, submit_id(api, renter.headers).json()["id"], "APPROVED")
    other = _second_renter(api, "copycat@example.com")

    response = submit_id(api, other.headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "identity_already_verified"


def test_duplicate_id_blocked_at_approval_time_too(
    api: TestClient, renter: Account, admin: Account
) -> None:
    """Both submitted before either was approved: the database index stops the second."""
    set_dob(api, renter.headers)
    first = submit_id(api, renter.headers).json()
    other = _second_renter(api, "early-copycat@example.com")
    second = submit_id(api, other.headers).json()

    assert decide(api, admin.headers, first["id"], "APPROVED").status_code == 200
    response = decide(api, admin.headers, second["id"], "APPROVED")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "identity_already_verified"
    queue = api.get("/api/v1/admin/verifications", headers=admin.headers).json()
    assert [item["id"] for item in queue] == [second["id"]]  # still pending, not half-approved


# --- private file access -------------------------------------------------------------


def test_document_file_access(
    api: TestClient, renter: Account, owner: Account, admin: Account, db_session: Session
) -> None:
    set_dob(api, renter.headers)
    submission = submit_id(api, renter.headers).json()
    file_id = submission["files"][0]["id"]
    own_url = f"{DOCS}/{submission['id']}/files/{file_id}"
    admin_url = f"/api/v1/admin/verifications/{submission['id']}/files/{file_id}"
    stranger = _second_renter(api, "stranger@example.com")

    mine = api.get(own_url, headers=renter.headers)
    assert mine.status_code == 200 and mine.content == JPEG
    assert mine.headers["cache-control"] == "no-store"
    assert mine.headers["x-content-type-options"] == "nosniff"
    assert mine.headers["content-type"] == "image/jpeg"

    assert api.get(own_url, headers=stranger.headers).status_code == 404
    assert api.get(own_url, headers=owner.headers).status_code == 403
    assert api.get(own_url).status_code == 401
    assert api.get(admin_url, headers=renter.headers).status_code == 403
    assert (
        api.get(
            f"{DOCS}/{submission['id']}/files/{submission['id']}", headers=renter.headers
        ).status_code
        == 404
    )

    viewed = api.get(admin_url, headers=admin.headers)
    assert viewed.status_code == 200 and viewed.content == JPEG
    audit = db_session.scalars(
        select(AuditLog.action).where(AuditLog.entity_id == submission["id"])
    ).all()
    assert audit == ["verification.document_viewed"]
