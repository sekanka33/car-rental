"""Owner vehicle registration, photos, documents, availability, and administrator review."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Select, and_, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.errors import AppError, NotFoundError, PermissionDeniedError
from app.integrations.storage import DocumentStorage
from app.models import (
    Booking,
    OwnerProfile,
    User,
    Vehicle,
    VehicleAvailabilityBlock,
    VehicleDocument,
    VehicleImage,
    VehiclePrice,
)
from app.models.enums import (
    BLOCKING_BOOKING_STATUSES,
    EXPIRING_VEHICLE_DOCUMENTS,
    REQUIRED_VEHICLE_DOCUMENTS,
    UserStatus,
    VehicleDocumentType,
    VehicleStatus,
)
from app.services import notify_events
from app.services.audit import record_audit
from app.services.uploads import DOCUMENT_TYPES, PHOTO_TYPES, InvalidUploadError, check_upload
from app.services.verification import today_in_south_africa

MIN_PHOTOS_TO_SUBMIT = 3
MAX_PHOTOS = 12

# Changing any of these on a vehicle that was already reviewed sends it back for review.
MATERIAL_FIELDS = frozenset(
    {"make", "model", "year", "registration_number", "vin", "transmission", "fuel_type", "seats"}
)
EDITABLE_STATUSES = frozenset(
    {VehicleStatus.DRAFT, VehicleStatus.REJECTED, VehicleStatus.APPROVED, VehicleStatus.UNAVAILABLE}
)
REVIEWED_STATUSES = frozenset({VehicleStatus.APPROVED, VehicleStatus.UNAVAILABLE})


class VehicleStateError(AppError):
    status_code = 409
    code = "invalid_vehicle_state"


class VehicleNotReadyError(AppError):
    status_code = 409
    code = "vehicle_not_ready"

    def __init__(self, message: str, missing: list[str]) -> None:
        super().__init__(f"{message} Missing: {', '.join(missing)}.")
        self.missing = missing


class DuplicateVehicleError(AppError):
    status_code = 409
    code = "vehicle_already_registered"


class AvailabilityConflictError(AppError):
    status_code = 409
    code = "availability_conflict"


@dataclass(frozen=True)
class Compliance:
    """Which required documents are missing or expired (latest document of each type)."""

    missing: list[str] = field(default_factory=list)
    expired: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing and not self.expired


def _now() -> datetime:
    return datetime.now(UTC)


# --- lookups ------------------------------------------------------------------------------


def get_owner_profile(session: Session, user: User) -> OwnerProfile:
    profile = session.scalar(select(OwnerProfile).where(OwnerProfile.user_id == user.id))
    if profile is None:
        raise NotFoundError("Owner profile not found.")
    return profile


def _vehicle_query() -> Select:
    # populate_existing: always reload the vehicle and its collections from the database,
    # even if this session already holds an older copy (prevents stale photo/document lists).
    return (
        select(Vehicle)
        .options(
            selectinload(Vehicle.images),
            selectinload(Vehicle.documents),
            selectinload(Vehicle.prices),
            selectinload(Vehicle.owner).selectinload(OwnerProfile.user),
        )
        .execution_options(populate_existing=True)
    )


def get_vehicle(session: Session, vehicle_id: uuid.UUID, *, for_update: bool = False) -> Vehicle:
    query = _vehicle_query().where(Vehicle.id == vehicle_id)
    if for_update:
        query = query.with_for_update(of=Vehicle)
    vehicle = session.scalar(query)
    if vehicle is None:
        raise NotFoundError("Vehicle not found.")
    return vehicle


def get_owned_vehicle(
    session: Session, user: User, vehicle_id: uuid.UUID, *, for_update: bool = False
) -> Vehicle:
    """The vehicle if it belongs to this owner; otherwise 404 (existence is not revealed)."""
    vehicle = get_vehicle(session, vehicle_id, for_update=for_update)
    if vehicle.owner.user_id != user.id:
        raise NotFoundError("Vehicle not found.")
    return vehicle


def list_owned_vehicles(session: Session, user: User) -> list[Vehicle]:
    owner = get_owner_profile(session, user)
    return list(
        session.scalars(
            _vehicle_query().where(Vehicle.owner_id == owner.id).order_by(Vehicle.created_at.desc())
        )
    )


def current_documents(vehicle: Vehicle) -> dict[VehicleDocumentType, VehicleDocument]:
    latest: dict[VehicleDocumentType, VehicleDocument] = {}
    for document in sorted(vehicle.documents, key=lambda d: d.created_at):
        latest[document.document_type] = document
    return latest


def compliance(vehicle: Vehicle, on: date | None = None) -> Compliance:
    on = on or today_in_south_africa()
    docs = current_documents(vehicle)
    missing = [t.value for t in REQUIRED_VEHICLE_DOCUMENTS if t not in docs]
    expired = [
        t.value
        for t in EXPIRING_VEHICLE_DOCUMENTS
        if t in docs and (docs[t].expiry_date is None or docs[t].expiry_date <= on)
    ]
    return Compliance(missing=missing, expired=expired)


# --- owner profile --------------------------------------------------------------------------


def update_owner_profile(session: Session, user: User, **changes: Any) -> OwnerProfile:
    profile = get_owner_profile(session, user)
    for name, value in changes.items():
        setattr(profile, name, value)
    session.commit()
    return profile


# --- registration and editing -----------------------------------------------------------------


def create_vehicle(session: Session, user: User, **fields: Any) -> Vehicle:
    owner = get_owner_profile(session, user)
    vehicle = Vehicle(owner_id=owner.id, status=VehicleStatus.DRAFT, **fields)
    session.add(vehicle)
    _flush_unique(session)
    session.commit()
    return get_vehicle(session, vehicle.id)


def update_vehicle(session: Session, user: User, vehicle_id: uuid.UUID, **changes: Any) -> Vehicle:
    vehicle = get_owned_vehicle(session, user, vehicle_id, for_update=True)
    if vehicle.status not in EDITABLE_STATUSES:
        raise VehicleStateError(
            f"A vehicle cannot be edited while it is {vehicle.status} "
            "(withdraw it from review first, or contact support if suspended)."
        )
    changed = {k: v for k, v in changes.items() if getattr(vehicle, k) != v}
    for name, value in changed.items():
        setattr(vehicle, name, value)
    if vehicle.status in REVIEWED_STATUSES and MATERIAL_FIELDS & changed.keys():
        _send_back_for_review(session, user, vehicle, sorted(MATERIAL_FIELDS & changed.keys()))
    _flush_unique(session)
    session.commit()
    return get_vehicle(session, vehicle.id)


def delete_vehicle(
    session: Session, storage: DocumentStorage, user: User, vehicle_id: uuid.UUID
) -> None:
    vehicle = get_owned_vehicle(session, user, vehicle_id, for_update=True)
    if vehicle.status not in (VehicleStatus.DRAFT, VehicleStatus.REJECTED):
        raise VehicleStateError("Only draft or rejected vehicles can be deleted.")
    keys = [i.storage_key for i in vehicle.images] + [d.storage_key for d in vehicle.documents]
    session.delete(vehicle)
    try:
        session.commit()
    except IntegrityError as exc:  # referenced by bookings or prices
        session.rollback()
        raise VehicleStateError("This vehicle has history and cannot be deleted.") from exc
    for key in keys:
        storage.delete(key)


def _flush_unique(session: Session) -> None:
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", "") or ""
        if "registration_number" in constraint or "vin" in constraint:
            raise DuplicateVehicleError(
                "A vehicle with this registration number or VIN is already registered."
            ) from exc
        raise


def _send_back_for_review(
    session: Session, user: User, vehicle: Vehicle, fields: list[str]
) -> None:
    previous = vehicle.status
    vehicle.status = VehicleStatus.PENDING_APPROVAL
    vehicle.submitted_at = _now()
    vehicle.approved_at = None
    vehicle.approved_by_id = None
    record_audit(
        session,
        actor_id=user.id,
        action="vehicle.resubmitted_after_change",
        entity_type="vehicle",
        entity_id=vehicle.id,
        changes={"status": {"from": previous, "to": "PENDING_APPROVAL"}, "fields": fields},
    )


# --- photos and documents ------------------------------------------------------------------------


def add_photo(
    session: Session,
    settings: Settings,
    storage: DocumentStorage,
    user: User,
    vehicle_id: uuid.UUID,
    data: bytes,
) -> VehicleImage:
    vehicle = get_owned_vehicle(session, user, vehicle_id, for_update=True)
    if vehicle.status == VehicleStatus.SUSPENDED:
        raise VehicleStateError("Photos cannot be changed while the vehicle is suspended.")
    if len(vehicle.images) >= MAX_PHOTOS:
        raise VehicleStateError(f"A vehicle can have at most {MAX_PHOTOS} photos.")
    upload = check_upload(data, allowed=PHOTO_TYPES, max_bytes=settings.max_document_bytes)
    next_order = max((i.sort_order for i in vehicle.images), default=-1) + 1
    key = storage.save(upload.data)
    image = VehicleImage(
        vehicle_id=vehicle.id,
        storage_key=key,
        content_type=upload.content_type,
        size_bytes=upload.size_bytes,
        sha256=upload.sha256,
        sort_order=next_order,
    )
    vehicle.images.append(image)  # keep the loaded collection in step with the database
    try:
        session.commit()
    except Exception:
        session.rollback()
        storage.delete(key)
        raise
    return image


def delete_photo(
    session: Session,
    storage: DocumentStorage,
    user: User,
    vehicle_id: uuid.UUID,
    photo_id: uuid.UUID,
) -> None:
    vehicle = get_owned_vehicle(session, user, vehicle_id, for_update=True)
    image = next((i for i in vehicle.images if i.id == photo_id), None)
    if image is None:
        raise NotFoundError("Photo not found.")
    if vehicle.status in REVIEWED_STATUSES and len(vehicle.images) <= MIN_PHOTOS_TO_SUBMIT:
        raise VehicleStateError(
            f"A listed vehicle must keep at least {MIN_PHOTOS_TO_SUBMIT} photos."
        )
    key = image.storage_key
    session.delete(image)
    session.commit()
    storage.delete(key)


def add_document(
    session: Session,
    settings: Settings,
    storage: DocumentStorage,
    user: User,
    vehicle_id: uuid.UUID,
    *,
    document_type: VehicleDocumentType,
    expiry_date: date | None,
    data: bytes,
) -> VehicleDocument:
    vehicle = get_owned_vehicle(session, user, vehicle_id, for_update=True)
    if vehicle.status == VehicleStatus.SUSPENDED:
        raise VehicleStateError("Documents cannot be changed while the vehicle is suspended.")
    if document_type in EXPIRING_VEHICLE_DOCUMENTS:
        if expiry_date is None or expiry_date <= today_in_south_africa():
            raise InvalidUploadError(f"{document_type.value} needs a future expiry date.")
    upload = check_upload(data, allowed=DOCUMENT_TYPES, max_bytes=settings.max_document_bytes)
    key = storage.save(upload.data)
    document = VehicleDocument(
        vehicle_id=vehicle.id,
        document_type=document_type,
        expiry_date=expiry_date,
        storage_key=key,
        content_type=upload.content_type,
        size_bytes=upload.size_bytes,
        sha256=upload.sha256,
        uploaded_by_id=user.id,
        created_at=_now(),
    )
    vehicle.documents.append(document)  # keep the loaded collection in step with the database
    # A new proof of ownership changes who the vehicle legally belongs to: review again.
    if (
        document_type == VehicleDocumentType.REGISTRATION_CERTIFICATE
        and vehicle.status in REVIEWED_STATUSES
    ):
        _send_back_for_review(session, user, vehicle, ["registration_certificate"])
    try:
        session.commit()
    except Exception:
        session.rollback()
        storage.delete(key)
        raise
    return document


def read_vehicle_file(
    session: Session,
    storage: DocumentStorage,
    *,
    viewer: User,
    vehicle_id: uuid.UUID,
    file_id: uuid.UUID,
    kind: str,
    as_admin: bool,
) -> tuple[str, bytes]:
    """Return (content_type, bytes) of a photo or document. Admin document views are audited."""
    vehicle = (
        get_vehicle(session, vehicle_id)
        if as_admin
        else get_owned_vehicle(session, viewer, vehicle_id)
    )
    items = vehicle.images if kind == "photo" else vehicle.documents
    item = next((i for i in items if i.id == file_id), None)
    if item is None:
        raise NotFoundError("File not found.")
    data = storage.read(item.storage_key)
    if as_admin and kind == "document":
        record_audit(
            session,
            actor_id=viewer.id,
            action="vehicle.document_viewed",
            entity_type="vehicle",
            entity_id=vehicle.id,
            changes={"document_id": str(item.id), "document_type": item.document_type.value},
        )
        session.commit()
    return item.content_type, data


# --- owner workflow ------------------------------------------------------------------------------


def submit_for_review(session: Session, user: User, vehicle_id: uuid.UUID) -> Vehicle:
    vehicle = get_owned_vehicle(session, user, vehicle_id, for_update=True)
    if vehicle.status not in (VehicleStatus.DRAFT, VehicleStatus.REJECTED):
        raise VehicleStateError(
            f"Only draft or rejected vehicles can be submitted (is {vehicle.status})."
        )
    missing: list[str] = []
    if user.email_verified_at is None:
        missing.append("verified email address")
    if len(vehicle.images) < MIN_PHOTOS_TO_SUBMIT:
        missing.append(f"at least {MIN_PHOTOS_TO_SUBMIT} photos")
    status = compliance(vehicle)
    missing += [f"{doc} document" for doc in status.missing]
    missing += [f"valid (unexpired) {doc}" for doc in status.expired]
    if missing:
        raise VehicleNotReadyError("The vehicle is not ready for review.", missing)
    previous = vehicle.status
    vehicle.status = VehicleStatus.PENDING_APPROVAL
    vehicle.submitted_at = _now()
    vehicle.rejection_reason = None
    record_audit(
        session,
        actor_id=user.id,
        action="vehicle.submitted",
        entity_type="vehicle",
        entity_id=vehicle.id,
        changes={"status": {"from": previous, "to": "PENDING_APPROVAL"}},
    )
    session.commit()
    return get_vehicle(session, vehicle.id)


def withdraw_from_review(session: Session, user: User, vehicle_id: uuid.UUID) -> Vehicle:
    vehicle = get_owned_vehicle(session, user, vehicle_id, for_update=True)
    if vehicle.status != VehicleStatus.PENDING_APPROVAL:
        raise VehicleStateError("Only vehicles awaiting review can be withdrawn.")
    vehicle.status = VehicleStatus.DRAFT
    vehicle.submitted_at = None
    session.commit()
    return get_vehicle(session, vehicle.id)


def set_listing_availability(
    session: Session, user: User, vehicle_id: uuid.UUID, *, available: bool
) -> Vehicle:
    """Owner switch between APPROVED (listed) and UNAVAILABLE (hidden). Bookings are kept."""
    vehicle = get_owned_vehicle(session, user, vehicle_id, for_update=True)
    target = VehicleStatus.APPROVED if available else VehicleStatus.UNAVAILABLE
    if vehicle.status not in REVIEWED_STATUSES:
        raise VehicleStateError("Only approved vehicles can be listed or unlisted.")
    if vehicle.status != target:
        record_audit(
            session,
            actor_id=user.id,
            action="vehicle.listing_changed",
            entity_type="vehicle",
            entity_id=vehicle.id,
            changes={"status": {"from": vehicle.status, "to": target}},
        )
        vehicle.status = target
    session.commit()
    return get_vehicle(session, vehicle.id)


# --- availability blocks -------------------------------------------------------------------------


def _overlapping_booking_exists(
    session: Session, vehicle_id: uuid.UUID, start: datetime, end: datetime
) -> bool:
    return session.scalar(
        select(
            exists().where(
                Booking.vehicle_id == vehicle_id,
                Booking.status.in_(BLOCKING_BOOKING_STATUSES),
                # Unpaid holds past their deadline no longer reserve dates.
                or_(Booking.status != "PENDING_PAYMENT", Booking.hold_expires_at > _now()),
                Booking.start_at < end,
                Booking.end_at > start,
            )
        )
    )


def add_availability_block(
    session: Session,
    user: User,
    vehicle_id: uuid.UUID,
    *,
    start_at: datetime,
    end_at: datetime,
    reason: str | None,
) -> VehicleAvailabilityBlock:
    vehicle = get_owned_vehicle(session, user, vehicle_id, for_update=True)
    if end_at <= start_at:
        raise AvailabilityConflictError("end_at must be after start_at.")
    if end_at <= _now():
        raise AvailabilityConflictError("The blocked period must end in the future.")
    if _overlapping_booking_exists(session, vehicle.id, start_at, end_at):
        raise AvailabilityConflictError(
            "This period overlaps an existing booking. Contact support to change a booked period."
        )
    block = VehicleAvailabilityBlock(
        vehicle_id=vehicle.id,
        start_at=start_at,
        end_at=end_at,
        reason=reason,
        created_by_id=user.id,
    )
    session.add(block)
    session.commit()
    return block


def list_availability_blocks(
    session: Session, user: User, vehicle_id: uuid.UUID
) -> list[VehicleAvailabilityBlock]:
    vehicle = get_owned_vehicle(session, user, vehicle_id)
    return list(
        session.scalars(
            select(VehicleAvailabilityBlock)
            .where(
                VehicleAvailabilityBlock.vehicle_id == vehicle.id,
                VehicleAvailabilityBlock.end_at > _now(),
            )
            .order_by(VehicleAvailabilityBlock.start_at)
        )
    )


def delete_availability_block(
    session: Session, user: User, vehicle_id: uuid.UUID, block_id: uuid.UUID
) -> None:
    vehicle = get_owned_vehicle(session, user, vehicle_id, for_update=True)
    block = session.get(VehicleAvailabilityBlock, block_id)
    if block is None or block.vehicle_id != vehicle.id:
        raise NotFoundError("Availability block not found.")
    session.delete(block)
    session.commit()


# --- administrator review ------------------------------------------------------------------------


def list_for_review(
    session: Session, *, status: VehicleStatus | None, limit: int, offset: int
) -> list[Vehicle]:
    query = _vehicle_query().order_by(
        func.coalesce(Vehicle.submitted_at, Vehicle.created_at), Vehicle.id
    )
    if status is not None:
        query = query.where(Vehicle.status == status)
    return list(session.scalars(query.limit(limit).offset(offset)))


def _reviewable(session: Session, reviewer: User, vehicle_id: uuid.UUID) -> Vehicle:
    vehicle = get_vehicle(session, vehicle_id, for_update=True)
    if vehicle.owner.user_id == reviewer.id:
        raise PermissionDeniedError("You cannot review your own vehicle.")
    if vehicle.status != VehicleStatus.PENDING_APPROVAL:
        raise VehicleStateError(
            f"Only vehicles awaiting review can be decided (is {vehicle.status})."
        )
    return vehicle


def approve_vehicle(session: Session, *, reviewer: User, vehicle_id: uuid.UUID) -> Vehicle:
    vehicle = _reviewable(session, reviewer, vehicle_id)
    status = compliance(vehicle)
    if not status.ok:
        raise VehicleNotReadyError(
            "Cannot approve a vehicle without valid documents.", status.missing + status.expired
        )
    if vehicle.owner.user.status != UserStatus.ACTIVE:
        raise VehicleStateError("The owner's account is not active.")
    vehicle.status = VehicleStatus.APPROVED
    vehicle.approved_at = _now()
    vehicle.approved_by_id = reviewer.id
    vehicle.rejection_reason = None
    record_audit(
        session,
        actor_id=reviewer.id,
        action="vehicle.approved",
        entity_type="vehicle",
        entity_id=vehicle.id,
        changes={"status": {"from": "PENDING_APPROVAL", "to": "APPROVED"}},
    )
    notify_events.vehicle_reviewed(session, vehicle, "approved", None)
    session.commit()
    return get_vehicle(session, vehicle.id)


def reject_vehicle(
    session: Session, *, reviewer: User, vehicle_id: uuid.UUID, reason: str
) -> Vehicle:
    vehicle = _reviewable(session, reviewer, vehicle_id)
    vehicle.status = VehicleStatus.REJECTED
    vehicle.rejection_reason = reason
    record_audit(
        session,
        actor_id=reviewer.id,
        action="vehicle.rejected",
        entity_type="vehicle",
        entity_id=vehicle.id,
        changes={"status": {"from": "PENDING_APPROVAL", "to": "REJECTED"}, "reason": reason},
    )
    notify_events.vehicle_reviewed(session, vehicle, "rejected", reason)
    session.commit()
    return get_vehicle(session, vehicle.id)


def suspend_vehicle(
    session: Session, *, admin: User, vehicle_id: uuid.UUID, reason: str
) -> Vehicle:
    """Take a vehicle off the marketplace. Existing bookings are not cancelled automatically."""
    vehicle = get_vehicle(session, vehicle_id, for_update=True)
    if vehicle.status in (VehicleStatus.SUSPENDED, VehicleStatus.DRAFT, VehicleStatus.REJECTED):
        raise VehicleStateError(f"A {vehicle.status} vehicle cannot be suspended.")
    previous = vehicle.status
    vehicle.status = VehicleStatus.SUSPENDED
    vehicle.suspended_at = _now()
    vehicle.suspension_reason = reason
    record_audit(
        session,
        actor_id=admin.id,
        action="vehicle.suspended",
        entity_type="vehicle",
        entity_id=vehicle.id,
        changes={"status": {"from": previous, "to": "SUSPENDED"}, "reason": reason},
    )
    notify_events.vehicle_reviewed(session, vehicle, "suspended", reason)
    session.commit()
    return get_vehicle(session, vehicle.id)


def reinstate_vehicle(session: Session, *, admin: User, vehicle_id: uuid.UUID) -> Vehicle:
    """Lift a suspension: previously approved vehicles return to APPROVED, others to DRAFT."""
    vehicle = get_vehicle(session, vehicle_id, for_update=True)
    if vehicle.status != VehicleStatus.SUSPENDED:
        raise VehicleStateError("Only suspended vehicles can be reinstated.")
    target = VehicleStatus.APPROVED if vehicle.approved_at is not None else VehicleStatus.DRAFT
    vehicle.status = target
    vehicle.suspended_at = None
    vehicle.suspension_reason = None
    record_audit(
        session,
        actor_id=admin.id,
        action="vehicle.reinstated",
        entity_type="vehicle",
        entity_id=vehicle.id,
        changes={"status": {"from": "SUSPENDED", "to": target}},
    )
    notify_events.vehicle_reviewed(session, vehicle, "reinstated", None)
    session.commit()
    return get_vehicle(session, vehicle.id)


# --- public visibility ---------------------------------------------------------------------------


def publicly_listed_vehicles() -> Select:
    """The only vehicles the marketplace may show or book (used from Stage 09).

    APPROVED, owner account ACTIVE, current licence disc and insurance not expired, and an
    official price already in effect.
    """
    today = today_in_south_africa()
    now = _now()

    def valid(doc_type: VehicleDocumentType):
        return exists().where(
            VehicleDocument.vehicle_id == Vehicle.id,
            VehicleDocument.document_type == doc_type,
            VehicleDocument.expiry_date > today,
            VehicleDocument.created_at
            == select(func.max(VehicleDocument.created_at))
            .where(
                VehicleDocument.vehicle_id == Vehicle.id,
                VehicleDocument.document_type == doc_type,
            )
            .correlate(Vehicle)
            .scalar_subquery(),
        )

    return (
        select(Vehicle)
        .join(OwnerProfile, OwnerProfile.id == Vehicle.owner_id)
        .join(User, User.id == OwnerProfile.user_id)
        .where(
            and_(
                Vehicle.status == VehicleStatus.APPROVED,
                User.status == UserStatus.ACTIVE,
                *(valid(t) for t in EXPIRING_VEHICLE_DOCUMENTS),
                exists().where(
                    VehiclePrice.vehicle_id == Vehicle.id, VehiclePrice.effective_from <= now
                ),
            )
        )
    )
