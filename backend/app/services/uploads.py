"""Shared checks for uploaded files: real type from content, size limit, checksum."""

import hashlib
from dataclasses import dataclass

from app.core.errors import AppError

# Magic numbers identify the real file type; client file names and Content-Type are ignored.
_SIGNATURES: tuple[tuple[bytes, int, str], ...] = (
    (b"\xff\xd8\xff", 0, "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", 0, "image/png"),
    (b"%PDF-", 0, "application/pdf"),
    (b"WEBP", 8, "image/webp"),  # RIFF....WEBP
)

DOCUMENT_TYPES = frozenset({"image/jpeg", "image/png", "application/pdf"})
PHOTO_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


class InvalidUploadError(AppError):
    status_code = 422
    code = "invalid_document"


class UploadTooLargeError(AppError):
    status_code = 413
    code = "document_too_large"


@dataclass(frozen=True)
class CheckedUpload:
    data: bytes
    content_type: str
    size_bytes: int
    sha256: str


def detect_content_type(data: bytes) -> str | None:
    for magic, offset, content_type in _SIGNATURES:
        if data[offset : offset + len(magic)] == magic and (
            offset == 0 or data.startswith(b"RIFF")
        ):
            return content_type
    return None


def check_upload(data: bytes, *, allowed: frozenset[str], max_bytes: int) -> CheckedUpload:
    if not data:
        raise InvalidUploadError("Uploaded file is empty.")
    if len(data) > max_bytes:
        raise UploadTooLargeError(f"Each file must be at most {max_bytes // (1024 * 1024)} MB.")
    content_type = detect_content_type(data)
    if content_type not in allowed:
        names = ", ".join(sorted(t.split("/")[1].upper() for t in allowed))
        raise InvalidUploadError(f"Only {names} files are accepted.")
    return CheckedUpload(data, content_type, len(data), hashlib.sha256(data).hexdigest())
