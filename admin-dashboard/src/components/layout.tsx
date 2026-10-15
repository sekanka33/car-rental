import { NavLink, Outlet, useLocation } from 'react-router';

import { get } from '../lib/api';
import { useAuth } from '../lib/auth';
import type { Overview } from '../lib/types';
import { useLoad } from '../lib/use-load';

const NAV: { to: string; label: string; count?: (o: Overview) => number }[] = [
  { to: '/', label: 'Overview' },
  { to: '/verifications', label: 'Verifications', count: (o) => o.verifications_pending },
  { to: '/vehicles', label: 'Vehicles & pricing', count: (o) => o.vehicles_pending_approval },
  { to: '/bookings', label: 'Bookings' },
  { to: '/payments', label: 'Payments & refunds', count: (o) => o.refunds_failed },
  { to: '/deliveries', label: 'Deliveries', count: (o) => o.deliveries_needing_attention },
  { to: '/users', label: 'Users' },
  { to: '/audit', label: 'Audit log' },
];

export function Layout() {
  const { state, logout } = useAuth();
  const location = useLocation();
  // Queue counts refresh on every navigation, so they drop as work gets done.
  const overview = useLoad(() => get<Overview>('/admin/reports/overview'), location.pathname + location.search);
  const me = state.status === 'signedIn' ? state.me : null;

  return (
    <div className="flex min-h-screen">
      <aside className="w-60 shrink-0 border-r border-surface-border bg-white">
        <div className="px-5 py-5">
          <p className="text-lg font-bold">CarHire SA</p>
          <p className="text-xs text-ink-muted">Administration</p>
        </div>
        <nav aria-label="Main" className="px-3">
          {NAV.map((item) => {
            const count = overview.status === 'ready' && item.count ? item.count(overview.data) : 0;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  `mb-1 flex items-center justify-between rounded-lg px-3 py-2 text-sm font-medium ${
                    isActive ? 'bg-brand-50 text-brand-700' : 'text-ink hover:bg-surface-muted'
                  }`
                }>
                {item.label}
                {count > 0 ? (
                  <span aria-label={`${count} waiting`} className="rounded-full bg-warning px-2 text-xs font-semibold text-white">
                    {count}
                  </span>
                ) : null}
              </NavLink>
            );
          })}
        </nav>
        {me ? (
          <div className="mt-6 border-t border-surface-border px-5 py-4 text-sm">
            <p className="font-medium">{me.full_name}</p>
            <p className="truncate text-xs text-ink-muted">{me.email}</p>
            <button type="button" className="mt-2 text-sm font-semibold text-brand-600" onClick={() => void logout()}>
              Sign out
            </button>
          </div>
        ) : null}
      </aside>
      <main className="min-w-0 flex-1 p-8">
        <Outlet />
      </main>
    </div>
  );
}
