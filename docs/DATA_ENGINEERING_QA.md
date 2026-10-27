# Data Engineering Assessment: Technical Q&A

Answers below describe the current implementation, not future plans. Files are relative to
the repository root.

## Architecture

### 1. Explain the pipeline from source to API.

- **Suggested answer:** `analytics-refresh` reads bookings, payments and refunds in one
  statement, validates them, groups by South African month, upserts a snapshot, and an
  admin-only route returns that stored snapshot.
- **Files:** `backend/app/cli.py`, `backend/app/services/analytics.py`,
  `backend/app/models/analytics.py`, `backend/app/api/routes/admin_analytics.py`.
- **Show:** run the CLI, query `monthly_platform_analytics`, request
  `/api/v1/admin/analytics/monthly`.
- **Follow-up:** Which step is the system of record? The operational booking/payment/refund
  tables remain authoritative; analytics rows are derived.

### 2. Why was this architecture chosen?

- **Suggested answer:** The app already uses PostgreSQL, SQLAlchemy and Alembic, and this
  workload is a small periodic aggregate. A transactional full refresh is easier to audit
  than adding a warehouse or a streaming platform.
- **Files:** `backend/app/services/analytics.py`, migration under
  `backend/migrations/versions/`.
- **Show:** point to the source query and the single snapshot table.
- **Follow-up:** What changes at much larger scale? Partitioned/incremental extraction and
  an orchestrator could be evaluated after measuring load.

### 3. Why keep operational and analytical data in the same PostgreSQL database?

- **Suggested answer:** At this scale, separate infrastructure would add operational cost
  without a demonstrated need. The analytics table is still a separate derived table and
  does not replace operational records.
- **Files:** `backend/app/models/analytics.py`, `docs/architecture.md`.
- **Show:** compare source and derived tables in the schema.
- **Follow-up:** What is the downside? Full refreshes consume operational database resources;
  a separate replica/warehouse may become appropriate.

### 4. Is this a data warehouse?

- **Suggested answer:** No. It is a small monthly aggregate table in the existing
  PostgreSQL database, not a separate warehouse or dimensional model.
- **Files:** `backend/app/models/analytics.py`, `docs/DATA_ENGINEERING_DEMO.md`.
- **Show:** migration creates only `monthly_platform_analytics`.
- **Follow-up:** What additional needs might justify a warehouse? Multiple source systems,
  historical dimensions, large analytical scans or workload isolation.

## Extraction

### 5. What are the pipeline's source tables and grain?

- **Suggested answer:** `bookings`, `payments` and `refunds` are extracted independently.
  The output grain is one row per South African calendar month.
- **Files:** `backend/app/services/analytics.py`, `backend/app/models/booking.py`,
  `backend/app/models/payment.py`.
- **Show:** source table SQL and the `month_start` primary key.
- **Follow-up:** Why is the grain important? It defines what one output row represents and
  prevents mixed record counts.

### 6. How are database resources managed?

- **Suggested answer:** The CLI creates an SQLAlchemy engine/session, runs the refresh in a
  transaction, commits only on success, and disposes the engine in `finally`.
- **Files:** `backend/app/cli.py`, `backend/app/db/session.py`.
- **Show:** run `python -m app.cli analytics-refresh` and inspect the command's cleanup.
- **Follow-up:** What happens if validation fails? No successful commit is issued and the
  session close rolls back its work.

### 7. Is extraction incremental?

- **Suggested answer:** No. It is a full scan. Booking status is mutable and payment/refund
  states can change; available timestamps alone do not provide a complete immutable change
  stream for all metrics.
- **Files:** `backend/app/services/analytics.py`, `backend/app/models/booking.py`,
  `backend/app/models/payment.py`.
- **Show:** explain why the command re-reads all three sources.
- **Follow-up:** How could incremental processing be made reliable? Capture all relevant
  changes in an outbox/change log with a monotonic watermark and reconciliation strategy.

### 8. How does the extraction handle growing source tables?

- **Suggested answer:** The query selects only fields needed for aggregation and uses
  `yield_per(1000)` so Python does not retain every source row. Memory grows mainly with
  the number of months, not the number of transactions.
- **Files:** `backend/app/services/analytics.py`.
- **Show:** inspect selected columns and the streaming loop.
- **Follow-up:** Does this remove database scan cost? No; every source record is still read
  on each full refresh.

### 9. Why use `UNION ALL` and not joins?

- **Suggested answer:** Bookings, payment attempts and refunds are different-grain facts.
  Joining them can multiply one booking/payment across several refunds. `UNION ALL` gives
  one source row per record in one consistent SQL statement.
