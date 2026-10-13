"""Password hashing and token primitives (no database)."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    generate_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    verify_password,
)

SECRET = "unit-test-secret-0123456789abcdefghijklmnop"
ISS, AUD = "car-rental-api", "car-rental-clients"


def make_token(**overrides) -> str:
    values = {
        "user_id": uuid.uuid4(),
        "token_version": 0,
        "secret": SECRET,
        "issuer": ISS,
        "audience": AUD,
        "ttl": timedelta(minutes=15),
    }
    values.update(overrides)
    return create_access_token(**values)


def decode(token: str):
    return decode_access_token(token, secret=SECRET, issuer=ISS, audience=AUD)


def test_password_hash_is_argon2id_and_salted() -> None:
    first, second = hash_password("s3cret-passphrase"), hash_password("s3cret-passphrase")

    assert first.startswith("$argon2id$")
    assert first != second  # unique salt per hash
    assert "s3cret-passphrase" not in first
    assert verify_password("s3cret-passphrase", first)
    assert not verify_password("wrong-passphrase", first)
    assert not password_needs_rehash(first)


def test_verify_password_handles_unknown_user_and_garbage_hash() -> None:
    assert not verify_password("anything", None)
    assert not verify_password("anything", "not-a-hash")


def test_access_token_round_trip() -> None:
    user_id = uuid.uuid4()

    claims = decode(make_token(user_id=user_id, token_version=3))

    assert claims.user_id == user_id
    assert claims.token_version == 3


def test_expired_token_rejected() -> None:
    token = make_token(now=datetime.now(UTC) - timedelta(hours=1), ttl=timedelta(minutes=15))

    with pytest.raises(InvalidTokenError):
        decode(token)


@pytest.mark.parametrize(
    "overrides",
    [
        {"secret": "a-different-secret-0123456789abcdefghijkl"},
        {"issuer": "someone-else"},
        {"audience": "another-app"},
    ],
    ids=["wrong-secret", "wrong-issuer", "wrong-audience"],
)
def test_tokens_from_other_signers_or_audiences_rejected(overrides: dict) -> None:
    with pytest.raises(InvalidTokenError):
        decode(make_token(**overrides))


def test_unsigned_alg_none_token_rejected() -> None:
    now = datetime.now(UTC)
    forged = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "ver": 0,
            "type": "access",
            "iss": ISS,
            "aud": AUD,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        key=None,
        algorithm="none",
    )

    with pytest.raises(InvalidTokenError):
        decode(forged)


@pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")
def test_other_algorithm_with_same_secret_rejected() -> None:
    now = datetime.now(UTC)
    claims = {
        "sub": str(uuid.uuid4()),
        "ver": 0,
        "type": "access",
        "iss": ISS,
        "aud": AUD,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    with pytest.raises(InvalidTokenError):
        decode(jwt.encode(claims, SECRET, algorithm="HS512"))


def test_tampered_payload_rejected() -> None:
    header, payload, signature = make_token().split(".")
    tampered_payload = payload[:-2] + ("AA" if payload[-2:] != "AA" else "BB")

    with pytest.raises(InvalidTokenError):
        decode(f"{header}.{tampered_payload}.{signature}")


def test_non_access_token_type_rejected() -> None:
    now = datetime.now(UTC)
    claims = {
        "sub": str(uuid.uuid4()),
        "ver": 0,
        "type": "refresh",
        "iss": ISS,
        "aud": AUD,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    with pytest.raises(InvalidTokenError):
        decode(jwt.encode(claims, SECRET, algorithm="HS256"))


def test_random_tokens_are_unique_and_hashes_are_stable() -> None:
    tokens = {generate_token() for _ in range(1000)}

    assert len(tokens) == 1000
    assert all(len(token) >= 43 for token in tokens)  # 32 bytes, base64url
    sample = next(iter(tokens))
    assert hash_token(sample) == hash_token(sample)
    assert len(hash_token(sample)) == 64 and sample not in hash_token(sample)
