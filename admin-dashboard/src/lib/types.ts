/** Response shapes of the admin API (backend `app/schemas`). Money is a decimal string. */

export type Role = 'ADMIN' | 'OWNER' | 'RENTER';
export type UserStatus = 'ACTIVE' | 'SUSPENDED' | 'DEACTIVATED';
export type VehicleStatus = 'DRAFT' | 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED' | 'SUSPENDED' | 'UNAVAILABLE';
export type BookingStatus =
  | 'PENDING_PAYMENT'
  | 'CONFIRMED'
  | 'CANCELLED'
  | 'EXPIRED'
  | 'DELIVERY_SCHEDULED'
  | 'IN_TRANSIT'
  | 'DELIVERED'
  | 'ACTIVE_RENTAL'
  | 'RETURN_PENDING'
  | 'COMPLETED';
export type PaymentStatus =
  | 'PENDING'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'CANCELLED'
  | 'REFUND_PENDING'
  | 'REFUNDED'
  | 'PARTIALLY_REFUNDED';
export type DeliveryStatus = 'PENDING_SCHEDULE' | 'SCHEDULED' | 'EN_ROUTE' | 'DELIVERED' | 'FAILED' | 'CANCELLED';
export type SubmissionStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'REQUIRES_MORE_INFORMATION' | 'SUPERSEDED';
export type VehicleDocumentType = 'REGISTRATION_CERTIFICATE' | 'LICENCE_DISC' | 'INSURANCE' | 'ROADWORTHY_CERTIFICATE';

export interface AdminUser {
  id: string;
  email: string;
  full_name: string;
  phone_number: string | null;
  status: UserStatus;
  roles: Role[];
  email_verified: boolean;
  created_at: string;
  suspended_at: string | null;
  suspension_reason: string | null;
  last_login_at: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Submission {
  id: string;
  document_type: 'SA_ID' | 'DRIVING_LICENCE';
  status: SubmissionStatus;
  document_number_masked: string;
  licence_expiry_date: string | null;
  licence_codes: string | null;
  review_note: string | null;
  submitted_at: string;
  reviewed_at: string | null;
  files: { id: string; side: 'FRONT' | 'BACK'; content_type: string; size_bytes: number }[];
  submitter: { id: string; full_name: string; email: string; date_of_birth: string | null };
  reviewed_by_id: string | null;
}

export interface Price {
  id: string;
  daily_rate: string;
  delivery_fee: string;
  deposit_amount: string;
  currency: 'ZAR';
  effective_from: string;
}

export interface OfficialPrice extends Price {
  change_reason: string | null;
  created_by_id: string;
  created_at: string;
  is_current: boolean;
}

export interface AdminVehicle {
  id: string;
  make: string;
  model: string;
  year: number;
  registration_number: string;
  vin: string;
  colour: string | null;
  transmission: 'AUTOMATIC' | 'MANUAL';
  fuel_type: 'PETROL' | 'DIESEL' | 'HYBRID' | 'ELECTRIC';
  seats: number;
  city: string;
  province: string;
  description: string | null;
  status: VehicleStatus;
  rejection_reason: string | null;
  suspension_reason: string | null;
  submitted_at: string | null;
  approved_at: string | null;
  created_at: string;
  current_price: Price | null;
  photos: { id: string; content_type: string; size_bytes: number; sort_order: number }[];
  documents: {
    id: string;
    document_type: VehicleDocumentType;
    expiry_date: string | null;
    content_type: string;
    size_bytes: number;
    uploaded_at: string;
    is_current: boolean;
  }[];
  compliance: { ok: boolean; missing: string[]; expired: string[] };
  owner: { user_id: string; full_name: string; email: string; business_name: string | null };
  approved_by_id: string | null;
}

export interface Quote {
  rental_days: number;
  daily_rate: string;
  rental_amount: string;
  delivery_fee: string;
  deposit_amount: string;
  total_amount: string;
}

export interface AdminBooking {
  id: string;
  reference: string;
  status: BookingStatus;
  vehicle: { id: string; make: string; model: string; year: number; city: string; province: string };
  start_at: string;
  end_at: string;
  hold_expires_at: string | null;
  price: {
    daily_rate: string;
    rental_days: number;
    rental_amount: string;
    delivery_fee: string;
    deposit_amount: string;
    total_amount: string;
    currency: 'ZAR';
  };
  delivery_address: string | null;
  created_at: string;
  confirmed_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  renter: { id: string; full_name: string; email: string };
  owner_user_id: string;
  cancelled_by_id: string | null;
}

export interface Refund {
  id: string;
  amount: string;
  currency: 'ZAR';
  status: 'PENDING' | 'PROCESSED' | 'FAILED';
  reason: string;
  created_at: string;
  processed_at: string | null;
}

export interface Payment {
  id: string;
  booking_id: string;
  reference: string;
  provider: string;
  status: PaymentStatus;
  amount: string;
  currency: 'ZAR';
  paid_at: string | null;
  failure_reason: string | null;
  created_at: string;
  refunds: Refund[];
  booking_status: BookingStatus | null;
}

export interface HandoverRecord {
  kind: 'HANDOVER' | 'RETURN';
  recorded_at: string;
  odometer_km: number;
  fuel_level: 'EMPTY' | 'QUARTER' | 'HALF' | 'THREE_QUARTERS' | 'FULL';
  condition_notes: string | null;
  renter_acknowledged_at: string | null;
  renter_notes: string | null;
  photos: { id: string; url: string; content_type: string; created_at: string }[];
}

export interface DeliveryIssue {
  id: string;
  kind: 'DELAY' | 'RENTER_UNAVAILABLE' | 'ADDRESS_PROBLEM' | 'VEHICLE_PROBLEM' | 'OTHER';
  notes: string;
  created_at: string;
  resolved_at: string | null;
  resolution: string | null;
}

export interface AdminDelivery {
  id: string;
  booking_id: string;
  booking_reference: string;
  booking_status: BookingStatus;
  status: DeliveryStatus;
  scheduled_for: string | null;
  dropoff_address: string;
  started_at: string | null;
  delivered_at: string | null;
  delivery_person_first_name: string | null;
  handover: HandoverRecord | null;
  return_record: HandoverRecord | null;
  exceptions: DeliveryIssue[];
  vehicle: { make: string; model: string; year: number };
  registration_number: string;
  rental_start_at: string;
  rental_end_at: string;
  renter: { full_name: string; phone_number: string | null };
  assigned_to_id: string | null;
  renter_id: string;
  has_open_exception: boolean;
}

export interface Overview {
  verifications_pending: number;
  vehicles_pending_approval: number;
  deliveries_needing_attention: number;
  refunds_pending: number;
  refunds_failed: number;
  bookings_upcoming: number;
  bookings_under_way: number;
  users_by_role: Record<Role, number>;
  users_suspended: number;
  vehicles_by_status: Record<VehicleStatus, number>;
  bookings_by_status: Record<BookingStatus, number>;
  month: string;
  month_collected: string;
  month_refunded: string;
  currency: 'ZAR';
}

export interface MonthRow {
  month: string;
  bookings_confirmed: number;
  collected: string;
  refunded: string;
  net: string;
  new_renters: number;
  new_owners: number;
}

export interface AuditEntry {
  id: number;
  created_at: string;
  action: string;
  entity_type: string;
  entity_id: string;
  actor: { id: string; full_name: string; email: string } | null;
  changes: Record<string, unknown> | null;
}
