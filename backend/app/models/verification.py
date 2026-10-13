import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.enums import DocumentSide, DocumentType, SubmissionStatus
from app.models.user import User

ALLOWED_DOCUMENT_CONTENT_TYPES = ("image/jpeg", "image/png", "application/pdf")


class VerificationSubmission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One submission of an identity document or driving licence, and its review decision.

    Full ID and licence numbers are never stored: only a keyed hash (HMAC-SHA256, for
    duplicate detection) and the last digits (for display).
    """

    __tablename__ = "verification_submissions"
    __table_args__ = (
        # At most one submission of each type awaiting review per user.
        Index(
            "uq_verification_submissions_one_pending",
            "user_id",
            "document_type",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
        # The same SA ID number cannot be verified on two accounts.
        Index(
            "uq_verification_submissions_approved_id_number",
            "document_number_hmac",
            unique=True,
            postgresql_where=text("status = 'APPROVED' AND document_type = 'SA_ID'"),
        ),
        Index("ix_verification_submissions_status_created", "status", "created_at"),
        CheckConstraint(
            "(status IN ('PENDING', 'SUPERSEDED')) = (reviewed_at IS NULL)",
            name="review_fields_consistent",
        ),
        CheckConstraint(
            "status NOT IN ('REJECTED', 'REQUIRES_MORE_INFORMATION') OR review_note IS NOT NULL",
            name="negative_decision_has_note",
        ),
        CheckConstraint(
            "document_type <> 'DRIVING_LICENCE' OR licence_expiry_date IS NOT NULL",
            name="licence_has_expiry",
        ),
        CheckConstraint("char_length(document_number_hmac) = 64", name="hmac_length"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    document_type: Mapped[DocumentType] = mapped_column(str_enum(DocumentType, "document_type"))
    status: Mapped[SubmissionStatus] = mapped_column(
        str_enum(SubmissionStatus, "submission_status"),
        default=SubmissionStatus.PENDING,
        server_default="PENDING",
    )
    document_number_hmac: Mapped[str] = mapped_column(String(64))
    document_number_last_digits: Mapped[str] = mapped_column(String(4))
    licence_expiry_date: Mapped[date | None]
    licence_codes: Mapped[str | None] = mapped_column(String(50))

    reviewed_at: Mapped[datetime | None]
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    review_note: Mapped[str | None] = mapped_column(String(1000))

    user: Mapped[User] = relationship(foreign_keys=[user_id])
    files: Mapped[list["VerificationFile"]] = relationship(
        back_populates="submission", order_by="VerificationFile.side", cascade="all, delete-orphan"
    )


class VerificationFile(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """An uploaded document image/PDF. The bytes live in private storage under storage_key."""

    __tablename__ = "verification_files"
    __table_args__ = (
        Index("uq_verification_files_submission_side", "submission_id", "side", unique=True),
        CheckConstraint(
            "content_type IN ("
            + ", ".join(f"'{content_type}'" for content_type in ALLOWED_DOCUMENT_CONTENT_TYPES)
            + ")",
            name="content_type_allowed",
        ),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        CheckConstraint("char_length(sha256) = 64", name="sha256_length"),
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("verification_submissions.id", ondelete="CASCADE")
    )
    side: Mapped[DocumentSide] = mapped_column(str_enum(DocumentSide, "document_side"))
    storage_key: Mapped[str] = mapped_column(String(200), unique=True)
    content_type: Mapped[str] = mapped_column(String(50))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))

    submission: Mapped[VerificationSubmission] = relationship(back_populates="files")
