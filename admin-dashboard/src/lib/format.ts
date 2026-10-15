/** Display helpers. Times are shown in South African time (UTC+2, no daylight saving). */
import type { BookingStatus, DeliveryStatus, PaymentStatus, SubmissionStatus, VehicleStatus } from './types';

const TIME_ZONE = 'Africa/Johannesburg';

/** "R 1 250.00" from a decimal string, without converting to a float. */
export function zar(amount: string): string {
  const match = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(amount.trim());
  if (!match) return amount;
  const [, sign, whole, fraction = ''] = match;
  return `${sign}R ${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ' ')}.${fraction.padEnd(2, '0')}`;
}

/** Exact decimal check for a rand amount typed by an administrator. */
export function isRandAmount(value: string, { allowZero = false } = {}): boolean {
  if (!/^\d{1,7}(\.\d{1,2})?$/.test(value.trim())) return false;
  return allowZero || Number(value) > 0;
}

/** Compares two rand amounts as cents (no float rounding surprises). */
export function cents(amount: string): number {
  const [whole, fraction = ''] = amount.trim().split('.');
  return Number(whole) * 100 + Number(fraction.padEnd(2, '0').slice(0, 2));
}

export function fromCents(value: number): string {
  return `${Math.floor(value / 100)}.${String(value % 100).padStart(2, '0')}`;
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Intl.DateTimeFormat('en-ZA', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: TIME_ZONE,
  }).format(new Date(iso));
}

export function dateOnly(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Intl.DateTimeFormat('en-ZA', { day: 'numeric', month: 'short', year: 'numeric', timeZone: TIME_ZONE }).format(
    new Date(iso.length === 10 ? `${iso}T12:00:00+02:00` : iso),
  );
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "2026-03" → "Mar 26". */
export function monthLabel(month: string): string {
  return `${MONTHS[Number(month.slice(5, 7)) - 1] ?? month} ${month.slice(2, 4)}`;
}

/** "2026-10-20T10:00" from a datetime-local input → ISO with the SA offset. */
export function saLocalToIso(local: string): string | null {
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(local) ? `${local}:00+02:00` : null;
}

export function humanise(code: string): string {
  return code.charAt(0) + code.slice(1).toLowerCase().replace(/_/g, ' ');
}

export type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';

export const VEHICLE_TONE: Record<VehicleStatus, Tone> = {
  DRAFT: 'neutral',
  PENDING_APPROVAL: 'warning',
  APPROVED: 'success',
  REJECTED: 'danger',
  SUSPENDED: 'danger',
  UNAVAILABLE: 'neutral',
};

export const BOOKING_TONE: Record<BookingStatus, Tone> = {
  PENDING_PAYMENT: 'warning',
  CONFIRMED: 'success',
  CANCELLED: 'neutral',
  EXPIRED: 'neutral',
  DELIVERY_SCHEDULED: 'info',
  IN_TRANSIT: 'info',
  DELIVERED: 'info',
  ACTIVE_RENTAL: 'success',
  RETURN_PENDING: 'info',
  COMPLETED: 'neutral',
};

export const PAYMENT_TONE: Record<PaymentStatus, Tone> = {
  PENDING: 'warning',
  SUCCEEDED: 'success',
  FAILED: 'danger',
  CANCELLED: 'neutral',
  REFUND_PENDING: 'info',
  REFUNDED: 'neutral',
  PARTIALLY_REFUNDED: 'info',
};

export const DELIVERY_TONE: Record<DeliveryStatus, Tone> = {
  PENDING_SCHEDULE: 'warning',
  SCHEDULED: 'info',
  EN_ROUTE: 'info',
  DELIVERED: 'success',
  FAILED: 'danger',
  CANCELLED: 'neutral',
};

export const SUBMISSION_TONE: Record<SubmissionStatus, Tone> = {
  PENDING: 'warning',
  APPROVED: 'success',
  REJECTED: 'danger',
  REQUIRES_MORE_INFORMATION: 'warning',
  SUPERSEDED: 'neutral',
};
