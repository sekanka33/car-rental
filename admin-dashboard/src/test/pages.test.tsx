import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AppRoutes } from '../App';
import { AuthProvider } from '../lib/auth';
import type { AdminUser, AdminVehicle, Overview, Payment, Submission } from '../lib/types';
import { ADMIN_ME, mockApi, reply, TOKENS } from './mock-api';

const OVERVIEW: Overview = {
  verifications_pending: 2,
  vehicles_pending_approval: 1,
  deliveries_needing_attention: 0,
  refunds_pending: 0,
  refunds_failed: 1,
  bookings_upcoming: 3,
  bookings_under_way: 1,
  users_by_role: { ADMIN: 1, OWNER: 4, RENTER: 9 },
  users_suspended: 1,
  vehicles_by_status: { DRAFT: 0, PENDING_APPROVAL: 1, APPROVED: 5, REJECTED: 0, SUSPENDED: 0, UNAVAILABLE: 0 },
  bookings_by_status: {
    PENDING_PAYMENT: 0, CONFIRMED: 3, CANCELLED: 1, EXPIRED: 0, DELIVERY_SCHEDULED: 0, IN_TRANSIT: 0,
    DELIVERED: 0, ACTIVE_RENTAL: 1, RETURN_PENDING: 0, COMPLETED: 2,
  },
  month: '2026-10',
  month_collected: '18250.50',
  month_refunded: '2100.00',
  currency: 'ZAR',
};

const SESSION = {
  'POST /auth/refresh': TOKENS,
  'GET /users/me': ADMIN_ME,
  'GET /admin/reports/overview': OVERVIEW,
  'GET /admin/audit-logs': { items: [], total: 0, limit: 50, offset: 0 },
};

function renderAt(path: string, routes: Record<string, unknown>) {
  sessionStorage.setItem('carhire.admin.refresh', 'refresh-1');
  const calls = mockApi({ ...SESSION, ...(routes as Record<string, object>) });
  render(
    <AuthProvider>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </AuthProvider>,
  );
  return calls;
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe('sign in', () => {
  it('shows the login form without a session and refuses non-administrators', async () => {
    const user = userEvent.setup();
    mockApi({ 'POST /auth/login': TOKENS, 'GET /users/me': { ...ADMIN_ME, roles: ['RENTER'] }, 'POST /auth/logout': reply(204) });
    render(
      <AuthProvider>
        <MemoryRouter>
          <AppRoutes />
        </MemoryRouter>
      </AuthProvider>,
    );
    await user.type(await screen.findByLabelText('Email'), 'renter@example.com');
    await user.type(screen.getByLabelText('Password'), 'secret-pass');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText('This account is not an administrator.')).toBeInTheDocument();
  });
});

describe('overview', () => {
  it('shows work queues with counts in the navigation, money and the monthly table', async () => {
    renderAt('/', {
      'GET /admin/reports/monthly': [
        { month: '2026-09', bookings_confirmed: 4, collected: '9000.00', refunded: '0.00', net: '9000.00', new_renters: 3, new_owners: 1 },
        { month: '2026-10', bookings_confirmed: 6, collected: '18250.50', refunded: '2100.00', net: '16150.50', new_renters: 5, new_owners: 2 },
      ],
    });
    expect(await screen.findByText('Verifications waiting')).toBeInTheDocument();
    expect(screen.getAllByText('R 18 250.50').length).toBeGreaterThan(0);
    expect(screen.getByText('R 16 150.50')).toBeInTheDocument(); // net in the table
    const nav = screen.getByRole('navigation', { name: 'Main' });
    expect(within(nav).getByLabelText('2 waiting')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Refunds failed/ })).toHaveAttribute('href', '/payments?refund_status=FAILED');
  });
});

