import { Component, lazy, Suspense } from 'react';
import type { ReactNode } from 'react';
import { Link } from 'react-router';

import { Card, Loading, LoadError, PageHeader, Table } from '../components/ui';
import { get } from '../lib/api';
import { monthLabel, zar } from '../lib/format';
import type { MonthRow, Overview } from '../lib/types';
import { useLoad } from '../lib/use-load';

// The chart library is large; it loads only for this page.
const Charts = lazy(() => import('../components/charts'));

class ChartsErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? <LoadError error={new Error('The charts could not be loaded.')} retry={() => window.location.reload()} /> : this.props.children;
  }
}

function Tile({ label, value, to, attention = false }: { label: string; value: string; to?: string; attention?: boolean }) {
  const body = (
    <div className={`h-full rounded-xl border bg-white p-4 ${attention ? 'border-warning' : 'border-surface-border'}`}>
      <p className={`text-2xl font-bold ${attention ? 'text-warning' : ''}`}>{value}</p>
      <p className="mt-1 text-sm text-ink-muted">{label}</p>
    </div>
  );
  return to ? (
    <Link to={to} className="block hover:opacity-80">
      {body}
    </Link>
  ) : (
    body
  );
}

function Dashboard({ overview, months }: { overview: Overview; months: MonthRow[] }) {
  const queues = [
    { label: 'Verifications waiting', value: overview.verifications_pending, to: '/verifications' },
    { label: 'Vehicles awaiting approval', value: overview.vehicles_pending_approval, to: '/vehicles' },
    { label: 'Deliveries needing attention', value: overview.deliveries_needing_attention, to: '/deliveries?open_exceptions=true' },
    { label: 'Refunds failed', value: overview.refunds_failed, to: '/payments?refund_status=FAILED' },
  ];
  return (
    <>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {queues.map((q) => (
          <Tile key={q.label} label={q.label} value={String(q.value)} to={q.to} attention={q.value > 0} />
        ))}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Tile label={`Collected in ${monthLabel(overview.month)}`} value={zar(overview.month_collected)} />
        <Tile label={`Refunded in ${monthLabel(overview.month)}`} value={zar(overview.month_refunded)} />
        <Tile label="Bookings upcoming · on the road" value={`${overview.bookings_upcoming} · ${overview.bookings_under_way}`} to="/bookings" />
        <Tile
          label="Renters · owners · suspended"
          value={`${overview.users_by_role.RENTER} · ${overview.users_by_role.OWNER} · ${overview.users_suspended}`}
          to="/users"
        />
      </div>

      <ChartsErrorBoundary>
        <Suspense fallback={<Loading label="Loading charts…" />}>
          <Charts overview={overview} months={months} />
        </Suspense>
      </ChartsErrorBoundary>

      <Card title="Monthly figures" className="mt-6">
        <Table head={['Month', 'Confirmed bookings', 'Collected', 'Refunded', 'Net', 'New renters', 'New owners']}>
          {months.map((m) => (
            <tr key={m.month}>
              <td className="px-3 py-2">{monthLabel(m.month)}</td>
              <td className="px-3 py-2">{m.bookings_confirmed}</td>
              <td className="px-3 py-2">{zar(m.collected)}</td>
              <td className="px-3 py-2">{zar(m.refunded)}</td>
              <td className="px-3 py-2 font-medium">{zar(m.net)}</td>
              <td className="px-3 py-2">{m.new_renters}</td>
              <td className="px-3 py-2">{m.new_owners}</td>
            </tr>
          ))}
        </Table>
      </Card>
    </>
  );
}

export function OverviewPage() {
  const data = useLoad(
    () => Promise.all([get<Overview>('/admin/reports/overview'), get<MonthRow[]>('/admin/reports/monthly', { months: 12 })]),
    'overview',
  );
  return (
    <>
      <PageHeader title="Overview" subtitle="Work waiting for you, and how the platform is doing. All figures come from live data." />
      {data.status === 'loading' ? <Loading /> : null}
      {data.status === 'error' ? <LoadError error={data.error} retry={data.reload} /> : null}
      {data.status === 'ready' ? <Dashboard overview={data.data[0]} months={data.data[1]} /> : null}
    </>
  );
}
