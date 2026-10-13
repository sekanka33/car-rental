# Business Rules

These rules are enforced by the **backend**. The mobile app and admin dashboard
may mirror them for user experience, but they are never the source of truth.

## BR-1 Identity and roles
1. Role assignments live only in the database. Roles in a client request are rejected (request bodies forbid unknown fields), and access tokens do not carry roles. Each request reads roles and account status from the database.
2. Nobody can self-register as `ADMIN`. Administrators are created through a controlled CLI command run by an operator.
3. Suspended accounts cannot authenticate, book, list vehicles, or update deliveries. Suspension takes effect immediately: existing access tokens stop working and all refresh tokens are revoked.
4. A user cannot approve, verify, or price anything they own or submitted.
5. Passwords are 8–128 characters, differ from the email address, and are stored only as Argon2id hashes. Password reset signs the user out everywhere.
6. Responses to login failures and password-reset requests do not reveal whether an email address is registered. (Registration does say "already registered", to keep sign-up usable; rate limiting follows in Stage 17.)

## BR-2 Renter eligibility
A renter may create a booking only if **all** of these are true at booking time:
1. The account is active (not suspended) and the email is verified.
2. The date of birth is recorded and the renter is at least `MIN_RENTER_AGE` years old (default 18) on the rental **start date**.
3. The ID document verification status is `APPROVED`.
4. The driving licence verification status is `APPROVED`, and the recorded licence expiry date is after the rental **end date**.
5. Any extra insurer rules from OPEN-4 are satisfied.

Additional rules:
- A South African ID number encodes the date of birth (YYMMDD) and has a Luhn check digit. The backend may use these to flag mismatches, but a valid format **does not prove** the document is genuine.
- Uploading a document sets its status to `PENDING`. Only an authorised reviewer can set `APPROVED`, `REJECTED`, or `REQUIRES_MORE_INFORMATION`, and each decision records the reviewer, timestamp, and reason. Reviewers cannot review their own documents.
- If a document is replaced after approval, its status returns to `PENDING`.
- The ID number must be structurally valid and its birth date must match the profile's date of birth. One SA ID number can be approved on only one account.
- The date of birth cannot be changed while the ID is pending or approved.
- Full ID and licence numbers are never stored; see [document-handling.md](document-handling.md).
- Implemented in Stage 06 by `app/services/eligibility.py`. `MIN_RENTER_AGE` is configurable (default 18; OPEN-4 may raise it).

## BR-3 Vehicles
1. New vehicles start in `DRAFT`. The owner submits them to `PENDING_APPROVAL`.
2. Only an administrator can move a vehicle to `APPROVED`, `REJECTED`, or `SUSPENDED`. Suspension (with a reason, audited) hides the vehicle at once and blocks owner edits. Reinstatement returns a previously approved vehicle to `APPROVED`, otherwise to `DRAFT`. Suspension does not cancel existing bookings automatically (Stage 10 and 12 handle affected bookings).
3. The owner can switch an approved vehicle between `APPROVED` and `UNAVAILABLE`. This does not cancel existing bookings; conflicts are flagged to an administrator.
4. Approval and official pricing are separate administrator actions. A vehicle is **publicly listed and bookable only when it is `APPROVED` and has an active official price** (price rules: Stage 08; enforced in listings: Stage 09). *(Revised in Stage 07: the original rule "price before approval" would have made approval impossible before Stage 08.)*
5. Only `APPROVED` vehicles appear in public listings or accept new bookings, and only while the owner's account is active and the current licence disc and insurance are unexpired (`publicly_listed_vehicles()` in `app/services/vehicles.py`).
6. Material edits to an approved or unavailable vehicle send it back to `PENDING_APPROVAL`: make, model, year, registration number, VIN, transmission, fuel type, seats, or a new registration certificate. Cosmetic edits (description, colour, location) and renewals of the licence disc, insurance or roadworthy certificate do **not** need re-approval. An expired licence disc or insurance removes the vehicle from listings until renewed.
7. Registration numbers and VINs are unique across all vehicles. Registration numbers are stored upper-case without spaces or hyphens.
8. To submit for review, the owner needs a verified email, at least 3 photos, and a registration certificate, a licence disc and insurance (the last two with future expiry dates). Approval re-checks the documents and requires the owner's account to be active.
9. Owners can edit only in `DRAFT`, `REJECTED`, `APPROVED` or `UNAVAILABLE`. A vehicle under review must be withdrawn first, and a suspended vehicle cannot be edited. Only `DRAFT` and `REJECTED` vehicles can be deleted.
10. Owners can block date ranges. A block may not overlap an existing reserving booking.
11. Administrators cannot review their own vehicles. Every administrator view of a vehicle document is audited.

