/** Display text and badge tones for owner-side statuses and codes. */
import type { BadgeTone } from '@/components/ui/badge';
import type { DeliveryException, DeliveryStatus, FuelLevel } from '@/types/delivery';
import type { VehicleDocumentType, VehicleStatus } from '@/types/owner';

export const VEHICLE_STATUS: Record<VehicleStatus, { label: string; tone: BadgeTone }> = {
  DRAFT: { label: 'Draft', tone: 'neutral' },
  PENDING_APPROVAL: { label: 'Under review', tone: 'info' },
  APPROVED: { label: 'Listed', tone: 'success' },
  REJECTED: { label: 'Rejected', tone: 'danger' },
  SUSPENDED: { label: 'Suspended', tone: 'danger' },
  UNAVAILABLE: { label: 'Hidden', tone: 'warning' },
};

export const DOCUMENT_TYPE: Record<VehicleDocumentType, string> = {
  REGISTRATION_CERTIFICATE: 'Registration certificate',
  LICENCE_DISC: 'Licence disc',
  INSURANCE: 'Proof of insurance',
  ROADWORTHY_CERTIFICATE: 'Roadworthy certificate',
};

/** These need an expiry date (the backend refuses them without one). */
export const EXPIRING_DOCUMENTS: VehicleDocumentType[] = ['LICENCE_DISC', 'INSURANCE'];

export const FUEL_LEVEL: Record<FuelLevel, string> = {
  EMPTY: 'Empty',
  QUARTER: '¼',
  HALF: '½',
  THREE_QUARTERS: '¾',
  FULL: 'Full',
};

export const DELIVERY_STATUS: Record<DeliveryStatus, string> = {
  PENDING_SCHEDULE: 'Time not confirmed',
  SCHEDULED: 'Scheduled',
  EN_ROUTE: 'On the way',
  DELIVERED: 'Delivered, awaiting return',
  FAILED: 'Stopped: support will contact you',
  CANCELLED: 'Cancelled',
};

export const PROBLEM_KIND: Record<DeliveryException['kind'], string> = {
  DELAY: 'Running late',
  RENTER_UNAVAILABLE: 'Renter not available',
  ADDRESS_PROBLEM: 'Address problem',
  VEHICLE_PROBLEM: 'Problem with the car',
  OTHER: 'Something else',
};

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "2026-03" → "Mar". */
export function monthLabel(month: string): string {
  return MONTHS[Number(month.slice(5, 7)) - 1] ?? month;
}

/** Strict YYYY-MM-DD that is a real calendar date. */
export function isIsoDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [y, m, d] = value.split('-').map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  return date.getUTCFullYear() === y && date.getUTCMonth() === m - 1 && date.getUTCDate() === d;
}
