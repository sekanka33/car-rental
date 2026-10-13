"""Whether a renter may book, derived only from trusted database records (BR-2)."""

from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.identity import age_on
from app.models import CustomerProfile, User
from app.models.enums import RoleName, UserStatus, VerificationStatus
from app.services.verification import SA_TIMEZONE


@dataclass(frozen=True)
class Eligibility:
    eligible: bool
    reasons: list[str] = field(default_factory=list)


def _local_date(value: datetime) -> date:
    return value.astimezone(SA_TIMEZONE).date()


def evaluate_renter_eligibility(
    session: Session,
    settings: Settings,
    user: User,
    *,
    rental_start: datetime,
    rental_end: datetime,
) -> Eligibility:
    """Every failed rule is reported, so the customer can see everything left to do."""
    reasons: list[str] = []
    if RoleName.RENTER not in {role.name for role in user.roles}:
        reasons.append("NOT_A_RENTER")
    if user.status != UserStatus.ACTIVE:
        reasons.append("ACCOUNT_NOT_ACTIVE")
    if user.email_verified_at is None:
        reasons.append("EMAIL_NOT_VERIFIED")

    profile = session.scalar(select(CustomerProfile).where(CustomerProfile.user_id == user.id))
    if profile is None:
        reasons.append("PROFILE_MISSING")
        return Eligibility(eligible=False, reasons=reasons)

    if profile.date_of_birth is None:
        reasons.append("DATE_OF_BIRTH_MISSING")
    elif age_on(profile.date_of_birth, _local_date(rental_start)) < settings.min_renter_age:
        reasons.append("UNDER_MINIMUM_AGE")
    if profile.id_verification_status != VerificationStatus.APPROVED:
        reasons.append("ID_NOT_APPROVED")
    if profile.licence_verification_status != VerificationStatus.APPROVED:
        reasons.append("LICENCE_NOT_APPROVED")
    elif profile.licence_expiry_date is None or profile.licence_expiry_date <= _local_date(
        rental_end
    ):
        reasons.append("LICENCE_EXPIRES_BEFORE_RENTAL_ENDS")
    return Eligibility(eligible=not reasons, reasons=reasons)
