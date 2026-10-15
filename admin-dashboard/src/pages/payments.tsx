import { useState } from 'react';
import { Link } from 'react-router';

import { Button, Card, Empty, errorMessage, Input, Loading, LoadError, Notice, PageHeader, Pager, Select, StatusBadge, Table } from '../components/ui';
import { get, post } from '../lib/api';
import { cents, dateTime, fromCents, humanise, isRandAmount, PAYMENT_TONE, zar } from '../lib/format';
import type { Payment, PaymentStatus } from '../lib/types';
import { useFilters } from '../lib/use-filters';
import { useLoad } from '../lib/use-load';

const LIMIT = 50;
const STATUSES: PaymentStatus[] = ['SUCCEEDED', 'PENDING', 'FAILED', 'PARTIALLY_REFUNDED', 'REFUND_PENDING', 'REFUNDED', 'CANCELLED'];

/** Amount still refundable: paid minus refunds that did not fail. */
export function refundable(payment: Payment): string {
  if (!payment.paid_at) return '0.00';
  const used = payment.refunds.filter((r) => r.status !== 'FAILED').reduce((sum, r) => sum + cents(r.amount), 0);
  return fromCents(Math.max(0, cents(payment.amount) - used));
}

/** Validates a refund: empty amount = everything left; otherwise > 0 and ≤ what is left. */
export function checkRefund(amount: string, reason: string, left: string): string | null {
  if (reason.trim().length < 3) return 'Give a reason (the renter may see it on their statement).';
  if (amount.trim() === '') return null;
  if (!isRandAmount(amount)) return 'Enter a rand amount above zero, e.g. 250 or 250.50.';
  if (cents(amount) > cents(left)) return `At most ${zar(left)} can still be refunded.`;
  return null;
}

function RefundForm({ payment, onDone }: { payment: Payment; onDone: () => void }) {
  const left = refundable(payment);
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (cents(left) === 0) return null;
  if (!open) {
    return (
      <Button variant="secondary" onClick={() => setOpen(true)}>
        Refund
      </Button>
    );
  }
  const submit = async () => {
    const problem = checkRefund(amount, reason, left);
    if (problem) return setError(problem);
    setBusy(true);
    setError(null);
    try {
      await post(`/admin/payments/${payment.id}/refunds`, { amount: amount.trim() || null, reason: reason.trim() });
      setOpen(false);
      onDone();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="mt-2 rounded-lg bg-surface-muted p-3">
      {error ? <Notice tone="danger">{error}</Notice> : null}
      <Input label={`Amount (R, empty = all ${zar(left)})`} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
      <Input label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />
      <div className="flex gap-2">
        <Button variant="danger" busy={busy} onClick={submit}>
          Send refund through Paystack
        </Button>
        <Button variant="secondary" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

export function PaymentsPage() {
  const filters = useFilters(['status', 'booking_id', 'refund_status'] as const);
  const list = useLoad(
    () =>
      get<Payment[]>('/admin/payments', {
        status: filters.values.status,
        booking_id: filters.values.booking_id,
        refund_status: filters.values.refund_status,
        limit: LIMIT,
        offset: filters.offset,
      }),
    filters.key,
  );
  const [reconciling, setReconciling] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null);

  const reconcile = async () => {
    setReconciling(true);
    setNotice(null);
    try {
      const result = await post<{ payments_checked: number; refunds_checked: number }>('/admin/payments/reconcile');
      setNotice({ tone: 'success', text: `Checked ${result.payments_checked} payment(s) and ${result.refunds_checked} refund(s) with Paystack.` });
      list.reload();
    } catch (e) {
      setNotice({ tone: 'danger', text: errorMessage(e) });
    } finally {
      setReconciling(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Payments & refunds"
        subtitle="Payments count only after the backend verifies them with Paystack."
        actions={
          <Button variant="secondary" busy={reconciling} onClick={reconcile}>
            Check pending with Paystack
          </Button>
        }
      />
      {notice ? <Notice tone={notice.tone}>{notice.text}</Notice> : null}
      <Card
        actions={
          <div className="flex gap-3">
            <Select
              label="Payment"
              value={filters.values.status}
              onChange={(e) => filters.set('status', e.target.value)}
              options={[{ value: '', label: 'All' }, ...STATUSES.map((s) => ({ value: s, label: humanise(s) }))]}
            />
            <Select
              label="Refunds"
              value={filters.values.refund_status}
              onChange={(e) => filters.set('refund_status', e.target.value)}
              options={[
                { value: '', label: 'Any' },
                { value: 'PENDING', label: 'Refund pending' },
                { value: 'FAILED', label: 'Refund failed' },
                { value: 'PROCESSED', label: 'Refund processed' },
              ]}
            />
          </div>
        }>
        {filters.values.booking_id ? (
          <p className="mb-3 text-sm text-ink-muted">
            One booking only.{' '}
            <button type="button" className="font-semibold text-brand-600" onClick={() => filters.set('booking_id', '')}>
              Show all
            </button>
          </p>
        ) : null}
        {list.status === 'loading' ? <Loading /> : null}
        {list.status === 'error' ? <LoadError error={list.error} retry={list.reload} /> : null}
        {list.status === 'ready' ? (
          list.data.length === 0 ? (
            <Empty>No payments.</Empty>
          ) : (
            <>
              <Table head={['Paid', 'Amount', 'Reference', 'Booking', 'Status', 'Refunds', '']}>
                {list.data.map((p) => (
                  <tr key={p.id} className="align-top">
                    <td className="px-3 py-2">{dateTime(p.paid_at ?? p.created_at)}</td>
                    <td className="px-3 py-2 font-medium">{zar(p.amount)}</td>
                    <td className="px-3 py-2 font-mono text-xs">{p.reference}</td>
                    <td className="px-3 py-2">
                      <Link className="text-brand-600" to={`/bookings/${p.booking_id}`}>
                        {p.booking_status ? humanise(p.booking_status) : 'Open'}
                      </Link>
                    </td>
                    <td className="px-3 py-2">
                      <StatusBadge status={p.status} tones={PAYMENT_TONE} />
                      {p.failure_reason ? <div className="text-xs text-danger">{p.failure_reason}</div> : null}
                    </td>
                    <td className="px-3 py-2 text-xs">
                      {p.refunds.length === 0
                        ? '—'
                        : p.refunds.map((r) => (
                            <div key={r.id} className={r.status === 'FAILED' ? 'text-danger' : ''}>
                              {zar(r.amount)} {humanise(r.status)}
                            </div>
                          ))}
                    </td>
                    <td className="px-3 py-2">
                      <RefundForm payment={p} onDone={list.reload} />
                    </td>
                  </tr>
                ))}
              </Table>
              <Pager offset={filters.offset} limit={LIMIT} count={list.data.length} onChange={filters.setOffset} />
            </>
          )
        ) : null}
      </Card>
    </>
  );
}
