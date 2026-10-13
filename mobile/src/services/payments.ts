import { apiRequest } from '@/lib/api';
import type { Payment } from '@/types/payment';

/** Start (or resume) checkout. The backend charges the booking's stored total. */
export function startPayment(bookingId: string): Promise<Payment> {
  return apiRequest<Payment>('POST', `/api/v1/bookings/${encodeURIComponent(bookingId)}/payments`, {
    auth: true,
  });
}

export function listBookingPayments(bookingId: string): Promise<Payment[]> {
  return apiRequest<Payment[]>('GET', `/api/v1/bookings/${encodeURIComponent(bookingId)}/payments`, {
    auth: true,
  });
}

/** Ask the backend to verify the payment with the provider now (after checkout). */
export function refreshPayment(paymentId: string): Promise<Payment> {
  return apiRequest<Payment>('POST', `/api/v1/payments/${encodeURIComponent(paymentId)}/refresh`, {
    auth: true,
  });
}
