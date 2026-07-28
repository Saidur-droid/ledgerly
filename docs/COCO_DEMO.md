# Ledgerly CoCo judge demo

This flow makes the Snowflake lineage visible without changing Ledgerly's UI or
API contracts. Run it only after the activation checklist in
`docs/SNOWFLAKE_COCO.md` passes.

## Before the demo

1. Confirm Render `/health` reports `"business_storage":"snowflake"`.
2. Open Ledgerly in one window and CoCo in another.
3. Start CoCo from the repository root with the least-privilege connection:

   ```bash
   cortex -c ledgerly -w .
   ```

4. Sign in with a fresh Ledgerly demo account.
5. Keep a small CSV ready with columns such as `date`, `revenue`, `expenses`,
   `cash`, and `customers`.

## Five-minute storyline

### 1. Establish the separation

Say: “Ledgerly keeps identity and sessions in PostgreSQL. The storage adapter
sends only business uploads, metrics, and Pulse history to Snowflake.”

In CoCo:

```text
/sql SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA()
```

Show `LEDGERLY_APP_ROLE`, `LEDGERLY_WH`, `LEDGERLY`, and `BUSINESS`.

### 2. Show the empty starting point

Before uploading, query the demo user's current rows or show the latest rows:

```text
/sql SELECT UPLOAD_ID, USER_ID, FILENAME, CREATED_AT FROM LEDGERLY.BUSINESS.UPLOADS ORDER BY CREATED_AT DESC LIMIT 5
```

### 3. Upload and expose the warehouse write

Upload the CSV in Ledgerly. The API stores the normalized upload and KPI rows in
Snowflake, queries those KPI rows back, calculates Business Pulse, and saves the
Pulse in the same transaction.

Immediately show:

```text
/sql SELECT UPLOAD_ID, USER_ID, FILENAME, ROW_COUNT, CONFIDENCE, CREATED_AT FROM LEDGERLY.BUSINESS.UPLOADS ORDER BY CREATED_AT DESC LIMIT 5
/sql SELECT UPLOAD_ID, METRIC_NAME, METRIC_VALUE FROM LEDGERLY.BUSINESS.BUSINESS_METRICS ORDER BY CREATED_AT DESC LIMIT 20
/sql SELECT UPLOAD_ID, SCORE, CONFIDENCE, SUMMARY FROM LEDGERLY.BUSINESS.PULSE_HISTORY ORDER BY CREATED_AT DESC LIMIT 5
```

### 4. Connect Snowflake to the product outcome

Return to Ledgerly:

1. Open Business Pulse and point out its score, confidence, factors, and trend.
2. Ask: “What changed in this upload, based only on my data?”
3. Show the dashboard charts.
4. Export the PDF report.

Say: “The dashboard, AI explanation, and report all use the Pulse created from
metrics read back from Snowflake.”

### 5. Finish with joined lineage

Ask CoCo to execute `snowflake/verify.sql`, or run its final joined query. Show
one row connecting the user, upload, detected metric count, and Pulse score.

The judge-visible chain is:

```text
CSV upload
  → UPLOADS + BUSINESS_METRICS in Snowflake
  → metrics queried from Snowflake
  → Business Pulse saved to PULSE_HISTORY
  → AI insight + dashboard
  → PDF report
```

## Proof points for questions

- PostgreSQL remains the safe default and authentication store.
- `STORAGE_PROVIDER` selects one business-data adapter; frontend contracts do
  not change.
- Every Snowflake history query includes `USER_ID`.
- The application role has only warehouse usage plus sequence usage and
  table `SELECT`/`INSERT`.
- The setup SQL is additive and idempotent.
- Restoring `STORAGE_PROVIDER=postgres` rolls business reads back without
  deleting Snowflake data.
