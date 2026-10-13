from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.identity import luhn_valid
from app.services.verification import today_in_south_africa

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200  # starts with the JPEG signature
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
PDF = b"%PDF-1.7\n" + b"0" * 200
DOB = date(1995, 6, 15)


def make_sa_id(birth: date, sequence: str = "5123", citizenship: str = "0") -> str:
    base = f"{birth:%y%m%d}{sequence}{citizenship}8"
    return base + next(d for d in "0123456789" if luhn_valid(base + d))


def future_date(days: int = 365 * 3) -> date:
    return today_in_south_africa() + timedelta(days=days)


def set_dob(api: TestClient, headers: dict, dob: date = DOB):
    return api.put(
        "/api/v1/customers/me/profile/date-of-birth",
        headers=headers,
        json={"date_of_birth": dob.isoformat()},
    )


def submit_id(
    api: TestClient, headers: dict, id_number: str | None = None, front: bytes = JPEG, **extra
):
    return api.post(
        "/api/v1/customers/me/documents",
        headers=headers,
        data={"document_type": "SA_ID", "document_number": id_number or make_sa_id(DOB), **extra},
        files={"front": ("id-front.jpg", front, "image/jpeg")},
    )


def submit_licence(
    api: TestClient,
    headers: dict,
    expiry: date | None = None,
    number: str = "1234567890AB",
    back: bytes | None = None,
):
    files = {"front": ("licence-front.png", PNG, "image/png")}
    if back is not None:
        files["back"] = ("licence-back.pdf", back, "application/pdf")
    return api.post(
        "/api/v1/customers/me/documents",
        headers=headers,
        data={
            "document_type": "DRIVING_LICENCE",
            "document_number": number,
            "licence_expiry_date": (expiry or future_date()).isoformat(),
            "licence_codes": "B",
        },
        files=files,
    )


def decide(api: TestClient, admin_headers: dict, submission_id: str, decision: str, **extra):
    return api.post(
        f"/api/v1/admin/verifications/{submission_id}/decision",
        headers=admin_headers,
        json={"decision": decision, **extra},
    )


def verify_email(api: TestClient, outbox, session: Session | None = None) -> None:
    token = outbox.outbox[-1].body.split("token=")[1].split()[0]
    assert api.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
