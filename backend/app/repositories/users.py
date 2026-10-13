"""Database queries for users, roles and authentication tokens."""

import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.models import RefreshToken, Role, User, UserActionToken, UserRole
from app.models.enums import RoleName, UserActionTokenPurpose


def get_user(session: Session, user_id: uuid.UUID) -> User | None:
    return session.scalar(select(User).options(selectinload(User.roles)).where(User.id == user_id))


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.scalar(
        select(User)
        .options(selectinload(User.roles))
        .where(func.lower(User.email) == email.strip().lower())
    )


def email_exists(session: Session, email: str) -> bool:
    return (
        session.scalar(
            select(func.count()).select_from(User).where(func.lower(User.email) == email.lower())
        )
        > 0
    )


def get_role(session: Session, name: RoleName) -> Role:
    return session.scalars(select(Role).where(Role.name == name)).one()


def assign_role(
    session: Session, user: User, name: RoleName, assigned_by: uuid.UUID | None = None
) -> None:
    session.add(
        UserRole(user_id=user.id, role_id=get_role(session, name).id, assigned_by_id=assigned_by)
    )


def list_users(session: Session, *, limit: int, offset: int) -> tuple[list[User], int]:
    total = session.scalar(select(func.count()).select_from(User)) or 0
    users = session.scalars(
        select(User)
        .options(selectinload(User.roles))
        .order_by(User.created_at.desc(), User.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(users), total


def get_refresh_token_by_hash(session: Session, token_hash: str) -> RefreshToken | None:
    return session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
    )


def revoke_refresh_family(session: Session, family_id: uuid.UUID, now: datetime) -> None:
    session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def revoke_all_refresh_tokens(session: Session, user_id: uuid.UUID, now: datetime) -> None:
    session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def get_action_token_by_hash(
    session: Session, token_hash: str, purpose: UserActionTokenPurpose
) -> UserActionToken | None:
    return session.scalar(
        select(UserActionToken)
        .where(UserActionToken.token_hash == token_hash, UserActionToken.purpose == purpose)
        .with_for_update()
    )


def invalidate_action_tokens(
    session: Session, user_id: uuid.UUID, purpose: UserActionTokenPurpose, now: datetime
) -> None:
    """Mark all unused tokens of a purpose as used (only the newest link should work)."""
    session.execute(
        update(UserActionToken)
        .where(
            UserActionToken.user_id == user_id,
            UserActionToken.purpose == purpose,
            UserActionToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
