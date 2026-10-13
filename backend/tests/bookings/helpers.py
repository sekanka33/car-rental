from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CustomerProfile, User
from app.models.enums import VerificationStatus
from app.services.verification import today_in_south_africa
from tests.api_fixtures import Account, login, register

URL = "/api/v1/bookings"
START = (datetime.now(UTC) + timedelta(days=7)).replace(hour=8, minute=0, second=0, microsecond=0)


def make_eligible(session: Session, email: str, licence_days: int = 1000) -> User:
    """Give a registered renter a verified email, date of birth, approved ID and licence."""
    user = session.scalar(select(User).where(User.email == email))
    user.email_verified_at = datetime.now(UTC)
    profile = session.scalar(select(CustomerProfile).where(CustomerProfile.user_id == user.id))
    profile.date_of_birth = date(1995, 6, 15)
    profile.id_verification_status = VerificationStatus.APPROVED
    profile.licence_verification_status = VerificationStatus.APPROVED
    profile.licence_expiry_date = today_in_south_africa() + timedelta(days=licence_days)
    session.flush()
    return user


def eligible_renter(api: TestClient, session: Session, email: str, **kwargs) -> Account:
    register(api, email, "RENTER")
    make_eligible(session, email, **kwargs)
    return login(api, email)


def book(
    api: TestClient, account: Account, vehicle_id, start: datetime = START, days: int = 3, **extra
):
    body = {
        "vehicle_id": str(vehicle_id),
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(days=days)).isoformat(),
        "delivery_address": "12 Long Street, Cape Town",
        **extra,
    }
    return api.post(URL, headers=account.headers, json=body)
