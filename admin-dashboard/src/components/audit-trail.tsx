import { get } from '../lib/api';
import { dateTime } from '../lib/format';
import type { AuditEntry, Page } from '../lib/types';
import { useLoad } from '../lib/use-load';
import { Card, Empty, Loading, LoadError } from './ui';

/** Short, readable summary of an audit entry's `changes` (they never hold secrets). */
export function summarise(changes: Record<string, unknown> | null): string {
  if (!changes) return '';
  return Object.entries(changes)
    .map(([key, value]) => {
      if (value && typeof value === 'object' && 'from' in value && 'to' in value) {
        const change = value as { from: unknown; to: unknown };
        return `${key}: ${String(change.from)} → ${String(change.to)}`;
      }
      return `${key}: ${typeof value === 'object' ? JSON.stringify(value) : String(value)}`;
    })
    .join(' · ');
}

export function AuditEntryRow({ entry, showEntity = false }: { entry: AuditEntry; showEntity?: boolean }) {
  return (
    <li className="py-2 text-sm">
      <div className="flex flex-wrap justify-between gap-2">
        <span className="font-medium">{entry.action}</span>
        <span className="text-ink-muted">{dateTime(entry.created_at)}</span>
      </div>
      <div className="text-ink-muted">
        {entry.actor ? `${entry.actor.full_name} (${entry.actor.email})` : 'System'}
        {showEntity ? ` · ${entry.entity_type} ${entry.entity_id}` : ''}
      </div>
      {entry.changes ? <div className="mt-0.5 break-words text-xs text-ink-muted">{summarise(entry.changes)}</div> : null}
    </li>
  );
}

/** The audit history of one record (newest first), shown on detail pages. */
export function AuditTrail({ entityType, entityId, version = 0 }: { entityType: string; entityId: string; version?: number }) {
  const log = useLoad(
    () => get<Page<AuditEntry>>('/admin/audit-logs', { entity_type: entityType, entity_id: entityId, limit: 50 }),
    `${entityType}:${entityId}:${version}`,
  );
  return (
    <Card title="History">
      {log.status === 'loading' ? <Loading /> : null}
      {log.status === 'error' ? <LoadError error={log.error} retry={log.reload} /> : null}
      {log.status === 'ready' ? (
        log.data.items.length === 0 ? (
          <Empty>No recorded actions yet.</Empty>
        ) : (
          <ul className="divide-y divide-surface-border">
            {log.data.items.map((entry) => (
              <AuditEntryRow key={entry.id} entry={entry} />
            ))}
          </ul>
        )
      ) : null}
    </Card>
  );
}
