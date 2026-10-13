import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.enums import RoleName, UserStatus, VerificationStatus


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[RoleName] = mapped_column(str_enum(RoleName, "role_name"), unique=True)
    description: Mapped[str] = mapped_column(String(255))


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # Emails are unique regardless of letter case.
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
        CheckConstraint("email = btrim(email) AND email LIKE '%_@_%'", name="email_format"),
        CheckConstraint(
            "(status = 'SUSPENDED') = (suspended_at IS NOT NULL)", name="suspension_consistent"
        ),
    )

    email: Mapped[str] = mapped_column(String(320))
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    phone_number: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[UserStatus] = mapped_column(
        str_enum(UserStatus, "user_status"), default=UserStatus.ACTIVE, server_default="ACTIVE"
    )
    email_verified_at: Mapped[datetime | None]
    suspended_at: Mapped[datetime | None]
    suspension_reason: Mapped[str | None] = mapped_column(String(500))
    last_login_at: Mapped[datetime | None]
    # Incremented to invalidate every access token issued so far
    # (password reset, "log out everywhere", suspension).
    token_version: Mapped[int] = mapped_column(default=0, server_default="0")

    roles: Mapped[list[Role]] = relationship(
        secondary="user_roles",
        primaryjoin="User.id == UserRole.user_id",
        secondaryjoin="Role.id == UserRole.role_id",
        viewonly=True,
    )
    owner_profile: Mapped["OwnerProfile | None"] = relationship(back_populates="user")
    customer_profile: Mapped["CustomerProfile | None"] = relationship(back_populates="user")


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    assigned_at: Mapped[datetime] = mapped_column(server_default=func.now())
    assigned_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class OwnerProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "owner_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    business_name: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    province: Mapped[str | None] = mapped_column(String(50))

    user: Mapped[User] = relationship(back_populates="owner_profile")


class CustomerProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Renter eligibility data. Document storage and ID/licence numbers arrive in Stage 06."""

    __tablename__ = "customer_profiles"
    __table_args__ = (
        CheckConstraint("date_of_birth > DATE '1900-01-01'", name="date_of_birth_plausible"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    date_of_birth: Mapped[date | None]
    id_verification_status: Mapped[VerificationStatus] = mapped_column(
        str_enum(VerificationStatus, "id_verification_status"),
        default=VerificationStatus.NOT_SUBMITTED,
        server_default="NOT_SUBMITTED",
    )
    licence_verification_status: Mapped[VerificationStatus] = mapped_column(
        str_enum(VerificationStatus, "licence_verification_status"),
        default=VerificationStatus.NOT_SUBMITTED,
        server_default="NOT_SUBMITTED",
    )
    licence_expiry_date: Mapped[date | None]

    user: Mapped[User] = relationship(back_populates="customer_profile")
