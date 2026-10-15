import type { BookingStatus } from '@/types/booking';
import type { DeliveryStatus } from '@/types/delivery';

export interface TrackedLocation {
  latitude: number;
  longitude: number;
  accuracy_m: number | null;
  heading: number | null;
  speed_mps: number | null;
  recorded_at: string;
  received_at: string;
}

/** What the live socket sends (snapshot, status and location messages share this shape). */
export interface TrackingState {
  delivery_id: string;
  status: DeliveryStatus;
  booking_status: BookingStatus;
  scheduled_for: string | null;
  tracking_active: boolean;
  location: TrackedLocation | null;
  eta: { seconds: number; distance_m: number | null; computed_at: string; arrives_at: string } | null;
}

export interface LocationFix {
  latitude: number;
  longitude: number;
  accuracy_m: number | null;
  heading: number | null;
  speed_mps: number | null;
  recorded_at: string;
}
