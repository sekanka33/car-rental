import { useState } from 'react';

import { AuditEntryRow } from '../components/audit-trail';
import { Button, Card, Empty, Input, Loading, LoadError, PageHeader, Pager, Select } from '../components/ui';
import { get } from '../lib/api';
import type { AuditEntry, Page } from '../lib/types';
import { useFilters } from '../lib/use-filters';
import { useLoad } from '../lib/use-load';

const LIMIT = 50;
const ENTITY_TYPES = ['vehicle', 'verification_submission', 'booking', 'payment', 'delivery', 'user', 'system'];

export function AuditPage() {
  const filters = useFilters(['entity_type', 'entity_id', 'action', 'actor_user_id'] as const);
  const [action, setAction] = useState(filters.values.action);
  const [entityId, setEntityId] = useState(filters.values.entity_id);
  const log = useLoad(
    () =>
      get<Page<AuditEntry>>('/admin/audit-logs', {
        entity_type: filters.values.entity_type,
        entity_id: filters.values.entity_id,
        action: filters.values.action,
        actor_user_id: filters.values.actor_user_id,
        limit: LIMIT,
        offset: filters.offset,
      }),
    filters.key,
  );

  return (
    <>
      <PageHeader title="Audit log" subtitle="Every sensitive action, newest first. Entries cannot be changed or deleted." />
      <Card>
        <form
          className="mb-2 flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            filters.set('action', action.trim());
            filters.set('entity_id', entityId.trim());
          }}>
          <div className="mb-4">
            <Select
              label="Record type"
              value={filters.values.entity_type}
              onChange={(e) => filters.set('entity_type', e.target.value)}
              options={[{ value: '', label: 'All' }, ...ENTITY_TYPES.map((t) => ({ value: t, label: t.replace(/_/g, ' ') }))]}
            />
          </div>
          <div className="w-56">
            <Input label="Action starts with" placeholder="e.g. vehicle." value={action} onChange={(e) => setAction(e.target.value)} />
          </div>
          <div className="w-80">
            <Input label="Record id" value={entityId} onChange={(e) => setEntityId(e.target.value)} />
          </div>
          <Button type="submit" className="mb-4">
            Filter
          </Button>
        </form>
        {filters.values.actor_user_id ? (
          <p className="mb-3 text-sm text-ink-muted">
            Actions by one user.{' '}
            <button type="button" className="font-semibold text-brand-600" onClick={() => filters.set('actor_user_id', '')}>
              Show everyone
            </button>
          </p>
        ) : null}
        {log.status === 'loading' ? <Loading /> : null}
        {log.status === 'error' ? <LoadError error={log.error} retry={log.reload} /> : null}
        {log.status === 'ready' ? (
          log.data.items.length === 0 ? (
            <Empty>No entries.</Empty>
          ) : (
            <>
              <ul className="divide-y divide-surface-border">
                {log.data.items.map((entry) => (
                  <AuditEntryRow key={entry.id} entry={entry} showEntity />
                ))}
              </ul>
              <Pager offset={filters.offset} limit={LIMIT} count={log.data.items.length} total={log.data.total} onChange={filters.setOffset} />
            </>
          )
        ) : null}
      </Card>
    </>
  );
}