## BR-4 Pricing
1. Only administrators create or change official prices. Owner and renter requests that include price fields are rejected or ignored.
2. Money is stored as `NUMERIC(12,2)` and handled as Python `Decimal`. The currency is always `ZAR`.
3. Price records are append-only, each with `effective_from` and `created_by`; a database trigger rejects any UPDATE or DELETE on `vehicle_prices`. The current price is the record with the latest `effective_from` that is not in the future. Prices may be scheduled for the future but never backdated, and two prices for one vehicle cannot take effect at the same instant.
4. Rental charge = daily rate × number of billable days. A billable day is each started 24-hour period from pickup or delivery (to be confirmed under OPEN-2). Delivery fee and deposit are separate line items.
5. Rounding: round half up to 2 decimal places, applied once per line item.
6. When a booking is created, its full price breakdown is copied into the booking. Later price changes never change existing bookings.
7. Every price change writes an audit log entry with the old value, new value, actor, reason, and time.
8. Prices are entered with at most 2 decimal places (daily rate greater than 0; fees and deposit at least 0; each at most R100 000) and are returned as exact strings, e.g. `"650.00"`.
9. Administrators cannot set the price of a vehicle they own (BR-1.4).
10. **VAT (OPEN-6, undecided):** official prices are treated as final, VAT-inclusive rand amounts. No separate VAT line is calculated until the business confirms its VAT registration.
11. Implemented in `app/services/pricing.py` (Stage 08). The quote total is rental plus delivery fee; the deposit is shown separately and held separately (BR-6, Stage 11).

## BR-5 Bookings
1. The backend calculates the price. Client-sent totals are ignored.
2. A new booking is `PENDING_PAYMENT` and holds the vehicle for `BOOKING_HOLD_MINUTES` (default 15). After that it becomes `EXPIRED` and releases the dates.
3. No two bookings in a blocking state (`PENDING_PAYMENT`, `CONFIRMED`, `DELIVERY_SCHEDULED`, `IN_TRANSIT`, `DELIVERED`, `ACTIVE_RENTAL`, `RETURN_PENDING`) may overlap for the same vehicle. A PostgreSQL exclusion constraint enforces this, so concurrent requests cannot both succeed. Periods are half-open (`[start, end)`), so back-to-back bookings are allowed. A pending hold blocks its dates until its status changes. The booking service marks expired holds `EXPIRED` before it checks availability (Stage 10).
4. The start must be at least `BOOKING_MIN_LEAD_MINUTES` (default 120) in the future, the end must be after the start, and the rental can last at most `BOOKING_MAX_DAYS` (default 30). Times must include a timezone; the app sends South African time (`+02:00`).
4a. A renter may hold at most `MAX_PENDING_BOOKINGS_PER_RENTER` (default 2) unpaid bookings at once, cannot book their own vehicle, and must pass the eligibility rules (BR-2) for the chosen dates. Ineligible renters receive every failing reason.
4b. Owner date blocks (BR-3.10) also make dates unavailable. Creating a booking locks the vehicle row, so bookings and blocks for one vehicle are serialised.
5. Allowed status transitions (refined in Stage 10):

```
PENDING_PAYMENT ─► CONFIRMED ─► DELIVERY_SCHEDULED ─► IN_TRANSIT ─► DELIVERED ─► ACTIVE_RENTAL ─► RETURN_PENDING ─► COMPLETED
      │                │                 │
      ├─► EXPIRED      └─► CANCELLED ◄───┘
      └─► CANCELLED
```

   Any transition not listed is rejected.
