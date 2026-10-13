# Car Rental Platform (South Africa)

A marketplace that connects vehicle owners with renters in South Africa,
with administrator-controlled pricing, renter verification, ZAR payments, and
live delivery tracking.

> **Current state:** Stages 01–11 complete. Renters can register and log in in the
> mobile app, browse real listings, choose dates, see the official price, **reserve a
> car and pay for it** (Paystack checkout, verified by the backend), then view, cancel
> and get refunds for their bookings. The FastAPI backend (PostgreSQL) enforces
> eligibility, availability, official pricing, the booking state machine and payment
> verification. Payments run in **test mode only** until live keys are approved. Commands for
> later stages are marked *planned* and will be confirmed when each stage is implemented.

---

## 1. Project Overview

- **Owners** register and list vehicles. An administrator approves them before they are shown publicly.
- **Renters** register, submit a South African ID and driving licence for verification, then book and pay for approved vehicles.
- **Administrators** (platform owner/CEO and authorised staff) set all official rental prices in ZAR and oversee users, vehicles, bookings, payments, deliveries, and audit logs.
- Renters follow their vehicle's delivery on a live map, similar to Bolt or Uber.

Detailed requirements: [docs/requirements.md](docs/requirements.md).
Business rules: [docs/business-rules.md](docs/business-rules.md).

## 2. Project Goals

1. Production-oriented, secure, POPIA-aware platform for the South African market.
2. The backend is the single source of truth for roles, prices, eligibility, availability, payment status, and delivery authorisation.
3. Exact monetary handling in ZAR with complete price and audit history.
4. No double bookings, even under concurrent requests.
5. Verified, idempotent payment processing through a South African provider.
6. Each stage is built incrementally and tested before it is marked complete.

## 3. Technology Stack

| Area | Technology |
|------|------------|
| Mobile | Expo SDK 57 (React Native 0.86, React 19.2), TypeScript 6, Expo Router 57, NativeWind 4.2.7 + Tailwind CSS 3.4, expo-image, ESLint 9 (`eslint-config-expo`), Jest 29 + jest-expo 57 + React Native Testing Library 14. Planned: Expo Location, `react-native-maps` (Google provider), WebSocket client |
| Backend | Python 3.12, FastAPI 0.143, Pydantic 2.14, pydantic-settings 2.15, SQLAlchemy 2.1.4, Alembic 1.20, psycopg 3.3, argon2-cffi 25.1 (Argon2id), PyJWT 2.15, Uvicorn 0.54, Pytest 9.1, Ruff 0.17. Planned: WebSockets (Stage 13) |
| Database | PostgreSQL 16 (local development: Docker Compose, `postgres:16-alpine`) |
| Admin dashboard | React, TypeScript, Vite, Tailwind CSS, Recharts |
| Payments | Paystack (ZAR), behind a `PaymentProvider` interface; test keys only until live payments are approved (OPEN-8). Mobile checkout via expo-web-browser |
| Maps | Google Maps Platform (Maps SDKs, Routes API) |
| Tooling | Git, npm, Python venv, ESLint, TypeScript, environment variables |

Exact dependency versions are pinned when each application is created.

## 4. System Architecture

```
Mobile app (Expo) ──HTTPS/WSS──►┐
                                ├──► FastAPI backend ──► PostgreSQL
Admin dashboard (React) ─HTTPS─►┘         │
                                          ├──► Private document storage
Payment provider ──signed webhook──►      ├──► Payment provider API
                                          └──► Google Maps / Email / Push
```

The backend is layered as routes → services (business rules) → repositories/models,
with external services behind adapters. Full details:
[docs/architecture.md](docs/architecture.md).

## 5. Repository Structure

```
car-rental/
├── README.md               # This file — central document and stage tracker
├── .gitignore              # Ignores .env files, venvs, node_modules, build output, uploads
├── docs/
│   ├── requirements.md     # Functional and non-functional requirements, open decisions
│   ├── document-handling.md # Identity documents: storage, access, logging, retention
│   ├── business-rules.md   # Rules enforced by the backend
│   ├── architecture.md     # Components, layering, data model plan, providers
│   └── development-roadmap.md
├── mobile/                 # Expo app (Stage 02) — see mobile/README.md
│   ├── src/app/            # Expo Router screens
│   ├── src/components/     # Reusable UI components
│   ├── src/services/       # Backend API calls (marketplace)
│   ├── __tests__/          # Jest tests
│   └── tailwind.config.js  # Theme tokens
├── backend/                # FastAPI service (Stage 03) — see backend/README.md
│   ├── app/                # main.py, cli.py, core/, api/, db/, models/, repositories/, services/, integrations/, schemas/
│   ├── migrations/         # Alembic migrations
│   ├── tests/              # Pytest suite (tests/db/ uses real PostgreSQL)
│   └── .env.example        # Placeholder settings (copy to .env)
├── docker-compose.yml      # Local PostgreSQL 16 (dev + test databases)
├── infra/postgres/init/    # Creates the test database on first start
├── .env.example            # Root settings for docker compose (copy to .env)
└── admin-dashboard/        # React admin — empty placeholder until Stage 15
```

## 6. Development Roadmap

The project is built in 18 stages, in order. A stage is marked COMPLETE only
after its acceptance criteria have been verified. Stage details and
dependencies: [docs/development-roadmap.md](docs/development-roadmap.md).

## 7. Stage Completion Tracker

| Stage | Name | Status | Verification |
|-------|------|--------|--------------|
| 01 | Repository Inspection and Project Planning | [x] COMPLETE | Repo inspected; docs and structure checked |
| 02 | Mobile Application Foundation | [x] COMPLETE | tsc, ESLint, expo-doctor, 3-platform bundle, web smoke test (16/16) |
| 03 | Python Backend Foundation | [x] COMPLETE | pytest 19/19, ruff, live server checks, clean-venv install |
| 04 | PostgreSQL and Database Foundation | [x] COMPLETE | pytest 62/62 on PostgreSQL 16, migration round-trip, alembic check, concurrency test |
| 05 | Authentication and Authorisation | [x] COMPLETE | pytest 129/129, 6 mutation checks, live E2E flow, fresh-venv install |
| 06 | Customer Eligibility and Document Verification | [x] COMPLETE | pytest 179/179, 8 mutation checks, live upload/review E2E, fresh-venv install |
| 07 | Owner Profiles and Vehicle Registration | [x] COMPLETE | pytest 219/219, 9 mutation checks, live owner→admin E2E |
| 08 | Administrator Pricing Management | [x] COMPLETE | pytest 259/259, 11 mutation checks, live E2E incl. direct-SQL tamper test |
| 09 | Customer Marketplace | [x] COMPLETE | backend pytest 293/293; mobile jest 19/19; app↔API browser E2E 24/24; 13 + 5 mutation checks |
| 10 | Booking and Availability | [x] COMPLETE | backend 426/426 (5 consecutive full runs); mobile 36/36; 30/30 concurrency stress; full renter journey E2E |
| 11 | Payment Integration | [x] COMPLETE | backend 476/476; mobile 40/40; 9/10 mutations caught (1 equivalent); live E2E 16/16 against a Paystack stand-in |
| 12 | Delivery Management | NOT STARTED | Not tested |
| 13 | Google Maps and Live Tracking | NOT STARTED | Not tested |
| 14 | Customer and Owner Dashboards | NOT STARTED | Not tested |
| 15 | Administrator Dashboard | NOT STARTED | Not tested |
| 16 | Notifications and Communication | NOT STARTED | Not tested |
| 17 | Security, Testing, and Quality Assurance | NOT STARTED | Not tested |
| 18 | Deployment and Documentation | NOT STARTED | Not tested |

### Stage 01: Repository Inspection and Project Planning

Status: COMPLETE (2026-10-13)

Implemented:
- Inspected the repository: a new Git repo on `main` with no commits and no files, so there was no existing work to preserve.
- Recorded the environment: Ubuntu 24.04.5, Node 20.20.2, npm 10.8.2, Python 3.12.3, Git 2.43.0, PostgreSQL 16.15 (running), Docker 29.8.1.
- Monorepo structure: `mobile/`, `backend/`, `admin-dashboard/`, `docs/`.
- Planning documents: requirements (with open business decisions), backend-enforced business rules, architecture, roadmap.
- `.gitignore` that excludes `.env*` (but keeps `.env.example`), keys, venvs, `node_modules`, native build output, and private uploads.

Files changed:
- `README.md`, `.gitignore`, `docs/requirements.md`, `docs/business-rules.md`, `docs/architecture.md`, `docs/development-roadmap.md`, `mobile/.gitkeep`, `backend/.gitkeep`, `admin-dashboard/.gitkeep`

Verification:
- `git status`: clean, empty repo before the work. After the work, only the files listed above are untracked.
- README has all 20 required sections (checked with `grep '^## '`).
- All 18 stages are in the README tracker and in `docs/development-roadmap.md`, and the statuses match (checked with a scripted `diff`).
- Every `docs/` link in the README points to an existing file.
- `git check-ignore`: `.env`, `backend/.env`, `mobile/.env.local`, `backend/storage/*`, and `mobile/android/` are ignored. `backend/.env.example` is tracked.
- No code, tests, or builds exist in this stage, so none were run.

Outstanding limitations:
- Open business decisions (OPEN-1 to OPEN-9 in `docs/requirements.md`) need answers before Stages 06, 08, 10, 11, and 12.
- The payment provider is not chosen. Candidate capabilities must be confirmed with the providers.

Next stage:
- Stage 02: Mobile Application Foundation.

### Stage 02: Mobile Application Foundation

Status: COMPLETE (2026-10-13)

Implemented:
- Expo SDK 57 app in `mobile/` (from `create-expo-app@5.0.0`, `default@sdk-57` template), TypeScript strict mode, `@/*` path alias.
- NativeWind 4.2.7 with Tailwind CSS 3.4 (Babel preset, Metro `withNativeWind`, `global.css`, type declarations). Brand, ink, surface, and status colour tokens are in `tailwind.config.js`.
- Expo Router navigation: root Stack → Welcome (`/`), `(auth)` stack (`/login`, `/register`), `(tabs)` (`/home`, `/profile`), `/vehicles/[id]`, and a not-found route.
- Reusable components: `Screen`, `Button` (primary, secondary, ghost, loading), `TextField` (with error text), `Badge`, `Notice`, `LoadingState`, `EmptyState`, `ErrorState`, `VehicleCard`, `VehiclePhoto` placeholder.
- `useAsync` hook for loading, success, and error states with retry.
- Screens: Welcome, Login, Registration (renter or owner choice; client-side validation of email, SA mobile number, and password), Home (vehicle list with search plus empty and error states), Vehicle details (specs, features, owner first name only, booking disabled), Customer profile (verification status badges).
- `formatZar()` formats ZAR decimal strings (e.g. `"1450.00"` → `R 1 450.00`) without float conversion.
- Branding placeholders: app name "CarHire SA", slug `car-rental`, scheme `carrental`, bundle ID and package `za.co.carhire.placeholder`.
- Removed template example code, unused dependencies (`@expo/ui`, `expo-glass-effect`, `expo-symbols`, `expo-web-browser`, `expo-device`), the template `LICENSE`, and `scripts/reset-project.js`.

