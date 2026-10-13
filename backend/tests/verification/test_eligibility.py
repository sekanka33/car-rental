from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.models.enums import UserStatus
from app.services.eligibility import evaluate_renter_eligibility
from tests.api_fixtures import Account
from tests.conftest import make_settings, requires_db
from tests.verification.helpers import (
    decide,
    future_date,
    set_dob,
    submit_id,
    submit_licence,
    verify_email,
)

pytestmark = requires_db
START = datetime.now(UTC) + timedelta(days=7)
END = START + timedelta(days=3)


def check(api: TestClient, account: Account, start=START, end=END):
    return api.get(
        "/api/v1/customers/me/eligibility",
        headers=account.headers,
        params={"start_at": start.isoformat(), "end_at": end.isoformat()},
    )


def make_fully_verified(
    api: TestClient, renter: Account, admin: Account, outbox, licence_days=1000
):
    verify_email(api, outbox)
    set_dob(api, renter.headers)
    decide(api, admin.headers, submit_id(api, renter.headers).json()["id"], "APPROVED")
    licence = submit_licence(api, renter.headers, expiry=future_date(licence_days)).json()
    decide(api, admin.headers, licence["id"], "APPROVED")


def test_new_renter_sees_everything_still_required(api: TestClient, renter: Account) -> None:
    response = check(api, renter)

    assert response.status_code == 200
    assert response.json() == {
        "eligible": False,
        "reasons": [
            "EMAIL_NOT_VERIFIED",
            "DATE_OF_BIRTH_MISSING",
            "ID_NOT_APPROVED",
            "LICENCE_NOT_APPROVED",
        ],
    }


def test_uploaded_but_unreviewed_documents_do_not_make_a_renter_eligible(
    api: TestClient, renter: Account, outbox
) -> None:
    verify_email(api, outbox)
    set_dob(api, renter.headers)
    submit_id(api, renter.headers)
    submit_licence(api, renter.headers)

    assert check(api, renter).json()["reasons"] == ["ID_NOT_APPROVED", "LICENCE_NOT_APPROVED"]


def test_fully_verified_renter_is_eligible(
    api: TestClient, renter: Account, admin: Account, outbox
) -> None:
    make_fully_verified(api, renter, admin, outbox)

    assert check(api, renter).json() == {"eligible": True, "reasons": []}


def test_licence_must_outlast_the_rental(
    api: TestClient, renter: Account, admin: Account, outbox
) -> None:
    make_fully_verified(api, renter, admin, outbox, licence_days=30)

    long_rental = check(api, renter, end=START + timedelta(days=60))

    assert long_rental.json()["reasons"] == ["LICENCE_EXPIRES_BEFORE_RENTAL_ENDS"]


def test_higher_minimum_age_and_inactive_account(
    api: TestClient, renter: Account, admin: Account, outbox, db_session: Session
) -> None:
    make_fully_verified(api, renter, admin, outbox)  # born 1995 -> 31 years old
    user = db_session.scalar(select(User).where(User.email == renter.email))

    strict = evaluate_renter_eligibility(
        db_session, make_settings(min_renter_age=30), user, rental_start=START, rental_end=END
    )
    assert strict.eligible
    user.status = UserStatus.DEACTIVATED
    stricter = evaluate_renter_eligibility(
        db_session,
        make_settings(min_renter_age=30),
        user,
        rental_start=START.replace(year=1995 + 25),
        rental_end=END.replace(year=1995 + 25),
    )
    assert stricter.reasons == ["ACCOUNT_NOT_ACTIVE", "UNDER_MINIMUM_AGE"]


def test_owner_is_not_eligible_to_rent(api: TestClient, owner: Account) -> None:
    assert check(api, owner).status_code == 403


def test_period_validation(api: TestClient, renter: Account) -> None:
    naive = START.replace(tzinfo=None)

    assert check(api, renter, start=naive, end=naive + timedelta(days=1)).status_code == 422
    assert check(api, renter, start=END, end=START).status_code == 422
