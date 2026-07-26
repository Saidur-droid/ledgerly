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