- **Files:** `backend/app/services/analytics.py`.
- **Show:** point to the three branches and the test with multiple refunds.
- **Follow-up:** Why not `UNION`? `UNION` removes duplicates and performs unnecessary
  distinct work; source uniqueness is already guaranteed by primary keys.

## Data quality

### 10. What validation is implemented?

- **Suggested answer:** The pipeline checks enum membership, finite positive amounts, ZAR
  currency, required booking dates, and the timestamps required for succeeded payments and
  processed refunds.
- **Files:** `backend/app/services/analytics.py`,
  `backend/tests/analytics/test_pipeline.py`.
- **Show:** run `pytest tests/analytics/test_pipeline.py::test_invalid_money_is_rejected`.
- **Follow-up:** Which validation is enforced by PostgreSQL too? Positive amounts, currency,
  status values, required relationships and some required status timestamps.

### 11. What happens when a record is invalid?

- **Suggested answer:** The refresh raises `PipelineDataQualityError` with source type and
  record ID. It fails the whole refresh rather than silently dropping a row.
- **Files:** `backend/app/services/analytics.py`, `backend/app/cli.py`.
- **Show:** run the invalid-money tests and note the command's non-zero exception path.
- **Follow-up:** Why fail the whole run? A partial monthly snapshot could be mistaken for a
  complete result.

### 12. How are duplicates and broken references detected?

- **Suggested answer:** Primary keys and foreign-key constraints enforce source uniqueness
  and references. The analytics output has a unique month primary key and conflict-upsert.
- **Files:** `backend/app/models/booking.py`, `backend/app/models/payment.py`,
  migration for `monthly_platform_analytics`.
- **Show:** database constraints and the `ON CONFLICT` key.
- **Follow-up:** What if data is imported with constraints disabled? Add a source audit
  before trusting that data; this pipeline intentionally relies on normal database
  enforcement.

### 13. Are missing values silently ignored?

- **Suggested answer:** A succeeded payment without `paid_at` and a processed refund without
  `processed_at` fail the refresh. An unpaid pending attempt legitimately has no `paid_at`
  and is not counted as cash.
- **Files:** `backend/app/services/analytics.py`.
- **Show:** inspect the timestamp checks and pending payment test.
- **Follow-up:** Why not treat a missing timestamp as the current month? That would invent
  event timing and misstate cash flow.

## Transformation and metrics

### 14. How are months calculated?

- **Suggested answer:** PostgreSQL converts event timestamps to `Africa/Johannesburg`,
  truncates to month, and casts to a date. This avoids assigning a late-UTC event to the
  wrong South African month.
- **Files:** `backend/app/services/analytics.py`,
  `backend/tests/analytics/test_pipeline.py`.
- **Show:** run the timezone-boundary test.
- **Follow-up:** What about daylight-saving changes? The IANA time-zone database applies
  the named zone's rules; South Africa currently has no seasonal DST changes.

### 15. What does `bookings_created` mean?

- **Suggested answer:** It counts booking rows by `created_at`; the status breakdown is
  their current status when refresh runs, not a historical status snapshot for that month.
- **Files:** `backend/app/models/booking.py`,
  `backend/app/models/analytics.py`.
- **Show:** compare one month's SQL count by status to the API row.
- **Follow-up:** How would you report status transitions over time? Store immutable status
  events with timestamps and aggregate those events.

### 16. Why is cash collected not calculated from `Booking.total_amount`?

- **Suggested answer:** A booking amount is an agreed price, not proof that funds were
  received. Cash collected uses payment records with `paid_at`; pending/failed attempts
  without that timestamp are excluded.
- **Files:** `backend/app/services/analytics.py`,
  `backend/app/services/payments.py`.
- **Show:** compare a pending payment and succeeded payment in the fixture test.
- **Follow-up:** Is this recognized accounting revenue? No; it is gross platform cash
  collected and does not model recognition, fees or payouts.

### 17. How are refunds and net cash handled?

- **Suggested answer:** Only `PROCESSED` refunds count, by `processed_at`; net cash is
  collected minus processed refunds. It can be negative in a month with refunds for earlier
  payments.
- **Files:** `backend/app/models/payment.py`,
  `backend/app/services/analytics.py`.
- **Show:** test fixture output: 1000.00 collected, 250.00 refunded, 750.00 net.
- **Follow-up:** Why not deduct pending refunds? The cash has not yet been confirmed as
  returned.

### 18. How are joins and duplicate totals avoided?

- **Suggested answer:** Each source table is scanned independently in one `UNION ALL`
  statement, with no payment/refund join. The test includes multiple refunds on one payment
  and verifies the payment amount is counted once.
- **Files:** `backend/app/services/analytics.py`,
  `backend/tests/analytics/test_pipeline.py`.
