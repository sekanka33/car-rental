import type { BookingStatus } from '@/types/booking';
import type { DeliveryStatus } from '@/types/delivery';
import type { FuelType, Transmission } from '@/types/vehicle';

export type VehicleStatus = 'DRAFT' | 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED' | 'SUSPENDED' | 'UNAVAILABLE';
export type VehicleDocumentType = 'REGISTRATION_CERTIFICATE' | 'LICENCE_DISC' | 'INSURANCE' | 'ROADWORTHY_CERTIFICATE';

export const PROVINCES = [
  'Eastern Cape',
  'Free State',
  'Gauteng',
  'KwaZulu-Natal',
  'Limpopo',
  'Mpumalanga',
  'North West',
  'Northern Cape',
  'Western Cape',
] as const;

/** Fields an owner may set (never price or status). */
export interface VehicleInput {
  make: string;
  model: string;
  year: number;
  registration_number: string;
  vin: string;
  colour: string | null;
  transmission: Transmission;
  fuel_type: FuelType;
  seats: number;
  city: string;
  province: string;
  description: string | null;
}

export interface OwnerVehicle extends VehicleInput {
  id: string;
  status: VehicleStatus;
  rejection_reason: string | null;
  suspension_reason: string | null;
  submitted_at: string | null;
  approved_at: string | null;
  created_at: string;
  current_price: { daily_rate: string; delivery_fee: string; deposit_amount: string; currency: 'ZAR' } | null;
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
  compliance: { ok: boolean; missing: VehicleDocumentType[]; expired: VehicleDocumentType[] };
}

export interface AvailabilityBlock {
  id: string;
  start_at: string;
  end_at: string;
  reason: string | null;
}

export type OwnerBookingScope = 'upcoming' | 'active' | 'past' | 'all';

export interface OwnerBooking {
  id: string;
  reference: string;
  status: BookingStatus;
  vehicle: { id: string; make: string; model: string; year: number; registration_number: string };
  start_at: string;
  end_at: string;
  rental_days: number;
  total_amount: string;
  currency: 'ZAR';
  renter_first_name: string;
  delivery_id: string | null;
  delivery_status: DeliveryStatus | null;
  cancelled_at: string | null;
}

export interface MonthTotal {
  month: string; // YYYY-MM
  bookings: number;
  collected: string;
  refunded: string;
  net: string;
}

export interface Earnings {
  year: number;
  currency: 'ZAR';
  basis: string;
  collected: string;
  refunded: string;
  net: string;
  months: MonthTotal[];
  bookings: {
    booking_id: string;
    reference: string;
    status: BookingStatus;
    vehicle: string;
    start_at: string;
    end_at: string;
    collected: string;
    refunded: string;
    net: string;
  }[];
}

export interface OwnerDashboard {
  vehicles_by_status: Record<VehicleStatus, number>;
  upcoming_bookings: number;
  active_rentals: number;
  deliveries_to_do: number;
  returns_to_record: number;
  month_net: string;
  year_net: string;
  currency: 'ZAR';
  expiring_documents: {
    vehicle_id: string;
    vehicle: string;
    document_type: VehicleDocumentType;
    expiry_date: string;
    expired: boolean;
  }[];
  next_booking: OwnerBooking | null;
}
