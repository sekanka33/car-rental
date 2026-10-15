import { useState } from 'react';
import { Link, useParams } from 'react-router';

import { AuditTrail } from '../components/audit-trail';
import { PrivateFile } from '../components/private-file';
import { ReasonAction } from '../components/reason-action';
import {
  Badge,
  Button,
  Card,
  Empty,
  errorMessage,
  Input,
  Loading,
  LoadError,
  Notice,
  PageHeader,
  Pager,
  Row,
  Select,
  StatusBadge,
  Table,
} from '../components/ui';
import { get, post } from '../lib/api';
import { dateOnly, dateTime, humanise, isRandAmount, saLocalToIso, VEHICLE_TONE, zar } from '../lib/format';
import type { AdminVehicle, OfficialPrice, Quote, VehicleStatus } from '../lib/types';
import { useFilters } from '../lib/use-filters';
import { useLoad } from '../lib/use-load';

const LIMIT = 25;
const STATUSES: VehicleStatus[] = ['PENDING_APPROVAL', 'APPROVED', 'UNAVAILABLE', 'REJECTED', 'SUSPENDED', 'DRAFT'];

export function VehiclesPage() {
  const filters = useFilters(['status'] as const);
  const status = filters.values.status || 'PENDING_APPROVAL';
  const list = useLoad(() => get<AdminVehicle[]>('/admin/vehicles', { status, limit: LIMIT, offset: filters.offset }), filters.key);
  return (
    <>
      <PageHeader title="Vehicles & pricing" subtitle="Approve owners' cars and set the official price renters pay." />
      <Card
        actions={
          <Select
            label="Status"
            value={status}
            onChange={(e) => filters.set('status', e.target.value)}
            options={STATUSES.map((s) => ({ value: s, label: humanise(s) }))}
          />
        }>
        {list.status === 'loading' ? <Loading /> : null}
        {list.status === 'error' ? <LoadError error={list.error} retry={list.reload} /> : null}
        {list.status === 'ready' ? (
          list.data.length === 0 ? (
            <Empty>No vehicles with this status.</Empty>
          ) : (
            <>
              <Table head={['Vehicle', 'Owner', 'Location', 'Price / day', 'Documents', 'Status']}>
                {list.data.map((v) => (
                  <tr key={v.id} className="hover:bg-surface-muted">
                    <td className="px-3 py-2">
                      <Link className="font-medium text-brand-600" to={`/vehicles/${v.id}`}>
                        {v.year} {v.make} {v.model}
                      </Link>
                      <div className="text-xs text-ink-muted">{v.registration_number}</div>
                    </td>
                    <td className="px-3 py-2">{v.owner.full_name}</td>
                    <td className="px-3 py-2">
                      {v.city}, {v.province}
                    </td>
                    <td className="px-3 py-2">{v.current_price ? zar(v.current_price.daily_rate) : <Badge label="Not set" tone="warning" />}</td>
                    <td className="px-3 py-2">{v.compliance.ok ? <Badge label="Complete" tone="success" /> : <Badge label="Incomplete" tone="danger" />}</td>
                    <td className="px-3 py-2">
                      <StatusBadge status={v.status} tones={VEHICLE_TONE} />
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

export interface PriceDraft {
  daily_rate: string;
  delivery_fee: string;
  deposit_amount: string;
  change_reason: string;
  effective_from: string; // datetime-local, empty = now
}

/** Checks a new official price before sending it; returns per-field messages. */
export function checkPrice(draft: PriceDraft, now: Date = new Date()): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!isRandAmount(draft.daily_rate)) errors.daily_rate = 'A rand amount above zero, e.g. 650 or 650.00.';
  if (!isRandAmount(draft.delivery_fee || '0', { allowZero: true })) errors.delivery_fee = 'A rand amount, e.g. 150.';
  if (!isRandAmount(draft.deposit_amount || '0', { allowZero: true })) errors.deposit_amount = 'A rand amount, e.g. 2000.';
  if (draft.change_reason.trim().length < 3) errors.change_reason = 'Say why the price is set or changed.';
  if (draft.effective_from) {
    const iso = saLocalToIso(draft.effective_from);
    if (!iso) errors.effective_from = 'Pick a date and time.';
    else if (Date.parse(iso) < now.getTime()) errors.effective_from = 'Cannot be in the past.';
  }
  return errors;
}

function PriceForm({ vehicleId, onSaved }: { vehicleId: string; onSaved: () => void }) {
  const empty: PriceDraft = { daily_rate: '', delivery_fee: '', deposit_amount: '', change_reason: '', effective_from: '' };
  const [draft, setDraft] = useState(empty);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const field = (key: keyof PriceDraft) => ({
    value: draft[key],
    onChange: (e: { target: { value: string } }) => setDraft((d) => ({ ...d, [key]: e.target.value })),
    error: errors[key],
  });

  const save = async () => {
    const found = checkPrice(draft);
    setErrors(found);
    if (Object.keys(found).length) return;
    setBusy(true);
    setMessage(null);
    try {
      await post(`/admin/vehicles/${vehicleId}/prices`, {
        daily_rate: draft.daily_rate.trim(),
        delivery_fee: draft.delivery_fee.trim() || '0',
        deposit_amount: draft.deposit_amount.trim() || '0',
        change_reason: draft.change_reason.trim(),
        effective_from: draft.effective_from ? saLocalToIso(draft.effective_from) : null,
      });
      setDraft(empty);
      onSaved();
    } catch (e) {
      setMessage(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      {message ? <Notice tone="danger">{message}</Notice> : null}
      <div className="grid gap-x-4 sm:grid-cols-3">
        <Input label="Daily rate (R)" inputMode="decimal" {...field('daily_rate')} />
        <Input label="Delivery fee (R)" inputMode="decimal" placeholder="0" {...field('delivery_fee')} />
        <Input label="Deposit (R)" inputMode="decimal" placeholder="0" {...field('deposit_amount')} />
      </div>
      <div className="grid gap-x-4 sm:grid-cols-2">
        <Input label="Reason" {...field('change_reason')} />
        <Input label="Takes effect (SA time, empty = now)" type="datetime-local" {...field('effective_from')} />
      </div>
      <p className="mb-3 text-xs text-ink-muted">Prices are final, VAT-inclusive amounts. Existing bookings keep the price they were made at.</p>
      <Button busy={busy} onClick={save}>
        Set official price
      </Button>
    </div>
  );
}

function QuotePreview({ vehicleId }: { vehicleId: string }) {
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [quote, setQuote] = useState<Quote | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = async () => {
    const startIso = saLocalToIso(start);
    const endIso = saLocalToIso(end);
    if (!startIso || !endIso) return setError('Pick a start and end.');
    try {
      setError(null);
      setQuote(await get<Quote>(`/admin/vehicles/${vehicleId}/quote`, { start_at: startIso, end_at: endIso }));
    } catch (e) {
      setQuote(null);
      setError(errorMessage(e));
    }
  };
  return (
    <div>
      <div className="grid gap-x-4 sm:grid-cols-2">
        <Input label="Start" type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} />
        <Input label="End" type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} />
      </div>
      <Button variant="secondary" onClick={run}>
        Preview the price
      </Button>
      {error ? <p className="mt-2 text-sm text-danger">{error}</p> : null}
      {quote ? (
        <dl className="mt-3">
          <Row label={`${quote.rental_days} day(s) × ${zar(quote.daily_rate)}`}>{zar(quote.rental_amount)}</Row>
          <Row label="Delivery">{zar(quote.delivery_fee)}</Row>
          <Row label="Total charged">
            <strong>{zar(quote.total_amount)}</strong>
          </Row>
          <Row label="Deposit (not charged online)">{zar(quote.deposit_amount)}</Row>
        </dl>
      ) : null}
    </div>
  );
}

function ReviewActions({ vehicle, onChanged }: { vehicle: AdminVehicle; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const approve = async () => {
    setBusy(true);
    setError(null);
    try {
      await post(`/admin/vehicles/${vehicle.id}/approve`);
      onChanged();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card title="Review">
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {vehicle.status === 'PENDING_APPROVAL' ? (
        <>
          {!vehicle.current_price ? <Notice tone="warning">Set an official price before approving, or renters cannot book it.</Notice> : null}
          <div className="flex flex-wrap items-start gap-2">
            <Button busy={busy} disabled={!vehicle.compliance.ok} onClick={approve}>
              Approve and list
            </Button>
            <ReasonAction label="Reject" reasonLabel="What must the owner fix? (they see this)" onSubmit={async (reason) => {
              await post(`/admin/vehicles/${vehicle.id}/reject`, { reason });
              onChanged();
            }} />
          </div>
        </>
      ) : null}
      {vehicle.status === 'APPROVED' || vehicle.status === 'UNAVAILABLE' ? (
        <ReasonAction
          label="Suspend"
          explanation="The car leaves the marketplace at once. Existing bookings are not cancelled automatically."
          onSubmit={async (reason) => {
            await post(`/admin/vehicles/${vehicle.id}/suspend`, { reason });
            onChanged();
          }}
        />
      ) : null}
      {vehicle.status === 'SUSPENDED' ? (
        <Button
          busy={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await post(`/admin/vehicles/${vehicle.id}/reinstate`);
              onChanged();
            } catch (e) {
              setError(errorMessage(e));
            } finally {
              setBusy(false);
            }
          }}>
          Reinstate
        </Button>
      ) : null}
      {['DRAFT', 'REJECTED'].includes(vehicle.status) ? <p className="text-sm text-ink-muted">Nothing to review: the owner has not submitted it.</p> : null}
    </Card>
  );
}

export function VehicleDetailPage() {
  const { id = '' } = useParams();
  const [version, setVersion] = useState(0);
  const data = useLoad(
    () => Promise.all([get<AdminVehicle>(`/admin/vehicles/${id}`), get<OfficialPrice[]>(`/admin/vehicles/${id}/prices`)]),
    id,
  );
  if (data.status === 'loading') return <Loading />;
  if (data.status === 'error') return <LoadError error={data.error} retry={data.reload} />;
  const [v, prices] = data.data;
  const changed = () => {
    data.reload();
    setVersion((n) => n + 1);
  };

  return (
    <>
      <PageHeader
        title={`${v.year} ${v.make} ${v.model}`}
        subtitle={`${v.registration_number} · VIN ${v.vin} · ${v.city}, ${v.province}`}
        actions={<StatusBadge status={v.status} tones={VEHICLE_TONE} />}
      />
      {v.rejection_reason && v.status === 'REJECTED' ? <Notice tone="danger">Rejected: {v.rejection_reason}</Notice> : null}
      {v.suspension_reason && v.status === 'SUSPENDED' ? <Notice tone="danger">Suspended: {v.suspension_reason}</Notice> : null}
      {!v.compliance.ok ? (
        <Notice tone="danger">
          Documents: {[...v.compliance.missing.map((d) => `${humanise(d)} missing`), ...v.compliance.expired.map((d) => `${humanise(d)} expired`)].join(', ')}
        </Notice>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-4">
          <ReviewActions vehicle={v} onChanged={changed} />
          <Card title="Details">
            <dl>
              <Row label="Owner">
                {v.owner.full_name} · {v.owner.email}
                {v.owner.business_name ? ` · ${v.owner.business_name}` : ''}
              </Row>
              <Row label="Transmission · fuel · seats">
                {humanise(v.transmission)} · {humanise(v.fuel_type)} · {v.seats}
              </Row>
              <Row label="Colour">{v.colour ?? '—'}</Row>
              <Row label="Submitted">{dateTime(v.submitted_at)}</Row>
              <Row label="Approved">{dateTime(v.approved_at)}</Row>
            </dl>
            {v.description ? <p className="mt-3 text-sm text-ink-muted">{v.description}</p> : null}
          </Card>
          <Card title="Official price">
            {v.current_price ? (
              <p className="mb-4 text-sm">
                Now <strong>{zar(v.current_price.daily_rate)}</strong> per day · delivery {zar(v.current_price.delivery_fee)} · deposit{' '}
                {zar(v.current_price.deposit_amount)}
              </p>
            ) : (
              <Notice tone="warning">No official price yet.</Notice>
            )}
            <PriceForm vehicleId={v.id} onSaved={changed} />
          </Card>
          <Card title="Price history">
            {prices.length === 0 ? (
              <Empty>No prices yet.</Empty>
            ) : (
              <Table head={['From', 'Daily', 'Delivery', 'Deposit', 'Reason']}>
                {prices.map((p) => (
                  <tr key={p.id}>
                    <td className="px-3 py-2">
                      {dateTime(p.effective_from)} {p.is_current ? <Badge label="Current" tone="success" /> : null}
                    </td>
                    <td className="px-3 py-2">{zar(p.daily_rate)}</td>
                    <td className="px-3 py-2">{zar(p.delivery_fee)}</td>
                    <td className="px-3 py-2">{zar(p.deposit_amount)}</td>
                    <td className="px-3 py-2 text-ink-muted">{p.change_reason ?? '—'}</td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
          <Card title="Quote preview">
            <QuotePreview vehicleId={v.id} />
          </Card>
        </div>
        <div className="space-y-4">
          <Card title={`Photos (${v.photos.length})`}>
            <div className="grid grid-cols-2 gap-3">
              {v.photos.map((p, i) => (
                <PrivateFile key={p.id} path={`/admin/vehicles/${v.id}/photos/${p.id}`} label={`photo ${i + 1}`} audited={false} />
              ))}
            </div>
          </Card>
          <Card title="Documents">
            <ul className="space-y-4">
              {v.documents
                .filter((d) => d.is_current)
                .map((d) => (
                  <li key={d.id}>
                    <p className="mb-1 text-sm font-medium">
                      {humanise(d.document_type)} {d.expiry_date ? <span className="text-ink-muted">· expires {dateOnly(d.expiry_date)}</span> : null}
                    </p>
                    <PrivateFile path={`/admin/vehicles/${v.id}/documents/${d.id}`} label={humanise(d.document_type).toLowerCase()} />
                  </li>
                ))}
            </ul>
          </Card>
          <AuditTrail entityType="vehicle" entityId={v.id} version={version} />
        </div>
      </div>
    </>
  );
}