Prototype data (clearly labelled):
- `mobile/src/data/sample-vehicles.ts` holds 6 fictional vehicles and a preview profile. All data access goes through `mobile/src/services/vehicles.ts`, which Stage 09 replaces with backend API calls.
- Login and registration only validate the form and then open Home. **No authentication exists** (Stage 05). Every screen that uses preview data shows a "Preview" notice.

Files changed:
- New: `mobile/` (`package.json`, `package-lock.json`, `app.json`, `tsconfig.json`, `babel.config.js`, `metro.config.js`, `tailwind.config.js`, `eslint.config.js`, `nativewind-env.d.ts`, `README.md`, `.gitignore`, `src/**`, `assets/**`).
- Template-provided and kept: `mobile/AGENTS.md`, `mobile/CLAUDE.md` (Expo guidance for AI assistants), `mobile/.claude/settings.json` (enables the official Expo Claude Code plugin), `mobile/.vscode/` (git-ignored by the root `.gitignore`).
- Removed: `mobile/.gitkeep`.
- Modified: `README.md`, `docs/development-roadmap.md`.

Verification (run in `mobile/`):
- `npm run typecheck` (`tsc --noEmit`): passed, 0 errors.
- `npm run lint` (`expo lint`): passed, 0 problems. A `react-hooks/set-state-in-effect` error in `useAsync` was fixed by deriving the loading state instead of disabling the rule.
- `npx expo-doctor`: 21/21 checks passed.
- `npx expo export --platform android --platform ios --platform web`: all three bundles built (Android 3.8 MB, iOS 3.6 MB Hermes bytecode; web 1.2 MB JS plus 11 KB Tailwind CSS).
- Browser smoke test (`expo start --web`, headless Chromium, 390×844 viewport): **16/16 checks passed**. Checks covered: Welcome renders; brand colour applied by NativeWind; Welcome→Login; login validation; Login→Home; 6 sample vehicles listed; search filters to 1; empty search state; Home→details (R 750.00); owner first name only; unknown vehicle shows not-found; profile shows 2 "Not submitted" badges; Log out→Welcome; registration validation; unknown route shows not-found; no console or page errors.
- `formatZar` edge cases (grouping, padding, negative, invalid input rejected): 8/8 passed (ad-hoc script; no mobile test runner yet).
- Bug found and fixed: under Tailwind's default `darkMode: 'media'`, NativeWind 4's web runtime threw "Cannot manually set color scheme". Fixed by setting `darkMode: 'class'`, which fits the light-only theme.

Outstanding limitations:
- **Not run on a physical device or emulator.** No Android emulator or `adb` is available on the development machine. Android and iOS bundles compile, but native rendering still needs a manual check with Expo Go (`npm start`, then scan the QR code).
- No automated mobile test runner (e.g. `jest-expo`) yet. Proposed for Stage 09, when real API logic arrives.
- `npm audit` reports 36 advisories (15 moderate, 21 high) from 5 root causes (`braces`, `decode-uri-component`, `node-forge`, `postcss-selector-parser`, `uuid`). All are in Expo CLI and config-plugin build tooling, not in app runtime code. The only automatic fix is `npm audit fix --force`, which downgrades Expo, so it was not applied. Review in Stage 17.
- Light theme only. Vehicle photos are icon placeholders. App icon and splash are template placeholders.
- On web, the browser draws its default focus outline on the search input (cosmetic, web only).

Next stage:
- Stage 03: Python Backend Foundation.

### Stage 03: Python Backend Foundation

Status: COMPLETE (2026-10-13)

Implemented:
- FastAPI app in `backend/` using an app factory (`create_app(settings)`) and a `lifespan` handler (Starlette 1.x no longer supports `on_event`).
- Configuration via `pydantic-settings`: `APP_ENV` (development/test/staging/production, validated), `APP_NAME`, `LOG_LEVEL` (validated), `CORS_ORIGINS` (comma-separated). Values come from environment variables or `backend/.env`. Nothing secret is hardcoded, and there are no secrets yet.
- Routing: `/api/v1` prefix through `app/api/router.py`, with one module per resource in `app/api/routes/`.
- `GET /api/v1/health` returns status, service, version, and environment.
- API docs (`/docs`, `/redoc`, `/api/v1/openapi.json`) are enabled outside production and disabled when `APP_ENV=production`.
- Error handling: a consistent `{"error": {code, message, details?}}` envelope for 404/405/HTTP errors, validation errors (422, submitted values never echoed back), an `AppError` base class for business errors, and unhandled exceptions (generic 500; full traceback logged on the server only).
- CORS restricted to the configured origins.
- Pinned dependencies (`requirements.txt` runtime, `requirements-dev.txt` dev tools), Ruff lint and format config, Pytest config in `pyproject.toml`, and `backend/.env.example`.

Files changed:
- New: `backend/app/**` (`main.py`, `core/config.py`, `core/errors.py`, `core/logging.py`, `api/router.py`, `api/routes/health.py`, `schemas/common.py`, `schemas/health.py`), `backend/tests/**` (`conftest.py`, `test_health.py`, `test_docs.py`, `test_errors.py`, `test_config.py`), `backend/requirements.txt`, `backend/requirements-dev.txt`, `backend/pyproject.toml`, `backend/.env.example`, `backend/README.md`.
- Removed: `backend/.gitkeep`.
- Modified: `README.md`, `docs/development-roadmap.md`.
- Local only (git-ignored): `backend/.venv/`, `backend/.env` (copied from `.env.example`).

Verification (run in `backend/`):
- `pytest`: **19 passed**, 0 failed, 0 warnings. Tests cover health; docs on and off by environment; 404/405 envelopes; validation errors (including malformed JSON and not echoing a password); `AppError` mapping; 500 hiding internal details while still logging them; settings loaded from environment; invalid settings rejected; CORS allow and deny.
- `ruff check .`: all checks passed. `ruff format --check .`: 19 files formatted.
- `pip check`: no broken requirements.
- Clean install: a fresh venv with `pip install -r requirements-dev.txt` passed `pip check`, pytest 19/19, and Ruff.
- Live server (`uvicorn app.main:app --port 8000` with `.env` from `.env.example`): `/api/v1/health` → 200 `{"status":"ok",...,"environment":"development"}`; `/docs` 200; `/redoc` 200; OpenAPI 3.1.0 lists `/api/v1/health`; unknown route → 404 envelope; CORS preflight from `http://localhost:8081` allowed. With `APP_ENV=production`: health 200, `/docs` 404, OpenAPI 404.
- Bugs found and fixed during the stage: the health route read the global settings instead of the app instance's settings (now `app.state.settings` through `get_app_settings`); Starlette deprecated `httpx` for its test client, so the dev dependency is now `httpx2`.

Outstanding limitations:
- No database yet. The health check does not test database connectivity (added in Stage 04).
- No authentication, request IDs, or rate limiting yet (Stages 05 and 17).
- Logging is plain text to stderr. Structured or JSON logging is planned for Stage 18.
- The mobile app is not yet connected to the backend (Stage 09).

Next stage:
- Stage 04: PostgreSQL and Database Foundation.

### Stage 04: PostgreSQL and Database Foundation

Status: COMPLETE (2026-10-13)

Implemented:
- PostgreSQL 16 through Docker Compose (`car-rental-db`, `127.0.0.1:5433`, persistent volume, health check). An init script creates the separate `car_rental_test` database. The password comes from the git-ignored root `.env`.
- SQLAlchemy 2.1 (sync, psycopg 3) with engine, session factory, and a `get_db` dependency. Services commit explicitly and failed requests roll back. Pool uses pre-ping.
- `DATABASE_URL` is a required setting, stored as `SecretStr` and validated to be `postgresql+psycopg://`.
- `/api/v1/health` now checks the database: 200 `"database": "ok"`, or 503 `"degraded"`/`"unavailable"`.
- Alembic configured with the URL read from settings (never from `alembic.ini`), a deterministic constraint naming convention, and dated migration file names.
- Migration `5c4b7a10d711` creates the 12 core tables (users, roles, user_roles, owner_profiles, customer_profiles, vehicles, vehicle_images, vehicle_prices, bookings, payments, deliveries, audit_logs), seeds roles ADMIN/OWNER/RENTER, enables `btree_gist`, and adds the append-only trigger on `audit_logs`.
- Constraints: UUID keys; FKs with deliberate `CASCADE`/`RESTRICT`/`SET NULL`; enum CHECKs; exact `NUMERIC(12,2)` ZAR money; booking price-snapshot consistency; **an exclusion constraint against overlapping bookings**; one successful payment per booking; unique provider references; one delivery per booking; case-insensitive unique email; VIN, registration, coordinate, and timestamp consistency checks.

Files changed:
- New: `docker-compose.yml`, `.env.example` (root), `infra/postgres/init/01-create-test-database.sh`, `backend/alembic.ini`, `backend/migrations/` (`env.py`, `script.py.mako`, `versions/2026_10_13_1112-5c4b7a10d711_create_core_tables.py`), `backend/app/db/` (`base.py`, `session.py`), `backend/app/models/` (`enums.py`, `user.py`, `vehicle.py`, `booking.py`, `payment.py`, `delivery.py`, `audit_log.py`, `__init__.py`), `backend/tests/db/` (`factories.py`, `test_migrations.py`, `test_constraints.py`, `test_concurrency.py`, `test_session.py`).
- Modified: `backend/app/core/config.py`, `backend/app/main.py`, `backend/app/api/routes/health.py`, `backend/app/schemas/health.py`, `backend/requirements.txt`, `backend/pyproject.toml`, `backend/.env.example`, `backend/README.md`, `backend/tests/conftest.py`, `backend/tests/test_config.py`, `backend/tests/test_health.py`, `docs/architecture.md`, `docs/business-rules.md`, `docs/development-roadmap.md`, `README.md`.
- Local only (git-ignored): root `.env` (generated random dev DB password), `backend/.env`.

