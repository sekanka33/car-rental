"""Registration, login, token rotation, email verification and password reset."""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, AuthenticationError, PermissionDeniedError
from app.core.security import (
    create_access_token,
    generate_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    verify_password,
)
from app.integrations.email import EmailMessage, EmailSender
from app.models import CustomerProfile, OwnerProfile, RefreshToken, User, UserActionToken
from app.models.enums import RoleName, UserActionTokenPurpose, UserStatus
from app.repositories import users as repo
from app.services.audit import record_audit

logger = logging.getLogger(__name__)

AccountType = Literal["RENTER", "OWNER"]


class EmailAlreadyRegisteredError(AppError):
    status_code = 409
    code = "email_already_registered"


class InvalidCredentialsError(AuthenticationError):
    code = "invalid_credentials"


class InvalidRefreshTokenError(AuthenticationError):
    code = "invalid_refresh_token"


class AccountSuspendedError(PermissionDeniedError):
    code = "account_suspended"


class AccountInactiveError(PermissionDeniedError):
    code = "account_inactive"


class InvalidActionTokenError(AppError):
    status_code = 400
    code = "invalid_or_expired_token"


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int  # access-token lifetime in seconds


def _now() -> datetime:
    return datetime.now(UTC)


def normalise_email(email: str) -> str:
    return email.strip().lower()


def ensure_can_sign_in(user: User) -> None:
    if user.status == UserStatus.SUSPENDED:
        raise AccountSuspendedError("This account is suspended. Contact support.")
    if user.status != UserStatus.ACTIVE:
        raise AccountInactiveError("This account is not active.")


# --- registration ---------------------------------------------------------------


def register_user(
    session: Session,
    settings: Settings,
    sender: EmailSender,
    *,
    email: str,
    password: str,
    full_name: str,
    phone_number: str | None,
    account_type: AccountType,
) -> User:
    """Create a renter or owner account. Administrators cannot self-register."""
    email = normalise_email(email)
    if repo.email_exists(session, email):
        raise EmailAlreadyRegisteredError("An account with this email already exists.")

    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        phone_number=phone_number,
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError as exc:  # concurrent registration with the same email
        session.rollback()
        raise EmailAlreadyRegisteredError("An account with this email already exists.") from exc

    role = RoleName.OWNER if account_type == "OWNER" else RoleName.RENTER
    repo.assign_role(session, user, role)
    session.add(
        OwnerProfile(user_id=user.id)
        if role == RoleName.OWNER
        else CustomerProfile(user_id=user.id)
    )
    token = _issue_action_token(session, settings, user, UserActionTokenPurpose.EMAIL_VERIFICATION)
    session.commit()

    _send(sender, _verification_email(settings, user, token))
    return user


# --- login and tokens ------------------------------------------------------------


def login(
    session: Session,
    settings: Settings,
    *,
    email: str,
    password: str,
    user_agent: str | None = None,
) -> TokenPair:
    user = repo.get_user_by_email(session, normalise_email(email))
    # verify_password does the same work for unknown users (timing-safe).
    if not verify_password(password, user.password_hash if user else None) or user is None:
        raise InvalidCredentialsError("Invalid email or password.")
    ensure_can_sign_in(user)

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = _now()
    pair = _issue_token_pair(session, settings, user, family_id=uuid.uuid4(), user_agent=user_agent)
    session.commit()
    return pair