- **Show:** execute the focused repeatability/grain test.
- **Follow-up:** What if a future metric needs dimensions? Aggregate facts at a documented
  grain before joining and test fan-out explicitly.

## Storage and database

### 19. Why store the result in a table?

- **Suggested answer:** The endpoint can serve a repeatable, inspectable snapshot without
  repeating all source scans on every request. It is derived and can be rebuilt.
- **Files:** `backend/app/models/analytics.py`, the Alembic migration.
- **Show:** inspect the persisted row and `refreshed_at`.
- **Follow-up:** Why not a materialized view? A table allows explicit validation, run timing
  and transactional replacement with the current project patterns; a materialized view
  could be reconsidered if operational requirements change.

### 20. How is repeatability achieved?

- **Suggested answer:** `month_start` is the primary key and each refresh upserts the
  computed values. Stale derived months are removed in the same transaction.
- **Files:** `backend/app/services/analytics.py`.
- **Show:** run refresh twice and confirm one row per month and unchanged totals.
- **Follow-up:** Can a failed load leave half a snapshot? The CLI commits only after load;
  database transaction rollback protects the prior snapshot.

### 21. How are schema changes managed?

- **Suggested answer:** The new table is added in a forward Alembic migration. Existing
  tables and records are not dropped or rewritten by the migration.
- **Files:** `backend/migrations/versions/2026_10_27_1319-d4a9c74a30fe_add_monthly_platform_analytics.py`,
  `backend/tests/db/test_migrations.py`.
- **Show:** run `python -m alembic current` and `python -m alembic check`.
- **Follow-up:** What is the downgrade effect? It removes only the newly added derived
  analytics table; run downgrade only with an explicit data-retention decision.

### 22. Why PostgreSQL?

- **Suggested answer:** PostgreSQL is already the operational database and provides
  transactions, exact `NUMERIC` values, constraints, JSONB status counts and the timezone
  functions used by the aggregate.
- **Files:** `backend/app/db/session.py`, `backend/app/models/analytics.py`.
- **Show:** inspect the `NUMERIC(12,2)` fields and source constraints.
- **Follow-up:** Would JSONB be right for every dimension? No; it fits this compact status
  map, while dimensions queried independently should likely be normalized.

## API, reliability and testing

### 23. How is the endpoint protected?

- **Suggested answer:** It reuses the app's `AdminUser` role dependency. Renters/owners get
  403 and unauthenticated requests get 401.
- **Files:** `backend/app/api/routes/admin_analytics.py`,
  `backend/app/api/deps.py`.
- **Show:** the API authorization tests.
- **Follow-up:** Is hiding the endpoint in a UI enough? No; authorization is enforced in
  the backend.

### 24. How does the API respond to a database error?

- **Suggested answer:** Query exceptions propagate to the shared error handler and produce
  an HTTP 500 envelope; they are not converted into an empty list.
- **Files:** `backend/app/api/routes/admin_analytics.py`,
  `backend/app/core/errors.py`.
- **Show:** run `test_database_errors_are_not_reported_as_empty_analytics`.
- **Follow-up:** Why not expose the database exception? It can leak internal details; the
  server logs retain diagnostic context while the client gets a generic error.

### 25. What tests prove the pipeline?

- **Suggested answer:** Tests cover multi-source aggregation, separate fact grains,
  repeatability, South African month boundaries, empty sources, invalid amounts, endpoint
  permissions/range, database errors and migration/model parity.
- **Files:** `backend/tests/analytics/`, `backend/tests/db/test_migrations.py`.
- **Show:** run the focused analytics/migration test command.
- **Follow-up:** What does a test fixture prove? Code behavior against controlled data, not
  that the current live database contains genuine business records.

### 26. What is the biggest current limitation?

- **Suggested answer:** The operational development database currently has no business
  records, so the real CLI run loads zero months. Non-empty values are verified in isolated
  test fixtures, but a meaningful live-data demonstration still needs records created
  through the app and an admin account.
- **Files:** `docs/DATA_ENGINEERING_READINESS.md`.
- **Show:** compare the live zero-row CLI output with fixture-backed test assertions.
- **Follow-up:** How will you avoid misrepresenting test data? State explicitly which result
  is fixture output and which is the current development database.

### 27. What would you improve next?

- **Suggested answer:** First collect operational records and repeat the end-to-end demo.
  Later, add immutable status/change events and a reliable incremental watermark, then
  schedule and monitor the refresh if volume justifies it.
- **Files:** `backend/app/services/analytics.py`,
  `docs/DATA_ENGINEERING_READINESS.md`.
- **Show:** explain the full-scan code path and its observable row counts.
- **Follow-up:** Why not add Kafka/Airflow now? The current scale and assessment flow do not
  justify another service or failure mode.
