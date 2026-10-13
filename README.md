# Car Rental Platform (South Africa)

A marketplace that connects vehicle owners with renters in South Africa,
with administrator-controlled pricing, renter verification, ZAR payments, and
live delivery tracking.

> **Current state:** Stage 02 complete. The mobile app foundation runs with
> **prototype sample data** and no backend or authentication yet. Commands for
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
| Mobile | Expo SDK 57 (React Native 0.86, React 19.2), TypeScript 6, Expo Router 57, NativeWind 4.2.7 + Tailwind CSS 3.4, ESLint 9 (`eslint-config-expo`). Planned: Expo Location, `react-native-maps` (Google provider), WebSocket client |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, Pytest, WebSockets |
| Database | PostgreSQL 16 |
| Admin dashboard | React, TypeScript, Vite, Tailwind CSS, Recharts |
| Payments | South African ZAR provider. Candidates: Paystack, PayFast, Peach Payments, Ozow. Decided in Stage 11. |
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
│   ├── business-rules.md   # Rules enforced by the backend
│   ├── architecture.md     # Components, layering, data model plan, providers
│   └── development-roadmap.md
├── mobile/                 # Expo app (Stage 02) — see mobile/README.md
│   ├── src/app/            # Expo Router screens
│   ├── src/components/     # Reusable UI components
│   ├── src/data/           # PROTOTYPE sample data (removed in Stage 09)
│   └── tailwind.config.js  # Theme tokens
├── backend/                # FastAPI service — empty placeholder until Stage 03
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
| 03 | Python Backend Foundation | NOT STARTED | Not tested |
| 04 | PostgreSQL and Database Foundation | NOT STARTED | Not tested |
| 05 | Authentication and Authorisation | NOT STARTED | Not tested |
| 06 | Customer Eligibility and Document Verification | NOT STARTED | Not tested |
| 07 | Owner Profiles and Vehicle Registration | NOT STARTED | Not tested |
| 08 | Administrator Pricing Management | NOT STARTED | Not tested |
| 09 | Customer Marketplace | NOT STARTED | Not tested |
| 10 | Booking and Availability | NOT STARTED | Not tested |
| 11 | Payment Integration | NOT STARTED | Not tested |
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

## 8. Prerequisites

Versions found on the development machine during Stage 01 (Ubuntu 24.04.5 LTS):

| Tool | Version found | Needed for |
|------|---------------|------------|
| Git | 2.43.0 | All |
| Node.js | 20.20.2 | Mobile, admin dashboard |
| npm | 10.8.2 | Mobile, admin dashboard |
| Python | 3.12.3 (with `venv`) | Backend |
| PostgreSQL | 16.15 (local service running) | Backend database |
| Docker / Compose | 29.8.1 / v5.5.1 | Optional: containerised Postgres |

To run the mobile app on a device: the **Expo Go** app (must support SDK 57),
or an Android emulator or iOS simulator. Needed in later stages: Google Maps
Platform API keys (Stage 13) and payment provider sandbox credentials (Stage 11).

## 9. Installation Instructions

```bash
git clone <repository-url> car-rental
cd car-rental

# Mobile app
cd mobile
npm install
```

*Planned:* backend (`python3 -m venv .venv && pip install -r requirements.txt`
in `backend/`, Stage 03) and admin dashboard (`npm install` in
`admin-dashboard/`, Stage 15).

## 10. Environment Configuration

- Each application will provide a `.env.example` with placeholder values. Copy it to `.env` and fill in local values.
- `.env` files are git-ignored. Never commit real secrets (JWT keys, database passwords, payment keys, Maps keys).
- No environment variables are required yet. The mobile app has no API URL or keys until Stage 09.

## 11. Database Setup

Not yet implemented (Stage 04). The plan is a local PostgreSQL 16 database for
development and a separate test database, with schema managed only through
Alembic migrations.

## 12. Running the Mobile Application

```bash
cd mobile
npm start          # Expo dev server; scan the QR code with Expo Go, or press:
                   #   a = Android emulator, i = iOS simulator (macOS), w = web
npm run web        # open directly in the browser
```

The app currently uses **prototype sample data** and has no real sign-in. See
[mobile/README.md](mobile/README.md) for the folder structure. Add packages with
`npx expo install <package>` so versions stay compatible with SDK 57.

## 13. Running the Python Backend

Not yet implemented (Stage 03).

## 14. Running the Admin Dashboard

Not yet implemented (Stage 15).

## 15. Running Tests

Mobile:

```bash
cd mobile
npm run typecheck   # TypeScript (tsc --noEmit)
npm run lint        # ESLint (expo lint)
npx expo-doctor     # dependency / SDK compatibility
```

Backend Pytest (Stage 03) and dashboard checks (Stage 15) will be added in
their stages.

## 16. API Documentation

Not yet implemented. FastAPI will serve interactive OpenAPI documentation at
`/docs` in development (Stage 03).

## 17. Security and Privacy

- The backend enforces all authorisation. Role, price, eligibility, and payment status values sent by clients are never trusted.
- Passwords are hashed (Argon2id/bcrypt). Tokens are short-lived and revocable.
- ID and licence documents are stored privately, access is logged, and their numbers never appear in public APIs or logs (POPIA).
- Money is stored as exact decimals in ZAR. Payments are verified by signed webhooks and processed idempotently.
- Location sharing is limited to the assigned delivery person while a delivery is active, and is visible only to the booking's renter and administrators.
- Secrets live only in environment variables. HTTPS is required in production.
- No real financial transactions or production deployments happen without explicit owner approval.

See [docs/business-rules.md](docs/business-rules.md) (BR-8, BR-9).

## 18. Known Issues

- Open business decisions (commission and payouts, cancellation policy, delivery model, insurance age rules, VAT, payment provider) are listed in [docs/requirements.md §5](docs/requirements.md#5-open-business-decisions). They do not block Stages 02–05.
- `backend/` and `admin-dashboard/` contain only `.gitkeep` placeholders.
- Mobile app: not yet run on a physical device or emulator (bundles compile; web verified). Login and registration are UI-only. Data is prototype sample data.
- Mobile `npm audit`: 36 advisories in Expo build tooling (not app runtime). Deferred to Stage 17; `--force` fix would downgrade Expo.

## 19. Current Development Status

Stages 01–02 are COMPLETE. The mobile app foundation (navigation, theme, components, six screens) runs with prototype data. No backend exists yet. Stage 03 has not started.

## 20. Next Stage

**Stage 03: Python Backend Foundation.** Create the FastAPI service in
`backend/`: virtual environment, settings from environment variables,
`.env.example`, API router structure, `/health` endpoint, request validation,
error handling, and Pytest. Waiting for owner approval to begin.
