import { useState } from 'react';
import { Link } from 'react-router';

import { Badge, Button, Card, Empty, errorMessage, Loading, LoadError, PageHeader, Pager, Select, Table } from '../components/ui';
import { get, post } from '../lib/api';
import { dateTime, humanise, type Tone } from '../lib/format';
import type { NotificationDelivery, Page } from '../lib/types';
import { useFilters } from '../lib/use-filters';
import { useLoad } from '../lib/use-load';

const LIMIT = 50;
const TONE: Record<NotificationDelivery['status'], Tone> = { PENDING: 'warning', SENT: 'success', FAILED: 'danger', SKIPPED: 'neutral' };

function Retry({ delivery, onDone }: { delivery: NotificationDelivery; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (delivery.status !== 'FAILED') return null;
  return (
    <div>
      <Button
        variant="secondary"
        busy={busy}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            await post(`/admin/notifications/${delivery.id}/retry`);
            onDone();
          } catch (e) {
            setError(errorMessage(e));
          } finally {
            setBusy(false);
          }
        }}>
        Retry
      </Button>
      {error ? <p className="mt-1 text-xs text-danger">{error}</p> : null}
    </div>
  );
}

export function NotificationsPage() {
  const filters = useFilters(['status'] as const);
  const status = filters.values.status || 'FAILED';
  const list = useLoad(
    () => get<Page<NotificationDelivery>>('/admin/notifications', { status, limit: LIMIT, offset: filters.offset }),
    filters.key,
  );
  return (
    <>
      <PageHeader
        title="Notifications"
        subtitle="Emails and push messages to users. Failed ones were retried automatically (after 1, 5 and 30 minutes and 2 hours) before giving up."
      />
      <Card
        actions={
          <Select
            label="Status"
            value={status}
            onChange={(e) => filters.set('status', e.target.value)}
            options={['FAILED', 'PENDING', 'SENT', 'SKIPPED'].map((s) => ({ value: s, label: humanise(s) }))}
          />
        }>
        {list.status === 'loading' ? <Loading /> : null}
        {list.status === 'error' ? <LoadError error={list.error} retry={list.reload} /> : null}
        {list.status === 'ready' ? (
          list.data.items.length === 0 ? (
            <Empty>{status === 'FAILED' ? 'Nothing failed. Every message was sent.' : 'Nothing here.'}</Empty>
          ) : (
            <>
              <Table head={['Created', 'To', 'Message', 'Channel', 'Status', 'Attempts', 'Last error', '']}>
                {list.data.items.map((d) => (
                  <tr key={d.id} className="align-top">
                    <td className="px-3 py-2">{dateTime(d.created_at)}</td>
                    <td className="px-3 py-2">
                      <Link className="text-brand-600" to={`/users?q=${encodeURIComponent(d.user_email)}`}>
                        {d.user_email}
                      </Link>
                    </td>
                    <td className="px-3 py-2">
                      {d.title}
                      <div className="text-xs text-ink-muted">{d.event}</div>
                    </td>
                    <td className="px-3 py-2">{humanise(d.channel)}</td>
                    <td className="px-3 py-2">
                      <Badge label={humanise(d.status)} tone={TONE[d.status]} />
                    </td>
                    <td className="px-3 py-2">{d.attempts}</td>
                    <td className="max-w-xs px-3 py-2 text-xs text-ink-muted">{d.last_error ?? '—'}</td>
                    <td className="px-3 py-2">
                      <Retry delivery={d} onDone={list.reload} />
                    </td>
                  </tr>
                ))}
              </Table>
              <Pager offset={filters.offset} limit={LIMIT} count={list.data.items.length} total={list.data.total} onChange={filters.setOffset} />
            </>
          )
        ) : null}
      </Card>
    </>
  );
}