describe('verification review', () => {
  const submission: Submission = {
    id: 's1', document_type: 'SA_ID', status: 'PENDING', document_number_masked: '••••••••••085', licence_expiry_date: null,
    licence_codes: null, review_note: null, submitted_at: '2026-10-14T08:00:00Z', reviewed_at: null,
    files: [{ id: 'f1', side: 'FRONT', content_type: 'image/jpeg', size_bytes: 1000 }],
    submitter: { id: 'u1', full_name: 'Naledi Dlamini', email: 'naledi@example.com', date_of_birth: '1995-06-15' },
    reviewed_by_id: null,
  };

  it('requires a note to reject, then sends the decision', async () => {
    const user = userEvent.setup();
    const calls = renderAt('/verifications/s1', {
      'GET /admin/verifications/s1': submission,
      'POST /admin/verifications/s1/decision': { ...submission, status: 'REJECTED' },
    });
    await user.click(await screen.findByRole('button', { name: 'Reject' }));
    expect(screen.getByText(/Explain to the renter/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === 'POST' && c.path.startsWith('/admin'))).toBe(false);

    await user.type(screen.getByLabelText('Note to the renter'), 'The photo is blurry');
    await user.click(screen.getByRole('button', { name: 'Reject' }));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path.startsWith('/admin'))?.body).toEqual({ decision: 'REJECTED', note: 'The photo is blurry', licence_expiry_date: null }));
  });

  it('fetches the document only when asked (each view is audited)', async () => {
    const user = userEvent.setup();
    URL.createObjectURL = vi.fn(() => 'blob:doc');
    URL.revokeObjectURL = vi.fn();
    const calls = renderAt('/verifications/s1', {
      'GET /admin/verifications/s1': submission,
      'GET /admin/verifications/s1/files/f1': () => ({ blob: new Blob(['x'], { type: 'image/jpeg' }) }),
    });
    await screen.findByText('Naledi Dlamini', { exact: false });
    expect(calls.some((c) => c.path.includes('/files/'))).toBe(false);
    await user.click(screen.getByRole('button', { name: 'View front side' }));
    expect(await screen.findByAltText('front side')).toHaveAttribute('src', 'blob:doc');
  });

  it('keeps the document open while the decision is saved and the page refreshes', async () => {
    const user = userEvent.setup();
    URL.createObjectURL = vi.fn(() => 'blob:doc');
    URL.revokeObjectURL = vi.fn();
    let approved = false;
    renderAt('/verifications/s1', {
      'GET /admin/verifications/s1': () => ({ json: approved ? { ...submission, status: 'APPROVED' } : submission }),
      'GET /admin/verifications/s1/files/f1': () => ({ blob: new Blob(['x'], { type: 'image/jpeg' }) }),
      'POST /admin/verifications/s1/decision': () => {
        approved = true;
        return { json: { ...submission, status: 'APPROVED' } };
      },
    });
    await user.click(await screen.findByRole('button', { name: 'View front side' }));
    await screen.findByAltText('front side');
    await user.click(screen.getByRole('button', { name: 'Approve' }));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Reject' })).not.toBeInTheDocument());
    expect(screen.getByAltText('front side')).toBeInTheDocument();
  });
});

describe('vehicle review', () => {
  const vehicle = (overrides: Partial<AdminVehicle> = {}): AdminVehicle => ({
    id: 'v1', make: 'Toyota', model: 'Corolla', year: 2022, registration_number: 'CA123456', vin: 'AHTBB3JE500012345',
    colour: null, transmission: 'AUTOMATIC', fuel_type: 'PETROL', seats: 5, city: 'Cape Town', province: 'Western Cape',
    description: null, status: 'PENDING_APPROVAL', rejection_reason: null, suspension_reason: null, submitted_at: null,
    approved_at: null, created_at: '2026-10-01T08:00:00Z', current_price: null, photos: [], documents: [],
    compliance: { ok: false, missing: ['INSURANCE'], expired: [] },
    owner: { user_id: 'o1', full_name: 'Thabo Owner', email: 'thabo@example.com', business_name: null }, approved_by_id: null,
    ...overrides,
  });

  it('cannot approve while documents are missing', async () => {
    renderAt('/vehicles/v1', { 'GET /admin/vehicles/v1': vehicle(), 'GET /admin/vehicles/v1/prices': [] });
    expect(await screen.findByRole('button', { name: 'Approve and list' })).toBeDisabled();
    expect(screen.getByText(/Insurance missing/)).toBeInTheDocument();
    expect(screen.getByText(/Set an official price before approving/)).toBeInTheDocument();
  });

  it('sets an official price with exact decimal strings', async () => {
    const user = userEvent.setup();
    const calls = renderAt('/vehicles/v1', {
      'GET /admin/vehicles/v1': vehicle({ compliance: { ok: true, missing: [], expired: [] } }),
      'GET /admin/vehicles/v1/prices': [],
      'POST /admin/vehicles/v1/prices': {},
    });
    await user.type(await screen.findByLabelText('Daily rate (R)'), '650.50');
    await user.type(screen.getByLabelText('Reason'), 'Launch price');
    await user.click(screen.getByRole('button', { name: 'Set official price' }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST' && c.path.startsWith('/admin'))?.body).toEqual({
        daily_rate: '650.50', delivery_fee: '0', deposit_amount: '0', change_reason: 'Launch price', effective_from: null,
      }),
    );
  });
});

