import { useState } from 'react';
import { Link } from 'react-router';

import { ReasonAction } from '../components/reason-action';
import { Badge, Button, Card, Empty, errorMessage, Input, Loading, LoadError, Notice, PageHeader, Pager, Select, Table } from '../components/ui';
import { get, post } from '../lib/api';
import { useAuth } from '../lib/auth';
import { dateTime, humanise } from '../lib/format';
import type { AdminUser, Page } from '../lib/types';
import { useFilters } from '../lib/use-filters';
import { useLoad } from '../lib/use-load';

const LIMIT = 25;

function UserActions({ user, me, onChanged }: { user: AdminUser; me: string | null; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (user.id === me) return <span className="text-xs text-ink-muted">You</span>;
  if (user.status === 'SUSPENDED') {
    return (
      <div>
        <Button
          variant="secondary"
          busy={busy}
          onClick={async () => {
            setBusy(true);
            setError(null);
            try {
              await post(`/admin/users/${user.id}/reactivate`);
              onChanged();
            } catch (e) {
              setError(errorMessage(e));
            } finally {
              setBusy(false);
            }
          }}>
          Reactivate
        </Button>
        {error ? <p className="mt-1 text-xs text-danger">{error}</p> : null}
      </div>
    );
  }
  if (user.status !== 'ACTIVE') return null;
  return (
    <ReasonAction
      label="Suspend"
      explanation="The user is signed out everywhere at once and cannot log in, book or deliver until reactivated."
      onSubmit={async (reason) => {
        await post(`/admin/users/${user.id}/suspend`, { reason });
        onChanged();
      }}
    />
  );
}

export function UsersPage() {
  const { state } = useAuth();
  const me = state.status === 'signedIn' ? state.me.id : null;
  const filters = useFilters(['q', 'role', 'status'] as const);
  const [search, setSearch] = useState(filters.values.q);
  const list = useLoad(
    () =>
      get<Page<AdminUser>>('/admin/users', {
        q: filters.values.q,
        role: filters.values.role,
        status: filters.values.status,
        limit: LIMIT,
        offset: filters.offset,
      }),
    filters.key,
  );

  return (
    <>
      <PageHeader title="Users" subtitle="Renters, owners and administrators. Administrators are created only with the server CLI." />
      <Card>
        <form
          className="mb-4 flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            filters.set('q', search.trim());
          }}>
          <div className="min-w-64 flex-1">
            <Input label="Search" placeholder="Name or email" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <div className="mb-4 flex gap-3">
            <Select
              label="Role"
              value={filters.values.role}
              onChange={(e) => filters.set('role', e.target.value)}
              options={[
                { value: '', label: 'All' },
                { value: 'RENTER', label: 'Renter' },
                { value: 'OWNER', label: 'Owner' },
                { value: 'ADMIN', label: 'Administrator' },
              ]}
            />
            <Select
              label="Status"
              value={filters.values.status}
              onChange={(e) => filters.set('status', e.target.value)}
              options={[
                { value: '', label: 'All' },
                { value: 'ACTIVE', label: 'Active' },
                { value: 'SUSPENDED', label: 'Suspended' },
                { value: 'DEACTIVATED', label: 'Deactivated' },
              ]}
            />
          </div>
          <Button type="submit" className="mb-4">
            Search
          </Button>
        </form>
        {list.status === 'loading' ? <Loading /> : null}
        {list.status === 'error' ? <LoadError error={list.error} retry={list.reload} /> : null}
        {list.status === 'ready' ? (
          list.data.items.length === 0 ? (
            <Empty>No users match.</Empty>
          ) : (
            <>
              <Table head={['Name', 'Roles', 'Status', 'Email', 'Joined', 'Last login', '']}>
                {list.data.items.map((u) => (
                  <tr key={u.id} className="align-top">
                    <td className="px-3 py-2">
                      <div className="font-medium">{u.full_name}</div>
                      <div className="text-xs text-ink-muted">{u.email}</div>
                      {u.phone_number ? <div className="text-xs text-ink-muted">{u.phone_number}</div> : null}
                    </td>
                    <td className="px-3 py-2">{u.roles.map((r) => humanise(r)).join(', ')}</td>
                    <td className="px-3 py-2">
                      <Badge label={humanise(u.status)} tone={u.status === 'ACTIVE' ? 'success' : 'danger'} />
                      {u.suspension_reason ? <div className="mt-1 text-xs text-ink-muted">{u.suspension_reason}</div> : null}
                    </td>
                    <td className="px-3 py-2">{u.email_verified ? 'Confirmed' : <Badge label="Not confirmed" tone="warning" />}</td>
                    <td className="px-3 py-2">{dateTime(u.created_at)}</td>
                    <td className="px-3 py-2">{dateTime(u.last_login_at)}</td>
                    <td className="px-3 py-2">
                      <UserActions user={u} me={me} onChanged={list.reload} />
                      <Link className="mt-1 block text-xs text-brand-600" to={`/audit?actor_user_id=${u.id}`}>
                        Actions by this user
                      </Link>
                    </td>
                  </tr>
                ))}
              </Table>
              <Pager offset={filters.offset} limit={LIMIT} count={list.data.items.length} total={list.data.total} onChange={filters.setOffset} />
            </>
          )
        ) : null}
      </Card>
      <Notice tone="info">Suspending signs the user out at once. It does not cancel their bookings or unlist their cars; do that separately if needed.</Notice>
    </>
  );
}
