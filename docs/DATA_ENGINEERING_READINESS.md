# Data Engineering Assessment: Readiness Report

Verification snapshot: 2026-10-27. This document distinguishes automated fixture evidence
from current live development-database evidence.

## Status summary

| Area | Status | Evidence |
|---|---|---|
| Repository architecture and source-model audit | **PASS** | Existing booking, payment, refund models and migrations inspected |
| New analytics snapshot schema | **PASS** | Alembic revision `d4a9c74a30fe` applied to the verified empty local development DB; `alembic check` reports no pending model changes |
| Extraction, validation and transformation | **PASS** | Full-refresh ETL implemented; focused pipeline tests pass |
| Repeatable analytics storage | **PASS** | Unique month key, conflict-upsert and stale derived-month reconciliation; test executes refresh twice |
| Admin API and authorization | **PASS** | FastAPI integration tests verify aggregate values, 401/403 authorization and 422 month bound |
| Database-error behavior | **PASS** | Test confirms query failure produces HTTP 500, not empty success |
| Full source → storage → API integration | **PASS** | Test uses isolated PostgreSQL fixture records and exercises pipeline then authenticated API |
| Non-empty live-data demonstration | **PARTIAL** | Actual development DB contains zero bookings/payments/refunds; live pipeline ran successfully with 0 source rows |
| Live authenticated HTTP demonstration | **PARTIAL** | Live health and marketplace endpoints verified; analytics route correctly returns 401 without auth. An admin account and real source records are not present locally |
| Documentation package | **PASS** | Demo, Q&A, presentation and this readiness report created |

**Was a complete non-empty source-to-API demonstration using genuine operational records
successfully executed? No.** The automated end-to-end test uses clearly identified isolated
test fixtures. The live development database has no source records, so its successful
refresh generated zero monthly rows. Do not present fixture values as live business data.

## Findings and implementation

- Before implementation, the project had operational `bookings`, `payments`, and `refunds`
  models and live administrator reporting, but no stored data pipeline, refresh command or
  analytics API route.
- The configured development PostgreSQL database was read-only inspected and found to have
  no tables before migration. Existing Alembic migrations plus the new additive migration
  were applied; no pre-existing business records were deleted or overwritten.
- The test database is separately configured as `car_rental_test`. It was empty before
  tests; the project's documented test fixture drops/rebuilds its schema.
- The new pipeline extracts independent source rows via one `UNION ALL`, validates status,
  currency, amount and event-date invariants, aggregates by `Africa/Johannesburg` month,
  then transactionally upserts `monthly_platform_analytics`.
- The admin-only endpoint is `GET /api/v1/admin/analytics/monthly?months=12` (1–120).
- Cash basis is gross payment amounts with `paid_at`, less `PROCESSED` refunds with
  `processed_at`. Booking counts are by `created_at`; status counts reflect status at
  refresh, not status history.

## Relevant files

- ETL and validation: `backend/app/services/analytics.py`
- CLI command: `backend/app/cli.py` (`analytics-refresh`)
- Snapshot model: `backend/app/models/analytics.py`
- API: `backend/app/api/routes/admin_analytics.py`; registered in
  `backend/app/api/router.py`
- Migration: `backend/migrations/versions/2026_10_27_1319-d4a9c74a30fe_add_monthly_platform_analytics.py`
- Tests: `backend/tests/analytics/test_pipeline.py`,
  `backend/tests/db/test_migrations.py`
- Architecture and operating instructions: `backend/README.md`,
  `docs/architecture.md`, `docs/DATA_ENGINEERING_DEMO.md`

## Database source and output

Operational sources:

- `bookings`: booking creation timestamp, current booking status.
- `payments`: attempted amount/status and `paid_at` when funds are received.
- `refunds`: attempted amount/status and `processed_at` when a refund is completed.

Derived output: `monthly_platform_analytics`, one row per active source month, with
`bookings_created`, `bookings_by_current_status`, `cash_collected`, `cash_refunded`,
`net_cash`, `currency` and `refreshed_at`. The database primary keys and foreign keys
provide uniqueness and relationship guarantees. The new table does not contain customer
names, emails or payment credentials.

## Commands executed and results

Commands were run from `backend/` unless stated:

| Command | Result |
|---|---|
| `python -m alembic upgrade head` | Passed; applied existing schema revisions and new analytics revision `d4a9c74a30fe` |
| `python -m alembic current` | `d4a9c74a30fe (head)` |
| `python -m alembic check` | `No new upgrade operations detected.` |
| `python -m app.cli analytics-refresh` | Passed twice; each run reported 0 bookings, 0 payments, 0 refunds, 0 months |
| Read-only PostgreSQL counts | `bookings=0`, `payments=0`, `refunds=0`, `monthly_platform_analytics=0` |
| `pytest tests/analytics/test_pipeline.py tests/db/test_migrations.py -q` | **16 passed** (final focused run, including the final empty-response and validation-atomicity tests) |
| `ruff check .` | **All checks passed** |
| `ruff format --check .` | **182 files already formatted** |
| `pytest -q --tb=short` (first full run) | **657 passed, 1 failed**; failure was `tests/notifications/test_dispatch.py::test_preferences_are_respected_except_for_essential_emails`, outside changed files |
| Isolated rerun of that notification test | **1 passed** |
| `pytest -q --tb=short` (second full run) | **658 passed in 278.76s** |
| `curl http://localhost:8000/api/v1/health` | HTTP 200 |
| `curl http://localhost:8000/api/v1/vehicles` | HTTP 200, `items=[]`, `total=0` |
| `curl http://localhost:8000/api/v1/admin/analytics/monthly` without token | HTTP 401, expected |

The second full-suite run completed successfully. The final focused run subsequently
added and passed two more analytics tests; those two were not part of the 658-test full
run. The first run's notification failure was not reproduced in either its isolated rerun
or the second full-suite run.

## Remaining work before assessment

1. Finish the second full backend test run and record its actual result. Investigate any
   persistent failure without changing tests to hide it.
2. Ensure the assessment environment has current migrations and create an administrator
   through the existing interactive CLI.
3. Use genuine application workflows to create representative bookings; use only a test
   payment provider for cash examples. Do not use demo seed data as proof of real records.
4. Run `analytics-refresh`, verify source SQL against snapshot SQL, then call the endpoint
   with an admin access token.
5. Update the presentation notes with the actual populated database's output and timestamp.

## Exact assessment commands

From the repository root:

```bash
docker compose up -d db
cd backend
python -m alembic upgrade head
python -m app.cli create-admin --email <admin-email> --full-name "<admin-name>"
python -m uvicorn app.main:app --reload --port 8000
```

In another backend terminal, once genuine source records exist:

```bash
cd backend
python -m app.cli analytics-refresh
```

Demonstrate `GET /api/v1/admin/analytics/monthly?months=12` with an administrator bearer
token and use the independent source/snapshot SQL in `docs/DATA_ENGINEERING_DEMO.md`.

## Decisions to understand and defend

- Output grain is one South African calendar month.
- No source-table joins are used because payment/refund relationships can multiply totals.
- Booking status is a current snapshot grouped by booking creation month, not historical
  status-at-month-end.
- Cash is based on actual payment/refund timestamps, not the agreed booking total.
- The pipeline is full refresh because no complete immutable change log supports a safe
  incremental watermark.
- Derived data is stored in the existing PostgreSQL database because this project's
  current volume does not justify another warehouse.
- Integration fixture results prove code behavior but are not evidence of live source
  records.
