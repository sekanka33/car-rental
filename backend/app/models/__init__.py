"""Import every model so Base.metadata is complete (used by Alembic and tests)."""

from app.models.audit_log import AuditLog
from app.models.auth_token import RefreshToken, UserActionToken
from app.models.booking import Booking
from app.models.delivery import Delivery
from app.models.payment import Payment
from app.models.user import CustomerProfile, OwnerProfile, Role, User, UserRole
from app.models.vehicle import Vehicle, VehicleImage, VehiclePrice

__all__ = [
    "AuditLog",
    "Booking",
    "CustomerProfile",
    "Delivery",
    "OwnerProfile",
    "Payment",
    "RefreshToken",
    "Role",
    "User",
    "UserActionToken",
    "UserRole",
    "Vehicle",
    "VehicleImage",
    "VehiclePrice",
]