Verification:
- `pytest -ra`: **62 passed, 0 skipped, 0 failed** against PostgreSQL 16.15. Covered:
  - Migrations: all tables created; `compare_metadata` finds no model/migration drift; downgrade to base then upgrade again; roles seeded.
  - Users, roles, and profiles: case-insensitive unique email; suspension consistency; enum CHECK; role assignment and cascade; customer profile defaults.
  - Vehicles: VIN, registration, and uniqueness rules; approval timestamp required.
  - Money: exact `Decimal` round trip; invalid prices rejected; referenced price history cannot be deleted.
  - Bookings: price-snapshot consistency; overlap rejection; back-to-back allowed; cancelled, expired, and completed bookings release their dates; re-activating into a conflict rejected.
  - Payments and deliveries: single successful payment; provider-reference uniqueness; one delivery per booking with valid coordinates.
  - Audit: UPDATE/DELETE blocked; user with audit history cannot be deleted.
  - Concurrency: two threads committing overlapping bookings at the same moment, one commits and the other is rejected by `ex_bookings_vehicle_period_overlap`.
  - Sessions and health: failed request rolls back; committed work persists; health returns 503 when the database is unreachable.
- Mutation check: with the exclusion constraint removed from the migration, the 3 overlap and concurrency tests **failed** as expected. The constraint was then restored.
- `alembic upgrade head`, `downgrade base`, `upgrade head` on the development database succeeded. `alembic check`: "No new upgrade operations detected". `alembic upgrade head --sql` renders offline.
- Live server: health 200 with the database up, 503 after `docker stop car-rental-db`, back to 200 after restart without restarting the API. The database password does not appear in server logs.
- `ruff check .` and `ruff format --check .` passed. `pip check` clean. A fresh venv from `requirements-dev.txt` passes 62/62.
- Problems found and fixed during the stage:
  - Autogenerate emitted duplicate enum CHECK constraints with the same name.
  - `btree_gist` was missing.
  - `func.lower("email")` would have indexed a constant string.
  - `audit_logs.actor_user_id ON DELETE SET NULL` conflicted with the append-only trigger, so it is now `RESTRICT`.

Outstanding limitations:
- No repositories or services yet. They are added with the first features that use them (Stage 05 onward).
- Expired `PENDING_PAYMENT` holds keep blocking dates until the booking service marks them `EXPIRED` (Stage 10). The database cannot compare against `now()` in a constraint.
- Tables for later features (documents, payment events, refunds, location updates, refresh tokens, and so on) are added in their stages.
- Docker Compose is for local development only. Production database hosting, backups, and TLS are covered in Stage 18.

Next stage:
- Stage 05: Authentication and Authorisation.

### Stage 05: Authentication and Authorisation

Status: COMPLETE (2026-10-13)

Implemented:
- Renter and owner registration (`account_type` limited to RENTER or OWNER). Creates the user, role, and matching profile, then sends a verification email. Email is normalised to lower case, and SA mobile numbers to `+27…`.
- Login, refresh, logout (one session), and logout-all.
- Password hashing with Argon2id. Hashes are upgraded on login when the parameters change.
- 15-minute HS256 access tokens carrying only the user id and `token_version`. Issuer, audience, expiry, and algorithm are enforced.
- 30-day refresh tokens stored as SHA-256 hashes. They rotate on every use, and re-use of a rotated token revokes that session family.
- Role-based access control: `get_current_user` reloads the user and checks status on every request; `require_roles(...)`; `AdminUser` and `OwnerUser` dependencies. Roles never come from the token or the client, and request bodies reject unknown fields.
- Email verification (single-use 48-hour links; resend invalidates older links) and password reset (30-minute single-use links). Reset responses are identical for unknown emails, and a reset signs the user out everywhere and is audited.
- Account suspension and reactivation by administrators: immediate effect, audited, cannot suspend yourself. Plus an admin user list.
- Controlled administrator creation: `python -m app.cli create-admin` (interactive hidden password or `--password-stdin`), audited. There is no HTTP route to create admins.
- Email adapter: `SmtpEmailSender` (STARTTLS, any SMTP provider) for staging and production; `ConsoleEmailSender` for development (refused in production); in-memory sender for tests.
- Migration `0ab336768893`: `refresh_tokens`, `user_action_tokens`, `users.token_version`.
- Migration tooling fix: a `render_item` hook in `migrations/env.py` plus a modernised `script.py.mako`, so autogenerated migrations no longer duplicate enum CHECK constraints and pass Ruff as generated.

Files changed:
- New:
  - `backend/app/core/security.py`, `backend/app/api/deps.py`, `backend/app/cli.py`
  - Routes: `backend/app/api/routes/{auth,users,owners,admin_users}.py`
  - Services, repositories, schemas, models: `backend/app/services/{auth,accounts,audit}.py`, `backend/app/repositories/users.py`, `backend/app/schemas/auth.py`, `backend/app/models/auth_token.py`
  - `backend/app/integrations/email.py`
  - Migration: `backend/migrations/versions/2026_10_13_1144-0ab336768893_add_authentication_tokens.py`
  - Tests: `backend/tests/auth/` (conftest plus 7 test modules), `backend/tests/test_email.py`
- Modified:
  - Backend: `app/core/config.py`, `app/core/errors.py`, `app/main.py`, `app/api/router.py`, `app/models/{__init__,enums,user}.py`
  - Migrations: `migrations/env.py`, `migrations/script.py.mako`
  - Config: `requirements.txt`, `pyproject.toml`, `.env.example`
  - Tests: `tests/conftest.py`, `tests/test_config.py`, `tests/test_docs.py`, `tests/db/test_migrations.py`
  - Docs: `backend/README.md`, `docs/business-rules.md`, `docs/development-roadmap.md`, `README.md`
- Local only (git-ignored): `backend/.env` now holds a generated 86-character `JWT_SECRET_KEY`.

Verification:
- `pytest -ra`: **129 passed, 0 skipped, 0 failed** (67 of them new). Covered:
  - Registration rules, including attempts to choose ADMIN, roles, or status (all rejected).
  - Hashing; JWT forgery and expiry (`alg=none`, foreign secret, wrong issuer or audience, HS512, tampering, wrong type).
  - Refresh rotation, reuse detection, and expiry.
  - Logout and logout-all.
  - Email verification and password reset (single use, expiry, latest-link-only, purpose separation, no enumeration).
  - An endpoint sweep built from the OpenAPI schema, asserting that **every non-public endpoint returns 401 without a token**.
  - Renter→owner 403, renter/owner→admin 403.
  - Suspension and reactivation flow with audit; the status check is tested on its own.
  - CLI admin creation and input validation.
  - SMTP adapter (STARTTLS, login, failures).
  - Email failure does not undo registration.
- Mutation checks: removing the role check, the token-version check, the status check, or refresh-reuse revocation, or allowing an extra JWT algorithm, each made tests **fail**. The status-check mutation first went undetected, so a dedicated test was added.
- Live end-to-end run (temporary `car_rental_e2e` database, real uvicorn, then dropped):
  - CLI admin creation.
  - Registration (ADMIN attempt → 422).
  - Console email link → verification.
  - RBAC matrix:

    | Endpoint | renter | owner | admin | anonymous |
    |----------|--------|-------|-------|-----------|
    | owner endpoint | 403 | 200 | — | — |
    | admin list | 403 | 403 | 200 | 401 |

  - Suspension → access 401 / refresh 401 / login 403; reactivation → login 200.
  - Audit trail `admin.created`, `user.suspended`, `user.reactivated`.
  - 3/3 password hashes Argon2id; 0 plaintext passwords in server logs.
- `ruff check .` and `ruff format --check .` passed. `alembic check`: no drift. `pip check` clean. Fresh venv from `requirements-dev.txt`: 129 passed.
- Problems found and fixed during the stage:
  - Production mode could not start with the console mailer, so an SMTP adapter was added.
  - The CLI accepted invalid emails.
  - FastAPI 0.143 nests included routers, so the route sweep now uses the OpenAPI schema.
  - Duplicate enum CHECKs in autogenerate.

Outstanding limitations:
- **No rate limiting or login lockout yet.** Brute-force protection is planned for Stage 17 (needs shared storage such as Redis when running more than one instance).
- After a single-session logout, that session's access token stays valid until it expires (at most 15 minutes). Logout-all, password reset, and suspension invalidate access tokens immediately.
- Registration reveals that an email is already registered (409) as a usability trade-off. Login and password reset do not.
- Logging in does not require a verified email. Booking eligibility (Stage 06/10) will require it, as BR-2 states.
- SMTP delivery is tested against a fake SMTP server only. No real provider account is configured; one is needed before staging or production.
- The mobile app's login and registration screens are not yet connected to these endpoints (Stage 09 connects the app; tokens will be stored with `expo-secure-store`).

Next stage:
- Stage 06: Customer Eligibility and Document Verification.

### Stage 06: Customer Eligibility and Document Verification

Status: COMPLETE (2026-10-13)

Defaults chosen for open decisions (changeable later): minimum age **18** (configurable through `MIN_RENTER_AGE`, OPEN-4), **SA ID only** (OPEN-5), **manual administrator review** (OPEN-9).

Implemented:
- **Date of birth:** must be at least the minimum age (calculated in South African time). It is locked while the ID is pending or approved.
- **Document submission** (multipart, `RENTER` only) for `SA_ID` and `DRIVING_LICENCE`, with a front and optional back file:
  - File type is detected from the content (JPEG, PNG, PDF); client names and types are ignored.
  - Size limit, with 413 for larger files.
  - SHA-256 is recorded, and files are cleaned up if the submission fails.
- **SA ID checks:** 13 digits, Luhn check digit, citizenship digit, and birth date matching the profile.
- **Full ID and licence numbers are never stored.** Only a keyed HMAC and the last 3 digits are kept.
- **One SA ID per approved account:** a check at submission plus a partial unique index, which also catches approvals made at the same time.
- **Private storage:** `DocumentStorage` interface; `LocalDocumentStorage` (random UUID keys, `0700` directories, `0600` files, path-traversal safe) and an in-memory version for tests.
- **Statuses:** `PENDING`, `APPROVED`, `REJECTED`, `REQUIRES_MORE_INFORMATION`, and `SUPERSEDED` (a newer submission replaced a pending one). The profile status mirrors the latest submission.
- **Administrator review:**
  - Queue, detail, and file viewer (**every view audited**).
  - Decision endpoint: a note is required unless approving; no self-review; only pending submissions; the reviewer can confirm the licence expiry; expired licences cannot be approved.
  - Decisions are recorded on the submission and in `audit_logs`.
- **Customer feedback:** own submissions with status and reviewer notes (numbers masked), plus download of own files.
- **`GET /customers/me/eligibility`:** checks from database records only, with every failing reason listed: role, account status, verified email, date of birth, minimum age at rental start, ID approved, licence approved, licence valid through the rental end.
- **Migration `b0aa20505e0f`:** `verification_submissions` and `verification_files`.
- **Documentation:** [docs/document-handling.md](docs/document-handling.md) covers the data inventory, verification rules, file handling, access, logging, keys, and proposed retention.