6. Cancellation fees and refunds follow the policy from OPEN-2. **Default until OPEN-2 is decided:** the renter can cancel a `PENDING_PAYMENT` hold at any time, and a `CONFIRMED` booking up to its start time. Afterwards (or from `DELIVERY_SCHEDULED`) only an administrator can cancel, with a reason. **Stage 11 default refund:** a cancelled paid booking is refunded in full, automatically. Every cancellation records who, when and why, and is audited.
7. Expired holds are released three ways: just before availability is checked for that vehicle, whenever bookings are listed or opened, and by the `python -m app.cli expire-holds` command (run it from cron, e.g. every minute). Marketplace availability ignores holds past their deadline even before they are marked `EXPIRED`.
8. Implemented in `app/services/bookings.py` (Stage 10). `confirm_booking()` (`PENDING_PAYMENT` → `CONFIRMED`) is reserved for verified payments (Stage 11) and refuses holds that have expired.

## BR-6 Payments
1. Only the backend creates payments, for the amount on the booking's price snapshot.
2. A payment becomes `SUCCEEDED` only after the backend itself verifies the charge with the provider's API **and** confirms the reference, amount and currency match the booking. A signed notification only triggers that check; its contents are never trusted. A mismatch is marked `FAILED`, audited and left for an administrator.
3. Every provider notification is signature-checked (Paystack: HMAC-SHA512 of the raw body) and stored once under a unique key (SHA-256 of the signed body, because Paystack sends no event ID). Duplicate events are acknowledged but not processed twice.
4. Payment success moves the booking from `PENDING_PAYMENT` to `CONFIRMED` in the same database transaction.
5. If payment succeeds after a hold has expired, after the booking was cancelled, or for a booking that is already paid, the payment becomes `REFUND_PENDING` and is refunded automatically in full. It is never applied silently. (Stage 11 chose automatic refunds rather than re-confirming a late payment even when the dates are still free, because the renter was told the hold had ended.)
6. Refunds are recorded as separate refund records linked to the payment and audited.
7. No real-money transaction is run in development or tests. Only provider sandbox credentials are used. The backend refuses to start with a live key unless `ALLOW_LIVE_PAYMENTS=true`.
8. One checkout per booking at a time: starting payment again returns the open checkout. A new one is created only after the previous attempt failed.
9. The amount charged is the booking total (rental plus delivery fee). The security deposit is **not** charged online until OPEN-7 is decided.
10. Refunds can be full or partial (administrator, with a reason), never more than what remains unrefunded. A refund's status follows the provider (`PENDING` → `PROCESSED` or `FAILED`); a failed refund leaves the payment for an administrator to retry.
11. Pending payments and refunds are re-checked with the provider by `python -m app.cli reconcile-payments` (cron) so a lost webhook cannot leave a paid booking unconfirmed.
12. **Payouts (OPEN-1 default):** the platform collects as merchant of record into its Paystack balance. Owner payouts and commission are settled outside the system for now; each `SUCCEEDED` payment, its refunds and the booking's vehicle owner give the data needed for a payout report. Paystack subaccounts (split payments) can automate this once the commission model is agreed.
13. Implemented in `app/services/payments.py` and `app/integrations/payments.py` (Stage 11).

## BR-7 Deliveries and tracking
1. A delivery exists only for a `CONFIRMED` (or later) booking.
2. Only the assigned delivery person (owner or driver) can post location updates or change the delivery status, and only while the delivery is active.
3. Only the booking's renter, the assigned delivery person, and administrators can view a delivery's location.
4. Location sharing stops when the delivery is `DELIVERED`, `CANCELLED`, or `FAILED`. Updates sent after that are rejected.
5. Location data is kept only as long as needed for disputes and audits (retention period to be set; proposed 90 days).
6. Handover and return records capture time, odometer, fuel level, condition notes, and photos.

## BR-8 Documents and privacy (POPIA)
1. Identity, licence, and vehicle documents are stored privately (never in a public bucket or path) and served only through authorised, short-lived URLs.
2. Only the document's owner and authorised administrators can access it. Every access is logged.
3. ID numbers and licence numbers never appear in public APIs, vehicle listings, or application logs. Administrator views show them masked by default.
4. Public owner information is limited to first name and general area.
5. Retention: verification documents are kept only as long as required for legal and insurance purposes (period to be confirmed with legal advice), then deleted.

## BR-9 Audit
Audit entries are append-only: the database rejects UPDATE and DELETE, and users with
audit history cannot be hard-deleted (they are deactivated or anonymised instead).
These actions write an `audit_logs` entry recording the actor, action, entity, time, and before/after summary (with sensitive values masked):
vehicle approval, rejection, and suspension; price changes; verification decisions; account suspension and reinstatement; refunds; manual booking or payment overrides; administrator account creation; and private document access.
