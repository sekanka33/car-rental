import { apiGet, apiRequest } from '@/lib/api';
import type { Booking, CreateBookingInput, Quote } from '@/types/booking';

export function getQuote(vehicleId: string, startAt: string, endAt: string): Promise<Quote> {
  return apiGet<Quote>(`/api/v1/vehicles/${encodeURIComponent(vehicleId)}/quote`, {
    start_at: startAt,
    end_at: endAt,
  });
}

export function createBooking(input: CreateBookingInput): Promise<Booking> {
  return apiRequest<Booking>('POST', '/api/v1/bookings', { body: input, auth: true });
}

export function listMyBookings(): Promise<Booking[]> {
  return apiRequest<Booking[]>('GET', '/api/v1/bookings', { auth: true });
}

export function getBooking(id: string): Promise<Booking> {
  return apiRequest<Booking>('GET', `/api/v1/bookings/${encodeURIComponent(id)}`, { auth: true });
}

export function cancelBooking(id: string, reason?: string): Promise<Booking> {
  return apiRequest<Booking>('POST', `/api/v1/bookings/${encodeURIComponent(id)}/cancel`, {
    body: reason ? { reason } : {},
    auth: true,
  });
}