Files changed:
- New:
  - `backend/app/core/identity.py`, `backend/app/integrations/storage.py`
  - Models and schemas: `backend/app/models/verification.py`, `backend/app/schemas/verification.py`
  - Services: `backend/app/services/{verification,eligibility}.py`
  - Routes: `backend/app/api/routes/{customers,admin_verifications}.py`
  - Migration: `backend/migrations/versions/2026_10_13_1202-b0aa20505e0f_add_identity_and_licence_verification.py`
  - Tests: `backend/tests/api_fixtures.py` (shared fixtures moved from `tests/auth/conftest.py`), `backend/tests/verification/` (helpers plus 3 test modules)
  - `docs/document-handling.md`
- Modified:
  - Backend: `app/core/config.py`, `app/main.py`, `app/api/{deps,router}.py`, `app/models/{__init__,enums}.py`
  - Config: `requirements.txt` (`python-multipart`), `.env.example`
  - Tests: `tests/conftest.py`, `tests/auth/conftest.py`, `tests/auth/*` (imports), `tests/test_config.py`, `tests/db/test_migrations.py`
  - Docs: `backend/README.md`, `docs/business-rules.md`, `docs/requirements.md`, `docs/development-roadmap.md`, `README.md`
- Local only (git-ignored): `backend/.env` now holds a generated `DOCUMENT_HASH_KEY`; `backend/storage/private/`.

Verification:
- `pytest -ra`: **179 passed, 0 skipped, 0 failed** (50 new). Covered:
  - ID number rules and century inference; age edge cases (18th birthday today, leap day); HMAC keying and normalisation.
  - Storage permissions and path-traversal rejection.
  - Date-of-birth rules and lock; renter-only access.
  - Submission stored privately, with the **full ID number absent from every table and from DEBUG logs**.
  - Invalid ID and date-of-birth mismatch; a disguised executable, HTML, and an empty file rejected; 413 for oversized files; front side required; resubmission supersedes.
  - Licence submission and expiry.
  - Review queue admin-only; customers cannot change their status (no endpoint, and extra fields rejected).
  - Approve, reject (note required), more-info then resubmit; reviewer-confirmed licence expiry; expired licence not approvable; no self-review.
  - Duplicate ID blocked at submission **and** at approval time (database index → 409, not 500).
  - File access: owner 200 with `no-store`/`nosniff`; other renter 404; owner role 403; anonymous 401; admin view audited.
  - Eligibility: missing items listed, unreviewed uploads not enough, fully verified eligible, licence must outlast the rental, configurable minimum age, inactive account, owner 403, period validation.
  - The anonymous-access sweep covers the 10 new endpoints.
- Mutation checks: each of these changes made tests **fail**:
  - removing the owner check on file download
  - removing the self-review check
  - removing content sniffing
  - removing the duplicate-ID pre-check
  - removing the ID and date-of-birth match
  - removing the admin file-view audit
  - removing the ID-approval check from eligibility
  - removing the email-verified check from eligibility
- Live end-to-end run (temporary database and storage directory, real uvicorn, `curl` multipart uploads, then all removed):
  - Under-18 date of birth → 422; disguised `.jpg` executable rejected.
  - ID JPEG and licence PDF uploaded as `PENDING` with the masked number.
  - Admin queue; admin file view returned identical bytes; renter decision attempt → 403.
  - Both approved, then eligibility `{"eligible": true}`. Audit: `admin.created`, 2× `verification.document_viewed`, 2× `verification.approved`.
  - Files on disk mode `600` in `700` directories. **The full ID number appeared 0 times in a full database dump and 0 times in the server log.**
- `ruff check .` and `ruff format --check .` passed. `alembic check`: no drift. `pip check` clean. Fresh venv: 179 passed.
- Bug found and fixed: approving the same ID on a second account raised the unique-index error during an autoflush, before the guarded commit, giving a 500. The decision is now flushed inside the guarded block and returns 409. A dedicated test covers it.

Outstanding limitations:
- **Local document storage is not encrypted at rest.** Production needs an encrypted private object store (Stage 18).
- Retention periods in `docs/document-handling.md` are **proposals** that need a POPIA or legal advisor. Automatic purging of old files is not implemented yet.
- No external KYC or face-match: verification is manual review of the images (OPEN-9). Passports and foreign licences are not supported (OPEN-5). Licence-duration rules are not implemented (OPEN-4).
- Images are checked by file signature only. Pixel content is not decoded or re-encoded (e.g. to strip EXIF), and there is no malware scanning. Consider both before launch.
- Requests are not size-capped before multipart parsing. A reverse-proxy body limit is needed in production (Stage 18).
- Data-only `pg_dump` warns about the self-referencing `refresh_tokens.replaced_by_id` foreign key. Use full dumps for backups (Stage 18).
- The mobile app does not yet have the upload or verification screens (Stage 14, after it connects to the API in Stage 09).

Next stage:
- Stage 07: Owner Profiles and Vehicle Registration.

### Stage 07: Owner Profiles and Vehicle Registration

Status: COMPLETE (2026-10-13)

Business-rule revisions (recorded in [docs/business-rules.md](docs/business-rules.md) BR-3):
- **BR-3.4:** approval and official pricing are separate administrator actions. A vehicle is publicly listed only when it is both approved and priced. The original "price before approval" rule would have blocked approval until Stage 08.
- **BR-3.6:** only identity-changing edits trigger re-review (make, model, year, registration, VIN, transmission, fuel, seats, or a new registration certificate). Renewing the licence disc or insurance does not; expired documents hide the vehicle until renewed.

Implemented:
- **Owner profile:** update business name, city and province. The province must be one of the 9 SA provinces.
- **Vehicle registration** (`OWNER` only), starting as `DRAFT`:
  - Registration number normalised (upper case, no spaces or hyphens); VIN validated (17 characters, no I/O/Q).
  - Year from 1981 to next year; seats 2–16; province validated.
  - Price, status, ownership and approval fields are rejected.
  - Registration and VIN are unique (409).
- **Photos:** JPEG, PNG or WebP detected by content; at most 12; private storage; view and delete.
- **Vehicle documents:** `REGISTRATION_CERTIFICATE`, `LICENCE_DISC` (expiry), `INSURANCE` (expiry), `ROADWORTHY_CERTIFICATE`. Append-only: a renewal adds a newer current document. Compliance reports missing or expired documents.
- **Owner workflow:**
  - Submit for review, which requires a verified email, 3 or more photos, and valid required documents. The error lists exactly what is missing.
  - Withdraw from review; no edits while under review.
  - Material edits on approved vehicles go back to review (audited).
  - Delete `DRAFT` or `REJECTED` vehicles together with their files.
- **Availability:**
  - The owner can list or unlist an approved vehicle (`APPROVED` ⇄ `UNAVAILABLE`, audited).
  - Blocked date ranges (timezone-aware, future, not overlapping an existing reserving booking).
- **Administrator review:**
  - Queue (oldest submission first) with owner details and compliance.
  - Photo viewer, and document viewer (**audited**).
  - Approve (re-checks documents and that the owner is active; never your own vehicle) and reject (reason shown to the owner).
- **`publicly_listed_vehicles()`:** the single query the marketplace will use. It returns only `APPROVED` vehicles of active owners whose current licence disc and insurance have not expired.
- **Shared upload checks** (`app/services/uploads.py`), now also used by identity verification.
- **Migration `fcc33d6d54bd`:** `vehicle_documents`, `vehicle_availability_blocks`, photo size and checksum columns, `vehicles.submitted_at`. The CHECK constraint on the existing `vehicle_images` table was added by hand, because Alembic does not detect new CHECKs on existing tables.

Files changed:
- New:
  - `backend/app/services/{vehicles,uploads}.py`, `backend/app/schemas/vehicles.py`
  - Routes: `backend/app/api/routes/{owner_vehicles,admin_vehicles}.py`
  - Migration: `backend/migrations/versions/2026_10_13_1233-fcc33d6d54bd_add_vehicle_documents_availability_and_.py`
  - Tests: `backend/tests/vehicles/` (helpers plus 2 test modules)
- Modified:
  - Backend: `app/models/{vehicle,enums,__init__}.py`, `app/services/verification.py` (uses shared upload checks), `app/api/routes/owners.py`, `app/api/router.py`
  - Tests: `tests/db/test_migrations.py`
  - Docs: `backend/README.md`, `docs/business-rules.md`, `docs/development-roadmap.md`, `README.md`

Verification:
- `pytest -ra`: **219 passed, 0 skipped, 0 failed** (40 new). Covered:
  - Owner profile and province validation.
  - Draft registration and normalisation; owners cannot send price, status, owner or approval fields.
  - Invalid VIN, year, seats, province, registration and transmission.
  - Registration and VIN uniqueness across owners; renters 403; anonymous 401.
  - Owners cannot see or change other owners' vehicles (404).
  - Photo types by content (PDF, executable, empty rejected); photo limit.
  - Document expiry rules and renewals.
  - Submission readiness (every missing item reported); expired document blocks submission; no edits under review; withdraw.
  - Delete removes stored files; availability blocks (validation, overlap with a booking → 409).
  - Admin-only queue; approve with audit; reject with reason, then resubmit; no self-approval.
  - No approval with expired documents or an inactive owner; document views audited (photos not).
  - Material and cosmetic edits; registration certificate vs licence-disc renewal; list and unlist.
  - **Public visibility:** draft, pending, unavailable, expired newest insurance and suspended owner are all hidden; approved and compliant is shown.
- Mutation checks: each of these changes made tests **fail**:
  - ownership check
  - self-approval check
  - submission readiness
  - approval compliance
  - material-change re-review
  - public status filter
  - public owner-active filter
  - block/booking overlap check
  - unknown-field rejection
- Live end-to-end run (temporary database and storage, real uvicorn, `curl` multipart uploads, then removed):
  - Early submit listed the 4 missing items; 3 photos and 3 documents uploaded; submitted.
  - Admin queue; document view admin 200, renter 403, owner via the admin route 403; owner approving 403.
  - Approve → publicly listed 1; unlist 0, relist 1; date block 201.
  - Seat change → `PENDING_APPROVAL` → listed 0; re-approve → 1.
  - Audit trail of 8 entries in the right order; 6 stored files, all mode 600.
  - My first run failed only because the test script extracted the wrong email line; the app correctly refused submission from an unverified owner.
- `ruff check .` and `ruff format --check .` passed. `alembic check`: no drift. No new dependencies this stage.

Outstanding limitations:
- **No official prices yet** (Stage 08), so nothing can be listed in a marketplace. Administrator suspension of vehicles is Stage 08.
- No public marketplace endpoints or public photo URLs yet (Stage 09). Photos are served only to the owner and administrators.
- No photo reordering or "main photo" choice (photos keep upload order).
- Owner payout details are not collected (Stage 11).
- Unlisting a vehicle does not notify renters with existing bookings, and conflicts are not yet flagged to administrators (bookings exist from Stage 10; notifications in Stage 16).
- The same storage caveats as Stage 06 apply: local disk is unencrypted, there is no image re-encoding or malware scan, and a proxy body limit is needed in production.