def refresh(
    session: Session, settings: Settings, *, refresh_token: str, user_agent: str | None = None
) -> TokenPair:
    """Rotate a refresh token. Re-use of a rotated token revokes the whole family."""
    now = _now()
    stored = repo.get_refresh_token_by_hash(session, hash_token(refresh_token))
    if stored is None:
        raise InvalidRefreshTokenError("Invalid refresh token.")
    if stored.revoked_at is not None:
        # A rotated/revoked token was presented again: assume it was stolen.
        repo.revoke_refresh_family(session, stored.family_id, now)
        session.commit()
        logger.warning("Refresh token reuse detected for user %s; family revoked", stored.user_id)
        raise InvalidRefreshTokenError("Invalid refresh token.")
    if stored.expires_at <= now:
        raise InvalidRefreshTokenError("Refresh token has expired.")

    user = repo.get_user(session, stored.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        repo.revoke_refresh_family(session, stored.family_id, now)
        session.commit()
        raise InvalidRefreshTokenError("Invalid refresh token.")

    pair, new_token = _issue_token_pair(
        session, settings, user, family_id=stored.family_id, user_agent=user_agent, return_row=True
    )
    stored.revoked_at = now
    stored.replaced_by_id = new_token.id
    session.commit()
    return pair


def logout(session: Session, *, refresh_token: str) -> None:
    """Revoke the session (refresh-token family). Idempotent; unknown tokens are ignored."""
    stored = repo.get_refresh_token_by_hash(session, hash_token(refresh_token))
    if stored is not None:
        repo.revoke_refresh_family(session, stored.family_id, _now())
        session.commit()


def logout_everywhere(session: Session, user: User) -> None:
    """Revoke every refresh token and invalidate all access tokens already issued."""
    repo.revoke_all_refresh_tokens(session, user.id, _now())
    user.token_version += 1
    session.commit()


def _issue_token_pair(
    session: Session,
    settings: Settings,
    user: User,
    *,
    family_id: uuid.UUID,
    user_agent: str | None,
    return_row: bool = False,
):
    raw_refresh = generate_token()
    now = _now()
    row = RefreshToken(
        user_id=user.id,
        family_id=family_id,
        token_hash=hash_token(raw_refresh),
        created_at=now,
        expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
        user_agent=(user_agent or "")[:255] or None,
    )
    session.add(row)
    session.flush()
    access_ttl = timedelta(minutes=settings.access_token_ttl_minutes)
    pair = TokenPair(
        access_token=create_access_token(
            user_id=user.id,
            token_version=user.token_version,
            secret=settings.jwt_secret_key.get_secret_value(),
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            ttl=access_ttl,
            now=now,
        ),
        refresh_token=raw_refresh,
        expires_in=int(access_ttl.total_seconds()),
    )
    return (pair, row) if return_row else pair


# --- email verification ----------------------------------------------------------


def verify_email(session: Session, *, token: str) -> User:
    action = _consume_action_token(session, token, UserActionTokenPurpose.EMAIL_VERIFICATION)
    user = repo.get_user(session, action.user_id)
    if user.email_verified_at is None:
        user.email_verified_at = _now()
    session.commit()
    return user


def resend_verification_email(
    session: Session, settings: Settings, sender: EmailSender, user: User
) -> None:
    if user.email_verified_at is not None:
        return
    token = _issue_action_token(session, settings, user, UserActionTokenPurpose.EMAIL_VERIFICATION)
    session.commit()
    _send(sender, _verification_email(settings, user, token))


# --- password reset ----------------------------------------------------------------


def request_password_reset(
    session: Session, settings: Settings, sender: EmailSender, *, email: str
) -> None:
    """Always succeeds from the caller's point of view (no account enumeration)."""
    user = repo.get_user_by_email(session, normalise_email(email))
    if user is None or user.status == UserStatus.DEACTIVATED:
        return
    token = _issue_action_token(session, settings, user, UserActionTokenPurpose.PASSWORD_RESET)
    session.commit()
    link = f"{settings.app_link_base_url}reset-password?token={token}"
    _send(
        sender,
        EmailMessage(
            to=user.email,
            subject="Reset your password",
            body=(
                f"Hi {user.full_name},\n\n"
                "Someone asked to reset the password for your account. If this was you, "
                f"open this link within {settings.password_reset_ttl_minutes} minutes:\n\n"
                f"{link}\n\n"
                "If you did not ask for this, you can ignore this email."
            ),
        ),
    )


def reset_password(session: Session, *, token: str, new_password: str) -> None:
    action = _consume_action_token(session, token, UserActionTokenPurpose.PASSWORD_RESET)
    user = repo.get_user(session, action.user_id)
    now = _now()
    user.password_hash = hash_password(new_password)
    user.token_version += 1  # existing access tokens stop working
    if user.email_verified_at is None:
        user.email_verified_at = now  # the user just proved control of the inbox
    repo.revoke_all_refresh_tokens(session, user.id, now)
    record_audit(
        session,
        actor_id=user.id,
        action="user.password_reset",
        entity_type="user",
        entity_id=user.id,
    )
    session.commit()


# --- helpers ---------------------------------------------------------------------------


def _issue_action_token(
    session: Session, settings: Settings, user: User, purpose: UserActionTokenPurpose
) -> str:
    now = _now()
    repo.invalidate_action_tokens(session, user.id, purpose, now)
    ttl = (
        timedelta(hours=settings.email_verification_ttl_hours)
        if purpose == UserActionTokenPurpose.EMAIL_VERIFICATION
        else timedelta(minutes=settings.password_reset_ttl_minutes)
    )
    raw = generate_token()
    session.add(
        UserActionToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_token(raw),
            created_at=now,
            expires_at=now + ttl,
        )
    )
    session.flush()
    return raw


def _consume_action_token(
    session: Session, token: str, purpose: UserActionTokenPurpose
) -> UserActionToken:
    action = repo.get_action_token_by_hash(session, hash_token(token), purpose)
    now = _now()
    if action is None or action.used_at is not None or action.expires_at <= now:
        raise InvalidActionTokenError("This link is invalid or has expired.")
    action.used_at = now
    return action


def _verification_email(settings: Settings, user: User, token: str) -> EmailMessage:
    link = f"{settings.app_link_base_url}verify-email?token={token}"
    return EmailMessage(
        to=user.email,
        subject="Confirm your email address",
        body=(
            f"Hi {user.full_name},\n\n"
            f"Please confirm your email address within {settings.email_verification_ttl_hours} "
            f"hours:\n\n{link}\n"
        ),
    )


def _send(sender: EmailSender, message: EmailMessage) -> None:
    """Email failures never undo committed account changes; users can request a resend."""
    try:
        sender.send(message)
    except Exception:
        logger.exception("Failed to send email '%s'", message.subject)
