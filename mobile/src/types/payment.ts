import type { BookingStatus } from '@/types/booking';

export type PaymentStatus =
  | 'PENDING'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'CANCELLED'
  | 'REFUND_PENDING'
  | 'REFUNDED'
  | 'PARTIALLY_REFUNDED';

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
  /** Open this to pay; only set while the payment is PENDING. */
  checkout_url: string | null;
  paid_at: string | null;
  failure_reason: string | null;
  created_at: string;
  refunds: Refund[];
  booking_status: BookingStatus | null;
}

/** GET /api/v1/customers/me/payments */
export interface RenterPayment extends Payment {
  booking_reference: string;
  vehicle: string;
}
