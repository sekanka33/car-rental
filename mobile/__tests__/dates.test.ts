import { addDays, dayLabel, saIso, saToday } from '@/lib/dates';

it('uses the South African calendar date', () => {
  // 23:30 UTC on 13 Oct is 01:30 on 14 Oct in Johannesburg.
  expect(saToday(new Date('2026-10-13T23:30:00Z'))).toBe('2026-10-14');
  expect(saToday(new Date('2026-10-13T21:59:00Z'))).toBe('2026-10-13');
});

it('adds days across month and year ends', () => {
  expect(addDays('2026-10-30', 3)).toBe('2026-11-02');
  expect(addDays('2026-12-31', 1)).toBe('2027-01-01');
  expect(addDays('2028-02-28', 1)).toBe('2028-02-29');
});

it('builds SA timestamps with a +02:00 offset', () => {
  expect(saIso('2026-10-20', 8)).toBe('2026-10-20T08:00:00+02:00');
  expect(new Date(saIso('2026-10-20', 8)).toISOString()).toBe('2026-10-20T06:00:00.000Z');
});

it('labels days', () => {
  expect(dayLabel('2026-10-20')).toMatch(/Tue.*20.*Oct/);
});
