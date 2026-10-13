# Architecture

## 1. System overview

```
┌──────────────────────┐        HTTPS/JSON + WSS        ┌───────────────────────────┐
│  Mobile app (Expo)   │ ─────────────────────────────► │                           │
│  renters & owners    │ ◄───── live delivery (WS) ──── │   FastAPI backend         │
└──────────────────────┘                                │   (Python 3.12)           │
                                                        │                           │
┌──────────────────────┐        HTTPS/JSON              │  routes → services →      │
│  Admin dashboard     │ ─────────────────────────────► │  repositories → DB        │
│  (React + Vite)      │                                │                           │
└──────────────────────┘                                └─────┬─────────┬───────┬───┘
                                                              │         │       │
                                               ┌──────────────▼─┐  ┌────▼────┐  ┌▼──────────────────┐
                                               │ PostgreSQL 16  │  │ Private │  │ External services │
                                               │ (SQLAlchemy +  │  │ object  │  │ - Payment provider│
                                               │  Alembic)      │  │ storage │  │ - Google Maps     │
                                               └────────────────┘  └─────────┘  │ - Email / Push    │
                                                                                └───────────────────┘
        Payment provider ──── signed webhook (HTTPS) ────► FastAPI /payments/webhooks/...
```

The backend is the only component that writes to the database, talks to the
payment provider with secret credentials, or makes trust decisions (roles,
prices, eligibility, payment status, delivery authorisation).

## 2. Component responsibilities

