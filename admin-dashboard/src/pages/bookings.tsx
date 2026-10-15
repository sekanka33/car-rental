import { useState } from 'react';
import { Link, useParams } from 'react-router';

import { AuditTrail } from '../components/audit-trail';
import { ReasonAction } from '../components/reason-action';
import { Card, Empty, Loading, LoadError, PageHeader, Pager, Row, Select, StatusBadge, Table } from '../components/ui';
import { get, post } from '../lib/api';
import { BOOKING_TONE, dateTime, humanise, PAYMENT_TONE, zar } from '../lib/format';
import type { AdminBooking, BookingStatus, Payment } from '../lib/types';
import { useFilters } from '../lib/use-filters';
import { useLoad } from '../lib/use-load';

const LIMIT = 50;
const STATUSES: BookingStatus[] = [
  'PENDING_PAYMENT',
  'CONFIRMED',
  'DELIVERY_SCHEDULED',
  'IN_TRANSIT',
  'DELIVERED',
  'ACTIVE_RENTAL',
  'RETURN_PENDING',
  'COMPLETED',
  'CANCELLED',
  'EXPIRED',
];
const FINAL: BookingStatus[] = ['COMPLETED', 'CANCELLED', 'EXPIRED'];

export function BookingsPage() {
  const filters = useFilters(['status', 'vehicle_id'] as const);
  const list = useLoad(
    () =>
      get<AdminBooking[]>('/admin/bookings', {
        status: filters.values.status,
        vehicle_id: filters.values.vehicle_id,
        limit: LIMIT,
        offset: filters.offset,
      }),
    filters.key,
  );
  return (
    <>
      <PageHeader title="Bookings" subtitle="Every booking, newest rental first. Cancelling a paid booking refunds it in full." />
      <Card
        actions={
          <Select
            label="Status"
            value={filters.values.status}
            onChange={(e) => filters.set('status', e.target.value)}
            options={[{ value: '', label: 'All' }, ...STATUSES.map((s) => ({ value: s, label: humanise(s) }))]}
          />
        }>
        {filters.values.vehicle_id ? (
          <p className="mb-3 text-sm text-ink-muted">
            One vehicle only.{' '}
            <button type="button" className="font-semibold text-brand-600" onClick={() => filters.set('vehicle_id', '')}>
              Show all
            </button>
          </p>
        ) : null}
        {list.status === 'loading' ? <Loading /> : null}
        {list.status === 'error' ? <LoadError error={list.error} retry={list.reload} /> : null}
        {list.status === 'ready' ? (
          list.data.length === 0 ? (
            <Empty>No bookings.</Empty>
          ) : (
            <>
              <Table head={['Reference', 'Renter', 'Vehicle', 'Rental', 'Total', 'Status']}>
                {list.data.map((b) => (
                  <tr key={b.id} className="hover:bg-surface-muted">
                    <td className="px-3 py-2">
                      <Link className="font-mono font-medium text-brand-600" to={`/bookings/${b.id}`}>
                        {b.reference}
                      </Link>
                    </td>
                    <td className="px-3 py-2">{b.renter.full_name}</td>
                    <td className="px-3 py-2">
                      {b.vehicle.make} {b.vehicle.model}
                    </td>
                    <td className="px-3 py-2">
                      {dateTime(b.start_at)} → {dateTime(b.end_at)}
                    </td>
                    <td className="px-3 py-2">{zar(b.price.total_amount)}</td>
                    <td className="px-3 py-2">
                      <StatusBadge status={b.status} tones={BOOKING_TONE} />
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

export function BookingDetailPage() {
  const { id = '' } = useParams();
  const [version, setVersion] = useState(0);
  const data = useLoad(
    () => Promise.all([get<AdminBooking>(`/admin/bookings/${id}`), get<Payment[]>('/admin/payments', { booking_id: id })]),
    id,
  );
  if (data.status === 'loading') return <Loading />;
  if (data.status === 'error') return <LoadError error={data.error} retry={data.reload} />;
  const [b, payments] = data.data;
  const paid = payments.some((p) => p.paid_at);

  return (
    <>
      <PageHeader
        title={`Booking ${b.reference}`}
        subtitle={`${b.vehicle.year} ${b.vehicle.make} ${b.vehicle.model} · ${b.renter.full_name} (${b.renter.email})`}
        actions={<StatusBadge status={b.status} tones={BOOKING_TONE} />}
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-4">
          <Card title="Booking">
            <dl>
              <Row label="Rental">
                {dateTime(b.start_at)} → {dateTime(b.end_at)}
              </Row>
              <Row label="Delivery address">{b.delivery_address ?? '—'}</Row>
              <Row label={`${b.price.rental_days} day(s) × ${zar(b.price.daily_rate)}`}>{zar(b.price.rental_amount)}</Row>
              <Row label="Delivery fee">{zar(b.price.delivery_fee)}</Row>
              <Row label="Total">
                <strong>{zar(b.price.total_amount)}</strong>
              </Row>
              <Row label="Deposit (arranged at handover)">{zar(b.price.deposit_amount)}</Row>
              <Row label="Booked">{dateTime(b.created_at)}</Row>
              <Row label="Confirmed">{dateTime(b.confirmed_at)}</Row>
              {b.cancelled_at ? (
                <Row label="Cancelled">
                  {dateTime(b.cancelled_at)} · {b.cancellation_reason}
                </Row>
              ) : null}
            </dl>
            <p className="mt-3 text-sm">
              <Link className="font-semibold text-brand-600" to={`/vehicles/${b.vehicle.id}`}>
                Vehicle
              </Link>
              {' · '}
              <Link className="font-semibold text-brand-600" to={`/deliveries?booking=${b.id}`}>
                Delivery
              </Link>
            </p>
          </Card>
          {!FINAL.includes(b.status) ? (
            <Card title="Cancel">
              <ReasonAction
                label="Cancel booking"
                confirmLabel="Cancel and refund"
                explanation={
                  paid
                    ? 'The renter is refunded in full automatically, the delivery is cancelled and the dates are freed.'
                    : 'The booking has not been paid; the hold is released.'
                }
                onSubmit={async (reason) => {
                  await post(`/admin/bookings/${b.id}/cancel`, { reason });
                  data.reload();
                  setVersion((v) => v + 1);
                }}
              />
            </Card>
          ) : null}
        </div>
        <div className="space-y-4">
          <Card title="Payments">
            {payments.length === 0 ? (
              <Empty>No payment attempts.</Empty>
            ) : (
              <ul className="divide-y divide-surface-border">
                {payments.map((p) => (
                  <li key={p.id} className="py-2 text-sm">
                    <div className="flex justify-between">
                      <span>
                        {zar(p.amount)} · {dateTime(p.paid_at ?? p.created_at)}
                      </span>
                      <StatusBadge status={p.status} tones={PAYMENT_TONE} />
                    </div>
                    {p.refunds.map((r) => (
                      <div key={r.id} className="text-xs text-ink-muted">
                        Refund {zar(r.amount)} · {humanise(r.status)} · {r.reason}
                      </div>
                    ))}
                  </li>
                ))}
              </ul>
            )}
            <Link className="mt-3 inline-block text-sm font-semibold text-brand-600" to={`/payments?booking_id=${b.id}`}>
              Refund or check payments
            </Link>
          </Card>
          <AuditTrail entityType="booking" entityId={b.id} version={version} />
        </div>
      </div>
    </>
  );
}
