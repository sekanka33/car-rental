# Admin dashboard

Web app for CarHire SA administrators: identity verification, vehicle approval and official
pricing, bookings, payments and refunds, deliveries, users and the audit log, with an overview
of work queues and charts drawn from live data. See the root [README.md](../README.md) for the
project overview and stage tracker.

Stack: React 19, TypeScript 6, Vite 8, Tailwind CSS 4, React Router 7, Recharts 3; tests with
Vitest 4 and Testing Library. All versions are pinned to ones that run on Node 20.19+.

## Setup

```bash
cd admin-dashboard
npm install
cp .env.example .env      # VITE_API_URL, default http://localhost:8000
npm run dev               # http://localhost:5173
```

The backend must be running and must allow this origin: `CORS_ORIGINS` in `backend/.env`
includes `http://localhost:5173` (and the production URL when deployed). Sign in with an
administrator account, created only with the server CLI:

```bash
cd backend && source .venv/bin/activate
python -m app.cli create-admin --email you@example.com --full-name "Your Name"
```

Accounts without the `ADMIN` role are signed out immediately ("This account is not an
administrator"). The backend enforces this on every endpoint; the app's check is only a courtesy.

## Commands

```bash
npm run dev         # development server
npm test            # Vitest (jsdom)
npm run typecheck   # tsc -b
npm run lint        # ESLint (typescript-eslint, react-hooks)
npm run build       # type-check and build to dist/
npm run preview     # serve dist/ locally
```

## Pages

| Page | What an administrator does there |
|------|-----------------------------------|
| Overview | Work queues (verifications, vehicles, deliveries needing attention, failed refunds), this month's money, counts, and charts: money per month, confirmed bookings, new accounts, bookings and vehicles by status, plus the same figures as a table |
| Verifications | Review queue by status; open the ID or licence file (each view is audited), approve, ask for more information or reject with a note the renter sees; confirm the licence expiry |
| Vehicles & pricing | Review queue; photos and documents; approve (only when documents are complete), reject with a reason, suspend, reinstate; set the official price (daily rate, delivery fee, deposit, reason, optional future start), price history, quote preview |
| Bookings | Filter by status; booking detail with payments; cancel with a reason (a paid booking is refunded in full automatically) |
| Payments & refunds | Filter by payment or refund state; full or partial refunds (limited to what is left); "Check pending with Paystack" runs reconciliation |
| Deliveries | "Needs attention" filter (failed, or a problem still open); reschedule, reassign to another active owner, resolve a delay; handover and return records with photos |
| Users | Search by name or email, filter by role and status; suspend with a reason (signs the user out everywhere) or reactivate; your own account cannot be suspended here |
| Notifications | Emails and pushes by status (default: failed after all retries), with the user, message and last error; retry a failed one |
| Audit log | Every audited action, filterable by record type, record id, action prefix and actor |

Every detail page shows that record's history from the audit log. Filters and the page live in
the URL, so links (for example from an overview tile) open the right list.

## Security

- **Session:** the access token is kept only in memory; the refresh token in `sessionStorage`,
  so a reload keeps you signed in and closing the tab signs you out. The client refreshes once
  on a 401 (parallel requests share one refresh) and signs out if that fails. Sign out revokes
  the refresh token on the server.
- **Content Security Policy** (in `index.html`): scripts only from this origin, API calls only
  to `VITE_API_URL`, images and frames only from this origin or `blob:`, no plugins.
- **Private files** (ID documents, vehicle documents, photos) are fetched with the access token
  only when the administrator clicks "View", shown from a `blob:` URL and released on close.
  Document views are recorded in the audit log by the backend.
- The app sends no cookies (`credentials: 'omit'`), so it is not exposed to CSRF.

## Structure

```
src/
├── App.tsx              # routes; the login page when signed out
├── main.tsx
├── index.css            # Tailwind theme tokens (same brand colours as the mobile app)
├── components/          # layout (sidebar with queue counts), ui kit, charts, audit trail,
│                        # private file viewer, reason-required actions
├── lib/                 # api client and session, auth context, types, formatting, data hooks
├── pages/               # one module per area (list + detail)
└── test/                # Vitest: api client, rules, pages (fetch is mocked per test)
```

Charts use two validated categorical colours (blue `#2a78d6`, orange `#eb6834`: colour-blind
separation ΔE 24.7, ≥ 3:1 contrast). The chart code is loaded only on the Overview page.
