"""Password hashing, JWT access tokens and opaque random tokens.

- Passwords: Argon2id (argon2-cffi defaults = RFC 9106 low-memory profile).
- Access tokens: short-lived HS256 JWTs carrying only the user id and token version;
  roles and account status are always read from the database.
- Refresh / email / reset tokens: random 256-bit values; only SHA-256 hashes are stored.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_password_hasher = PasswordHasher()
# Verified against when an account does not exist, so the response time does not
# reveal whether an email address is registered.
_DUMMY_HASH = _password_hasher.hash(secrets.token_urlsafe(16))

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"  # noqa: S105 - token type label, not a secret


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-work check; pass None for unknown users."""
    try:
        return _password_hasher.verify(password_hash or _DUMMY_HASH, password) and (
            password_hash is not None
        )
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _password_hasher.check_needs_rehash(password_hash)


def generate_token() -> str:
    """URL-safe random token with 256 bits of entropy."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    token_version: int


class InvalidTokenError(Exception):
    pass


def create_access_token(
    *,
    user_id: uuid.UUID,
    token_version: int,
    secret: str,
    issuer: str,
    audience: str,
    ttl: timedelta,
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "ver": token_version,
        "type": ACCESS_TOKEN_TYPE,
        "iss": issuer,
        "aud": audience,
        "iat": issued_at,
        "exp": issued_at + ttl,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(
    token: str, *, secret: str, issuer: str, audience: str
) -> AccessTokenClaims:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],  # never accept "none" or other algorithms
            issuer=issuer,
            audience=audience,
            options={"require": ["sub", "exp", "iat", "iss", "aud", "ver", "type"]},
        )
        if payload["type"] != ACCESS_TOKEN_TYPE:
            raise InvalidTokenError("Wrong token type")
        return AccessTokenClaims(
            user_id=uuid.UUID(payload["sub"]), token_version=int(payload["ver"])
        )
    except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
        raise InvalidTokenError(str(exc)) from exc
