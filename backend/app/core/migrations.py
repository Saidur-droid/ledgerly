from pathlib import Path

from sqlalchemy import Engine, text

MIGRATIONS_DIRECTORY = Path(__file__).resolve().parents[2] / "migrations"
STATEMENT_SEPARATOR = "-- ledgerly:statement-break"


def run_postgres_migrations(engine: Engine) -> None:
    """Apply pending, versioned SQL migrations in a single transaction."""
    if engine.dialect.name != "postgresql":
        return

    migration_files = sorted(MIGRATIONS_DIRECTORY.glob("*.sql"))
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS ledgerly_schema_migrations (
                    version VARCHAR(255) PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        applied_versions = set(
            connection.execute(text("SELECT version FROM ledgerly_schema_migrations")).scalars()
        )

        for migration_file in migration_files:
            if migration_file.name in applied_versions:
                continue
            migration_sql = migration_file.read_text(encoding="utf-8")
            statements = (
                statement.strip() for statement in migration_sql.split(STATEMENT_SEPARATOR)
            )
            for statement in statements:
                if statement:
                    connection.exec_driver_sql(statement)
            connection.execute(
                text(
                    "INSERT INTO ledgerly_schema_migrations (version) "
                    "VALUES (:version)"
                ),
                {"version": migration_file.name},
            )
