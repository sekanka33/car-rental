import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models.enums import DocumentSide, DocumentType, SubmissionStatus, VerificationStatus
from app.schemas.auth import RequestModel


class DateOfBirthUpdate(RequestModel):
    date_of_birth: date


class CustomerProfileResponse(BaseModel):
    date_of_birth: date | None
    id_verification_status: VerificationStatus
    licence_verification_status: VerificationStatus
    licence_expiry_date: date | None
    minimum_age: int


class VerificationFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    side: DocumentSide
    content_type: str
    size_bytes: int


class SubmissionResponse(BaseModel):
    """What a customer sees about their own submission (numbers are masked)."""

    id: uuid.UUID
    document_type: DocumentType
    status: SubmissionStatus
    document_number_masked: str
    licence_expiry_date: date | None
    licence_codes: str | None
    review_note: str | None
    submitted_at: datetime
    reviewed_at: datetime | None
    files: list[VerificationFileResponse]

    @classmethod
    def from_model(cls, submission, **extra) -> "SubmissionResponse":
        return cls(
            id=submission.id,
            document_type=submission.document_type,
            status=submission.status,
            document_number_masked="•" * 6 + submission.document_number_last_digits,
            licence_expiry_date=submission.licence_expiry_date,
            licence_codes=submission.licence_codes,
            review_note=submission.review_note,
            submitted_at=submission.created_at,
            reviewed_at=submission.reviewed_at,
            files=[VerificationFileResponse.model_validate(f) for f in submission.files],
            **extra,
        )


class SubmitterSummary(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    date_of_birth: date | None


class AdminSubmissionResponse(SubmissionResponse):
    submitter: SubmitterSummary
    reviewed_by_id: uuid.UUID | None


class ReviewDecision(RequestModel):
    decision: Literal["APPROVED", "REJECTED", "REQUIRES_MORE_INFORMATION"]
    note: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)]
        | None
    ) = None
    licence_expiry_date: date | None = Field(
        default=None, description="Reviewer-confirmed licence expiry (driving licences only)"
    )

    @model_validator(mode="after")
    def note_required_unless_approved(self) -> "ReviewDecision":
        if self.decision != "APPROVED" and not self.note:
            raise ValueError("note is required when rejecting or requesting more information")
        return self


class EligibilityResponse(BaseModel):
    eligible: bool
    reasons: list[str]
