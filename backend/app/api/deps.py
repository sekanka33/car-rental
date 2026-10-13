"""Shared route dependencies: database session, current user, role checks."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_app_settings
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_db
from app.integrations.email import EmailSender
from app.integrations.payments import PaymentProvider
from app.integrations.storage import DocumentStorage
from app.models import User
from app.models.enums import RoleName
from app.repositories import users as repo
from app.services.auth import ensure_can_sign_in

_bearer = HTTPBearer(auto_error=False, description="Access token from /auth/login")

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]


def get_email_sender(request: Request) -> EmailSender:
    return request.app.state.email_sender


EmailSenderDep = Annotated[EmailSender, Depends(get_email_sender)]


def get_document_storage(request: Request) -> DocumentStorage:
    return request.app.state.document_storage


DocumentStorageDep = Annotated[DocumentStorage, Depends(get_document_storage)]


def get_payment_provider(request: Request) -> PaymentProvider | None:
    return request.app.state.payment_provider


PaymentProviderDep = Annotated[PaymentProvider | None, Depends(get_payment_provider)]


def get_current_user(
    session: DbSession,
    settings: AppSettings,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Authenticate the bearer token. Status and roles come from the database every time."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("Not authenticated.")
    try:
        claims = decode_access_token(
            credentials.credentials,
            secret=settings.jwt_secret_key.get_secret_value(),
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    except InvalidTokenError as exc:
        raise AuthenticationError("Invalid or expired access token.") from exc

    user = repo.get_user(session, claims.user_id)
    if user is None or user.token_version != claims.token_version:
        raise AuthenticationError("Invalid or expired access token.")
    ensure_can_sign_in(user)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*allowed: RoleName) -> Callable[[User], User]:
    """Dependency factory: the current user must hold at least one of `allowed`."""

    def _check(user: CurrentUser) -> User:
        if not {role.name for role in user.roles} & set(allowed):
            raise PermissionDeniedError("You do not have permission to perform this action.")
        return user

    return _check


AdminUser = Annotated[User, Depends(require_roles(RoleName.ADMIN))]
OwnerUser = Annotated[User, Depends(require_roles(RoleName.OWNER))]
RenterUser = Annotated[User, Depends(require_roles(RoleName.RENTER))]
