<div align="center">

# Ledgerly

### Your business speaks.

Turn scattered business files into a clear, explainable view of what is
happening—without needing to become a data analyst first.

</div>

## The problem

Business owners often have the data they need but not the time or tooling to
interpret it. Revenue sits in a spreadsheet, costs live in an export, and the
answer to “How are we doing?” still requires manual reconciliation.

Ledgerly turns uploaded business data into detected KPIs, an explainable
Business Pulse™, historical comparisons, bounded AI explanations, an
interactive dashboard, and a downloadable PDF report.

Ledgerly explains uploaded data. It does not provide investment, pricing,
hiring, or financial advice, and it does not guarantee outcomes.

## Product flow

```text
Register or sign in
  → upload CSV, XLSX, PDF, or JSON
  → parse and validate
  → persist the upload in PostgreSQL
  → calculate metrics and Business Pulse
  → dashboard, business memory, and AI chat
  → PDF report
```

PostgreSQL is the only supported application database. It stores users,
uploads, normalized business records, metrics, and Pulse history.

## Features

- JWT authentication with Argon2 password hashing
- CSV, Excel, PDF, and JSON ingestion
- Automatic KPI detection and transparent confidence
- Explainable Business Pulse score and factors
- Historical upload comparison and persistent business memory
- Question-aware AI chat over persisted period rows, with deterministic analysis
  and a strict versioned response contract
- Authenticated, user-isolated dashboard APIs
- PDF report export
- Responsive Next.js interface
- Versioned PostgreSQL migrations applied at API startup
- Production CORS and secret validation

## Screenshots

> Product screenshot: Business Pulse dashboard

> Product screenshot: Talk to Your Business

> Product screenshot: PDF report

## Architecture

```text
Next.js + TypeScript
        │
        ▼
FastAPI REST API
  ├── Authentication
  ├── Business Engine
  ├── Business Pulse
  ├── Business Memory
  ├── AI Explanation
  └── Report Engine
        │
        ▼
PostgreSQL
```

The frontend never connects directly to the database. FastAPI owns
authentication, authorization, persistence, migrations, parsing, scoring, AI
context, and report generation.

### Period and cash semantics

Tabular uploads retain up to 500 normalized source rows. Ledgerly derives
row-level profit, net margin, and period-over-period revenue growth when the
required values are present. Ask Ledgerly can use those persisted rows for
totals, best/worst-period ranking, trends, seasonality, margins, cash, risks,
historical projections, and transparent scenarios.

Best/worst period rankings use a backend-owned composite score:
`40% profit + 35% net margin + 25% revenue growth`. Each input is min-max
normalized across the persisted periods before weighting. The first
chronological period receives a neutral growth score of `0.50` because it has
no preceding period. The API includes this methodology in the Markdown answer,
and the frontend renders it without maintaining a second copy of the weights.

Ask Ledgerly responses use one strict versioned envelope. Schema version `1`
discriminates `markdown` responses from `structured` responses. Structured
content is limited to explicit `text`, `metrics`, `table`, `list`, `scenarios`,
`forecast`, `risks`, `actions`, and `notice` sections; table cells can contain
only JSON primitives.

The backend validates and size-checks every envelope through one adapter before
returning it. The frontend validates the same contract at the network boundary
and renders every variant through one exhaustive renderer. Unsupported payloads
receive a correlation-safe user-facing error instead of raw JSON or implicit
object coercion.

A column named `cash`, `cash balance`, or another balance-style alias is treated
as a period-ending balance. The latest dated balance is the headline cash KPI;
Ledgerly also retains its average, minimum, maximum, and first-to-latest change,
but does not sum balances. Cash is additive only when the source column
explicitly identifies a period flow, such as `cash_flow`.

## Repository

```text
ledgerly/
├── backend/
│   ├── app/
│   │   ├── ai/
│   │   ├── api/
│   │   ├── business_engine/
│   │   ├── business_pulse/
│   │   ├── core/
│   │   └── report_engine/
│   ├── migrations/
│   └── tests/
├── frontend/
├── docs/
├── docker-compose.yml
└── render.yaml
```

