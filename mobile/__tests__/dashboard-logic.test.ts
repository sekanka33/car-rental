import { ApiError } from '@/lib/api';
import { fieldErrors, formMessage } from '@/lib/form-errors';
import { isIsoDate, monthLabel } from '@/lib/labels';
import { barShares, blockPeriod, scheduleChoices } from '@/lib/owner';
import { groupRenterBookings } from '@/lib/renter';
import type { Booking, BookingStatus } from '@/types/booking';

describe('isIsoDate', () => {
  it('accepts real calendar dates only', () => {
    expect(isIsoDate('2026-02-28')).toBe(true);
    expect(isIsoDate('2028-02-29')).toBe(true);
    expect(isIsoDate('2026-02-29')).toBe(false);
    expect(isIsoDate('2026-13-01')).toBe(false);
    expect(isIsoDate('26-01-01')).toBe(false);
  });

  it('labels months', () => {
    expect(monthLabel('2026-03')).toBe('Mar');
  });
});

describe('blockPeriod', () => {
  it('covers whole South African days, last day included', () => {
    expect(blockPeriod('2026-11-02', '2026-11-03', '2026-10-15')).toEqual({
      start_at: '2026-11-02T00:00:00+02:00',
      end_at: '2026-11-04T00:00:00+02:00',
    });
  });

  it('rejects past, reversed and malformed dates', () => {
    expect(blockPeriod('2026-10-14', '2026-10-20', '2026-10-15')).toMatch(/past/);
    expect(blockPeriod('2026-10-20', '2026-10-19', '2026-10-15')).toMatch(/on or after/);
    expect(blockPeriod('20/10/2026', '2026-10-21', '2026-10-15')).toMatch(/YYYY-MM-DD/);
  });
});

describe('barShares', () => {
  it('scales months against the best one and never goes negative', () => {
    expect(barShares([{ net: '500.00' }, { net: '1000.00' }, { net: '-50.00' }])).toEqual([0.5, 1, 0]);
    expect(barShares([{ net: '0.00' }])).toEqual([0]);
  });
});

describe('scheduleChoices', () => {
  const start = '2026-10-20T08:00:00.000Z';

  it('offers the start and 1, 2, 3 and 24 hours before it', () => {
    const choices = scheduleChoices(start, Date.parse('2026-10-15T00:00:00Z'));
    expect(choices.map((c) => c.value)).toEqual([
      '2026-10-20T08:00:00.000Z',
      '2026-10-20T07:00:00.000Z',
      '2026-10-20T06:00:00.000Z',
      '2026-10-20T05:00:00.000Z',
      '2026-10-19T08:00:00.000Z',
    ]);
    expect(choices[0].label).toMatch(/^At the start/);
    expect(choices[4].label).toMatch(/^24 h before/);
  });

  it('leaves out times that have passed', () => {
    const choices = scheduleChoices(start, Date.parse('2026-10-20T06:30:00Z'));
    expect(choices.map((c) => c.value)).toEqual(['2026-10-20T08:00:00.000Z', '2026-10-20T07:00:00.000Z']);
  });
});

describe('groupRenterBookings', () => {
  const b = (id: string, status: BookingStatus, start: string) =>
    ({ id, status, start_at: start }) as unknown as Booking;

  it('puts each booking in one section and flags what needs doing', () => {
    const groups = groupRenterBookings([
      b('later', 'CONFIRMED', '2026-12-01T08:00:00Z'),
      b('hold', 'PENDING_PAYMENT', '2026-11-01T08:00:00Z'),
      b('handed', 'DELIVERED', '2026-10-14T08:00:00Z'),
      b('old', 'COMPLETED', '2026-01-01T08:00:00Z'),
      b('newer', 'CANCELLED', '2026-05-01T08:00:00Z'),
      b('gone', 'EXPIRED', '2026-04-01T08:00:00Z'),
    ]);
    expect(groups.toPay.map((x) => x.id)).toEqual(['hold']);
    expect(groups.toConfirm.map((x) => x.id)).toEqual(['handed']);
    expect(groups.current.map((x) => x.id)).toEqual(['handed']);
    expect(groups.upcoming.map((x) => x.id)).toEqual(['hold', 'later']);
    expect(groups.past.map((x) => x.id)).toEqual(['newer', 'gone', 'old']);
  });
});

describe('form errors', () => {
  it('maps backend validation details to fields', () => {
    const error = new ApiError('Request validation failed.', 422, 'validation_error', [
      { location: ['body', 'vin'], message: 'Value error, VIN must be 17 characters' },
      { location: ['body', 'year'], message: 'year must be between 1981 and 2027' },
    ]);
    expect(fieldErrors(error)).toEqual({ vin: 'VIN must be 17 characters', year: 'year must be between 1981 and 2027' });
    expect(formMessage(error)).toBe('Please correct the highlighted fields.');
  });

  it('uses the API message for other errors', () => {
    const error = new ApiError('This vehicle is already registered.', 409, 'vehicle_already_registered');
    expect(fieldErrors(error)).toEqual({});
    expect(formMessage(error)).toBe('This vehicle is already registered.');
    expect(formMessage(new Error('x'), 'Fallback')).toBe('Fallback');
  });
});
