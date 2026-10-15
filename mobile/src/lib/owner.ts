/** Small calculations behind the owner screens (kept out of the route files for testing). */
import { addDays, formatDateTime, saIso, saToday } from '@/lib/dates';
import { isIsoDate } from '@/lib/labels';

/** Whole days in South African time: from the start of `from` to the end of `to`. */
export function blockPeriod(from: string, to: string, today = saToday()): { start_at: string; end_at: string } | string {
  if (!isIsoDate(from) || !isIsoDate(to)) return 'Enter both dates as YYYY-MM-DD.';
  if (from < today) return 'The first day cannot be in the past.';
  if (to < from) return 'The last day must be on or after the first day.';
  return { start_at: saIso(from, 0), end_at: saIso(addDays(to, 1), 0) };
}

/** Height of each month's bar relative to the best month. Amounts are compared as cents. */
export function barShares(months: { net: string }[]): number[] {
  const cents = months.map((m) => Math.max(0, Math.round(Number(m.net) * 100)));
  const top = Math.max(...cents, 0);
  return cents.map((c) => (top === 0 ? 0 : c / top));
}

const HOUR_MS = 60 * 60 * 1000;
const SCHEDULE_OFFSETS_H = [0, 1, 2, 3, 24];

/**
 * Delivery times the owner can pick (BR-7.9): the rental start, or 1, 2, 3 or 24 hours before
 * it, leaving out times already past. `value` is an ISO timestamp for the API.
 */
export function scheduleChoices(rentalStartIso: string, now = Date.now()): { value: string; label: string }[] {
  const start = Date.parse(rentalStartIso);
  return SCHEDULE_OFFSETS_H.map((hours) => new Date(start - hours * HOUR_MS))
    .filter((time) => time.getTime() > now)
    .map((time) => {
      const hours = (start - time.getTime()) / HOUR_MS;
      const when = formatDateTime(time.toISOString());
      return {
        value: time.toISOString(),
        label: hours === 0 ? `At the start (${when})` : `${hours} h before (${when})`,
      };
    });
}