## Prerequisites

- Python 3.12+
- Node.js 22+
- npm 10+
- PostgreSQL 16+, or Docker Desktop

## Local setup

### 1. Start PostgreSQL

From the repository root:

```bash
docker compose up -d postgres
```

The development database is available at `localhost:5432` with the credentials
defined in `docker-compose.yml`.

### 2. Start the backend

```bash
cd backend
python -m venv .venv
```

Activate the environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS or Linux:

```bash
source .venv/bin/activate
```

Install dependencies and create local configuration:

```bash
pip install -r requirements-dev.txt
cp .env.example .env
python -m uvicorn app.main:app --reload
```

The API starts at `http://localhost:8000`. PostgreSQL migrations run
automatically before the application accepts traffic. API documentation is at
`http://localhost:8000/docs`.

### 3. Start the frontend

In another terminal:

```bash
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

Open `http://localhost:3000`.

### Docker-only setup

After copying `backend/.env.example` to `backend/.env`, start the complete
stack:

```bash
docker compose up --build
```

## Environment variables

### Backend

| Variable | Required | Purpose |
| --- | --- | --- |
| `APP_ENV` | Yes | `development`, `test`, or `production` |
| `DATABASE_URL` | Yes | PostgreSQL connection URL |
| `SECRET_KEY` | Yes | JWT signing secret; 32+ unique characters in production |
| `CORS_ORIGINS` | Yes | Comma-separated trusted frontend origins |
| `GEMINI_API_KEY` | No | Enables Gemini-generated explanations |
| `GEMINI_MODEL` | No | Gemini model identifier |
| `MAX_UPLOAD_MB` | No | Maximum accepted upload size |
| `ACCESS_TOKEN_MINUTES` | No | JWT lifetime |

Both `postgres://` and `postgresql://` managed-provider URLs are normalized to
the psycopg 3 SQLAlchemy driver.

### Frontend

| Variable | Required | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | Yes | Public FastAPI origin |
| `NEXT_PUBLIC_APP_URL` | Yes | Public frontend origin |

Never commit production credentials or complete database connection URLs.

## PostgreSQL migrations

Migrations live in `backend/migrations` and execute in lexical order during
FastAPI startup. Applied filenames are recorded in
`ledgerly_schema_migrations`.

To add a migration:

1. Add the next numbered SQL file.
2. Separate statements with `-- ledgerly:statement-break`.
3. Make the migration safe for one-time production execution.
4. Add a focused test.
5. Deploy normally.

Never edit a migration after it has reached production. Add a new migration
instead. Existing PostgreSQL data is preserved across deployments.

## Quality gate

From the repository root:

```bash
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
cd backend
.venv/Scripts/python.exe -m pytest tests
.venv/Scripts/python.exe -m compileall -q app scripts
.venv/Scripts/python.exe -m pip check
.venv/Scripts/python.exe -c "from app.main import app; print(app.title)"
```

On macOS or Linux, replace the Python executable with
`backend/.venv/bin/python`.

Enable the repository pre-commit gate:

```bash
git config core.hooksPath .githooks
```

## End-to-end smoke test

The smoke runner uses
`backend/tests/fixtures/sample_business_data.csv` and calls the real API. It
registers a synthetic user, logs in, uploads the 36-row CSV, verifies persisted
Business Memory and Pulse responses, compares aggregate and month-ranking chat
answers, downloads and reads the PDF, and signs in again to confirm persistence.

With the backend running:

```bash
cd backend
python scripts/smoke_test.py --api-url http://localhost:8000
```

To additionally query upload and Pulse rows directly from local PostgreSQL,
export the same `DATABASE_URL` used by the API and run:

```bash
python scripts/smoke_test.py --api-url http://localhost:8000 --verify-database
```

Against production:

```bash
python scripts/smoke_test.py --api-url https://ledgerly-z984.onrender.com
```

The script never prints credentials or access tokens. Smoke-test accounts use
synthetic `example.com` addresses and contain no customer data.

## Production deployment

