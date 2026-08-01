import re
from pathlib import Path

from app.core.migrations import MIGRATIONS_DIRECTORY, STATEMENT_SEPARATOR


def test_initial_postgres_migration_covers_ledgerly_schema():
    migration_path = MIGRATIONS_DIRECTORY / "001_initial_schema.sql"
    migration = migration_path.read_text(encoding="utf-8")

    assert Path(migration_path).is_file()
    assert "CREATE TABLE IF NOT EXISTS users" in migration
    assert "CREATE TABLE IF NOT EXISTS uploads" in migration
    assert "CREATE TABLE IF NOT EXISTS pulses" in migration
    assert "JSONB" in migration
    assert "ON DELETE CASCADE" in migration
    assert STATEMENT_SEPARATOR in migration
    assert set(
        re.findall(
            r"CREATE TABLE IF NOT EXISTS ([a-z_]+)",
            migration,
            flags=re.IGNORECASE,
        )
    ) == {"users", "uploads", "pulses"}
    assert "upload_id INTEGER NOT NULL UNIQUE" in migration
    assert "email VARCHAR(320) NOT NULL UNIQUE" in migration
    assert "CREATE INDEX IF NOT EXISTS ix_uploads_user_id" in migration
    assert "CREATE INDEX IF NOT EXISTS ix_uploads_created_at" in migration


def test_reconciliation_center_migration_has_audit_and_review_indexes():
    migration = (MIGRATIONS_DIRECTORY / "003_reconciliation_center.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE reconciliation_audit_events" in migration
    assert "original_state JSONB" in migration
    assert "suggested_state JSONB" in migration
    assert "final_state JSONB" in migration
    assert "uq_reconciliation_audit_idempotency" in migration
