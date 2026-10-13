"""Renter identity / licence document submission and administrator review."""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.errors import AppError, NotFoundError, PermissionDeniedError
from app.core.identity import (
    age_on,
    document_number_hmac,
    last_digits,
    normalise_document_number,
    sa_id_birth_date,
    validate_sa_id_number,
)
from app.integrations.storage import DocumentStorage
from app.models import CustomerProfile, User, VerificationFile, VerificationSubmission
from app.models.enums import DocumentSide, DocumentType, SubmissionStatus, VerificationStatus
from app.services.audit import record_audit
from app.services.uploads import DOCUMENT_TYPES, InvalidUploadError, check_upload

logger = logging.getLogger(__name__)
SA_TIMEZONE = ZoneInfo("Africa/Johannesburg")

InvalidDocumentError = InvalidUploadError


class ProfileIncompleteError(AppError):
    status_code = 409
    code = "profile_incomplete"


class DuplicateIdentityError(AppError):
    status_code = 409
    code = "identity_already_verified"


class ProfileLockedError(AppError):
    status_code = 409
    code = "profile_locked"


class UnderageError(AppError):
    status_code = 422
    code = "under_minimum_age"


class SubmissionNotReviewableError(AppError):
    status_code = 409
    code = "submission_not_reviewable"


@dataclass(frozen=True)
class UploadedFile:
    side: DocumentSide
    data: bytes


def today_in_south_africa() -> date:
    return datetime.now(SA_TIMEZONE).date()


def get_customer_profile(session: Session, user: User) -> CustomerProfile:
    profile = session.scalar(select(CustomerProfile).where(CustomerProfile.user_id == user.id))
    if profile is None:
        raise NotFoundError("Customer profile not found.")
    return profile


# --- date of birth -----------------------------------------------------------------


def set_date_of_birth(
    session: Session, settings: Settings, user: User, date_of_birth: date
) -> CustomerProfile:
    profile = get_customer_profile(session, user)
    if profile.id_verification_status in (VerificationStatus.PENDING, VerificationStatus.APPROVED):
        raise ProfileLockedError(
            "Your date of birth cannot be changed while your ID is under review or approved."
        )
    today = today_in_south_africa()
    if date_of_birth >= today:
        raise UnderageError("Date of birth must be in the past.")
    if age_on(date_of_birth, today) < settings.min_renter_age:
        raise UnderageError(f"You must be at least {settings.min_renter_age} years old to rent.")
    profile.date_of_birth = date_of_birth
    session.commit()
    return profile


# --- submission ----------------------------------------------------------------------


def submit_document(
    session: Session,
    settings: Settings,
    storage: DocumentStorage,
    user: User,
    *,
    document_type: DocumentType,
    document_number: str,
    files: list[UploadedFile],
    licence_expiry_date: date | None = None,
    licence_codes: str | None = None,
) -> VerificationSubmission:
    """Store the files privately and queue the submission for review (status PENDING)."""
    profile = get_customer_profile(session, user)
    today = today_in_south_africa()
    number = normalise_document_number(document_number)
    key = settings.document_hash_key.get_secret_value()

    if document_type == DocumentType.SA_ID:
        if profile.date_of_birth is None:
            raise ProfileIncompleteError("Add your date of birth before submitting your ID.")
        if error := validate_sa_id_number(number, today):
            raise InvalidDocumentError(error)
        if sa_id_birth_date(number, today) != profile.date_of_birth:
            raise InvalidDocumentError("The ID number does not match your date of birth.")
        if _approved_elsewhere(session, document_number_hmac(number, key), user.id):
            raise DuplicateIdentityError(
                "This ID number is already verified on another account. Contact support."
            )
    else:
        if not 6 <= len(number) <= 20 or not number.isalnum():
            raise InvalidDocumentError("Licence number must be 6-20 letters or digits.")
        if licence_expiry_date is None or licence_expiry_date <= today:
            raise InvalidDocumentError("The driving licence must not be expired.")

    checked = [
        (
            f.side,
            check_upload(f.data, allowed=DOCUMENT_TYPES, max_bytes=settings.max_document_bytes),
        )
        for f in files
    ]
    sides = [side for side, _ in checked]
    if DocumentSide.FRONT not in sides or len(set(sides)) != len(sides):
        raise InvalidDocumentError("Upload the front of the document (and optionally the back).")

    stored_keys: list[str] = []
    try:
        # A new submission replaces one still waiting for review.
        session.execute(
            update(VerificationSubmission)
            .where(
                VerificationSubmission.user_id == user.id,
                VerificationSubmission.document_type == document_type,
                VerificationSubmission.status == SubmissionStatus.PENDING,
            )
            .values(status=SubmissionStatus.SUPERSEDED)
        )
        submission = VerificationSubmission(
            user_id=user.id,
            document_type=document_type,
            document_number_hmac=document_number_hmac(number, key),
            document_number_last_digits=last_digits(number, 3),
            licence_expiry_date=licence_expiry_date
            if document_type == DocumentType.DRIVING_LICENCE
            else None,
            licence_codes=licence_codes if document_type == DocumentType.DRIVING_LICENCE else None,
        )
        for side, upload in checked:
            storage_key = storage.save(upload.data)
            stored_keys.append(storage_key)
            submission.files.append(
                VerificationFile(
                    side=side,
                    storage_key=storage_key,
                    content_type=upload.content_type,
                    size_bytes=upload.size_bytes,
                    sha256=upload.sha256,
                )
            )
        session.add(submission)
        _set_profile_status(profile, document_type, VerificationStatus.PENDING)
        session.commit()
    except Exception:
        session.rollback()
        for storage_key in stored_keys:  # do not leave orphaned files behind
            storage.delete(storage_key)
        raise
    return submission


