# Requirements

Status: Draft v1 (Stage 01). Items marked **OPEN** need a business decision
before the stage that depends on them.

## 1. Purpose

A car rental marketplace for South Africa that connects vehicle owners with
renters. The platform administrator approves vehicles, sets all official rental
prices, verifies renter eligibility, and oversees bookings, payments, and
deliveries. All amounts are in South African rand (ZAR).

## 2. Actors

| Actor | Description |
|-------|-------------|
| Renter (customer) | Registers, submits ID and driving licence, books and pays for vehicles, tracks delivery. |
| Owner | Registers, lists vehicles, submits vehicle documents, manages availability, handles or receives deliveries. |
| Administrator | Platform owner/CEO and authorised staff. Approves vehicles and verifications, sets prices, monitors the platform. |
| Driver (deferred) | Delivers vehicles to renters. Added only if the delivery model needs a separate role (see OPEN-3). |
| Payment provider | External system that processes ZAR payments and sends webhooks. |
| Google Maps Platform | External maps, geocoding, routes, and ETA service. |

## 3. Functional requirements

### 3.1 Accounts and access
- FR-1 Renters and owners can register with email and password.
- FR-2 Users can log in and log out. Sessions use short-lived access tokens plus revocable refresh tokens.
- FR-3 Email verification and password reset are supported.
- FR-4 Roles: `ADMIN`, `OWNER`, `RENTER` (and `DRIVER` if adopted). One user may hold more than one role.
- FR-5 Administrator accounts cannot be self-registered. They are created through a controlled CLI or seed process.
- FR-6 Administrators can suspend accounts. Suspended users cannot log in or transact.

### 3.2 Renter eligibility
- FR-7 Renters provide their date of birth. The backend enforces a minimum age of 18 (configurable upward).
- FR-8 Renters upload a South African ID document (or passport for non-citizens, see OPEN-5) and a driving licence.
- FR-9 Verification statuses: `NOT_SUBMITTED`, `PENDING`, `APPROVED`, `REJECTED`, `REQUIRES_MORE_INFORMATION`.
- FR-10 Only authorised administrators can change a verification status. Every decision is recorded with the reviewer, time, and reason.
- FR-11 Uploading a document does not make it valid. Approval requires a human review or an approved verification service.

### 3.3 Vehicles
- FR-12 Owners register vehicles with make, model, year, registration number, VIN, transmission, fuel type, seats, location, photos, and required documents (e.g. licence disc, roadworthy certificate, proof of insurance).
- FR-13 Vehicle statuses: `DRAFT`, `PENDING_APPROVAL`, `APPROVED`, `REJECTED`, `SUSPENDED`, `UNAVAILABLE`.
- FR-14 Only `APPROVED` vehicles appear in the marketplace and can be booked.
- FR-15 Owners manage availability (blocked dates) but cannot set prices or approve vehicles.

### 3.4 Pricing
- FR-16 Only administrators set official prices (daily rate, plus optional delivery fee and deposit).
- FR-17 Prices are stored as exact decimals in ZAR with full history: who changed the price, when, and the old and new values.
- FR-18 A booking stores a snapshot of its price breakdown. Later price changes do not affect existing bookings.

### 3.5 Marketplace and booking
- FR-19 Renters browse, search, and filter approved vehicles by location, dates, price, transmission, seats, and so on.
- FR-20 Renters pick rental dates. The backend checks eligibility and availability and calculates the price.
- FR-21 A booking starts as `PENDING_PAYMENT` and holds the vehicle for a limited time. Unpaid holds expire.
- FR-22 Overlapping confirmed bookings for the same vehicle are impossible, including under concurrent requests.
- FR-23 Renters can cancel according to the cancellation policy (OPEN-2) and view their booking history.

### 3.6 Payments
- FR-24 The backend creates payment requests with a ZAR payment provider.
- FR-25 Payment success is set only after the backend verifies it (signed webhook plus provider confirmation). Client-reported status is never trusted.
- FR-26 Webhook processing is idempotent.
- FR-27 Refunds are supported where the provider allows them.
- FR-28 Owner payouts and platform commission are recorded (OPEN-1).

### 3.7 Delivery and tracking
- FR-29 Every paid booking has one delivery record linked to it.
- FR-30 Deliveries are assigned to an authorised owner or driver.
- FR-31 The assigned delivery person shares location only while the delivery is active.
- FR-32 Renters see the live location, ETA, and last-update time of their own active delivery over WebSockets.
- FR-33 Handover (delivery) and return are recorded, including time, odometer, fuel level, and condition notes or photos.

### 3.8 Dashboards and notifications
- FR-34 Renters and owners each have a mobile dashboard for their own data.
- FR-35 Administrators use a separate web dashboard covering users, owners, vehicles, pricing, bookings, payments, refunds, deliveries, verification, reports, and audit logs.
- FR-36 Users receive email and push notifications for booking, payment, verification, delivery, cancellation, and return-reminder events.

## 4. Non-functional requirements

| ID | Requirement |
|----|-------------|
| NFR-1 Security | HTTPS in production, hashed passwords (Argon2id or bcrypt), backend-enforced RBAC on every protected endpoint, no secrets in source control. |
| NFR-2 Privacy | POPIA (Protection of Personal Information Act) compliance: minimal collection, purpose limitation, access control, retention limits, and data-subject rights. ID and licence data never appear in public responses or logs. |
| NFR-3 Data integrity | Money uses `NUMERIC`/`Decimal`, never floats. Booking overlap is enforced in the database. Payment processing is idempotent. |
| NFR-4 Auditability | Sensitive actions (approvals, price changes, verification decisions, refunds, suspensions) are written to `audit_logs`. |
| NFR-5 Time | Times are stored in UTC and shown in Africa/Johannesburg (SAST, UTC+2). |
| NFR-6 Testability | Critical business rules have automated tests. External services are used through adapters so tests can use sandbox or test doubles. |
| NFR-7 Real data | Production features use backend data only. Mock data is limited to tests and clearly labelled prototypes. |
| NFR-8 Platforms | The mobile app targets Android and iOS through Expo. The admin dashboard targets modern desktop and tablet browsers. |

## 5. Open business decisions

| ID | Question | Needed by |
|----|----------|-----------|
| OPEN-1 | Commission model and owner payout schedule. Is the platform a merchant of record or a split-payment marketplace? | Stage 11 |
| OPEN-2 | Cancellation and refund policy (time windows, fees). | Stage 10 |
| OPEN-3 | Who delivers vehicles: owners, platform drivers, or both? Decides whether the `DRIVER` role is needed. | Stage 12 |
| OPEN-4 | Insurance arrangement and any insurer-imposed minimum age or licence-duration rules (many SA insurers require 21+ or 23+, or several years of licence history). | Stage 06 |
| OPEN-5 | Are foreign nationals (passport plus international driving permit) supported? | Stage 06 |
| OPEN-6 | Is the business VAT-registered? If so, prices are shown VAT-inclusive at 15%. | Stage 08 |
| OPEN-7 | Security deposit amount and holding mechanism. | Stage 11 |
| OPEN-8 | Choice of payment provider after the merchant account review (see architecture.md). | Stage 11 |
| OPEN-9 | Manual document review only, or an external KYC/ID verification service? | Stage 06 |
