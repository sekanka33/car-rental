"""Domain enumerations stored in the database (as VARCHAR + CHECK constraints)."""

from enum import StrEnum


class RoleName(StrEnum):
    ADMIN = "ADMIN"
    OWNER = "OWNER"
    RENTER = "RENTER"


class UserActionTokenPurpose(StrEnum):
    EMAIL_VERIFICATION = "EMAIL_VERIFICATION"
    PASSWORD_RESET = "PASSWORD_RESET"  # noqa: S105 - enum label, not a secret


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DEACTIVATED = "DEACTIVATED"


class VerificationStatus(StrEnum):
    NOT_SUBMITTED = "NOT_SUBMITTED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REQUIRES_MORE_INFORMATION = "REQUIRES_MORE_INFORMATION"


class VehicleStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUSPENDED = "SUSPENDED"
    UNAVAILABLE = "UNAVAILABLE"


class Transmission(StrEnum):
    AUTOMATIC = "AUTOMATIC"
    MANUAL = "MANUAL"


class FuelType(StrEnum):
    PETROL = "PETROL"
    DIESEL = "DIESEL"
    HYBRID = "HYBRID"
    ELECTRIC = "ELECTRIC"


class BookingStatus(StrEnum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    DELIVERY_SCHEDULED = "DELIVERY_SCHEDULED"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    ACTIVE_RENTAL = "ACTIVE_RENTAL"
    RETURN_PENDING = "RETURN_PENDING"
    COMPLETED = "COMPLETED"


# Bookings in these states reserve the vehicle; the database rejects overlaps among them.
BLOCKING_BOOKING_STATUSES: tuple[BookingStatus, ...] = (
    BookingStatus.PENDING_PAYMENT,
    BookingStatus.CONFIRMED,
    BookingStatus.DELIVERY_SCHEDULED,
    BookingStatus.IN_TRANSIT,
    BookingStatus.DELIVERED,
    BookingStatus.ACTIVE_RENTAL,
    BookingStatus.RETURN_PENDING,
)


class PaymentStatus(StrEnum):
    PENDING = "PENDING"  # created; customer has not completed checkout (or result unknown)
    SUCCEEDED = "SUCCEEDED"  # verified with the provider and applied to the booking
    FAILED = "FAILED"  # declined, abandoned, or rejected (e.g. amount mismatch)
    CANCELLED = "CANCELLED"
    REFUND_PENDING = (
        "REFUND_PENDING"  # money received but being returned (late/duplicate/cancelled)
    )
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"


class RefundStatus(StrEnum):
    PENDING = "PENDING"  # requested; provider still processing
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class DeliveryStatus(StrEnum):
    PENDING_SCHEDULE = "PENDING_SCHEDULE"  # created on payment; delivery person sets the time
    SCHEDULED = "SCHEDULED"
    EN_ROUTE = "EN_ROUTE"
    DELIVERED = "DELIVERED"  # handover recorded
    FAILED = "FAILED"  # an exception stopped the delivery; an administrator resolves it
    CANCELLED = "CANCELLED"


class DeliveryExceptionKind(StrEnum):
    DELAY = "DELAY"  # informational: the delivery continues
    RENTER_UNAVAILABLE = "RENTER_UNAVAILABLE"
    ADDRESS_PROBLEM = "ADDRESS_PROBLEM"
    VEHICLE_PROBLEM = "VEHICLE_PROBLEM"
    OTHER = "OTHER"


class HandoverKind(StrEnum):
    HANDOVER = "HANDOVER"  # vehicle given to the renter
    RETURN = "RETURN"  # vehicle collected back from the renter


class FuelLevel(StrEnum):
    EMPTY = "EMPTY"
    QUARTER = "QUARTER"
    HALF = "HALF"
    THREE_QUARTERS = "THREE_QUARTERS"
    FULL = "FULL"


class DocumentType(StrEnum):
    SA_ID = "SA_ID"
    DRIVING_LICENCE = "DRIVING_LICENCE"


class DocumentSide(StrEnum):
    FRONT = "FRONT"
    BACK = "BACK"


class SubmissionStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REQUIRES_MORE_INFORMATION = "REQUIRES_MORE_INFORMATION"
    SUPERSEDED = "SUPERSEDED"  # replaced by a newer submission of the same type


class VehicleDocumentType(StrEnum):
    REGISTRATION_CERTIFICATE = "REGISTRATION_CERTIFICATE"  # NaTIS RC1 / proof of ownership
    LICENCE_DISC = "LICENCE_DISC"
    INSURANCE = "INSURANCE"
    ROADWORTHY_CERTIFICATE = "ROADWORTHY_CERTIFICATE"


# Documents an owner must provide before a vehicle can be submitted, and which of them expire.
REQUIRED_VEHICLE_DOCUMENTS: tuple[VehicleDocumentType, ...] = (
    VehicleDocumentType.REGISTRATION_CERTIFICATE,
    VehicleDocumentType.LICENCE_DISC,
    VehicleDocumentType.INSURANCE,
)
EXPIRING_VEHICLE_DOCUMENTS: tuple[VehicleDocumentType, ...] = (
    VehicleDocumentType.LICENCE_DISC,
    VehicleDocumentType.INSURANCE,
)


class Province(StrEnum):
    EASTERN_CAPE = "Eastern Cape"
    FREE_STATE = "Free State"
    GAUTENG = "Gauteng"
    KWAZULU_NATAL = "KwaZulu-Natal"
    LIMPOPO = "Limpopo"
    MPUMALANGA = "Mpumalanga"
    NORTH_WEST = "North West"
    NORTHERN_CAPE = "Northern Cape"
    WESTERN_CAPE = "Western Cape"
