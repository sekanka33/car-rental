"""Renter profile, identity/licence document submission and eligibility."""

import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.deps import AppSettings, DbSession, DocumentStorageDep, RenterUser
from app.core.errors import AppError
from app.models.enums import DocumentSide, DocumentType
from app.schemas.verification import (
    CustomerProfileResponse,
    DateOfBirthUpdate,
    EligibilityResponse,
    SubmissionResponse,
)
from app.services import verification
from app.services.eligibility import evaluate_renter_eligibility

router = APIRouter(prefix="/customers/me", tags=["customers"])

PRIVATE_FILE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Content-Disposition": "inline",
}


def _profile_response(profile, settings) -> CustomerProfileResponse:
    return CustomerProfileResponse(
        date_of_birth=profile.date_of_birth,
        id_verification_status=profile.id_verification_status,
        licence_verification_status=profile.licence_verification_status,
        licence_expiry_date=profile.licence_expiry_date,
        minimum_age=settings.min_renter_age,
    )


@router.get("/profile", response_model=CustomerProfileResponse)
def read_profile(
    user: RenterUser, session: DbSession, settings: AppSettings
) -> CustomerProfileResponse:
    return _profile_response(verification.get_customer_profile(session, user), settings)


@router.put("/profile/date-of-birth", response_model=CustomerProfileResponse)
def update_date_of_birth(
    body: DateOfBirthUpdate, user: RenterUser, session: DbSession, settings: AppSettings
) -> CustomerProfileResponse:
    profile = verification.set_date_of_birth(session, settings, user, body.date_of_birth)
    return _profile_response(profile, settings)


def _read_upload(upload: UploadFile, max_bytes: int) -> bytes:
    # Read one byte past the limit so oversize files are detected without loading them fully.
    return upload.file.read(max_bytes + 1)


@router.post(
    "/documents",
    status_code=status.HTTP_201_CREATED,
    response_model=SubmissionResponse,
    summary="Submit an SA ID or driving licence for verification",
)
def submit_document(
    user: RenterUser,
    session: DbSession,
    settings: AppSettings,
    storage: DocumentStorageDep,
    document_type: Annotated[DocumentType, Form()],
    document_number: Annotated[str, Form(min_length=6, max_length=30)],
    front: Annotated[UploadFile, File(description="JPEG, PNG or PDF")],
    back: Annotated[UploadFile | None, File(description="Optional back side")] = None,
    licence_expiry_date: Annotated[date | None, Form()] = None,
    licence_codes: Annotated[str | None, Form(max_length=50)] = None,
) -> SubmissionResponse:
    """Uploading does not verify anything: an administrator reviews every submission."""
    files = [
        verification.UploadedFile(
            DocumentSide.FRONT, _read_upload(front, settings.max_document_bytes)
        )
    ]
    if back is not None:
        files.append(
            verification.UploadedFile(
                DocumentSide.BACK, _read_upload(back, settings.max_document_bytes)
            )
        )
    submission = verification.submit_document(
        session,
        settings,
        storage,
        user,
        document_type=document_type,
        document_number=document_number,
        files=files,
        licence_expiry_date=licence_expiry_date,
        licence_codes=licence_codes,
    )
    return SubmissionResponse.from_model(submission)


@router.get("/documents", response_model=list[SubmissionResponse])
def list_documents(user: RenterUser, session: DbSession) -> list[SubmissionResponse]:
    return [
        SubmissionResponse.from_model(s) for s in verification.list_own_submissions(session, user)
    ]


@router.get("/documents/{submission_id}/files/{file_id}", response_class=Response)
def download_own_file(
    submission_id: uuid.UUID,
    file_id: uuid.UUID,
    user: RenterUser,
    session: DbSession,
    storage: DocumentStorageDep,
) -> Response:
    file, data = verification.read_file(
        session, storage, viewer=user, submission_id=submission_id, file_id=file_id, as_admin=False
    )
    return Response(content=data, media_type=file.content_type, headers=PRIVATE_FILE_HEADERS)


class InvalidRentalPeriodError(AppError):
    status_code = 422
    code = "invalid_rental_period"


@router.get("/eligibility", response_model=EligibilityResponse)
def check_eligibility(
    user: RenterUser,
    session: DbSession,
    settings: AppSettings,
    start_at: Annotated[datetime, Query(description="Rental start (ISO 8601 with timezone)")],
    end_at: Annotated[datetime, Query(description="Rental end (ISO 8601 with timezone)")],
) -> EligibilityResponse:
    if start_at.tzinfo is None or end_at.tzinfo is None:
        raise InvalidRentalPeriodError("start_at and end_at must include a timezone.")
    if end_at <= start_at:
        raise InvalidRentalPeriodError("end_at must be after start_at.")
    result = evaluate_renter_eligibility(
        session, settings, user, rental_start=start_at, rental_end=end_at
    )
    return EligibilityResponse(eligible=result.eligible, reasons=result.reasons)