def _approved_elsewhere(session: Session, number_hmac: str, user_id: uuid.UUID) -> bool:
    return (
        session.scalar(
            select(VerificationSubmission.id).where(
                VerificationSubmission.document_number_hmac == number_hmac,
                VerificationSubmission.document_type == DocumentType.SA_ID,
                VerificationSubmission.status == SubmissionStatus.APPROVED,
                VerificationSubmission.user_id != user_id,
            )
        )
        is not None
    )


def _set_profile_status(
    profile: CustomerProfile, document_type: DocumentType, status: VerificationStatus
) -> None:
    if document_type == DocumentType.SA_ID:
        profile.id_verification_status = status
    else:
        profile.licence_verification_status = status


# --- queries ---------------------------------------------------------------------------


def list_own_submissions(session: Session, user: User) -> list[VerificationSubmission]:
    return list(
        session.scalars(
            select(VerificationSubmission)
            .options(selectinload(VerificationSubmission.files))
            .where(VerificationSubmission.user_id == user.id)
            .order_by(VerificationSubmission.created_at.desc())
        )
    )


def list_submissions(
    session: Session, *, status: SubmissionStatus | None, limit: int, offset: int
) -> list[VerificationSubmission]:
    query = (
        select(VerificationSubmission)
        .options(
            selectinload(VerificationSubmission.files), selectinload(VerificationSubmission.user)
        )
        .order_by(VerificationSubmission.created_at)
        .limit(limit)
        .offset(offset)
    )
    if status is not None:
        query = query.where(VerificationSubmission.status == status)
    return list(session.scalars(query))


def get_submission(session: Session, submission_id: uuid.UUID) -> VerificationSubmission:
    submission = session.scalar(
        select(VerificationSubmission)
        .options(
            selectinload(VerificationSubmission.files), selectinload(VerificationSubmission.user)
        )
        .where(VerificationSubmission.id == submission_id)
    )
    if submission is None:
        raise NotFoundError("Submission not found.")
    return submission


def read_file(
    session: Session,
    storage: DocumentStorage,
    *,
    viewer: User,
    submission_id: uuid.UUID,
    file_id: uuid.UUID,
    as_admin: bool,
) -> tuple[VerificationFile, bytes]:
    """Return a document file. Owners see their own; administrators' access is audited."""
    submission = get_submission(session, submission_id)
    if not as_admin and submission.user_id != viewer.id:
        raise NotFoundError("Submission not found.")  # do not reveal other users' submissions
    file = next((f for f in submission.files if f.id == file_id), None)
    if file is None:
        raise NotFoundError("File not found.")
    data = storage.read(file.storage_key)
    if as_admin:
        record_audit(
            session,
            actor_id=viewer.id,
            action="verification.document_viewed",
            entity_type="verification_submission",
            entity_id=submission.id,
            changes={"file_id": str(file.id), "side": file.side.value},
        )
        session.commit()
    return file, data


# --- review --------------------------------------------------------------------------------


def review_submission(
    session: Session,
    *,
    reviewer: User,
    submission_id: uuid.UUID,
    decision: SubmissionStatus,
    note: str | None,
    licence_expiry_date: date | None = None,
) -> VerificationSubmission:
    if decision not in (
        SubmissionStatus.APPROVED,
        SubmissionStatus.REJECTED,
        SubmissionStatus.REQUIRES_MORE_INFORMATION,
    ):
        raise SubmissionNotReviewableError("Invalid decision.")
    submission = session.scalar(
        select(VerificationSubmission)
        .where(VerificationSubmission.id == submission_id)
        .with_for_update()
    )
    if submission is None:
        raise NotFoundError("Submission not found.")
    if submission.user_id == reviewer.id:
        raise PermissionDeniedError("You cannot review your own documents.")
    if submission.status != SubmissionStatus.PENDING:
        raise SubmissionNotReviewableError(
            f"Only pending submissions can be reviewed (this one is {submission.status})."
        )
    if decision != SubmissionStatus.APPROVED and not note:
        raise SubmissionNotReviewableError("A note for the customer is required.")

    if (
        decision == SubmissionStatus.APPROVED
        and submission.document_type == DocumentType.DRIVING_LICENCE
        and licence_expiry_date is not None
    ):
        submission.licence_expiry_date = licence_expiry_date  # reviewer-confirmed value
    if (
        decision == SubmissionStatus.APPROVED
        and submission.document_type == DocumentType.DRIVING_LICENCE
        and submission.licence_expiry_date <= today_in_south_africa()
    ):
        raise SubmissionNotReviewableError("Cannot approve an expired driving licence.")

    now = datetime.now(UTC)
    submission.status = decision
    submission.reviewed_at = now
    submission.reviewed_by_id = reviewer.id
    submission.review_note = note
    try:
        # Flush now: the unique index on approved ID numbers fires here if the same
        # ID was approved on another account in the meantime.
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise DuplicateIdentityError(
            "This ID number is already verified on another account."
        ) from exc

    profile = session.scalar(
        select(CustomerProfile).where(CustomerProfile.user_id == submission.user_id)
    )
    _set_profile_status(profile, submission.document_type, VerificationStatus(decision.value))
    if (
        decision == SubmissionStatus.APPROVED
        and submission.document_type == DocumentType.DRIVING_LICENCE
    ):
        profile.licence_expiry_date = submission.licence_expiry_date

    record_audit(
        session,
        actor_id=reviewer.id,
        action=f"verification.{decision.value.lower()}",
        entity_type="verification_submission",
        entity_id=submission.id,
        changes={
            "user_id": str(submission.user_id),
            "document_type": submission.document_type.value,
            "decision": decision.value,
            "note": note,
        },
    )
    session.commit()
    return submission