Next stage:
- Stage 08: Administrator Pricing Management.

### Stage 08: Administrator Pricing Management

Status: COMPLETE (2026-10-13)

Default for an open decision: **OPEN-6 (VAT)** is undecided, so official prices are treated as final, VAT-inclusive rand amounts with no separate VAT line.

Implemented:
- **Administrator vehicle management:**
  - Approve and reject (from Stage 07).
  - **Suspend** with a reason: hidden at once, owner cannot edit or relist, audited.
  - **Reinstate:** back to `APPROVED` if previously approved, otherwise `DRAFT`.
- **Official pricing** (`ADMIN` only; administrators cannot price their own vehicles):
  - Daily rate, delivery fee, and deposit as exact `Decimal` ZAR.
  - Input limited to 2 decimal places and sane bounds; returned as exact strings.
  - A change reason is required.
  - Optional **scheduled** `effective_from`; no backdating; at most one price per vehicle per instant.
- **Price history:** append-only rows recording who set each price, when, why, and when it takes effect. The `is_current` flag is shown. **A database trigger blocks UPDATE and DELETE on `vehicle_prices`.**
- **Audit:** every price change is audited with the old and new values and the reason.
- **Price calculation** (`app/services/pricing.py`):
  - Every started 24 hours is one billable day.
  - Rental = rate × days; total = rental + delivery; the deposit is a separate line.
  - Rounded half-up to cents; `Decimal` throughout.
  - Admin quote endpoint.
- **Existing bookings keep their agreed price:** bookings store the full breakdown (Stage 04 schema), and prices cannot be edited.
- **Public listing now also requires an official price already in effect.** Owners see their vehicle's current price read-only.
- **Migration `5e999a61700a`:** vehicle suspension fields and their consistency CHECK (added by hand); a unique index on `(vehicle_id, effective_from)`; the append-only trigger.
- **Migration template fix:** generated migrations no longer contain a stray blank line that failed Ruff.

Files changed:
- New:
  - `backend/app/services/pricing.py`
  - `backend/migrations/versions/2026_10_13_1248-5e999a61700a_add_vehicle_suspension_and_append_only_.py`
  - Tests: `backend/tests/vehicles/test_pricing.py`
- Modified:
  - Backend: `app/models/vehicle.py`, `app/services/vehicles.py` (suspension, price-aware listing), `app/schemas/vehicles.py` (price and suspension schemas, `current_price`), `app/api/routes/admin_vehicles.py`
  - Migrations: `migrations/script.py.mako`
  - Tests: `tests/db/test_constraints.py` (price history is now fully append-only), `tests/vehicles/test_admin_review.py` (listing needs a price)
  - Docs: `backend/README.md`, `docs/business-rules.md` (BR-3.2, BR-4.3, BR-4.7–4.11), `docs/requirements.md`, `docs/development-roadmap.md`, `README.md`

Verification:
- `pytest -ra`: **259 passed, 0 skipped, 0 failed** (40 new). Covered:
  - **Calculation:** billable days (1 minute, exactly 24 h, 24 h + 1 s, 3 days + 1 h); invalid periods; exact breakdown; no float drift (0.10 × 3 = 0.30); half-up rounding.
  - **Access:** only admins set or view price history (owner and renter 403); owners cannot smuggle prices through vehicle endpoints.
  - **Validation:** 10 invalid inputs rejected (3 decimals, 0, negative, text, too large, negative fee, no reason, backdated, no timezone, currency field).
  - **Audit and history:** old and new values with reason and actor; history order and `is_current`.
  - **Scheduling:** a scheduled price does not apply early; duplicate instant rejected.
  - **Bookings:** a booking made at R650 keeps R650 / R1950 / R2100 after the price rises to R999, while new quotes use R999.
  - **Other:** quote needs a price; no self-pricing; a vehicle with only a future price is not listed.
  - **Suspension:** suspend and reinstate flow and rules; unapproved vehicles reinstate to `DRAFT`.
- Mutation checks: each of these changes made tests **fail**:
  - price route opened to any user
  - price audit removed
  - partial days not billed
  - banker's rounding
  - deposit added to total
  - backdating allowed
  - self-pricing allowed
  - future prices applied early
  - listing price condition removed
  - listing allowing future-only prices
  - money precision validation removed
  - The "future-only price" mutation was **not caught at first**, so a dedicated test was added.
- Live end-to-end run (temporary database, real uvicorn and `curl`, then removed):
  - Approved but unpriced → not listed; owner setting a price → 403; `480.005` → 422.
  - Price R480/R120/R1500 → listed; scheduled R560 not current; owner sees R480.
  - Quote for 3 days 2 hours → 4 days, R1920 + R120 = R2040 (deposit R1500 separate).
  - **Direct `UPDATE` and `DELETE` on `vehicle_prices` through `psql` were both refused by the trigger.**
  - Suspend → hidden and owner relist 409; reinstate → listed.
  - Audit `price_set 480.00 → 560.00 (Summer)`.
- `ruff check .` and `ruff format --check .` passed. `alembic check`: no drift. No new dependencies this stage.

Outstanding limitations:
- **Intermittent test failure:** one full-suite run in 10 reported `1 failed`, and it did not recur in 9 consecutive runs. *Resolved in Stage 10:* two causes were found and fixed (stale relationship collections in a shared session, and a PostgreSQL deadlock in a raw-insert concurrency test).
- VAT is not broken out (OPEN-6). Prices are a single VAT-inclusive amount.
- No public quote endpoint yet; renters will get quotes in the marketplace and booking flows (Stages 09 and 10).
- Suspending a vehicle does not yet affect existing bookings or notify anyone (Stages 10, 12, 16).
- Price changes are not announced to owners (Stage 16).
- Commission and owner payout split are not modelled (OPEN-1, Stage 11).

Next stage:
- Stage 09: Customer Marketplace.

### Stage 09: Customer Marketplace

Status: COMPLETE (2026-10-13)

Implemented:

**Backend (public, no login):**
- `GET /api/v1/vehicles`:
  - Search by make, model or city (case-insensitive; LIKE wildcards escaped).
  - Filters: city, province, transmission, fuel, minimum seats, minimum/maximum daily rate, and free between `available_from` and `available_to` (excludes reserving bookings and owner blocks).
  - Sorting (price ascending/descending, newest) and pagination with a total count.
- `GET /api/v1/vehicles/{id}`: details with photo URLs.
- Public photo endpoint, which serves photos **only while the vehicle is listed**.
- Availability: merged booked or blocked periods, with no reasons or renter data.
- Quote: official price breakdown plus whether the vehicle is free for the period.
- Everything is built on `publicly_listed_vehicles()` joined to the official price in effect, so unlisted vehicles return 404 everywhere.
- **Privacy:** no VIN, registration, owner surname, contact details or documents. The owner appears as first name and area only.
- **Development-only demo data:** `python -m app.cli seed-demo-data` creates 6 vehicles with generated placeholder photos and demo accounts that cannot log in. It is refused unless `APP_ENV=development` and is idempotent.
- The 5 public endpoints are added to the anonymous-access test's explicit public allow-list.

**Mobile:**
- API client (`src/lib/api.ts`):
  - Base URL from `EXPO_PUBLIC_API_URL`, with a 15 s timeout.
  - Backend error envelope → `ApiError` (`status`, `code`, `message`); friendly network and timeout messages.
- **The prototype vehicle data is removed.** Home and Vehicle details use `/api/v1/vehicles`. The profile placeholder remains (moved to `src/data/sample-profile.ts`, labelled) until Stage 14.
- **Home:**
  - Debounced server-side search; filter chips for gearbox, fuel and maximum price; sort chips.
  - Result count, pull-to-refresh, infinite scroll; stale responses are ignored.
  - Loading, empty ("Clear filters") and error ("Try again") states.
- **Vehicle details:**
  - Real photo carousel (expo-image, placeholder on failure).
  - Specs and description.
  - **Official pricing breakdown** (daily rate, delivery fee, deposit; ZAR, VAT-inclusive).
  - Unavailable dates (South African time).
  - Owner first name and area.
  - 404 → "Vehicle not found"; booking still disabled until Stage 10.
- **Mobile automated tests (new):** Jest with jest-expo 57 and React Native Testing Library 14, covering the API client, formatting, and the Home and Details screens with mocked services.

Files changed:
- Backend:
  - New: `app/services/marketplace.py`, `app/schemas/marketplace.py`, `app/api/routes/marketplace.py`, `app/demo_data.py`
  - New tests: `tests/marketplace/` (factory plus 30 tests), `tests/test_demo_data.py`
  - Modified: `app/cli.py`, `app/api/router.py`, `tests/auth/test_access_control.py`
- Mobile:
  - New: `src/lib/api.ts`, `src/hooks/use-vehicle-search.ts`, `src/hooks/use-debounced-value.ts`, `src/components/ui/chip.tsx`
  - New tests and config: `__tests__/` (4 test files, fixtures, type reference), `jest.setup.ts`, `.env.example`
  - Rewritten: `src/types/vehicle.ts`, `src/services/vehicles.ts`, `src/app/(tabs)/home.tsx`, `src/app/vehicles/[id].tsx`, `src/components/vehicle-card.tsx`, `src/components/vehicle-photo.tsx`
  - Modified: `src/lib/format.ts` (date ranges), `src/app/(tabs)/profile.tsx`, `package.json`, `package-lock.json`, `README.md`
  - Moved: `src/data/sample-vehicles.ts` → `src/data/sample-profile.ts` (vehicles removed)
- Docs: `README.md`, `backend/README.md`, `docs/development-roadmap.md`

Verification:
- **Backend** `pytest -ra`: **293 passed, 0 skipped, 0 failed** (34 new). Covered:
  - Only listed vehicles are visible: draft, pending, rejected, unavailable, suspended, unpriced, expired insurance and suspended owner → 404 for details, photos and availability.
  - Privacy: no VIN, registration, surname or email in responses.
  - Price shown is the one in effect (a scheduled price is not shown early).
  - Text search including literal `%` and `_`; 9 filter and sort combinations; invalid filters → 422; pagination.
  - Availability filter with a booking and a block; details and public photos (cache header; a photo id works only with its own vehicle).
  - Merged availability without reasons; quote breakdown and availability; quote period validation; released bookings do not block.
  - Demo data refused outside development, real PNG photos, listed, idempotent.
  - Ruff and `alembic check` clean.
- **Backend mutation checks:** each of these changes made tests **fail**:
  - listing filter bypassed
  - future price shown
  - owner full name exposed
  - LIKE wildcards not escaped
  - availability filter ignored
  - photo not tied to its vehicle
  - cancelled bookings blocking availability
  - past quotes allowed

  The cancelled-bookings mutation was **not caught at first**, so a test was added.
