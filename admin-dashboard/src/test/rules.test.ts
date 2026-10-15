import { describe, expect, it } from 'vitest';

import { summarise } from '../components/audit-trail';
import { cents, fromCents, isRandAmount, monthLabel, saLocalToIso, zar } from '../lib/format';
import type { Payment } from '../lib/types';
import { checkReschedule } from '../pages/deliveries';
import { checkRefund, refundable } from '../pages/payments';
import { checkPrice } from '../pages/vehicles';
import { checkDecision } from '../pages/verifications';

describe('money', () => {
  it('formats rand strings without floats', () => {
    expect(zar('1250')).toBe('R 1 250.00');
    expect(zar('1234567.5')).toBe('R 1 234 567.50');
    expect(zar('-200.00')).toBe('-R 200.00');
  });

  it('works in cents', () => {
    expect(cents('0.1')).toBe(10);
    expect(cents('19.99')).toBe(1999);
    expect(fromCents(cents('0.1') + cents('0.2'))).toBe('0.30');
  });

  it('accepts only plain rand amounts', () => {
    expect(isRandAmount('650')).toBe(true);
    expect(isRandAmount('650.5')).toBe(true);
    expect(isRandAmount('0')).toBe(false);
    expect(isRandAmount('0', { allowZero: true })).toBe(true);
    for (const bad of ['650.555', '-5', 'R650', '6,50', '1e3', '']) expect(isRandAmount(bad)).toBe(false);
  });
});

describe('dates', () => {
  it('turns a datetime-local value into SA time', () => {
    expect(saLocalToIso('2026-10-20T10:00')).toBe('2026-10-20T10:00:00+02:00');
    expect(saLocalToIso('2026-10-20')).toBeNull();
  });

  it('labels months', () => {
    expect(monthLabel('2026-03')).toBe('Mar 26');
  });
});

describe('verification decisions', () => {
  it('needs a note unless approving', () => {
    expect(checkDecision('REJECTED', '', false, '', '2026-10-15')).toMatch(/Explain/);
    expect(checkDecision('REQUIRES_MORE_INFORMATION', 'ok', false, '', '2026-10-15')).toMatch(/Explain/);
    expect(checkDecision('REJECTED', 'Blurry photo', false, '', '2026-10-15')).toBeNull();
    expect(checkDecision('APPROVED', '', false, '', '2026-10-15')).toBeNull();
  });

  it('refuses an expired licence date when approving', () => {
    expect(checkDecision('APPROVED', '', true, '2026-10-15', '2026-10-15')).toMatch(/future/);
    expect(checkDecision('APPROVED', '', true, '2030-01-01', '2026-10-15')).toBeNull();
  });
});

describe('official prices', () => {
  const base = { daily_rate: '650', delivery_fee: '', deposit_amount: '2000', change_reason: 'Launch', effective_from: '' };

  it('accepts a valid price with optional fees', () => {
    expect(checkPrice(base)).toEqual({});
  });

  it('reports each problem on its field', () => {
    const errors = checkPrice(
      { daily_rate: '0', delivery_fee: '-1', deposit_amount: '1.234', change_reason: 'x', effective_from: '2020-01-01T10:00' },
      new Date('2026-10-15T00:00:00Z'),
    );
    expect(Object.keys(errors).sort()).toEqual(['change_reason', 'daily_rate', 'delivery_fee', 'deposit_amount', 'effective_from']);
  });
});

describe('refunds', () => {
  const payment = (amount: string, refunds: [string, 'PENDING' | 'PROCESSED' | 'FAILED'][], paid = true) =>
    ({
      amount,
      paid_at: paid ? '2026-10-01T08:00:00Z' : null,
      refunds: refunds.map(([value, status]) => ({ amount: value, status })),
    }) as unknown as Payment;

  it('counts pending and processed refunds, not failed ones', () => {
    expect(refundable(payment('2100.00', [['500.00', 'PROCESSED'], ['100.00', 'PENDING'], ['900.00', 'FAILED']]))).toBe('1500.00');
    expect(refundable(payment('2100.00', [], false))).toBe('0.00');
  });

  it('limits a refund to what is left', () => {
    expect(checkRefund('', 'Goodwill', '1500.00')).toBeNull();
    expect(checkRefund('1500.01', 'Goodwill', '1500.00')).toMatch(/At most R 1 500.00/);
    expect(checkRefund('0', 'Goodwill', '1500.00')).toMatch(/above zero/);
    expect(checkRefund('100', 'x', '1500.00')).toMatch(/reason/);
  });
});

describe('rescheduling', () => {
  const now = Date.parse('2026-10-15T08:00:00Z');
  const end = '2026-10-23T08:00:00Z';

  it('must be in the future, before the rental ends, with a note', () => {
    expect(checkReschedule('2026-10-20T10:00', 'Owner sick', end, now)).toBeNull();
    expect(checkReschedule('2026-10-15T09:00', 'Owner sick', end, now)).toMatch(/future/); // 07:00 UTC
    expect(checkReschedule('2026-10-23T10:00', 'Owner sick', end, now)).toMatch(/before the rental ends/);
    expect(checkReschedule('2026-10-20T10:00', '', end, now)).toMatch(/note/);
    expect(checkReschedule('', 'x', end, now)).toMatch(/Pick/);
  });
});

describe('audit summaries', () => {
  it('shows from → to changes', () => {
    expect(summarise({ status: { from: 'PENDING_APPROVAL', to: 'APPROVED' }, reason: 'ok' })).toBe(
      'status: PENDING_APPROVAL → APPROVED · reason: ok',
    );
    expect(summarise(null)).toBe('');
  });
});

describe('chart axis', () => {
  it('keeps one decimal for thousands', async () => {
    const { compactRand } = await import('../components/charts');
    expect([0, 750, 1500, 3000, 4500].map(compactRand)).toEqual(['R 0', 'R 750', 'R 1.5k', 'R 3k', 'R 4.5k']);
  });
});
