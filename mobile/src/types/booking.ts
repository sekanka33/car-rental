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

export interface PriceBreakdown {
  daily_rate: string;
  rental_days: number;
  rental_amount: string;
  delivery_fee: string;
  deposit_amount: string;
  total_amount: string;
  currency: 'ZAR';
}

export interface Booking {
  id: string;
  reference: string;
  status: BookingStatus;
  vehicle: {
    id: string;
    make: string;
    model: string;
    year: number;
    city: string;
    province: string;
    primary_photo_url: string | null;
  };
  start_at: string;
  end_at: string;
  hold_expires_at: string | null;
  price: PriceBreakdown;
  delivery_address: string | null;
  created_at: string;
  confirmed_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
}

export interface Quote extends Omit<PriceBreakdown, 'currency'> {
  available: boolean;
  currency: 'ZAR';
}

export interface CreateBookingInput {
  vehicle_id: string;
  start_at: string;
  end_at: string;
  delivery_address: string;
}
