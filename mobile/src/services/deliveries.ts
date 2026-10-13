import { ApiError, apiRequest } from '@/lib/api';
import type { Delivery } from '@/types/delivery';

const base = (bookingId: string) => `/api/v1/bookings/${encodeURIComponent(bookingId)}`;

/** The booking's delivery, or null before it exists (it is created when payment is confirmed). */
export async function getDelivery(bookingId: string): Promise<Delivery | null> {
  try {
    return await apiRequest<Delivery>('GET', `${base(bookingId)}/delivery`, { auth: true });
  } catch (error) {
    if (error instanceof ApiError && error.isNotFound) return null;
    throw error;
  }
}

/** Confirm the car was handed over (optionally noting anything you disagree with). */
export function acknowledgeHandover(bookingId: string, notes?: string): Promise<Delivery> {
  return apiRequest<Delivery>('POST', `${base(bookingId)}/delivery/acknowledge`, {
    body: notes ? { notes } : {},
    auth: true,
  });
}

export function requestReturn(bookingId: string): Promise<Delivery> {
  return apiRequest<Delivery>('POST', `${base(bookingId)}/return-request`, { auth: true });
}
