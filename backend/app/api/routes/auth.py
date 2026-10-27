from typing import Annotated

from fastapi import APIRouter, Header, Request, status

from app.api.deps import AppSettings, CurrentUser, DbSession, EmailSenderDep
from app.core.rate_limits import enforce_request_limit
from app.schemas.auth import (
    LoginRequest,
    MessageResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
    VerifyEmailRequest,
)
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

UserAgent = Annotated[str | None, Header()]


def _tokens(pair: auth_service.TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=pair.access_token, refresh_token=pair.refresh_token, expires_in=pair.expires_in
    )


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
def register(
    body: RegisterRequest,
    session: DbSession,
    settings: AppSettings,
    sender: EmailSenderDep,
    request: Request,
) -> UserResponse:
    """Create a renter or owner account and send an email-verification link."""
    enforce_request_limit(request, "register", settings.auth_registration_requests_per_hour, 3600)
    user = auth_service.register_user(
        session,
        settings,
        sender,
        email=str(body.email),
        password=body.password,
        full_name=body.full_name,
        phone_number=body.phone_number,
        account_type=body.account_type,
    )
    session.refresh(user)
    return UserResponse.from_user(user)


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    session: DbSession,
    settings: AppSettings,
    request: Request,
    user_agent: UserAgent = None,
) -> TokenResponse:
    enforce_request_limit(request, "login", settings.auth_login_requests_per_minute, 60)
    return _tokens(
        auth_service.login(
            session, settings, email=str(body.email), password=body.password, user_agent=user_agent
        )
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    body: RefreshRequest, session: DbSession, settings: AppSettings, user_agent: UserAgent = None
) -> TokenResponse:
    """Exchange a refresh token for a new token pair (the old refresh token stops working)."""
    return _tokens(
        auth_service.refresh(
            session, settings, refresh_token=body.refresh_token, user_agent=user_agent
        )
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: RefreshRequest, session: DbSession) -> None:
    """End this session. Access tokens already issued expire within their short lifetime."""
    auth_service.logout(session, refresh_token=body.refresh_token)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(user: CurrentUser, session: DbSession) -> None:
    """End every session of the current user, including access tokens already issued."""
    auth_service.logout_everywhere(session, user)


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(body: VerifyEmailRequest, session: DbSession) -> MessageResponse:
    auth_service.verify_email(session, token=body.token)
    return MessageResponse(message="Email address confirmed.")


@router.post(
    "/verify-email/resend", status_code=status.HTTP_202_ACCEPTED, response_model=MessageResponse
)
def resend_verification(
    user: CurrentUser, session: DbSession, settings: AppSettings, sender: EmailSenderDep
) -> MessageResponse:
    auth_service.resend_verification_email(session, settings, sender, user)
    return MessageResponse(message="If your email is not yet confirmed, a new link has been sent.")


@router.post(
    "/password-reset/request",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MessageResponse,
)
def request_password_reset(
    body: PasswordResetRequest,
    session: DbSession,
    settings: AppSettings,
    sender: EmailSenderDep,
    request: Request,
) -> MessageResponse:
    """Always returns the same response, whether or not the email is registered."""
    enforce_request_limit(
        request, "password-reset", settings.password_reset_requests_per_hour, 3600
    )
    auth_service.request_password_reset(session, settings, sender, email=str(body.email))
    return MessageResponse(
        message="If an account exists for this email, a password reset link has been sent."
    )


@router.post("/password-reset/confirm", response_model=MessageResponse)
def confirm_password_reset(body: PasswordResetConfirm, session: DbSession) -> MessageResponse:
    """Set a new password. All sessions of the account are signed out."""
    auth_service.reset_password(session, token=body.token, new_password=body.new_password)
    return MessageResponse(message="Your password has been changed. Please log in again.")
