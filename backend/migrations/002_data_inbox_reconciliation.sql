CREATE TABLE source_mappings (
  id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  source_key VARCHAR(255) NOT NULL, column_mapping JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_source_mapping_user_source UNIQUE (user_id, source_key)
);
CREATE INDEX ix_source_mappings_user_id ON source_mappings(user_id);
-- ledgerly:statement-break
CREATE TABLE data_source_profiles (
  id SERIAL PRIMARY KEY, upload_id INTEGER NOT NULL UNIQUE REFERENCES uploads(id) ON DELETE CASCADE,
  role VARCHAR(40) NOT NULL DEFAULT 'unknown', period VARCHAR(40), currency VARCHAR(3),
  column_mapping JSONB NOT NULL DEFAULT '{}'::jsonb, mapping_confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
  mapping_approved BOOLEAN NOT NULL DEFAULT FALSE
);
-- ledgerly:statement-break
CREATE TABLE cleaning_issues (
  id SERIAL PRIMARY KEY, upload_id INTEGER NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
  row_number INTEGER, column_name VARCHAR(255), issue_type VARCHAR(40) NOT NULL,
  severity VARCHAR(12) NOT NULL DEFAULT 'warning', original_value JSONB, suggested_value JSONB,
  final_value JSONB, status VARCHAR(12) NOT NULL DEFAULT 'pending', explanation TEXT NOT NULL,
  reviewed_at TIMESTAMPTZ
);
CREATE INDEX ix_cleaning_issues_upload_id ON cleaning_issues(upload_id);
CREATE INDEX ix_cleaning_issues_issue_type ON cleaning_issues(issue_type);
CREATE INDEX ix_cleaning_issues_status ON cleaning_issues(status);
-- ledgerly:statement-break
CREATE TABLE reconciliation_runs (
  id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  bank_upload_id INTEGER NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
  ledger_upload_id INTEGER NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
  status VARCHAR(20) NOT NULL DEFAULT 'review', created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_reconciliation_runs_user_id ON reconciliation_runs(user_id);
-- ledgerly:statement-break
CREATE TABLE reconciliation_matches (
  id SERIAL PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES reconciliation_runs(id) ON DELETE CASCADE,
  bank_row INTEGER, ledger_row INTEGER, match_type VARCHAR(20) NOT NULL, score DOUBLE PRECISION NOT NULL,
  rule VARCHAR(120) NOT NULL, amount DOUBLE PRECISION, transaction_date VARCHAR(40),
  status VARCHAR(20) NOT NULL DEFAULT 'suggested', evidence JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX ix_reconciliation_matches_run_id ON reconciliation_matches(run_id);
CREATE INDEX ix_reconciliation_matches_match_type ON reconciliation_matches(match_type);