### Mobile app (`mobile/`)
Expo, React Native, TypeScript, Expo Router, NativeWind, Expo Location, a map library (`react-native-maps` using the Google provider), and a WebSocket client.
- Renter flows: register, verify documents, browse, book, pay (through the provider's hosted checkout), track delivery, view history.
- Owner flows: list vehicles, upload photos and documents, manage availability, view bookings and earnings, act as delivery person (send location while a delivery is active).
- Holds **no** business authority. It shows backend-calculated prices and statuses.
- Stores tokens in `expo-secure-store`, never in plain AsyncStorage.
- Uses only the restricted Google Maps key (limited to the app's package name and signing certificate).

### Backend (`backend/`)
FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, PostgreSQL, Pytest.

Layering (each layer may only call the one beneath it):

| Layer | Folder (planned) | Responsibility |
|-------|------------------|----------------|
| API / routes | `app/api/` | HTTP and WebSocket endpoints, request/response schemas, auth dependencies. No business logic. |
| Schemas | `app/schemas/` | Pydantic models for validation and serialisation. |
| Services | `app/services/` | Business rules: eligibility, pricing, booking state machine, payments, deliveries. Transaction boundaries. |
| Repositories / models | `app/models/`, `app/repositories/` | SQLAlchemy models and queries. |
| Integrations | `app/integrations/` | Adapters for payment provider, storage, email, push, and maps. Each sits behind an interface so tests can use sandbox or fake implementations. |
| Core | `app/core/` | Settings (environment variables), security (hashing, JWT), logging, error handling. |

- Auth: short-lived JWT access token (about 15 minutes) and a rotating refresh token stored hashed in the database so it can be revoked. RBAC is enforced through FastAPI dependencies on every protected route.
- Live tracking: a WebSocket endpoint authenticated with the access token, plus authorisation checks per delivery. One process uses an in-memory broadcaster. Running several instances requires Postgres `LISTEN/NOTIFY` or Redis pub/sub (decided in Stage 13).
- Background jobs (hold expiry, reminders, notification retries) start as a simple scheduler. Moving to a task queue happens only if needed.

### Admin dashboard (`admin-dashboard/`)
React, TypeScript, Vite, Tailwind CSS, and Recharts for charts.
- Administrator-only. Every action calls protected backend endpoints. Hiding UI elements is not treated as security.
- All metrics come from backend aggregate endpoints over real data.

### Database (PostgreSQL 16)
Planned core tables for Stage 04 (more added as features need them):

`users`, `roles`, `user_roles`, `owner_profiles`, `customer_profiles`,
`vehicles`, `vehicle_images`, `vehicle_prices`, `bookings`, `payments`,
`deliveries`, `audit_logs`

Added since: `refresh_tokens`, `user_action_tokens`, `verification_submissions`,
`verification_files`, `vehicle_documents`, `vehicle_availability_blocks`,
`payment_events`, `refunds` (Stage 11), `handover_records`, `handover_photos` and
`delivery_exceptions` (Stage 12). Still to come: `delivery_location_updates` (Stage 13)
and `notifications` (Stage 16).

Key integrity decisions:
- Money: `NUMERIC(12,2)` with a `currency CHAR(3) DEFAULT 'ZAR'` check.
- Booking overlap: the `btree_gist` extension plus `EXCLUDE USING gist (vehicle_id WITH =, tstzrange(start_at, end_at, '[)') WITH &&) WHERE (status IN (...blocking states...))`. Implemented in Stage 04, and a concurrency test confirms it.
- Enums: `VARCHAR` + `CHECK` constraints rather than native PostgreSQL enum types, which are easier to change in migrations.
- Idempotency: unique `(provider, provider_reference)` on `payments` and a partial unique index allowing one `SUCCEEDED` payment per booking. `payment_events` has a unique `(provider, event_key)`, where the key is the SHA-256 of the signed body (Stage 11); `refunds` has a unique `(provider, provider_refund_id)`.
- Audit: `audit_logs` is append-only, enforced by a trigger.
- Sessions: sync SQLAlchemy 2.x with psycopg 3. FastAPI runs sync routes in a threadpool. Services commit explicitly, and failed requests roll back.
- Timestamps: `timestamptz`, stored in UTC.
- UUID primary keys for externally visible entities, so IDs cannot be guessed by enumeration.

### File storage
- Development: a local private directory outside any public path (`backend/storage/`, git-ignored), served only through authorised endpoints.
- Production: S3-compatible private bucket (e.g. AWS S3 `af-south-1` Cape Town, to keep data in South Africa) with server-side encryption and short-lived pre-signed URLs.
- Uploads are validated for type, size, and image decoding. File names are generated by the server.

## 3. Payment provider

**Stage 11 default: Paystack** (OPEN-8), implemented in `app/integrations/payments.py`
against Paystack's published OpenAPI spec:

```
App ──POST /bookings/{id}/payments──► API ──POST /transaction/initialize──► Paystack
App ◄──────── checkout_url ────────── API
App ──opens checkout (expo-web-browser)──────────────────────────────────► Paystack
Paystack ──signed webhook (x-paystack-signature)──► API: check HMAC, store event once
API ──GET /transaction/verify/{reference}──► Paystack   (the only source of truth)
API: reference + amount + currency match → payment SUCCEEDED + booking CONFIRMED (one transaction)
App ──POST /payments/{id}/refresh──► API (same verification; no waiting for the webhook)
cron: python -m app.cli reconcile-payments → verifies anything still pending
```

Without `PAYSTACK_SECRET_KEY` payments are disabled (503). Live keys are refused unless
`ALLOW_LIVE_PAYMENTS=true`. Tests use a fake provider and an `httpx` mock transport, so
they never contact Paystack.

Candidates considered for ZAR payments for South African merchants:

| Provider | Notes to verify during Stage 11 |
|----------|----------------------------------|
| Paystack (South Africa) | Signed webhooks (HMAC), refunds API, split payments/subaccounts for owner payouts. Check the SA availability of each feature. |
| PayFast | Widely used in SA. ITN notifications with signature plus server-side validation. Check refund and split-payment support for this business model. |
| Peach Payments | SA enterprise gateway with card and EFT methods. Check the onboarding requirements. |
| Ozow | Instant EFT. May complement a card provider. |

Capabilities, fees, and marketplace/payout rules **must be confirmed with the
provider and the merchant agreement** before implementation. Nothing in this
table is assumed final. The backend uses a `PaymentProvider` interface so the
choice does not leak into business logic.

## 4. Google Maps Platform
- Mobile map display: Maps SDK for Android and iOS (through `react-native-maps`).
- Backend: Routes API for ETA (server-side key, restricted by IP), and optionally the Geocoding API.
- Keys are kept separate per platform and restricted. No unrestricted key is shipped in the app.

## 5. Environments

| Environment | Purpose | Data |
|-------------|---------|------|
| local | Developer machine. Postgres runs locally or through Docker. | Seeded **development** data, clearly labelled. |
| test | Pytest with a separate test database. | Fixtures created and destroyed per test run. |
| staging | Pre-production with provider sandbox accounts. | Synthetic data only. |
| production | Live. Deployment needs explicit owner approval. | Real data. |

Configuration comes only from environment variables (`.env.example` files hold
placeholders). Secrets are never committed.

## 6. Repository layout

```
car-rental/
├── README.md               # Central project document and stage tracker
├── .gitignore
├── docs/
│   ├── requirements.md
│   ├── business-rules.md
│   ├── architecture.md
│   └── development-roadmap.md
├── mobile/                 # Expo React Native app        (Stage 02)
├── backend/                # FastAPI service              (Stage 03–04)
├── docker-compose.yml      # Local PostgreSQL 16          (Stage 04)
├── infra/postgres/init/    # Container init (creates the test database)
└── admin-dashboard/        # React + Tailwind web admin   (Stage 15)
```

The three applications are independent npm and Python projects, with no shared
JS workspace tooling for now. Shared API types may later be generated from the
backend's OpenAPI schema.
