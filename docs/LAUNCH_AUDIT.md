# Ledgerly Launch Audit

Audit date: 2026-08-02. Scope: Phase 1–5 auth, tenancy, ingestion, migrations, APIs, calculations, reconciliation, closing, reporting, Ask Ledgerly, permissions, logging, and deployment.

## Findings and disposition

| Severity | Finding | Disposition |
|---|---|---|
| High | Public report lookup trusted `report_id` without re-binding the report to the share owner. Corrupt or manually altered rows could cross tenant boundaries. | Fixed with owner-bound lookup and regression coverage. |
| High | Report generation fetched the source upload by ID alone. | Fixed by binding upload ID and authenticated owner. |
| High | Pilot evidence and outcome tracking did not exist, so launch claims could not be audited. | Fixed with workspace-isolated pilot metrics, audit events, validation, sample template and report endpoint. |
| Medium | XLSX ingestion reads only the first worksheet. | Disclosed; pilot checklist requires the financial sheet first or separate uploads. |
| Medium | PDF ingestion supports text PDFs, not scanned/OCR statements, and recognizes summary labels rather than transaction tables. | Disclosed; verify extracted totals before close. |
| Medium | Money is stored/calculated as floating point. Rounding is applied at outputs but decimal arithmetic is preferable before regulated or high-volume use. | Known limitation; pilot users must validate trial balance and reports. |
| Medium | Unicode PDF output depends on ReportLab's available fonts and does not perform Arabic shaping/bidi layout. | Bengali/Arabic web content is supported; localized PDF requires manual visual QA and is not production-approved. |
| Medium | API rate limiting is process-local. | Adequate only for a single pilot instance; use a shared limiter before horizontal scaling. |
| Low | Health response identifies PostgreSQL even in SQLite tests. | Operational only; readiness performs a real query. |

## Controls verified

- Passwords use the recommended `pwdlib` hash; JWT signature, expiry, subject and user existence are validated.
- Production startup rejects the development secret, short secrets, missing trusted origins, wildcard CORS, and non-PostgreSQL URLs.
- Uploads, calculations, reconciliations, closing runs, templates and reports bind resource IDs to their owner. Phase 5 workspace access requires an active membership and role.
- Original uploaded values remain in immutable normalized records; cleaning/reconciliation keep original, suggested and final states plus audit events.
- Ask Ledgerly uses stored metrics and deterministic calculations; absent data returns an explicit missing-data response. It does not invent financial values.
- Source search found no application logging of request bodies, normalized financial rows, API keys, tokens, or passwords. Errors returned to clients are generic.
- Versioned migrations execute in filename order in one transaction and are recorded only after success. Clean-schema and already-applied migration tests cover idempotency.
- `/health` is a liveness check and `/ready` queries the database. Render uses `/ready`.

## Production gate

Required variables: `APP_ENV=production`, unique `SECRET_KEY` (32+ characters), PostgreSQL `DATABASE_URL`, exact HTTPS `CORS_ORIGINS`, `MAX_UPLOAD_MB`, `ACCESS_TOKEN_MINUTES`; `GEMINI_API_KEY` is optional because deterministic Ask Ledgerly remains available. Frontend requires `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_APP_URL`.

Private GitHub → Vercel/Render verification is manual: connect the private repository with least-privilege GitHub access, select `frontend` as Vercel root, configure production variables, and restrict deploys to `main`. Connect Render using `render.yaml`, then confirm `/ready`, login, upload, and a tenant-isolation smoke test.

## Backup and restore

Before every migration, take a provider snapshot and a logical dump: `pg_dump --format=custom --no-owner --file ledgerly.dump "$DATABASE_URL"`. Restore into a new database first: `createdb ledgerly_restore_test` then `pg_restore --clean --if-exists --no-owner --dbname "$RESTORE_DATABASE_URL" ledgerly.dump`. Run `/ready`, migration tests and a known report reconciliation before switching traffic. Never restore over production without a tested snapshot and rollback window.
