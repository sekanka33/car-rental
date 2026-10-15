import { apiRequest } from '@/lib/api';
import type { Delivery } from '@/types/delivery';
import type { LocationFix } from '@/types/tracking';

/** What the delivery person sees (owner endpoints). */
export interface AssignedDelivery extends Delivery {
  vehicle: { make: string; model: string; year: number };
  registration_number: string;
  rental_start_at: string;
  rental_end_at: string;
  renter: { full_name: string; phone_number: string | null };
}

const BASE = '/api/v1/owners/me/deliveries';

export function listMyDeliveries(): Promise<AssignedDelivery[]> {
  return apiRequest<AssignedDelivery[]>('GET', BASE, { auth: true });
}

export function getMyDelivery(id: string): Promise<AssignedDelivery> {
  return apiRequest<AssignedDelivery>('GET', `${BASE}/${encodeURIComponent(id)}`, { auth: true });
}

export function startDelivery(id: string): Promise<AssignedDelivery> {
  return apiRequest<AssignedDelivery>('POST', `${BASE}/${encodeURIComponent(id)}/start`, { auth: true });
}

export function sendLocation(id: string, fix: LocationFix): Promise<void> {
  return apiRequest<void>('POST', `${BASE}/${encodeURIComponent(id)}/location`, { body: fix, auth: true });
}
