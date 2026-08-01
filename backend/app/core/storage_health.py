from sqlalchemy import Engine, inspect, text


REQUIRED_STORAGE_TABLES = {
    "users", "uploads", "pulses", "source_mappings", "data_source_profiles",
    "cleaning_issues", "reconciliation_runs", "reconciliation_matches",
    "reconciliation_audit_events", "calculation_versions", "financial_periods",
    "calculated_metrics", "metric_evidence", "validation_results",
    "forecast_results", "workspace_closing_settings", "monthly_closing_runs",
    "monthly_closing_audit_events", "report_templates", "report_snapshots",
    "report_shares", "workspaces", "workspace_members", "workspace_periods",
    "workspace_notes", "workspace_audit_events",
}
REQUIRED_MIGRATIONS = {f"00{number}_{name}.sql" for number, name in (
    (1, "initial_schema"), (2, "data_inbox_reconciliation"),
    (3, "reconciliation_center"), (4, "financial_engine_lineage"),
    (5, "monthly_closing_report_studio"), (6, "accountant_workspace"),
)}


def storage_readiness(engine: Engine) -> dict[str, object]:
    """Verify upload persistence dependencies without reading tenant data."""
    existing = set(inspect(engine).get_table_names())
    missing_tables = sorted(REQUIRED_STORAGE_TABLES - existing)
    missing_migrations: list[str] = []
    if engine.dialect.name == "postgresql":
        if "ledgerly_schema_migrations" not in existing:
            missing_migrations = sorted(REQUIRED_MIGRATIONS)
        else:
            with engine.connect() as connection:
                applied = set(connection.execute(text("SELECT version FROM ledgerly_schema_migrations")).scalars())
            missing_migrations = sorted(REQUIRED_MIGRATIONS - applied)
    return {
        "status": "ready" if not missing_tables and not missing_migrations else "unavailable",
        "database": engine.dialect.name,
        "required_schema": "001-006",
        "missing_tables": missing_tables,
        "missing_migrations": missing_migrations,
    }
