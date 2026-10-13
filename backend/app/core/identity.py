"""South African identity-number checks and privacy helpers.

An SA ID number is 13 digits: YYMMDD (date of birth), SSSS (sequence/gender),
C (citizenship: 0 citizen, 1 permanent resident), A (historical), Z (Luhn check digit).
A valid format proves nothing about who presented it; documents still need review.
"""

import hashlib
import hmac
import re
from datetime import date

_SA_ID = re.compile(r"^\d{13}$")


def luhn_valid(number: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(number)):
        digit = int(char)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def sa_id_birth_date(id_number: str, today: date) -> date | None:
    """Date of birth encoded in the ID number (century inferred), or None if invalid."""
    yy, mm, dd = int(id_number[0:2]), int(id_number[2:4]), int(id_number[4:6])
    century = 2000 if 2000 + yy <= today.year else 1900
    try:
        return date(century + yy, mm, dd)
    except ValueError:
        return None


def validate_sa_id_number(id_number: str, today: date) -> str | None:
    """Return an error message, or None if the number is structurally valid."""
    if not _SA_ID.match(id_number):
        return "ID number must be exactly 13 digits."
    if sa_id_birth_date(id_number, today) is None:
        return "ID number does not contain a valid date of birth."
    if id_number[10] not in "01":
        return "ID number has an invalid citizenship digit."
    if not luhn_valid(id_number):
        return "ID number check digit is invalid."
    return None


def normalise_document_number(value: str) -> str:
    return re.sub(r"[\s-]", "", value).upper()


def document_number_hmac(value: str, key: str) -> str:
    return hmac.new(
        key.encode(), normalise_document_number(value).encode(), hashlib.sha256
    ).hexdigest()


def last_digits(value: str, count: int) -> str:
    return normalise_document_number(value)[-count:]


def age_on(birth_date: date, on: date) -> int:
    return on.year - birth_date.year - ((on.month, on.day) < (birth_date.month, birth_date.day))
