CREATE TABLE calculation_versions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    upload_id INTEGER NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    engine_version VARCHAR(40) NOT NULL,
    fingerprint VARCHAR(64) NOT NULL,
    status VARCHAR(12) NOT NULL,
    input_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    CONSTRAINT uq_calculation_user_fingerprint UNIQUE (user_id, fingerprint)
);
CREATE INDEX ix_calculation_versions_user_id ON calculation_versions(user_id);
CREATE INDEX ix_calculation_versions_upload_id ON calculation_versions(upload_id);
CREATE INDEX ix_calculation_versions_status ON calculation_versions(status);
-- ledgerly:statement-break
CREATE TABLE financial_periods (
    id SERIAL PRIMARY KEY,
    calculation_id INTEGER NOT NULL REFERENCES calculation_versions(id) ON DELETE CASCADE,
    period_key VARCHAR(20) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    currency VARCHAR(3),
    status VARCHAR(12) NOT NULL,
    CONSTRAINT uq_financial_period_calculation_key UNIQUE (calculation_id, period_key)
);
CREATE INDEX ix_financial_periods_calculation_id ON financial_periods(calculation_id);
-- ledgerly:statement-break
CREATE TABLE calculated_metrics (
    id SERIAL PRIMARY KEY,
    calculation_id INTEGER NOT NULL REFERENCES calculation_versions(id) ON DELETE CASCADE,
    period_id INTEGER REFERENCES financial_periods(id) ON DELETE CASCADE,
    metric_key VARCHAR(80) NOT NULL,
    dimensions_key VARCHAR(255) NOT NULL DEFAULT '',
    value DOUBLE PRECISION,
    unit VARCHAR(20) NOT NULL DEFAULT 'currency',
    status VARCHAR(12) NOT NULL,
    breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_calculated_metric_identity UNIQUE (calculation_id, metric_key, dimensions_key)
);
CREATE INDEX ix_calculated_metrics_calculation_id ON calculated_metrics(calculation_id);
CREATE INDEX ix_calculated_metrics_period_id ON calculated_metrics(period_id);
CREATE INDEX ix_calculated_metrics_metric_key ON calculated_metrics(metric_key);
CREATE INDEX ix_calculated_metrics_status ON calculated_metrics(status);
-- ledgerly:statement-break
CREATE TABLE metric_evidence (
    id SERIAL PRIMARY KEY,
    metric_id INTEGER NOT NULL REFERENCES calculated_metrics(id) ON DELETE CASCADE,
    upload_id INTEGER NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    source_file VARCHAR(255) NOT NULL,
    source_location VARCHAR(255) NOT NULL DEFAULT 'data',
    included_records JSONB NOT NULL DEFAULT '[]'::jsonb,
    excluded_records JSONB NOT NULL DEFAULT '[]'::jsonb,
    formula TEXT NOT NULL,
    mappings JSONB NOT NULL DEFAULT '{}'::jsonb,
    adjustments JSONB NOT NULL DEFAULT '[]'::jsonb,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    engine_version VARCHAR(40) NOT NULL
);
CREATE INDEX ix_metric_evidence_metric_id ON metric_evidence(metric_id);
CREATE INDEX ix_metric_evidence_upload_id ON metric_evidence(upload_id);
-- ledgerly:statement-break
CREATE TABLE validation_results (
    id SERIAL PRIMARY KEY,
    calculation_id INTEGER NOT NULL REFERENCES calculation_versions(id) ON DELETE CASCADE,
    code VARCHAR(80) NOT NULL,
    status VARCHAR(12) NOT NULL,
    message TEXT NOT NULL,
    row_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX ix_validation_results_calculation_id ON validation_results(calculation_id);
CREATE INDEX ix_validation_results_code ON validation_results(code);
CREATE INDEX ix_validation_results_status ON validation_results(status);
-- ledgerly:statement-break
CREATE TABLE forecast_results (
    id SERIAL PRIMARY KEY,
    calculation_id INTEGER NOT NULL REFERENCES calculation_versions(id) ON DELETE CASCADE,
    horizon_days INTEGER NOT NULL DEFAULT 30,
    status VARCHAR(12) NOT NULL,
    opening_cash DOUBLE PRECISION,
    projected_inflow DOUBLE PRECISION,
    projected_outflow DOUBLE PRECISION,
    projected_closing_cash DOUBLE PRECISION,
    shortage_date DATE,
    inputs JSONB NOT NULL DEFAULT '{}'::jsonb,
    daily_results JSONB NOT NULL DEFAULT '[]'::jsonb
);
CREATE INDEX ix_forecast_results_calculation_id ON forecast_results(calculation_id);
CREATE INDEX ix_forecast_results_status ON forecast_results(status);
