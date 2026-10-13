import re
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.models.enums import RoleName, UserStatus

# Length limits follow NIST SP 800-63B: at least 8 characters, long passphrases allowed,
# capped to bound hashing cost.
Password = Annotated[str, Field(min_length=8, max_length=128)]
FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]
OpaqueToken = Annotated[str, Field(min_length=20, max_length=200)]

_SA_MOBILE = re.compile(r"^(?:0|\+27|27)([6-8]\d{8})$")


class RequestModel(BaseModel):
    """Request bodies reject unknown fields (e.g. a client trying to send `role`)."""

    model_config = ConfigDict(extra="forbid")


class RegisterRequest(RequestModel):
    email: EmailStr
    password: Password
    full_name: FullName
    phone_number: str | None = Field(default=None, description="South African mobile number")
    account_type: Literal["RENTER", "OWNER"]

    @field_validator("phone_number")
    @classmethod
    def normalise_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        match = _SA_MOBILE.match(re.sub(r"[\s-]", "", value))
        if not match:
            raise ValueError("must be a South African mobile number, e.g. 082 123 4567")
        return f"+27{match.group(1)}"

    @model_validator(mode="after")
    def password_differs_from_email(self) -> "RegisterRequest":
        if self.password.strip().lower() == str(self.email).lower():
            raise ValueError("password must not be the same as the email address")
        return self


class LoginRequest(RequestModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=128)]


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - OAuth token type label
    expires_in: int = Field(description="Access-token lifetime in seconds")


class RefreshRequest(RequestModel):
    refresh_token: OpaqueToken


class VerifyEmailRequest(RequestModel):
    token: OpaqueToken


class PasswordResetRequest(RequestModel):
    email: EmailStr


class PasswordResetConfirm(RequestModel):
    token: OpaqueToken
    new_password: Password


class MessageResponse(BaseModel):
    message: str


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    phone_number: str | None
    status: UserStatus
    roles: list[RoleName]
    email_verified: bool
    created_at: datetime

    @classmethod
    def from_user(cls, user) -> "UserResponse":
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            phone_number=user.phone_number,
            status=user.status,
            roles=sorted(role.name for role in user.roles),
            email_verified=user.email_verified_at is not None,
            created_at=user.created_at,
        )


class AdminUserResponse(UserResponse):
    suspended_at: datetime | None
    suspension_reason: str | None
    last_login_at: datetime | None

    @classmethod
    def from_user(cls, user) -> "AdminUserResponse":
        base = UserResponse.from_user(user).model_dump()
        return cls(
            **base,
            suspended_at=user.suspended_at,
            suspension_reason=user.suspension_reason,
            last_login_at=user.last_login_at,
        )


class UserListResponse(BaseModel):
    items: list[AdminUserResponse]
    total: int
    limit: int
    offset: int


class SuspendUserRequest(RequestModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class OwnerProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_name: str | None
    city: str | None
    province: str | None
