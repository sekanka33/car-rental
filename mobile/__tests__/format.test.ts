import { formatDateRange, formatTransmission, formatZar } from '@/lib/format';

describe('formatZar', () => {
  it.each([
    ['750.00', 'R 750.00'],
    ['1450.00', 'R 1 450.00'],
    ['1234567.5', 'R 1 234 567.50'],
    ['0', 'R 0.00'],
  ])('formats %s as %s', (input, expected) => {
    expect(formatZar(input)).toBe(expected);
  });

  it('rejects values that are not decimal strings', () => {
    expect(() => formatZar('12.345')).toThrow();
    expect(() => formatZar('abc')).toThrow();
  });
});

describe('formatDateRange', () => {
  it('uses South African time', () => {
    // 22:30 UTC on 13 Oct is already 14 Oct in Johannesburg (UTC+2).
    expect(formatDateRange('2026-10-13T22:30:00Z', '2026-10-16T08:00:00Z')).toMatch(/^14 Oct – 16 Oct 2026$/);
  });
});

it('labels transmissions', () => {
  expect(formatTransmission('AUTOMATIC')).toBe('Automatic');
});
