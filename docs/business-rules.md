# Business Rules

These rules are enforced by the **backend**. The mobile app and admin dashboard
may mirror them for user experience, but they are never the source of truth.

## BR-1 Identity and roles
1. Role assignments live only in the database. Roles in a client request or in unsigned client data are ignored.
2. Nobody can self-register as `ADMIN`. Administrators are created through a controlled CLI command run by an operator.
3. Suspended accounts cannot authenticate, book, list vehicles, or update deliveries.
4. A user cannot approve, verify, or price anything they own or submitted.

## BR-2 Renter eligibility
A renter may create a booking only if **all** of these are true at booking time:
1. The account is active (not suspended) and the email is verified.
2. The date of birth is recorded and the renter is at least `MIN_RENTER_AGE` years old (default 18) on the rental **start date**.
3. The ID document verification status is `APPROVED`.
4. The driving licence verification status is `APPROVED`, and the recorded licence expiry date is after the rental **end date**.
5. Any extra insurer rules from OPEN-4 are satisfied.

Additional rules:
- A South African ID number encodes the date of birth (YYMMDD) and has a Luhn check digit. The backend may use these to flag mismatches, but a valid format **does not prove** the document is genuine.
- Uploading a document sets its status to `PENDING`. Only an authorised reviewer can set `APPROVED`, `REJECTED`, or `REQUIRES_MORE_INFORMATION`, and each decision records the reviewer, timestamp, and reason.
- If a document is replaced after approval, its status returns to `PENDING`.

## BR-3 Vehicles
1. New vehicles start in `DRAFT`. The owner submits them to `PENDING_APPROVAL`.
2. Only an administrator can move a vehicle to `APPROVED`, `REJECTED`, or `SUSPENDED`.
3. The owner can switch an approved vehicle between `APPROVED` and `UNAVAILABLE`. This does not cancel existing bookings; conflicts are flagged to an administrator.
4. A vehicle needs an active official price before it can be `APPROVED`.
5. Only `APPROVED` vehicles appear in public listings or accept new bookings.
6. Material edits to an approved vehicle (such as registration, VIN, or documents) send it back to `PENDING_APPROVAL`.
7. Registration numbers and VINs are unique across active vehicles.

## BR-4 Pricing
1. Only administrators create or change official prices. Owner and renter requests that include price fields are rejected or ignored.
2. Money is stored as `NUMERIC(12,2)` and handled as Python `Decimal`. The currency is always `ZAR`.
3. Price records are append-only, each with `effective_from` and `created_by`. The current price is the most recent active record.
4. Rental charge = daily rate × number of billable days. A billable day is each started 24-hour period from pickup or delivery (to be confirmed under OPEN-2). Delivery fee and deposit are separate line items.
5. Rounding: round half up to 2 decimal places, applied once per line item.
6. When a booking is created, its full price breakdown is copied into the booking. Later price changes never change existing bookings.
7. Every price change writes an audit log entry with the old value, new value, actor, and time.

## BR-5 Bookings
1. The backend calculates the price. Client-sent totals are ignored.
2. A new booking is `PENDING_PAYMENT` and holds the vehicle for `BOOKING_HOLD_MINUTES` (default 15). After that it becomes `EXPIRED` and releases the dates.
3. No two bookings in a blocking state (`PENDING_PAYMENT` with an unexpired hold, `CONFIRMED`, or later active states) may overlap for the same vehicle. A PostgreSQL exclusion constraint enforces this, so concurrent requests cannot both succeed.
4. The start date must be in the future, the end date must be after the start, and the length must be within the configured minimum and maximum.
5. Allowed status transitions (refined in Stage 10):

```
PENDING_PAYMENT ─► CONFIRMED ─► DELIVERY_SCHEDULED ─► IN_TRANSIT ─► DELIVERED ─► ACTIVE_RENTAL ─► RETURN_PENDING ─► COMPLETED
      │                │                 │
      ├─► EXPIRED      └─► CANCELLED ◄───┘
      └─► CANCELLED
```

   Any transition not listed is rejected.
6. Cancellation fees and refunds follow the policy from OPEN-2.

## BR-6 Payments
1. Only the backend creates payments, for the amount on the booking's price snapshot.
2. A payment becomes `SUCCEEDED` only after the backend verifies the provider's signed notification **and** confirms the amount and currency match the booking.
3. Every provider event is stored with a unique provider event ID. Duplicate events are acknowledged but not processed twice.
4. Payment success moves the booking from `PENDING_PAYMENT` to `CONFIRMED` in the same database transaction.
5. If payment succeeds after a hold has expired and the dates are no longer free, the payment is refunded automatically or flagged for an administrator. It is never applied silently.
6. Refunds are recorded as separate refund records linked to the payment and audited.
7. No real-money transaction is run in development or tests. Only provider sandbox credentials are used.

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
These actions write an `audit_logs` entry recording the actor, action, entity, time, and before/after summary (with sensitive values masked):
vehicle approval, rejection, and suspension; price changes; verification decisions; account suspension and reinstatement; refunds; manual booking or payment overrides; administrator account creation; and private document access.
