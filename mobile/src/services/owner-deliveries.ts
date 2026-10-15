import { apiRequest } from '@/lib/api';
import { appendFile, type PickedFile } from '@/lib/upload';
import type { Delivery, DeliveryException, FuelLevel } from '@/types/delivery';
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

/** Omit `scheduledFor` to deliver at the rental start. */
export function scheduleDelivery(id: string, scheduledFor?: string): Promise<AssignedDelivery> {
  return apiRequest<AssignedDelivery>('POST', `${BASE}/${encodeURIComponent(id)}/schedule`, {
    auth: true,
    body: scheduledFor ? { scheduled_for: scheduledFor } : {},
  });
}

export interface ConditionRecord {
  odometer_km: number;
  fuel_level: FuelLevel;
  condition_notes: string | null;
}

export function recordHandover(id: string, record: ConditionRecord): Promise<AssignedDelivery> {
  return apiRequest<AssignedDelivery>('POST', `${BASE}/${encodeURIComponent(id)}/handover`, { auth: true, body: record });
}

export function recordReturn(id: string, record: ConditionRecord): Promise<AssignedDelivery> {
  return apiRequest<AssignedDelivery>('POST', `${BASE}/${encodeURIComponent(id)}/return`, { auth: true, body: record });
}

export function reportProblem(id: string, kind: DeliveryException['kind'], notes: string): Promise<AssignedDelivery> {
  return apiRequest<AssignedDelivery>('POST', `${BASE}/${encodeURIComponent(id)}/exceptions`, {
    auth: true,
    body: { kind, notes },
  });
}

export async function uploadRecordPhoto(id: string, kind: 'HANDOVER' | 'RETURN', file: PickedFile): Promise<void> {
  const form = new FormData();
  await appendFile(form, 'photo', file);
  await apiRequest('POST', `${BASE}/${encodeURIComponent(id)}/records/${kind}/photos`, {
    auth: true,
    form,
    timeoutMs: 60_000,
  });
}
