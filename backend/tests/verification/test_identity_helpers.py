"""SA ID number checks, document hashing and local private storage (no database)."""

import os
import stat
from datetime import date

import pytest

from app.core.identity import (
    age_on,
    document_number_hmac,
    last_digits,
    sa_id_birth_date,
    validate_sa_id_number,
)
from app.integrations.storage import DocumentNotFoundError, LocalDocumentStorage
from tests.verification.helpers import make_sa_id

TODAY = date(2026, 10, 13)


def test_valid_id_numbers_pass() -> None:
    for birth, citizenship in [(date(1995, 6, 15), "0"), (date(2004, 2, 29), "1")]:
        number = make_sa_id(birth, citizenship=citizenship)
        assert validate_sa_id_number(number, TODAY) is None
        assert sa_id_birth_date(number, TODAY) == birth


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda n: n[:-1] + str((int(n[-1]) + 1) % 10), "check digit"),
        (lambda n: n[:12], "13 digits"),
        (lambda n: n[:6] + "ABCD" + n[10:], "13 digits"),
        (lambda n: "951315" + n[6:], "date of birth"),
        (lambda n: n[:10] + "2" + n[11:], "citizenship"),
    ],
    ids=["bad-check-digit", "too-short", "letters", "month-13", "citizenship-2"],
)
def test_invalid_id_numbers_rejected(mutate, message: str) -> None:
    number = mutate(make_sa_id(date(1995, 6, 15)))

    assert message in (validate_sa_id_number(number, TODAY) or "")


def test_century_is_inferred_from_today() -> None:
    assert sa_id_birth_date(make_sa_id(date(2001, 1, 1)), TODAY).year == 2001
    assert sa_id_birth_date(make_sa_id(date(1950, 1, 1)), TODAY).year == 1950


@pytest.mark.parametrize(
    ("birth", "on", "age"),
    [
        (date(2008, 10, 13), date(2026, 10, 13), 18),  # 18th birthday today
        (date(2008, 10, 14), date(2026, 10, 13), 17),  # turns 18 tomorrow
        (date(2004, 2, 29), date(2022, 2, 28), 17),  # leap-day birthday
        (date(2004, 2, 29), date(2022, 3, 1), 18),
    ],
)
def test_age_on(birth: date, on: date, age: int) -> None:
    assert age_on(birth, on) == age


def test_document_hash_is_keyed_normalised_and_irreversible() -> None:
    number = make_sa_id(date(1995, 6, 15))
    spaced = f"{number[:6]} {number[6:10]} {number[10:]}"

    assert document_number_hmac(number, "k" * 32) == document_number_hmac(spaced, "k" * 32)
    assert document_number_hmac(number, "k" * 32) != document_number_hmac(number, "j" * 32)
    assert number not in document_number_hmac(number, "k" * 32)
    assert last_digits(spaced, 3) == number[-3:]


def test_local_storage_is_private(tmp_path) -> None:
    storage = LocalDocumentStorage(tmp_path / "docs")

    key = storage.save(b"secret document")

    path = next((tmp_path / "docs").rglob(key))
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(path.parent).st_mode) == 0o700
    assert storage.read(key) == b"secret document"
    storage.delete(key)
    with pytest.raises(DocumentNotFoundError):
        storage.read(key)


@pytest.mark.parametrize("key", ["../../etc/passwd", "..", "not-a-uuid", "/tmp/x"])  # noqa: S108 - hostile input
def test_local_storage_rejects_untrusted_keys(tmp_path, key: str) -> None:
    with pytest.raises(DocumentNotFoundError):
        LocalDocumentStorage(tmp_path).read(key)
