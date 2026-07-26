# Supabase PostgreSQL operations

Ledgerly uses Supabase as managed PostgreSQL. FastAPI remains the only application layer with database access; the frontend does not receive Supabase keys or credentials.

## Connection

Use Supabase Dashboard → **Connect** → **Direct** → **Session pooler**. The session pooler is compatible with Render's IPv4 network and FastAPI's long-lived SQLAlchemy connection pool.

Store the URI only as Render's `DATABASE_URL` secret:

```text
postgresql://postgres.<project-ref>:<percent-encoded-password>@<pooler-host>:5432/postgres?sslmode=require
```

Ledgerly normalizes both `postgres://` and `postgresql://` provider URLs to the psycopg 3 SQLAlchemy driver.

## Migrations without the Supabase CLI

Migration files are ordered lexically from `backend/migrations`. Each file uses:

```sql
-- ledgerly:statement-break
```

between executable statements. FastAPI applies pending migrations in one transaction during startup, then records the filename in `ledgerly_schema_migrations`.

For a new project, `001_initial_schema.sql` can also be pasted into Supabase Dashboard → **SQL Editor**. The SQL is idempotent, so rerunning it is safe.

## Adding a migration

1. Add the next numbered SQL file, for example `002_add_business_name.sql`.
2. Make each operation safe for one-time production execution.
3. Separate statements with the Ledgerly marker.
4. Add a focused migration test.
5. Deploy normally; application startup applies the migration before serving traffic.

Do not edit a migration after it has reached production. Add a new migration instead.