### Backend on Render

1. Open the
   [Ledgerly Render Blueprint](https://render.com/deploy?repo=https://github.com/Saidur-droid/ledgerly).
2. Confirm `backend` is the service root.
3. Set `DATABASE_URL` to the Supabase PostgreSQL session-pooler URL with
   `sslmode=require`.
4. Allow Render to generate `SECRET_KEY`.
5. Deploy and verify `GET /health` returns:

   ```json
   {"status":"ok","database":"postgresql"}
   ```
6. Verify `GET /ready` returns:

   ```json
   {"status":"ready","database":"postgresql"}
   ```

The complete checklist is in
[Render deployment](docs/RENDER_DEPLOYMENT.md). Database operations are
documented in [Supabase PostgreSQL](docs/SUPABASE_POSTGRES.md).

### Frontend on Vercel

1. Import this repository and set the root directory to `frontend`.
2. Set `NEXT_PUBLIC_API_URL` to the Render backend origin.
3. Set `NEXT_PUBLIC_APP_URL` to the Vercel production origin.
4. Deploy.
5. Register a new user and complete the verification flow below.

## Production verification checklist

- [ ] `GET /health` returns the PostgreSQL health contract.
- [ ] `GET /ready` returns `200` after executing a database query.
- [ ] The Vercel app loads without console or failed-network errors.
- [ ] A new account registers and can sign in again.
- [ ] An empty account shows the upload-first state without fabricated KPIs.
- [ ] `sample_business_data.csv` uploads successfully.
- [ ] Revenue is `41,250`, expenses are `24,350`, and profit is `16,900`.
- [ ] Business Pulse shows a bounded score, confidence, summary, and factors.
- [ ] Refreshing preserves the upload, dashboard metrics, and Pulse.
- [ ] AI chat cites `sample_business_data.csv`.
- [ ] PDF export downloads a non-empty PDF containing revenue `41,250.00`.
- [ ] A second account cannot see the first account's upload.
- [ ] The automated production smoke runner prints `PASS`.
- [ ] The deployed Git commit matches `origin/main`.

## Security

- Passwords are hashed with Argon2.
- Business history is filtered by authenticated user ID.
- Upload size and type are validated before persistence.
- AI context is limited to the authenticated user's latest business data.
- Production rejects weak signing secrets, wildcard CORS, and non-PostgreSQL
  database URLs.
- Secrets are supplied through deployment environments only.

Before a broad public launch, add rate limiting, malware scanning, structured
audit logs, recovery drills, dependency scanning, and an external security
review. See [Security policy](SECURITY.md).

## Scalability

The current modular boundaries allow parsing, report generation, and AI work to
move to background jobs without changing the public API. Likely next steps are
object storage for original files, organization-level authorization, queued
processing, database read replicas, caching, and observability.

## Roadmap

**Now:** reliable uploads, KPI detection, explainable Pulse, persistent memory,
AI chat, PDF export, and production deployment.

**Next:** richer date inference, accounting integrations, organization roles,
scheduled reports, and reviewed metric mappings.

**Later:** collaborative business narratives, vertical Pulse models, and
privacy-preserving benchmarks.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md), keep changes focused, add regression
coverage, run the complete quality gate, and use Conventional Commits.

## FAQ

<details>
<summary><strong>Does Ledgerly provide financial advice?</strong></summary>
No. Ledgerly explains and compares uploaded data. It does not recommend
investments, prices, or hiring decisions and does not guarantee outcomes.
</details>

<details>
<summary><strong>Is Gemini required?</strong></summary>
No. Uploads, KPI detection, Business Pulse, historical comparisons, and PDF
reports work without Gemini. A safe deterministic explanation is used when the
API key is absent.
</details>

<details>
<summary><strong>Which database does Ledgerly support?</strong></summary>
PostgreSQL is the only supported application database.
</details>

## License

Ledgerly is available under the [MIT License](LICENSE).

<div align="center">
  <br/>
  <strong>Ledgerly</strong><br/>
  <sub>Your business speaks.</sub>
</div>
