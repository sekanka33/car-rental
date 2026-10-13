import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import AdminUser, DbSession, DocumentStorageDep
from app.api.routes.customers import PRIVATE_FILE_HEADERS
from app.models import CustomerProfile
from app.models.enums import SubmissionStatus
from app.schemas.verification import AdminSubmissionResponse, ReviewDecision, SubmitterSummary
from app.services import verification

router = APIRouter(prefix="/admin/verifications", tags=["admin: verifications"])


def _admin_view(session, submission) -> AdminSubmissionResponse:
    profile = session.query(CustomerProfile).filter_by(user_id=submission.user_id).one_or_none()
    return AdminSubmissionResponse.from_model(
        submission,
        submitter=SubmitterSummary(
            id=submission.user.id,
            full_name=submission.user.full_name,
            email=submission.user.email,
            date_of_birth=profile.date_of_birth if profile else None,
        ),
        reviewed_by_id=submission.reviewed_by_id,
    )


@router.get("", response_model=list[AdminSubmissionResponse])
def list_submissions(
    _: AdminUser,
    session: DbSession,
    status: SubmissionStatus | None = SubmissionStatus.PENDING,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AdminSubmissionResponse]:
    """Review queue, oldest first. Defaults to submissions awaiting review."""
    submissions = verification.list_submissions(session, status=status, limit=limit, offset=offset)
    return [_admin_view(session, s) for s in submissions]


@router.get("/{submission_id}", response_model=AdminSubmissionResponse)
def read_submission(
    submission_id: uuid.UUID, _: AdminUser, session: DbSession
) -> AdminSubmissionResponse:
    return _admin_view(session, verification.get_submission(session, submission_id))


@router.get("/{submission_id}/files/{file_id}", response_class=Response)
def view_file(
    submission_id: uuid.UUID,
    file_id: uuid.UUID,
    admin: AdminUser,
    session: DbSession,
    storage: DocumentStorageDep,
) -> Response:
    """Every administrator view of a private document is recorded in the audit log."""
    file, data = verification.read_file(
        session, storage, viewer=admin, submission_id=submission_id, file_id=file_id, as_admin=True
    )
    return Response(content=data, media_type=file.content_type, headers=PRIVATE_FILE_HEADERS)


@router.post("/{submission_id}/decision", response_model=AdminSubmissionResponse)
def decide(
    submission_id: uuid.UUID, body: ReviewDecision, admin: AdminUser, session: DbSession
) -> AdminSubmissionResponse:
    submission = verification.review_submission(
        session,
        reviewer=admin,
        submission_id=submission_id,
        decision=SubmissionStatus(body.decision),
        note=body.note,
        licence_expiry_date=body.licence_expiry_date,
    )
    return _admin_view(session, verification.get_submission(session, submission.id))