- **Mobile:** `npm test` **19 passed** (4 suites); `npm run typecheck` 0 errors; `npm run lint` clean; `npx expo-doctor` 21/21.
- **Mobile mutation checks:** each of these made tests **fail**: filters not sent, error code not mapped, empty parameters sent, 404 shown as a generic error, retry doing nothing.
- **App ↔ API end-to-end** (throwaway database seeded with demo data, real uvicorn, Expo web pointed at it through `EXPO_PUBLIC_API_URL`, headless Chromium at 390×844): **24/24 checks passed.**
  - Home: 6 vehicles from the API shown by name; cheapest first, R 390.00 matching the API; **6 real photos loaded from the API**.
  - Search and filters: "toyota" → 2; Manual → 3; Manual + up to R500 → 2; Electric → empty state; clear filters → 6.
  - Details: R 390.00 / R 150.00 / R 2 000.00; "Johan · Gqeberha"; availability shown; VIN absent; unknown vehicle → "Vehicle not found"; no page errors.
  - **API stopped → "Could not reach the server" error state; API restarted → "Try again" loads the list.**
  - Everything was removed afterwards.
- While testing I found an existing `expo start` on port 8081 (running for about 3 hours, not started by me). I left it untouched and used port 8082.

Outstanding limitations:
- **Not run on a physical device or emulator** (no emulator on this machine). The web build was verified. For Expo Go on a phone, set `EXPO_PUBLIC_API_URL` to the computer's LAN IP (see `mobile/README.md`).
- The app is not yet connected to authentication: login, registration and the profile remain UI-only (Stage 14 wires accounts, documents and dashboards; tokens go in `expo-secure-store`).
- No date picker or quote in the app yet. Date selection and booking come in Stage 10; the quote API already exists.
- Four rows of filter chips take about a third of a small screen; a collapsible filter sheet would be better.
- Public photos are served by the API itself (with a 5-minute cache), not a CDN; image resizing and thumbnails are not implemented.
- No rate limiting on the public endpoints (Stage 17).
- **Mobile `npm audit`:** 6 root advisories (`braces`, `decode-uri-component`, `node-forge`, `postcss-selector-parser`, `uuid`, and newly `sprintf-js`), all in Expo CLI, build and test tooling, not app runtime code. The counted total rose because the new Jest tooling adds more copies of the same packages. Review in Stage 17.

Next stage:
- Stage 10: Booking and Availability.

### Stage 10: Booking and Availability

Status: COMPLETE (2026-10-13)

Default for an open decision: **OPEN-2 (cancellation policy)** is undecided. Renters can cancel unpaid holds at any time and confirmed bookings until the start; after that only an administrator can cancel. Refund amounts are left to Stage 11.

Scope note: booking needs a signed-in renter, so this stage also connected the app's **login, registration, secure session storage and logout** to the backend. That was previously planned for Stage 14. Document upload in the app remains Stage 14.

Implemented:

**Backend:**
- **`POST /api/v1/bookings`** (renter only) checks, in one transaction:
  - The period (timezone required; at least 2 h lead time; at most 30 days).
  - Eligibility from Stage 06; failures return 403 with **every reason**.
  - The vehicle is listed (404 otherwise) and is not the renter's own.
  - Stale holds are expired; at most 2 unpaid holds per renter; owner date blocks are respected.
  - The vehicle row is **locked**, then the booking is inserted; the exclusion constraint returns 409 `vehicle_unavailable` on overlap.
  - The **official price breakdown** is calculated by the backend and stored.
  - The booking is `PENDING_PAYMENT` with a 15-minute hold, a `BK…` reference, and an audit entry.
- **State machine:** BR-5.5 transitions defined in one table and enforced everywhere.
- **Confirmation:** `confirm_booking()` is ready for Stage 11 and refuses expired holds.
- **Hold expiry:** lazy on reads and before availability checks, plus `python -m app.cli expire-holds` for cron. The marketplace ignores expired holds immediately.
- **Booking history and detail:** own bookings only (others → 404).
- **Cancellation:**
  - Renter: holds any time, confirmed bookings before the start.
  - Admin: with a required reason.
  - `cancelled_by`, `cancelled_at` and the reason are recorded; audited; the dates are released.
- **Admin booking list and detail.**
- **Migration `76421ebbad3d`:** `confirmed_at`, `cancelled_by_id`, and a cancellation consistency CHECK (added by hand).
- `AppError` can carry `details` (used for eligibility reasons).
- **New settings:** `BOOKING_HOLD_MINUTES`, `BOOKING_MIN_LEAD_MINUTES`, `BOOKING_MAX_DAYS`, `MAX_PENDING_BOOKINGS_PER_RENTER`.

**Mobile:**
- **Real authentication:**
  - Registration and login against the API.
  - Tokens in **expo-secure-store**; web falls back to `localStorage` (development preview only).
  - Automatic access-token refresh: one shared refresh, then retry; sign-out if renewal fails.
  - Logout revokes the server session.
  - The welcome screen redirects signed-in users.
- **Profile:** the real account, email confirmation state, and ID and licence verification status. The prototype profile data is **deleted**; the app now has no sample data at all.
- **Booking screen** (`/vehicles/[id]/book`):
  - Start day (next 30 days), delivery time and length chips, all in South African time.
  - Live backend quote and availability; delivery address.
  - Reserve; ineligible renters see each requirement in plain language.
- **Bookings tab:** history with status badges and totals. **Booking detail:** agreed price breakdown, hold countdown, and a two-tap cancel.
- **New tests:** API auth and refresh, South African date helpers, the booking flow, the bookings list and detail.

Files changed:
- Backend:
  - New: `app/services/bookings.py`, `app/schemas/bookings.py`, `app/api/routes/{bookings,admin_bookings}.py`, `migrations/versions/2026_10_13_1401-76421ebbad3d_add_booking_confirmation_and_.py`, `tests/bookings/` (helpers, state machine, API, concurrency)
  - Modified: `app/models/booking.py`, `app/core/{config,errors}.py`, `app/services/{marketplace,vehicles}.py`, `app/cli.py`, `app/api/router.py`, `.env.example`, `tests/db/{factories,test_concurrency}.py`
- Mobile:
  - New: `src/lib/{token-storage,dates,eligibility}.ts`, `src/context/auth.tsx`, `src/services/{auth,bookings,customers}.ts`, `src/types/{auth,booking}.ts`, `src/components/{sign-in-prompt,booking-status-badge}.tsx`, `src/app/(tabs)/bookings.tsx`, `src/app/vehicles/[id]/book.tsx`, `src/app/bookings/[id].tsx`, `__tests__/{api-auth,dates,booking-flow}.test.*`
  - Changed: `src/lib/api.ts` (authenticated requests, refresh), `src/app/_layout.tsx`, `src/app/index.tsx`, `src/app/(auth)/{login,register}.tsx`, `src/app/(tabs)/{_layout,profile}.tsx`, `src/components/ui/notice.tsx`, `src/types/profile.ts`, `jest.setup.ts`, `package.json` (expo-secure-store)
  - Moved: `src/app/vehicles/[id].tsx` → `src/app/vehicles/[id]/index.tsx`
  - Deleted: `src/data/sample-profile.ts`
- Docs: all READMEs, `docs/business-rules.md` (BR-5), `docs/requirements.md` (OPEN-2), `docs/development-roadmap.md`

Verification:
- **Backend** `pytest -ra`: **426 passed, 0 skipped, 0 failed**, in **5 consecutive full runs** (133 new). Covered:
  - State machine: all 100 status pairs checked against BR-5.5.
  - Creation: price breakdown and hold; client price, status or renter fields → 422; current official price used.
  - Eligibility: an ineligible renter gets all reasons; licence must outlast the rental; renters only; unlisted → 404; own vehicle → 403; 5 invalid periods.
  - Availability: overlap 409 but back-to-back allowed; owner block 409; an expired hold releases its dates in booking **and** marketplace; pending limit.
  - Privacy: history is private.
  - Cancellation: renter rules, expired holds, after start, admin with reason.
  - Confirmation rules; expiry counts; exact decimals (R333.33 × 3 = R999.99).
  - **Service-level concurrency:** two renters at the same instant → exactly one booking.
- **Concurrency stress:** the service-level test passed **30/30** runs.
- **Backend mutation checks:** each of these changes made tests **fail**:
  - eligibility skipped
  - stale holds not expired
  - blocks ignored
  - pending limit
  - own vehicle
  - lead time
  - other renters' bookings readable
  - cancel after start
  - extra transition
  - expired hold confirmable
  - wrong price period
  - expired holds blocking the marketplace
- **Mobile:** `npm test` **36 passed** (7 suites); typecheck 0 errors; lint clean; `expo-doctor` 21/21.
- **Mobile mutation checks:** each of these made tests **fail**: no retry after refresh, refresh not shared, tokens kept after a failed refresh, duration ignored, cancel without confirmation, wrong timezone offset.
- **Full renter journey end to end** (throwaway database with demo data and a CLI admin, real uvicorn, Expo web, headless Chromium):
  1. **Register in the app:** signed in, real profile, email shown as not confirmed. Reserving shows plain-language reasons (confirm email, date of birth, ID, licence).
  2. **Become eligible through real flows:** email link from the server log, date of birth, ID (valid SA ID) and licence uploads, admin approval → eligibility `{"eligible": true}`.
  3. **Book in the app:** log in; quote R750 × 3 + R150 = R2 400; switching to 5 days re-quotes R3 900; reserve → "Awaiting payment", "held for 15 more minutes"; the session survives a page reload; My bookings lists it.
  4. **Database:** the stored booking is `PENDING_PAYMENT`, 5 days, R750 / R3 750 / R3 900 / deposit R2 000, 10:00 SAST, 15-minute hold. A clashing booking for the same car is rejected (`vehicle_unavailable`) and the marketplace shows it unavailable.
  5. **Cancel and log out:** two-tap cancel in the app → Cancelled; the same dates become available again; the profile shows both documents approved; logging out makes Bookings require login again and revokes that session's refresh token.
  - Audit trail `booking.created, booking.cancelled`. Everything was removed afterwards; your existing dev server on port 8081 was not touched.
- **Problems found and fixed during the stage:**
  - **Stale photo and document collections:** a vehicle already loaded in a session kept outdated photo and document lists after an upload. It depended on garbage collection, so the Stage 07 test failed intermittently. Fixed by appending through the relationship and reloading vehicles with `populate_existing`.
  - **Deadlock in the Stage 04 raw-insert concurrency test:** two transactions inserting overlapping bookings at the same instant without a lock can deadlock in PostgreSQL. One is aborted, and **integrity is preserved** (one booking). The test now accepts that abort as a valid rejection. The booking service locks the vehicle row first, so it is not affected (30/30 stress runs).
  - These two causes very likely explain the unexplained one-off failure recorded in Stage 08.
  - Two React-Compiler lint errors (clock read during render; setState called from an effect) were fixed by restructuring, not by disabling the rules.
  - The registration submit handler was missing `async`.
  - Testing Library's hoisted mocks: the router mock is now created inside the factory.
  - The eligibility error no longer mentions API jargon ("details").

