import { useState } from 'react';
import { Link, useParams } from 'react-router';

import { AuditTrail } from '../components/audit-trail';
import { PrivateFile } from '../components/private-file';
import { ReasonAction } from '../components/reason-action';
import { Badge, Button, Card, Empty, errorMessage, Input, Loading, LoadError, Notice, PageHeader, Pager, Row, Select, StatusBadge, Table, TextArea } from '../components/ui';
import { get, post } from '../lib/api';
import { dateTime, DELIVERY_TONE, humanise, saLocalToIso } from '../lib/format';
import type { AdminDelivery, AdminUser, DeliveryStatus, HandoverRecord, Page } from '../lib/types';
import { useFilters } from '../lib/use-filters';
import { useLoad } from '../lib/use-load';

const LIMIT = 50;
const STATUSES: DeliveryStatus[] = ['PENDING_SCHEDULE', 'SCHEDULED', 'EN_ROUTE', 'DELIVERED', 'FAILED', 'CANCELLED'];

export function DeliveriesPage() {
  const filters = useFilters(['status', 'open_exceptions', 'booking'] as const);
  const list = useLoad(
    () =>
      get<AdminDelivery[]>('/admin/deliveries', {
        status: filters.values.status,
        open_exceptions: filters.values.open_exceptions === 'true' || undefined,
        booking_id: filters.values.booking,
        limit: LIMIT,
        offset: filters.offset,
      }),
    filters.key,
  );
  return (
    <>
      <PageHeader title="Deliveries" subtitle="Owners deliver their own cars. Step in when a delivery is stopped or a problem is reported." />
      <Card
        actions={
          <div className="flex items-end gap-3">
            <label className="flex items-center gap-2 pb-2 text-sm">
              <input
                type="checkbox"
                checked={filters.values.open_exceptions === 'true'}
                onChange={(e) => filters.set('open_exceptions', e.target.checked ? 'true' : '')}
              />
              Needs attention
            </label>
            <Select
              label="Status"
              value={filters.values.status}
              onChange={(e) => filters.set('status', e.target.value)}
              options={[{ value: '', label: 'All' }, ...STATUSES.map((s) => ({ value: s, label: humanise(s) }))]}
            />
          </div>
        }>
        {list.status === 'loading' ? <Loading /> : null}
        {list.status === 'error' ? <LoadError error={list.error} retry={list.reload} /> : null}
        {list.status === 'ready' ? (
          list.data.length === 0 ? (
            <Empty>No deliveries.</Empty>
          ) : (
            <>
              <Table head={['Booking', 'Vehicle', 'Deliver to', 'When', 'Status']}>
                {list.data.map((d) => (
                  <tr key={d.id} className="hover:bg-surface-muted">
                    <td className="px-3 py-2">
                      <Link className="font-mono font-medium text-brand-600" to={`/deliveries/${d.id}`}>
                        {d.booking_reference}
                      </Link>
                    </td>
                    <td className="px-3 py-2">
                      {d.vehicle.make} {d.vehicle.model}
                      <div className="text-xs text-ink-muted">{d.registration_number}</div>
                    </td>
                    <td className="px-3 py-2">{d.dropoff_address}</td>
                    <td className="px-3 py-2">{dateTime(d.scheduled_for ?? d.rental_start_at)}</td>
                    <td className="px-3 py-2">
                      <StatusBadge status={d.status} tones={DELIVERY_TONE} />{' '}
                      {d.has_open_exception ? <Badge label="Problem reported" tone="danger" /> : null}
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

function Record({ delivery, record }: { delivery: AdminDelivery; record: HandoverRecord }) {
  return (
    <Card title={record.kind === 'HANDOVER' ? 'Handover' : 'Return'}>
      <dl>
        <Row label="Recorded">{dateTime(record.recorded_at)}</Row>
        <Row label="Odometer">{record.odometer_km} km</Row>
        <Row label="Fuel">{humanise(record.fuel_level)}</Row>
        <Row label="Condition">{record.condition_notes ?? '—'}</Row>
        {record.kind === 'HANDOVER' ? <Row label="Renter confirmed">{dateTime(record.renter_acknowledged_at)}</Row> : null}
        {record.renter_notes ? <Row label="Renter disagrees">{record.renter_notes}</Row> : null}
      </dl>
      <div className="mt-3 grid grid-cols-2 gap-3">
        {record.photos.map((p, i) => (
          <PrivateFile key={p.id} path={p.url.replace(/^\/api\/v1/, '')} label={`${record.kind.toLowerCase()} photo ${i + 1} (${delivery.booking_reference})`} audited={false} />
        ))}
      </div>
    </Card>
  );
}

function Reassign({ delivery, onDone }: { delivery: AdminDelivery; onDone: () => void }) {
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const owners = useLoad(
    () => get<Page<AdminUser>>('/admin/users', { role: 'OWNER', status: 'ACTIVE', q: query.trim() || undefined, limit: 10 }),
    `owners:${query.trim()}`,
  );
  const assign = async (userId: string) => {
    setBusyId(userId);
    setError(null);
    try {
      await post(`/admin/deliveries/${delivery.id}/assign`, { user_id: userId });
      onDone();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusyId(null);
    }
  };
  return (
    <div>
      {error ? <Notice tone="danger">{error}</Notice> : null}
      <Input label="Find an active owner account" placeholder="Name or email" value={query} onChange={(e) => setQuery(e.target.value)} />
      {owners.status === 'ready' ? (
        <ul className="divide-y divide-surface-border">
          {owners.data.items.map((o) => (
            <li key={o.id} className="flex items-center justify-between py-2 text-sm">
              <span>
                {o.full_name} <span className="text-ink-muted">· {o.email}</span>
                {o.id === delivery.assigned_to_id ? <Badge label="Assigned now" tone="info" /> : null}
              </span>
              {o.id !== delivery.assigned_to_id ? (
                <Button variant="secondary" busy={busyId === o.id} disabled={busyId !== null} onClick={() => assign(o.id)}>
                  Assign
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** A reschedule must be in the future and before the rental ends (the backend checks too). */
export function checkReschedule(local: string, note: string, rentalEndIso: string, now = Date.now()): string | null {
  const iso = saLocalToIso(local);
  if (!iso) return 'Pick the new delivery date and time.';
  if (Date.parse(iso) <= now) return 'The new time must be in the future.';
  if (Date.parse(iso) >= Date.parse(rentalEndIso)) return 'The new time must be before the rental ends.';
  if (note.trim().length < 3) return 'Add a note (shown on the record).';
  return null;
}

function Reschedule({ delivery, onDone }: { delivery: AdminDelivery; onDone: () => void }) {
  const [when, setWhen] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    const problem = checkReschedule(when, note, delivery.rental_end_at);
    if (problem) return setError(problem);
    setBusy(true);
    setError(null);
    try {
      await post(`/admin/deliveries/${delivery.id}/reschedule`, { scheduled_for: saLocalToIso(when), note: note.trim() });
      onDone();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div>
      {error ? <Notice tone="danger">{error}</Notice> : null}
      <Input label="New delivery time (SA time)" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
      <TextArea label="Note" value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} hint="Resolves any open problems on this delivery." />
      <Button busy={busy} onClick={submit}>
        Reschedule
      </Button>
    </div>
  );
}

export function DeliveryDetailPage() {
  const { id = '' } = useParams();
  const [version, setVersion] = useState(0);
  const delivery = useLoad(() => get<AdminDelivery>(`/admin/deliveries/${id}`), id);
  if (delivery.status === 'loading') return <Loading />;
  if (delivery.status === 'error') return <LoadError error={delivery.error} retry={delivery.reload} />;
  const d = delivery.data;
  const changed = () => {
    delivery.reload();
    setVersion((v) => v + 1);
  };
  const active = ['PENDING_SCHEDULE', 'SCHEDULED', 'EN_ROUTE', 'FAILED'].includes(d.status);
  // Not while the car is on its way (the backend refuses it too).
  const reschedulable = ['PENDING_SCHEDULE', 'SCHEDULED', 'FAILED'].includes(d.status);

  return (
    <>
      <PageHeader
        title={`Delivery · ${d.booking_reference}`}
        subtitle={`${d.vehicle.year} ${d.vehicle.make} ${d.vehicle.model} (${d.registration_number})`}
        actions={<StatusBadge status={d.status} tones={DELIVERY_TONE} />}
      />
      {d.status === 'FAILED' ? (
        <Notice tone="danger">This delivery is stopped. Reschedule it, or cancel the booking (the renter is refunded in full).</Notice>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-4">
          <Card title="Delivery">
            <dl>
              <Row label="Renter">
                {d.renter.full_name}
                {d.renter.phone_number ? ` · ${d.renter.phone_number}` : ''}
              </Row>
              <Row label="Deliver to">{d.dropoff_address}</Row>
              <Row label="Rental">
                {dateTime(d.rental_start_at)} → {dateTime(d.rental_end_at)}
              </Row>
              <Row label="Scheduled">{dateTime(d.scheduled_for)}</Row>
              <Row label="Set off">{dateTime(d.started_at)}</Row>
              <Row label="Delivered">{dateTime(d.delivered_at)}</Row>
              <Row label="Delivery person">{d.delivery_person_first_name ?? 'Unassigned'}</Row>
            </dl>
            <Link className="mt-3 inline-block text-sm font-semibold text-brand-600" to={`/bookings/${d.booking_id}`}>
              Booking ({humanise(d.booking_status)})
            </Link>
          </Card>
          <Card title="Problems reported">
            {d.exceptions.length === 0 ? (
              <Empty>None.</Empty>
            ) : (
              <ul className="space-y-3">
                {d.exceptions.map((x) => (
                  <li key={x.id} className="rounded-lg border border-surface-border p-3 text-sm">
                    <div className="flex justify-between">
                      <strong>{humanise(x.kind)}</strong>
                      <span className="text-ink-muted">{dateTime(x.created_at)}</span>
                    </div>
                    <p className="mt-1">{x.notes}</p>
                    {x.resolved_at ? (
                      <p className="mt-1 text-ink-muted">
                        Resolved {dateTime(x.resolved_at)}: {x.resolution}
                      </p>
                    ) : x.kind === 'DELAY' ? (
                      <div className="mt-2">
                        <ReasonAction
                          label="Mark resolved"
                          variant="primary"
                          reasonLabel="Resolution note"
                          onSubmit={async (note) => {
                            await post(`/admin/deliveries/${d.id}/exceptions/${x.id}/resolve`, { note });
                            changed();
                          }}
                        />
                      </div>
                    ) : (
                      <p className="mt-1 text-danger">Open: reschedule the delivery or cancel the booking.</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
          {reschedulable ? (
            <Card title="Reschedule">
              <Reschedule delivery={d} onDone={changed} />
            </Card>
          ) : null}
          {active ? (
            <Card title="Reassign">
              <Reassign delivery={d} onDone={changed} />
            </Card>
          ) : null}
        </div>
        <div className="space-y-4">
          {d.handover ? <Record delivery={d} record={d.handover} /> : null}
          {d.return_record ? <Record delivery={d} record={d.return_record} /> : null}
          <AuditTrail entityType="delivery" entityId={d.id} version={version} />
        </div>
      </div>
    </>
  );
}
