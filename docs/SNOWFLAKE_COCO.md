# Snowflake + CoCo deployment

Ledgerly uses Snowflake for business uploads, detected KPI values, and Business
Pulse history. Authentication is deliberately unchanged. The API automatically
selects Snowflake when its complete credential set is present, so the migration
can be activated without a frontend release or API contract change.

## 1. Install and connect CoCo CLI

CoCo's executable is named `cortex`.

```powershell
irm https://ai.snowflake.com/static/cc-scripts/install.ps1 | iex
cortex --version
cortex
```

In the setup wizard, choose an existing entry from
`~/.snowflake/connections.toml` or create one. A safe browser-SSO template is
available at `snowflake/connections.toml.example`. The connection needs a role
that can create a warehouse, database, and schema. It also needs access to a
supported Cortex model for CoCo itself.

## 2. Create Ledgerly objects

From the repository root:

```bash
cortex -c ledgerly -w . -f snowflake/coco-bootstrap.prompt
```

CoCo reads and executes `snowflake/setup.sql`. The script creates:

- `LEDGERLY_WH`, an X-Small auto-suspending warehouse;
- `LEDGERLY.BUSINESS`;
- `UPLOADS`, containing upload metadata and normalized source rows;
- `BUSINESS_METRICS`, containing one detected KPI per row;
- `PULSE_HISTORY`, containing explainable score, confidence, factors, and metrics.

The sequence is idempotent: rerunning it preserves existing data.

Grant the application role to the service user from an administrative Snowflake
worksheet, replacing the quoted identifier:

```sql
GRANT ROLE LEDGERLY_APP_ROLE TO USER "<service-user>";
```

## 3. Configure the FastAPI service

Set these Render environment variables:

```text
SNOWFLAKE_ACCOUNT=<organization-account>
SNOWFLAKE_USER=<service-user>
SNOWFLAKE_PASSWORD=<service-user-password>
SNOWFLAKE_WAREHOUSE=LEDGERLY_WH
SNOWFLAKE_DATABASE=LEDGERLY
SNOWFLAKE_SCHEMA=BUSINESS
SNOWFLAKE_ROLE=LEDGERLY_APP_ROLE
```

Keep credentials in Render, never in `.env.example`,
`connections.toml.example`, source code, screenshots, or demo recordings.
Redeploy the backend and open:

```text
https://ledgerly-z984.onrender.com/health
```

The response must contain:

```json
{"status":"healthy","service":"ledgerly-api","business_storage":"snowflake"}
```

If it reports `database`, one or more required Snowflake values is absent.

## 4. Verify the data path

Upload a CSV through the unchanged Ledgerly UI, then ask CoCo:

```text
/sql SELECT * FROM LEDGERLY.BUSINESS.UPLOADS ORDER BY CREATED_AT DESC LIMIT 5
/sql SELECT * FROM LEDGERLY.BUSINESS.BUSINESS_METRICS ORDER BY CREATED_AT DESC LIMIT 20
/sql SELECT * FROM LEDGERLY.BUSINESS.PULSE_HISTORY ORDER BY CREATED_AT DESC LIMIT 5
```

For one joined proof, execute `snowflake/verify.sql`. A successful upload has one
`UPLOADS` row, at least one `BUSINESS_METRICS` row when KPI columns are detected,
and one `PULSE_HISTORY` row. The application inserts the upload and KPI rows,
queries those KPI rows back, calculates Business Pulse from the query result,
and commits the Pulse in the same transaction.

## 5. Demo checklist

- Login and signup still work.
- Upload returns a Pulse and creates Snowflake rows.
- `/api/v1/uploads` lists only the authenticated user's uploads.
- `/api/v1/pulse/latest` reads Snowflake Pulse history.
- AI chat uses the latest Snowflake upload and Pulse as bounded context.
- PDF export uses that same Pulse.
- The dashboard renders without a frontend or contract change.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `/health` says `database` | Complete all six required Snowflake values and redeploy |
| Login fails | `DATABASE_URL` and `SECRET_KEY`; auth does not use Snowflake |
| Upload returns 503 | Snowflake account, role grants, warehouse, database, and schema |
| Pulse returns 404 | The authenticated user has no completed Snowflake upload |
| CoCo cannot connect | `~/.snowflake/connections.toml`, account identifier, and authenticator |
| Empty metrics | CSV headers do not match a supported KPI alias; inspect upload warnings |