Outstanding limitations:
- **No payment yet (Stage 11):** every reservation expires after 15 minutes unless an operator confirms it. Refund amounts for cancelled paid bookings are not defined (OPEN-2).
- **Holds expire lazily plus via `expire-holds`.** Production must schedule that command (e.g. cron every minute; Stage 18).
- Mobile: no document upload screens yet (Stage 14), so new renters cannot become eligible from the app alone. Not tested on a physical device. On web, tokens live in `localStorage` (development preview only).
- Owners cannot yet see bookings of their vehicles in the app (Stage 14). Unlisting or suspending a vehicle does not notify affected renters (Stage 16).
- Date selection uses chips (next 30 days, fixed delivery times) rather than a calendar.
- No rate limiting on booking creation (Stage 17).
- Mobile `npm audit` is unchanged in kind: 6 root advisories in Expo build and test tooling (Stage 17).

Next stage:
- Stage 11: Payment Integration.

### Stage 11: Payment Integration

Status: COMPLETE (2026-10-13)

Defaults for open decisions (all configurable later; recorded in `docs/requirements.md`):
- **OPEN-8 provider: Paystack**, behind a `PaymentProvider` interface. Chosen for its documented HMAC-signed webhooks, verify and refund APIs, and ZAR support. The merchant agreement and fees must still be confirmed before going live.
- **OPEN-2 refunds:** a cancelled paid booking is refunded **in full** (renter before the start; administrator at any time). Administrators can also make partial refunds.
- **OPEN-7 deposit:** the deposit is **not charged online**. The checkout charges the booking total (rental plus delivery fee); the deposit is arranged at handover until a holding mechanism is chosen.
- **OPEN-1 payouts:** the platform collects as merchant of record; owner payouts are settled outside the system for now (see BR-6 payout notes).

Implemented:

**Backend:**
- **`POST /api/v1/bookings/{id}/payments`** (renter): starts Paystack checkout for a `PENDING_PAYMENT` booking, for the **stored booking total** (any client amount is ignored). It reuses an open checkout instead of creating a second one, refuses expired holds and other states (409), and returns 503 when payments are not configured and 502 when Paystack is down.
- **Verification:** a payment becomes `SUCCEEDED` only after the backend calls Paystack's verify API and the **reference, amount (in cents) and currency all match**. A mismatch is marked `FAILED`, audited and logged for review, never applied. Success confirms the booking through `confirm_booking()` in the same transaction.
- **Webhook `POST /api/v1/payments/webhooks/paystack`:** HMAC-SHA512 signature over the raw body (401 otherwise). Each event is stored once (unique SHA-256 of the body), so **re-deliveries are no-ops**. The payload only *triggers* verification and is never trusted. Stored payloads keep only reconciliation fields (no card or customer data, for POPIA).
- **Late or duplicate money (BR-6.5):** a payment that succeeds after the hold expired, after cancellation, or for an already-paid booking becomes `REFUND_PENDING` and is **refunded automatically**.
- **Refunds:** `refunds` table linked to payments; full or partial; audited. Admin `POST /api/v1/admin/payments/{id}/refunds`. Cancelling a paid booking (renter or admin) refunds it in full. Refund state follows Paystack (`PENDING` → `PROCESSED`/`FAILED`) through webhooks or reconciliation; payments move to `PARTIALLY_REFUNDED` / `REFUNDED`.
- **Reconciliation:** `python -m app.cli reconcile-payments` (cron) and `POST /api/v1/admin/payments/reconcile` re-check pending payments and refunds, which catches lost webhooks. `POST /api/v1/payments/{id}/refresh` lets a renter returning from checkout verify immediately.
- **Admin list** `GET /api/v1/admin/payments[?status=&booking_id=]`; renter `GET /api/v1/bookings/{id}/payments`.
- **Safety switch:** only `sk_test_…` keys are accepted. A live key makes the app **refuse to start** unless `ALLOW_LIVE_PAYMENTS=true`.
- **Migration `7896d127780b`:** `payment_events`, `refunds`, and payment tracking columns (checkout URL, transaction id, last verified, initiated by).
- **New settings:** `PAYSTACK_SECRET_KEY`, `PAYSTACK_PUBLIC_KEY`, `PAYSTACK_BASE_URL`, `ALLOW_LIVE_PAYMENTS`, `PAYMENT_CALLBACK_URL`. `httpx2` moved from dev to runtime requirements (the Paystack client).

**Mobile:**
- Booking detail shows **"Pay R…"** while the hold is live. It opens checkout with `expo-web-browser`, then asks the backend to verify; the browser result is never trusted. Declined payments explain themselves and can be retried; unconfirmed ones say so.
- **Payment history** on the booking: paid, refunded, and refund in progress amounts.
- **`/payments/return`** screen: the checkout return page (`?payment_id=`). It completes the web popup and shows the verified result.
- Copy updated: the deposit is not charged online; cancelling before the trip refunds in full.

Files changed:
- Backend:
  - New: `app/integrations/payments.py`, `app/services/payments.py`, `app/schemas/payments.py`, `app/api/routes/{payments,admin_payments}.py`, `migrations/versions/2026_10_13_1500-7896d127780b_add_payment_events_refunds_and_payment_.py`, `tests/payments/` (fake provider, Paystack adapter tests, flow tests)
  - Modified: `app/models/{payment,enums,__init__}.py`, `app/core/config.py`, `app/main.py`, `app/api/{deps,router}.py`, `app/api/routes/{bookings,admin_bookings}.py`, `app/cli.py`, `.env.example`, `requirements*.txt`, `tests/{api_fixtures,auth/test_access_control,db/test_migrations}.py`
- Mobile:
  - New: `src/types/payment.ts`, `src/services/payments.ts`, `src/app/payments/return.tsx`
  - Changed: `src/app/bookings/[id].tsx`, `src/app/vehicles/[id]/book.tsx`, `src/app/_layout.tsx`, `__tests__/booking-flow.test.tsx`, `app.json` and `package.json` (expo-web-browser)
- Docs: all READMEs, `docs/business-rules.md` (BR-5, BR-6), `docs/requirements.md` (OPEN-1, 2, 7, 8), `docs/architecture.md`, `docs/development-roadmap.md`

Verification (sandbox or test doubles only; **no real money moved**):
- **Backend** `pytest -ra`: **476 passed, 0 skipped, 0 failed** (50 new). Covered:
  - Paystack adapter against recorded HTTP shapes: integer cents in ZAR, conservative status mapping (only `success` is paid), refunds, HTTP and network errors, HMAC-SHA512 webhook signatures, the live-key guard.
  - Flows: the checkout amount comes from the booking; open checkout reuse; state rules; provider outage; payments disabled; only verified payments confirm; failed then retry; mismatch flagged; late payment and duplicate payment refunded; verify outage leaves the payment pending; signed, forged, replayed and unknown-reference webhooks; untrusted payload; partial and full refunds; refund rules and provider failure; cancellation refunds (renter and admin); reconciliation of missed webhooks; privacy between renters; the return URL carries the payment id.
- **Mutation checks:** 9 of 10 caught (amount check removed, signature check removed, expired hold confirmed, re-delivery reprocessed, second checkout opened, deposit charged, over-refund, pending treated as paid, final payment reprocessed). The tenth (dropping the duplicate-payment branch) is equivalent: the booking is already confirmed, so the payment is refunded for the same reason.
- **Mobile:** `npm test` **40 passed** (4 new: pay and confirm, decline and retry, no pay button after expiry, refunds shown); typecheck 0 errors; lint clean; `expo-doctor` 21/21.
- **Live end to end, 16/16:** a real uvicorn server talking HTTP to a local Paystack stand-in using a `sk_test_` key. It covered: checkout for the booking total with the client amount ignored; a forged webhook rejected with the booking still unpaid; pay → signed webhook → booking `CONFIRMED`; the redirect carries `payment_id`; a replayed webhook stored once; cancel → full refund → refund webhook → `REFUNDED`; a declined payment leaves the hold and a retry gets a new checkout; a lost webhook is caught by `reconcile-payments`. Stored webhook payloads contain no card or customer data.
- `alembic upgrade` / `downgrade -1` / `upgrade` round trip and `alembic check` clean.
- **Problems found and fixed during the stage:**
  - The test fake provider did not record `callback_url`.
  - Refund webhooks without a refund id we know now re-check that payment's pending refunds instead of being ignored.
  - In the app, a declined payment's message disappeared because the screen reloaded; the screen now reloads only when the booking actually changed.

Outstanding limitations:
- **Not yet run against the real Paystack sandbox:** no test keys were available. Before launch, set `PAYSTACK_SECRET_KEY=sk_test_…`, point the Paystack dashboard webhook at `/api/v1/payments/webhooks/paystack` (public HTTPS), and repeat the E2E. **Live keys need your explicit approval** (`ALLOW_LIVE_PAYMENTS`).
- Payments whose verified amount does not match are marked `FAILED` for review. The admin API cannot refund them; handle them in the Paystack dashboard.
- On a phone, Paystack returns to an `http(s)` URL, so the in-app browser does not close by itself. The renter closes it and the app then verifies the payment. Not yet tested on a device. The pay flow was tested with Jest, not in a real browser.
- `reconcile-payments` and `expire-holds` must be scheduled in production (Stage 18). Without a configured provider, cancelling a paid booking logs an error and does not refund.
- No payment receipts or refund emails yet (Stage 16). No owner payout automation (OPEN-1). The security deposit is not collected online (OPEN-7). There is no admin payments UI until Stage 15.

Next stage:
- Stage 12: Delivery Management.

## 8. Prerequisites

Versions found on the development machine during Stage 01 (Ubuntu 24.04.5 LTS):

| Tool | Version found | Needed for |
|------|---------------|------------|
| Git | 2.43.0 | All |
| Node.js | 20.20.2 | Mobile, admin dashboard |
| npm | 10.8.2 | Mobile, admin dashboard |
| Python | 3.12.3 (with `venv`) | Backend |
| PostgreSQL | 16.15 (system service present but **not used**; the project uses the Docker container on port 5433) | Backend database |
| Docker / Compose | 29.8.1 / v5.5.1 | Local PostgreSQL (`docker compose up -d db`) |

To run the mobile app on a device: the **Expo Go** app (must support SDK 57),
or an Android emulator or iOS simulator. Needed in later stages: Google Maps
Platform API keys (Stage 13) and Paystack **test** keys (`sk_test_…`) to exercise payments against the real sandbox.

## 9. Installation Instructions

