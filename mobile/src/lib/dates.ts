/**
 * Calendar helpers in South African time (Africa/Johannesburg, UTC+2 all year: South
 * Africa has no daylight saving). Dates are "YYYY-MM-DD" strings in SA time.
 */
const SA_OFFSET = '+02:00';
const TIME_ZONE = 'Africa/Johannesburg';

export function saToday(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now);
  const get = (type: string) => parts.find((p) => p.type === type)?.value;
  return `${get('year')}-${get('month')}-${get('day')}`;
}

export function addDays(date: string, days: number): string {
  const [y, m, d] = date.split('-').map(Number);
  const value = new Date(Date.UTC(y, m - 1, d + days));
  return value.toISOString().slice(0, 10);
}

/** ISO 8601 timestamp for a SA calendar date and hour, e.g. 2026-10-20T10:00:00+02:00. */
export function saIso(date: string, hour: number): string {
  return `${date}T${String(hour).padStart(2, '0')}:00:00${SA_OFFSET}`;
}

/** "Tue 20 Oct" for a SA calendar date. */
export function dayLabel(date: string): string {
  return new Intl.DateTimeFormat('en-ZA', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  }).format(new Date(`${date}T00:00:00Z`));
}

/** "20 Oct 2026, 10:00" in SA time. */
export function formatDateTime(iso: string): string {
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
