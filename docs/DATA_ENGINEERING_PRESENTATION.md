# Data Engineering Assessment: Presentation Script

Target duration: approximately 12 minutes. The exact live values depend on source records
in the development database. The values verified so far are zero live operational rows;
automated integration-test values are fixtures and must be identified as such.

## 1. Introduction and problem statement — 45 seconds

- **Say:** “I’m demonstrating a real ETL path inside the existing Car Rental system:
  operational PostgreSQL records are extracted, validated and transformed into persisted
  monthly analytics, then served through the existing FastAPI backend.”
- **Show:** this guide's architecture diagram, then the repo README and stack.
- **Command/file:** `docs/DATA_ENGINEERING_DEMO.md`; `backend/README.md`.
- **Expect:** clear distinction between operational data and derived metrics.
- **Point:** the endpoint is the last stage, not the whole pipeline.

## 2. Overview of the Car Rental application — 45 seconds

- **Say:** “The existing application already models owners, renters, vehicles, bookings,
  payments and refunds. The pipeline reuses those real operational records.”
- **Show:** project architecture diagram and the booking/payment models.
- **Command/file:** `docs/architecture.md`; `backend/app/models/booking.py`;
  `backend/app/models/payment.py`.
- **Expect:** PostgreSQL is already the system of record; no unrelated project was created.
- **Point:** assessment work integrates with the current architecture.

## 3. Source data — 50 seconds

- **Say:** “I use three source tables, but they represent different fact grains:
  one booking, one payment attempt, and one refund. They must not be joined before summing.”
- **Show:** table definitions and independent SQL queries in the demo guide.
- **Command/file:** inspect `bookings`, `payments`, `refunds` in PostgreSQL.
- **Expect:** statuses, timestamps and money amounts correspond to actual model fields.
- **Point:** correct grain prevents a payment being multiplied by several refunds.

## 4. Pipeline architecture — 55 seconds

- **Say:** “A CLI command runs a single `UNION ALL` extraction statement, validates rows,
  aggregates by South African month, and transactionally upserts the snapshot table.”
- **Show:** Mermaid diagram and pipeline implementation.
- **Command/file:** `backend/app/services/analytics.py`;
  `backend/app/models/analytics.py`.
- **Expect:** a direct path from source tables to persisted table to protected endpoint.
- **Point:** no separate warehouse or undocumented background service is involved.

## 5. Extraction — 55 seconds

- **Say:** “The query selects only needed fields, avoids joins and streams batches. One SQL
  statement gives the three source scans one consistent PostgreSQL snapshot.”
- **Show:** `_source_rows()` and the `yield_per(1000)` loop.
- **Command/file:** `backend/app/services/analytics.py`.
- **Expect:** source rows enter the same validation/transformation loop with a source label.
- **Point:** a full scan is deliberate because status/payment/refund changes lack a complete
  incremental change log.

## 6. Validation — 55 seconds

- **Say:** “Statuses, ZAR currency, finite positive amounts and required event timestamps
  are checked. The refresh rejects the full run on an invalid row; it does not silently
  drop data.”
- **Show:** `PipelineDataQualityError` and related tests.
- **Command/file:** `python -m pytest tests/analytics/test_pipeline.py::test_invalid_money_is_rejected -q`
- **Expect:** four passing invalid-money cases; no database row is modified.
- **Point:** model/database constraints provide a second line of defense.

## 7. Transformation and metric definitions — 1 minute

- **Say:** “Bookings are counted by creation month and broken down by their current status.
  Cash collected is assigned by `paid_at`, processed refunds by `processed_at`; net is
  gross collected minus processed refunds.”
- **Show:** metric definition table in the demo guide and transform loop.
- **Command/file:** `backend/app/services/analytics.py`.
- **Expect:** no booking `total_amount` is mislabeled as earned revenue.
- **Point:** cash-flow metrics are not accounting revenue or owner earnings.

## 8. Analytics storage and repeatability — 55 seconds

- **Say:** “There is one row per month, keyed by `month_start`. Upsert makes repeated runs
  stable; stale derived months are reconciled inside the same transaction.”
- **Show:** Alembic migration and snapshot table query.
- **Command/file:** `python -m alembic current`;
  `backend/migrations/versions/2026_10_27_1319-d4a9c74a30fe_add_monthly_platform_analytics.py`.
- **Expect:** current migration at head; one output row for each active month.
- **Point:** only derived analytics rows are replaced; source records are never written by
  this command.

## 9. Pipeline execution — 45 seconds

- **Say:** “This is the actual refresh command. Its row counts tell me whether the source
  database contains data; zero is not success-shaped fabricated output.”
- **Show:** terminal output.
- **Command:** from `backend/`, `python -m app.cli analytics-refresh`.
- **Expect:** current verified local result is 0 bookings, 0 payments, 0 refunds, 0 months.
- **Point:** before the assessment, populate real application records and rerun; do not use
  fixture output as live business data.

## 10. Database verification — 1 minute

- **Say:** “I independently query each source at its native grain, then compare the
  results with the stored aggregate.”
- **Show:** source queries and derived-table query in the demo guide.
- **Command/file:** SQL in `docs/DATA_ENGINEERING_DEMO.md`.
- **Expect:** booking status counts sum to `bookings_created`; net equals collected less
  processed refunds.
- **Point:** the output is verifiable without trusting the pipeline code alone.

## 11. FastAPI request and JSON — 55 seconds

- **Say:** “Only an administrator can read stored analytics. A database error remains a
  server error; it is never reported as an empty successful result.”
- **Show:** route and OpenAPI docs; use an administrator token.
- **Command/file:** `GET /api/v1/admin/analytics/monthly?months=12`;
  `backend/app/api/routes/admin_analytics.py`.
- **Expect:** a JSON list of the requested latest months; currently empty on the live
  development DB until real source records exist.
- **Point:** this endpoint reads the persisted snapshot; it does not recalculate it.

## 12. Testing and reliability — 1 minute

- **Say:** “The pipeline tests cover source grains, multiple refunds, idempotency, month
  boundaries, empty input, validation, authorization and database errors.”
- **Show:** focused test command and test summary.
- **Command:** `python -m pytest tests/analytics tests/db/test_migrations.py -q`
- **Expect:** 16 focused tests pass. The second full-suite run passed all 658 tests; the
  first run had one unrelated notification-test failure that passed on isolated rerun.
- **Point:** automated fixture coverage proves behavior, not the presence of live data.

## 13. Limitations, improvements and transition to Q&A — 1 minute

- **Say:** “The main limitation is that this local operational database is empty, so a
  non-empty live-data assessment run still needs real records and an admin account. The
  next justified step would be an immutable change log for incremental extraction, followed
  by scheduling/monitoring if needed.”
- **Show:** readiness report, limitations and the Q&A guide.
- **Command/file:** `docs/DATA_ENGINEERING_READINESS.md`;
  `docs/DATA_ENGINEERING_QA.md`.
- **Expect:** honest separation of verified automated results and remaining live-demo work.
- **Point:** conclude with “I’m ready to explain the grain, cash basis, failure behavior and
  repeatability choices.”
