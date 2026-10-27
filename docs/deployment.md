# Production deployment and operations

This runbook defines the platform-independent release gates for Stage 18. It is
not a deployment configuration: no hosting provider, production account, data
region, domain, or production credentials have been selected or approved.
Production deployment remains blocked until those decisions are made.

## Production blockers

- Select hosting for the API, PostgreSQL, private document storage, and static
  admin dashboard. Confirm South African data residency and the provider's
  backup, encryption, access logging, and restore capabilities.
- Implement and exercise an encrypted private object-storage adapter. The
  current local filesystem adapter is for development and is not suitable for
  production documents.
- Obtain and configure SMTP, Expo/EAS, Maps, and (if approved) Paystack
  credentials. Live payments remain disabled until separately approved.
- Confirm POPIA retention periods and deletion procedures with the responsible
  legal/privacy adviser.
- Replace the placeholder Android package and iOS bundle identifiers in
  `mobile/app.json`, create/attach the EAS project, and provision store signing
  credentials before creating release builds.
- Choose domains and set the production admin origin, API URL, TLS termination,
  trusted proxy addresses, upload limits, and alert destinations.

## Release checklist

1. Use a separate production database and secret store. Generate unique
   `JWT_SECRET_KEY` and `DOCUMENT_HASH_KEY` values; back them up securely.
   Never reuse CI or development credentials.
2. Set `APP_ENV=production`, `DATABASE_ECHO=false`, `EMAIL_BACKEND=smtp`,
   `CORS_ORIGINS` to exact HTTPS origins, and `PAYMENT_CALLBACK_URL` to the
   HTTPS customer-return page when a Paystack key is configured. The backend
   rejects insecure CORS, SQL echo, and payment URLs at startup.
3. Keep the API behind a TLS-terminating reverse proxy. Forward WebSocket
   upgrades. Configure Uvicorn to trust only the known proxy IPs; do not accept
   arbitrary `X-Forwarded-For` values. Set the proxy request-body cap above
   `MAX_DOCUMENT_BYTES` to account for multipart overhead, with a separate
   reviewed cap for photos.
4. Keep one API process. Both live tracking and the abuse-rate-limit windows
   are process-local. Do not increase workers or run multiple replicas until
   those stores use shared infrastructure.
5. Before each release, run the CI workflow, build the admin bundle with the
   production `VITE_API_URL`, apply reviewed Alembic migrations as a one-off
   job, then roll out the API and static dashboard.
6. Confirm `/api/v1/health` returns 200 with the database available, the admin
   dashboard can sign in, and notification/payment/tracking health indicators
   are behaving as expected. Keep docs disabled in production.
7. Schedule `expire-holds` (at least once per minute), `reconcile-payments`
   (frequency set by the operator), `send-reminders` (hourly),
   `purge-locations` and `purge-notifications` (daily). Do not enable document
   purging until legal retention periods and the purge policy are approved.

## Logs, health, and alerts

The API writes one JSON record per request to stdout, with a generated
`request_id`, method, path (never query parameters), status, and duration.
Responses include the same `X-Request-ID`. Internal exceptions are logged but
their details are not returned to clients. Send logs to the selected provider's
restricted-access log service; exclude request/response bodies, authorization
headers, tokens, ID/licence numbers, and document content.

Use `GET /api/v1/health` as the API/database readiness check (200 when the
database is reachable, 503 otherwise). Alert on sustained health failures,
elevated 5xx/429 rates, failed notification deliveries, payment reconciliation
backlog, database capacity, and storage capacity. Set alert thresholds and
on-call contacts with the hosting operator before launch. The health endpoint
is not a substitute for provider-level database, storage, and backup monitoring.

## Backup and restore

- Take encrypted, access-restricted PostgreSQL backups on a documented schedule
  and retain them only for the approved period. Keep encrypted copies in a
  separate failure domain and test that they can be decrypted by an authorised
  operator.
- Back up the `DOCUMENT_HASH_KEY` and storage encryption keys separately from
  the data. Losing or casually rotating the HMAC key breaks duplicate-ID
  detection. Back up uploaded private documents using the storage provider's
  encrypted/versioned mechanism; database backups alone do not include files.
- A custom-format database backup can be made with
  `pg_dump --format=custom --no-owner --no-acl --dbname="$PGDATABASE" --file="$BACKUP_FILE"`
  using securely provisioned `PGHOST`, `PGPORT`, `PGUSER`, and `PGPASSFILE` settings.
- Restore first into an isolated recovery database using
  `pg_restore --no-owner --dbname="$RESTORE_DATABASE" "$BACKUP_FILE"` with the
  same securely provisioned libpq connection settings.
  Verify Alembic revision, row counts, application health, and access to a
  sample of private files before considering a recovery complete. Never test a
  restore against the production database.
- Define and approve RPO/RTO targets with the business and hosting provider,
  and record each restore drill, duration, and findings.

## Migration and rollback

Take and verify a restorable backup before a production schema change. Review
generated Alembic SQL, apply migrations once as a controlled release step, and
prefer backward-compatible expand/migrate/contract changes. Do not have every
API replica run migrations at startup.

For an application-only failure, roll back to the last compatible application
image and retain the forward schema. Do not automatically run `alembic
downgrade` in production: downgrades can discard data or be incompatible with
the previous image. If a migration itself must be reversed, stop writes, use
the approved recovery plan, and require explicit operator approval. Record the
release, migration revision, decision, and recovery result.

## Mobile production builds

Create separate Android and iOS release builds only after final application
identifiers, EAS ownership, signing credentials, and production `EXPO_PUBLIC_API_URL`
are configured. From `mobile/`, configure the EAS project and build each platform
with `eas build --profile production --platform android` or `--platform ios`.
The API URL is embedded in the binary; changing it requires a new build. Restrict
Maps keys to the final package/bundle identifiers and signing certificates.
Never put backend secrets in Expo public variables.

Use EAS internal distribution for a signed-device acceptance test before
submitting to either store. Verify login, document upload, checkout in test
mode, notifications, and live tracking on real devices. Store submission and
public rollout require a separate owner approval.