```bash
git clone <repository-url> car-rental
cd car-rental

# Mobile app
cd mobile
npm install

# Database (repository root)
cd ..
cp .env.example .env            # set POSTGRES_PASSWORD to a random value
docker compose up -d db

# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # put the same password into DATABASE_URL / TEST_DATABASE_URL
alembic upgrade head
python -m app.cli create-admin --email you@example.com --full-name "Your Name"   # first administrator
```

*Planned:* admin dashboard (`npm install` in `admin-dashboard/`, Stage 15).

## 10. Environment Configuration

- Each application will provide a `.env.example` with placeholder values. Copy it to `.env` and fill in local values.
- `.env` files are git-ignored. Never commit real secrets (JWT keys, database passwords, payment keys, Maps keys).
- **Root (Docker Compose):** `.env.example` lists `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_TEST_DB`, and `POSTGRES_PORT`. Use a random password, e.g. `python3 -c "import secrets; print(secrets.token_urlsafe(24))"`.
- **Backend:** `backend/.env.example` lists `APP_ENV`, `APP_NAME`, `LOG_LEVEL`, `CORS_ORIGINS`, `DATABASE_URL` (required), `TEST_DATABASE_URL`, `DATABASE_ECHO`, `JWT_SECRET_KEY` (required; generate a random 64-byte value), token lifetimes, `EMAIL_BACKEND` (`console` or `smtp`), `EMAIL_FROM`, `SMTP_*`, `APP_LINK_BASE_URL`, `MIN_RENTER_AGE`, `DOCUMENT_HASH_KEY` (required; generate once and keep), `DOCUMENT_STORAGE_DIR`, and `MAX_DOCUMENT_BYTES`. See [backend/README.md](backend/README.md#configuration).
- Production refuses to start with `EMAIL_BACKEND=console`, and `JWT_SECRET_KEY` must be at least 32 characters.
- **Mobile:** `mobile/.env.example` contains `EXPO_PUBLIC_API_URL` (the backend URL; never put secrets in `EXPO_PUBLIC_*`).
- Booking limits: `BOOKING_HOLD_MINUTES`, `BOOKING_MIN_LEAD_MINUTES`, `BOOKING_MAX_DAYS`, `MAX_PENDING_BOOKINGS_PER_RENTER` (backend).
- Payments: `PAYSTACK_SECRET_KEY` (empty disables online payment; only `sk_test_…` unless `ALLOW_LIVE_PAYMENTS=true`), `PAYSTACK_BASE_URL`, `PAYMENT_CALLBACK_URL` (backend).

## 11. Database Setup

Local PostgreSQL 16 runs in Docker on `127.0.0.1:5433`. The first start creates
`car_rental` (development) and `car_rental_test` (tests).

```bash
docker compose up -d db                 # start (repository root)
docker compose ps                       # should show "healthy"
cd backend && source .venv/bin/activate
alembic upgrade head                    # apply migrations
alembic current                         # show applied revision
alembic downgrade -1                    # revert the last migration
alembic revision --autogenerate -m "…"  # new migration from model changes (review it!)
alembic check                           # verify models and migrations match
docker compose down -v                  # DELETE all local database data
```

The schema changes only through Alembic migrations. Integrity rules enforced by
the database are listed in [backend/README.md](backend/README.md#integrity-rules-enforced-by-postgresql).

## 12. Running the Mobile Application

```bash
cd mobile
npm start          # Expo dev server; scan the QR code with Expo Go, or press:
                   #   a = Android emulator, i = iOS simulator (macOS), w = web
npm run web        # open directly in the browser
```

The marketplace screens load vehicles from the backend, so start the API first. For
demo listings run `APP_ENV=development python -m app.cli seed-demo-data` in `backend/`.
Copy `mobile/.env.example` to `mobile/.env` and set `EXPO_PUBLIC_API_URL` (default
`http://localhost:8000`; use the computer's LAN IP for a physical phone). Accounts, login
and bookings use the real backend. A renter must be verified (date of birth, ID, licence
approved by an administrator) before booking; document upload is still API-only (see
[backend/README.md](backend/README.md)). See [mobile/README.md](mobile/README.md). Add packages with
`npx expo install <package>` so versions stay compatible with SDK 57.

## 13. Running the Python Backend

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

The database must be running (`docker compose up -d db`). Health check:
http://localhost:8000/api/v1/health (503 if the database is unreachable). All API
routes live under `/api/v1`. More detail is in [backend/README.md](backend/README.md).

## 14. Running the Admin Dashboard

Not yet implemented (Stage 15).

## 15. Running Tests

Mobile:

```bash
cd mobile
npm test            # Jest (jest-expo + React Native Testing Library)
npm run typecheck   # TypeScript (tsc --noEmit)
npm run lint        # ESLint (expo lint)
npx expo-doctor     # dependency / SDK compatibility
```

Backend:

```bash
cd backend
source .venv/bin/activate
pytest -ra             # automated tests (database tests need the Docker database)
ruff check .           # lint
ruff format --check .  # formatting
alembic check          # models match migrations
```

Database tests use `TEST_DATABASE_URL`. Its schema is **dropped and recreated** on
every run, so the name must end in `_test`. Dashboard checks are added in Stage 15.

## 16. API Documentation

With the backend running in a non-production environment:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI schema: http://localhost:8000/api/v1/openapi.json

These are disabled when `APP_ENV=production`. Use **Authorize** in Swagger UI with
an access token from `POST /api/v1/auth/login`.

Current endpoints: health; auth (register, login, refresh, logout, logout-all,
verify-email, resend, password-reset request and confirm); `GET /users/me`;
owner profile and vehicles (`/owners/me/...`: registration, photos, documents,
submit and withdraw, listing, availability blocks); admin vehicle management
(`/admin/vehicles`: queue, detail, audited document view, approve, reject, suspend,
reinstate, official price history, set price, quote); **public marketplace**
(`/vehicles`: search and filters, details, photos, availability, quote); **bookings**
(`/bookings`: create, history, detail, cancel; `/admin/bookings`: list, detail, cancel); **payments**
(`/bookings/{id}/payments`: start checkout, list; `/payments/{id}/refresh`; the signed Paystack webhook;
`/admin/payments`: list, refund, reconcile); renter profile, date of birth, document upload and
list, own-file download, and eligibility (`/customers/me/...`); admin users
(list, suspend, reactivate) and verifications (queue, detail, audited file view,
decision). The full tables with access rules are in
[backend/README.md](backend/README.md#authentication-and-authorisation). Every
error uses the envelope `{"error": {"code", "message", "details"?}}`.

## 17. Security and Privacy

- The backend enforces all authorisation. Role, price, eligibility, and payment status values sent by clients are never trusted.
- Passwords are hashed with Argon2id. Access tokens last 15 minutes and carry no roles. Refresh tokens are hashed, rotated, and revocable, with reuse detection.
- Administrator accounts are created only with the operator CLI (`python -m app.cli create-admin`), never through the API.
- Suspension, password reset, and logout-all invalidate all of a user's sessions immediately. Login and reset responses do not reveal whether an email is registered.
- An automated test checks that every non-public endpoint rejects anonymous requests.
- ID and licence documents are stored privately, access is logged, and their numbers never appear in public APIs or logs (POPIA).
- Money is stored as exact decimals in ZAR. Webhooks are HMAC-verified and de-duplicated, and a payment counts only after the backend itself verifies the reference, amount and currency with Paystack. Live payment keys are refused unless `ALLOW_LIVE_PAYMENTS=true`.
- Location sharing is limited to the assigned delivery person while a delivery is active, and is visible only to the booking's renter and administrators.
- Secrets live only in environment variables. HTTPS is required in production.
- No real financial transactions or production deployments happen without explicit owner approval.

- Full SA ID and licence numbers are never stored, only a keyed HMAC and the last 3 digits. Document files live in private storage with server-generated names, are type-checked by content, can be viewed only by their owner and administrators, and **every administrator view is audited**.

See [docs/business-rules.md](docs/business-rules.md) (BR-8, BR-9) and
[docs/document-handling.md](docs/document-handling.md).

## 18. Known Issues

- Open business decisions (commission and payouts, cancellation policy, delivery model, insurance age rules, VAT, payment provider) are listed in [docs/requirements.md §5](docs/requirements.md#5-open-business-decisions). They do not block Stages 02–05.
- `admin-dashboard/` contains only a `.gitkeep` placeholder.
- Backend: no vehicle, booking, payment, or delivery endpoints yet (Stage 06 onward). Expired booking holds are released by the booking service in Stage 10.
- **No login rate limiting or lockout yet** (Stage 17).
- Email: only the development console mailer has been exercised. A real SMTP provider account must be configured before staging or production.
- Prices are VAT-inclusive with no VAT breakdown (OPEN-6). The public marketplace has no rate limiting yet (Stage 17).
- The intermittent test failure seen in Stage 08 has been traced to two causes and fixed in Stage 10 (see its summary); the suite then passed 5 full runs in a row.
- Identity documents: local storage is not encrypted at rest (production needs encrypted object storage); retention periods await legal confirmation; no automatic purge; no image re-encoding or malware scanning yet. See [docs/document-handling.md](docs/document-handling.md).
- The system PostgreSQL on port 5432 is not used. The project database is the Docker container on port 5433.
- Mobile app: not yet run on a physical device or emulator (web verified end to end against the real API). Document upload screens come in Stage 14. On web, session tokens are kept in `localStorage` (development preview only).
- Payments are tested with test doubles and a local Paystack stand-in, not yet against the real Paystack sandbox (no test keys yet). Schedule `python -m app.cli expire-holds` and `python -m app.cli reconcile-payments` in production.
- Mobile `npm audit`: 6 root advisories in Expo CLI, build and test tooling (not app runtime). Deferred to Stage 17; the `--force` fix would downgrade Expo.

## 19. Current Development Status

Stages 01–11 are COMPLETE. The backend (PostgreSQL 16) provides authentication, eligibility, vehicle registration and approval, official pricing, a public marketplace, bookings (holds, state machine, cancellation) and Paystack payments (verified checkout, idempotent webhooks, automatic and admin refunds, reconciliation), with 476 passing tests. The mobile app has real accounts, the marketplace, booking, payment and My bookings, with 40 passing tests. Delivery management (Stage 12) has not started.

## 20. Next Stage

**Stage 12: Delivery Management.** Delivery records for confirmed bookings, assignment,
scheduling, the delivery status machine (`CONFIRMED` → `DELIVERY_SCHEDULED` →
`IN_TRANSIT` → `DELIVERED` → `ACTIVE_RENTAL` → `RETURN_PENDING` → `COMPLETED`), handover
and return records, exceptions and an audit trail. **Needs a decision on OPEN-3** (who
delivers: owners, platform drivers, or both), which decides whether a `DRIVER` role is
added. Waiting for owner approval to begin.
