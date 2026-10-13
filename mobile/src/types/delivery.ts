import type { BookingStatus } from '@/types/booking';

export type DeliveryStatus = 'PENDING_SCHEDULE' | 'SCHEDULED' | 'EN_ROUTE' | 'DELIVERED' | 'FAILED' | 'CANCELLED';
export type FuelLevel = 'EMPTY' | 'QUARTER' | 'HALF' | 'THREE_QUARTERS' | 'FULL';

export interface HandoverRecord {
  kind: 'HANDOVER' | 'RETURN';
  recorded_at: string;
  odometer_km: number;
  fuel_level: FuelLevel;
  condition_notes: string | null;
  renter_acknowledged_at: string | null;
  renter_notes: string | null;
  photos: { id: string; url: string; content_type: string; created_at: string }[];
}

export interface DeliveryException {
  id: string;
  kind: 'DELAY' | 'RENTER_UNAVAILABLE' | 'ADDRESS_PROBLEM' | 'VEHICLE_PROBLEM' | 'OTHER';
  notes: string;
  created_at: string;
  resolved_at: string | null;
  resolution: string | null;
}

export interface Delivery {
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
  exceptions: DeliveryException[];
}
