# Snowflake + CoCo activation

Ledgerly can store business uploads, detected KPI values, and Business Pulse
history in Snowflake. Authentication remains on the existing JWT and Supabase
PostgreSQL path. PostgreSQL is the production default; Snowflake activates only
when `STORAGE_PROVIDER=snowflake`.

## Readiness contract

Both storage adapters implement the same operations:

- save an upload and its detected metrics;
- fetch metrics for a user-owned upload;
- list user-owned upload history;
- fetch the latest upload and Pulse context;
- fetch the previous Pulse for historical comparison;
- save a Business Pulse result;
- roll back and close the current transaction.

The Snowflake adapter maps those operations to:

| Object | Purpose |
| --- | --- |
| `LEDGERLY.BUSINESS.UPLOADS` | Upload metadata and normalized source rows |
| `LEDGERLY.BUSINESS.BUSINESS_METRICS` | One detected KPI per row |
| `LEDGERLY.BUSINESS.PULSE_HISTORY` | Score, confidence, factors, summary, and metrics |
| `LEDGERLY.BUSINESS.LEDGERLY_UPLOAD_SEQUENCE` | Stable upload IDs |

All history reads filter by `USER_ID`; upload and Pulse writes commit together.

## 1. Install CoCo and define connections

CoCo's executable is `cortex`.

```powershell
irm https://ai.snowflake.com/static/cc-scripts/install.ps1 | iex
cortex --version
```

Copy the profiles in `snowflake/connections.toml.example` into
`~/.snowflake/connections.toml` and replace only the account and user
placeholders.

- `ledgerly-bootstrap` is the one-time administrative connection. It omits the
  Ledgerly warehouse, database, and schema because they do not exist yet.
- `ledgerly` is the least-privilege connection used after setup and role grants.

If account policy does not allow `ACCOUNTADMIN`, use an approved setup role
with equivalent warehouse, database, schema, role, and grant privileges.

## 2. Bootstrap the Snowflake objects

From the repository root:

```bash
cortex -c ledgerly-bootstrap -w . -f snowflake/coco-bootstrap.prompt
```

CoCo reads and executes `snowflake/setup.sql`. The script is additive and
idempotent: it uses `IF NOT EXISTS` and contains no destructive statements.

From an administrative session, grant the generated application role to both
identities that need it:

```sql
GRANT ROLE LEDGERLY_APP_ROLE TO USER "<render-service-user>";
GRANT ROLE LEDGERLY_APP_ROLE TO USER "<coco-demo-user>";
```

One grant is enough when Render and CoCo use the same Snowflake user. Reconnect
CoCo with the `ledgerly` profile and run:

```text
/sql SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA()
```

The result must be `LEDGERLY_APP_ROLE`, `LEDGERLY_WH`, `LEDGERLY`, `BUSINESS`.

## 3. Stage Render configuration

These are the complete Snowflake environment variables:

```text
SNOWFLAKE_ACCOUNT=<organization-account>
SNOWFLAKE_USER=<render-service-user>
SNOWFLAKE_PASSWORD=<password-or-programmatic-access-token>
SNOWFLAKE_WAREHOUSE=LEDGERLY_WH
SNOWFLAKE_DATABASE=LEDGERLY
SNOWFLAKE_SCHEMA=BUSINESS
SNOWFLAKE_ROLE=LEDGERLY_APP_ROLE
```

Add them while leaving `STORAGE_PROVIDER=postgres`; this stages credentials
without changing production behavior. Keep `DATABASE_URL` and `SECRET_KEY`
unchanged because authentication still uses PostgreSQL.

Never store credentials in source, example files, screenshots, or recordings.

## 4. Migration boundary and activation

The adapter does not perform a hidden cross-provider backfill. Existing
PostgreSQL uploads and Pulse history remain in PostgreSQL and are not visible
while Snowflake is selected.

For the hackathon, the lowest-risk activation is:

1. Record the current Render environment values.
2. Bootstrap and verify the empty Snowflake objects.
3. Use a fresh demo account, or accept that an existing account starts with an
   empty Snowflake business history.
4. Change only `STORAGE_PROVIDER` to `snowflake`.
5. Redeploy the backend.
6. Upload the demo CSV after activation.

If preserving historical production business data is mandatory, do not switch
providers until a separately reviewed, one-time backfill has been prepared and
reconciled. This release intentionally does not mutate or copy production data.

Rollback is one setting change: restore `STORAGE_PROVIDER=postgres` and
redeploy. Snowflake rows remain intact and PostgreSQL history becomes visible
again.

## 5. Verify activation

Open:

```text
https://ledgerly-z984.onrender.com/health
```

The response must contain:

```json
{"status":"healthy","service":"ledgerly-api","business_storage":"snowflake"}
```

Then complete the unchanged product path:

1. Register or sign in.
2. Upload a CSV with recognizable KPI columns.
3. Confirm Business Pulse renders.
4. Ask one data-grounded AI chat question.
5. Export the PDF.
6. Sign out and in again; confirm the upload and Pulse persist.

In CoCo, prove the warehouse lineage:

```text
/sql SELECT * FROM LEDGERLY.BUSINESS.UPLOADS ORDER BY CREATED_AT DESC LIMIT 5
/sql SELECT * FROM LEDGERLY.BUSINESS.BUSINESS_METRICS ORDER BY CREATED_AT DESC LIMIT 20
/sql SELECT * FROM LEDGERLY.BUSINESS.PULSE_HISTORY ORDER BY CREATED_AT DESC LIMIT 5
```

Run `snowflake/verify.sql` for the joined upload → metrics → Pulse view. A
successful path creates one upload row, at least one metric row when KPI columns
are detected, and one Pulse row. Business Pulse is calculated only after the
application queries the stored metrics back from Snowflake.

The complete presentation sequence is in [CoCo judge demo](COCO_DEMO.md).

## Activation checklist

- [ ] CoCo connects through `ledgerly-bootstrap`.
- [ ] `snowflake/setup.sql` completes without a privilege error.
- [ ] `LEDGERLY_APP_ROLE` is granted to the Render and CoCo users.
- [ ] The `ledgerly` profile reports the expected role and object context.
- [ ] All seven Snowflake environment variables are staged in Render.
- [ ] `STORAGE_PROVIDER` remains `postgres` until the activation window.
- [ ] The post-switch health response reports `business_storage: snowflake`.
- [ ] A new CSV produces upload, metric, and Pulse rows in Snowflake.
- [ ] Dashboard, AI chat, and PDF use the new Snowflake-backed Pulse.
- [ ] Logout/login preserves the Snowflake-backed business history.
- [ ] Rollback values are recorded.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Bootstrap connection fails | Use `ledgerly-bootstrap`; do not name objects that have not been created |
| `/health` says `postgres` | `STORAGE_PROVIDER`, complete credential set, and successful Render redeploy |
| Login fails | `DATABASE_URL` and `SECRET_KEY`; authentication does not use Snowflake |
| Upload returns 503 | Account identifier, credentials, role grants, warehouse, database, and schema |
| Pulse returns 404 after switch | The user has not uploaded business data to the selected provider |
| CoCo cannot use `ledgerly` | Grant `LEDGERLY_APP_ROLE`, then reconnect so the new role is visible |
| Empty metrics | CSV headers do not match a supported KPI alias; inspect upload warnings |