describe('refunds', () => {
  const payment: Payment = {
    id: 'p1', booking_id: 'b1', reference: 'ref-1', provider: 'paystack', status: 'PARTIALLY_REFUNDED', amount: '2100.00',
    currency: 'ZAR', paid_at: '2026-10-01T08:00:00Z', failure_reason: null, created_at: '2026-10-01T08:00:00Z',
    refunds: [{ id: 'r1', amount: '600.00', currency: 'ZAR', status: 'PROCESSED', reason: 'x', created_at: '', processed_at: '' }],
    booking_status: 'CANCELLED',
  };

  it('blocks a refund larger than what is left', async () => {
    const user = userEvent.setup();
    const calls = renderAt('/payments', { 'GET /admin/payments': [payment], 'POST /admin/payments/p1/refunds': {} });
    await user.click(await screen.findByRole('button', { name: 'Refund' }));
    await user.type(screen.getByLabelText(/Amount/), '1600');
    await user.type(screen.getByLabelText('Reason'), 'Goodwill');
    await user.click(screen.getByRole('button', { name: 'Send refund through Paystack' }));
    expect(screen.getByText('At most R 1 500.00 can still be refunded.')).toBeInTheDocument();
    expect(calls.some((c) => c.method === 'POST' && c.path.startsWith('/admin'))).toBe(false);
  });
});

describe('users', () => {
  const user = (overrides: Partial<AdminUser>): AdminUser => ({
    id: 'u1', email: 'sipho@example.com', full_name: 'Sipho Ndlovu', phone_number: null, status: 'ACTIVE', roles: ['RENTER'],
    email_verified: true, created_at: '2026-10-01T08:00:00Z', suspended_at: null, suspension_reason: null, last_login_at: null,
    ...overrides,
  });

  it('suspends with a reason, and never offers it on your own account', async () => {
    const ue = userEvent.setup();
    const calls = renderAt('/users', {
      'GET /admin/users': { items: [user({}), user({ id: 'admin-1', email: 'admin@example.com', full_name: 'Platform Admin', roles: ['ADMIN'] })], total: 2, limit: 25, offset: 0 },
      'POST /admin/users/u1/suspend': user({ status: 'SUSPENDED' }),
    });
    expect(await screen.findByText('You')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Suspend' })).toHaveLength(1);

    await ue.click(screen.getByRole('button', { name: 'Suspend' }));
    await ue.click(screen.getByRole('button', { name: 'Suspend' })); // confirm without a reason
    expect(screen.getByText(/at least 3 characters/)).toBeInTheDocument();
    await ue.type(screen.getByLabelText(/Reason/), 'Fraudulent documents');
    await ue.click(screen.getByRole('button', { name: 'Suspend' }));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path.startsWith('/admin'))?.body).toEqual({ reason: 'Fraudulent documents' }));
  });

  it('searches through the URL filter', async () => {
    const ue = userEvent.setup();
    const calls = renderAt('/users', { 'GET /admin/users': { items: [], total: 0, limit: 25, offset: 0 } });
    await ue.type(await screen.findByLabelText('Search'), 'sipho');
    await ue.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(calls.filter((c) => c.path === '/admin/users').at(-1)?.query.get('q')).toBe('sipho'));
  });
});
