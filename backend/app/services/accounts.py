"""Administrator account management: suspension, reactivation, admin creation."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.core.security import hash_password
from app.models import User
from app.models.enums import RoleName, UserStatus
from app.repositories import users as repo
from app.services.audit import record_audit
from app.services.auth import EmailAlreadyRegisteredError, normalise_email


class InvalidAccountStateError(AppError):
    status_code = 409
    code = "invalid_account_state"


class CannotModifySelfError(AppError):
    status_code = 400
    code = "cannot_modify_self"


def _get_target(session: Session, user_id: uuid.UUID) -> User:
    user = repo.get_user(session, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    return user


def suspend_user(session: Session, *, actor: User, user_id: uuid.UUID, reason: str) -> User:
    if actor.id == user_id:
        raise CannotModifySelfError("You cannot suspend your own account.")
    user = _get_target(session, user_id)
    if user.status != UserStatus.ACTIVE:
        raise InvalidAccountStateError(f"Only active accounts can be suspended (is {user.status}).")
    now = datetime.now(UTC)
    user.status = UserStatus.SUSPENDED
    user.suspended_at = now
    user.suspension_reason = reason
    user.token_version += 1
    repo.revoke_all_refresh_tokens(session, user.id, now)
    record_audit(
        session,
        actor_id=actor.id,
        action="user.suspended",
        entity_type="user",
        entity_id=user.id,
        changes={"status": {"from": "ACTIVE", "to": "SUSPENDED"}, "reason": reason},
    )
    session.commit()
    return user


def reactivate_user(session: Session, *, actor: User, user_id: uuid.UUID) -> User:
    user = _get_target(session, user_id)
    if user.status != UserStatus.SUSPENDED:
        raise InvalidAccountStateError("Only suspended accounts can be reactivated.")
    user.status = UserStatus.ACTIVE
    user.suspended_at = None
    user.suspension_reason = None
    record_audit(
        session,
        actor_id=actor.id,
        action="user.reactivated",
        entity_type="user",
        entity_id=user.id,
        changes={"status": {"from": "SUSPENDED", "to": "ACTIVE"}},
    )
    session.commit()
    return user


def create_admin(session: Session, *, email: str, full_name: str, password: str) -> User:
    """Create an administrator. Only reachable from the operator CLI, never over HTTP."""
    email = normalise_email(email)
    if repo.email_exists(session, email):
        raise EmailAlreadyRegisteredError("An account with this email already exists.")
    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        email_verified_at=datetime.now(UTC),
    )
    session.add(user)
    session.flush()
    repo.assign_role(session, user, RoleName.ADMIN)
    record_audit(
        session,
        actor_id=None,
        action="admin.created",
        entity_type="user",
        entity_id=user.id,
        changes={"email": email, "via": "cli"},
    )
    session.commit()
    return user
