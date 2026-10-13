# Development Roadmap

The root `README.md` is the official progress tracker. This file adds detail
for each stage and must always show the **same statuses** as the README.

Status values: `COMPLETE`, `IN PROGRESS`, `BLOCKED`, `NOT STARTED`.

| Stage | Name | Status | Depends on |
|-------|------|--------|------------|
| 01 | Repository Inspection and Project Planning | [x] COMPLETE | — |
| 02 | Mobile Application Foundation | [x] COMPLETE | 01 |
| 03 | Python Backend Foundation | [x] COMPLETE | 01 |
| 04 | PostgreSQL and Database Foundation | [x] COMPLETE | 03 |
| 05 | Authentication and Authorisation | [x] COMPLETE | 04 |
| 06 | Customer Eligibility and Document Verification | [x] COMPLETE | 05 |
| 07 | Owner Profiles and Vehicle Registration | [x] COMPLETE | 05 |
| 08 | Administrator Pricing Management | NOT STARTED | 07 |
| 09 | Customer Marketplace | NOT STARTED | 02, 08 |
| 10 | Booking and Availability | NOT STARTED | 06, 08, 09 |
| 11 | Payment Integration | NOT STARTED | 10 |
| 12 | Delivery Management | NOT STARTED | 11 |
| 13 | Google Maps and Live Tracking | NOT STARTED | 12 |
| 14 | Customer and Owner Dashboards | NOT STARTED | 13 |
| 15 | Administrator Dashboard | NOT STARTED | 14 |
| 16 | Notifications and Communication | NOT STARTED | 15 |
| 17 | Security, Testing, and Quality Assurance | NOT STARTED | 16 |
| 18 | Deployment and Documentation | NOT STARTED | 17 |

## Stage details

### 01 — Repository Inspection and Project Planning
Inspect the environment and repository, create the monorepo structure, and write the README and the `docs/` planning documents.
**Verify:** repository state recorded, all 18 stages listed in the README, setup instructions match the actual tool versions.

### 02 — Mobile Application Foundation
Expo + TypeScript + Expo Router + NativeWind in `mobile/`. Theme, reusable components, loading/empty/error states, and the screens Welcome, Login, Registration, Home, Vehicle details, Customer profile. Sample vehicles are allowed (labelled as prototype data).
**Verify:** app starts, navigation works, `tsc --noEmit` passes, styling renders.

### 03 — Python Backend Foundation
FastAPI app in `backend/` with venv, settings from environment variables, router structure, `/health`, validation and error handlers, Pytest, `.env.example`.
**Verify:** server starts, `/health` returns 200, `/docs` reachable in development, pytest passes.

### 04 — PostgreSQL and Database Foundation
SQLAlchemy 2.x, Alembic, session management, core tables (users, roles, user_roles, owner_profiles, customer_profiles, vehicles, vehicle_images, vehicle_prices, bookings, payments, deliveries, audit_logs) with constraints.
**Verify:** migrations upgrade and downgrade cleanly, database tests pass against a real test database.

### 05 — Authentication and Authorisation
Registration (renter and owner), login and logout, Argon2/bcrypt hashing, JWT access plus refresh tokens, RBAC, email verification (provider adapter), password reset, suspension, and an admin-creation CLI.
**Verify:** security tests for unauthenticated and wrong-role access.

### 06 — Customer Eligibility and Document Verification
Date of birth and the 18+ rule, ID and licence uploads to private storage, verification statuses and reviewer workflow, decision records, access control.
**Verify:** self-approval impossible, document access restricted, eligibility derived from database records.

### 07 — Owner Profiles and Vehicle Registration
Owner profile, vehicle CRUD, photos, vehicle documents, status workflow, availability blocks.
**Verify:** approval-workflow tests, unapproved vehicles hidden from public listings.

### 08 — Administrator Pricing Management
Admin approve, reject, and suspend endpoints. Append-only `Decimal` ZAR pricing with history and audit.
**Verify:** only admins can set prices, price snapshots on bookings unaffected by changes, pricing calculation tests.

### 09 — Customer Marketplace
Mobile app connected to the backend: approved listings, photos, details, official prices, search and filters, privacy-safe owner information.
**Verify:** data comes from the API, error states handled.

### 10 — Booking and Availability
Date selection, eligibility and availability checks, backend price calculation, holds with expiry, database exclusion constraint against overlaps, cancellation, history, state machine.
**Verify:** concurrency test proves no double-booking, invalid transitions rejected.

### 11 — Payment Integration
Provider selection (OPEN-8), backend initiation, payment records, signed webhook verification, idempotency, failures, refunds, reconciliation, payout documentation.
**Verify:** sandbox or test-double tests only. **No real transactions without approval.**

### 12 — Delivery Management
Delivery records, assignment, scheduling, status machine, handover and return records, exceptions, audit.

### 13 — Google Maps and Live Tracking
Maps in the app, location permissions, authorised location updates, WebSocket broadcast, ETA, stale and reconnect handling, tracking stops when the delivery ends.
**Requires:** Google Maps Platform API keys.

### 14 — Customer and Owner Dashboards
Mobile dashboards for bookings, payments, deliveries, verification, owner vehicles, availability, and earnings.

### 15 — Administrator Dashboard
React + TypeScript + Tailwind web app in `admin-dashboard/` covering all admin workflows, with charts drawn from real aggregates.

### 16 — Notifications and Communication
Email and Expo push notifications for booking, payment, verification, delivery, cancellation, and return events, with failure handling.

### 17 — Security, Testing, and Quality Assurance
Full test, lint, and type-check runs, dependency audit, secret scan, concurrency, webhook, access-control and migration tests.

### 18 — Deployment and Documentation
Production configuration, logging and monitoring, backups, deployment and rollback procedures, mobile production builds. **No deployment without approval.**
