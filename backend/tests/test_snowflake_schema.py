from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_setup_sql_defines_every_snowflake_storage_object():
    setup_sql = (REPOSITORY_ROOT / "snowflake" / "setup.sql").read_text(
        encoding="utf-8"
    )

    for statement in (
        "CREATE WAREHOUSE IF NOT EXISTS LEDGERLY_WH",
        "CREATE DATABASE IF NOT EXISTS LEDGERLY",
        "CREATE SCHEMA IF NOT EXISTS LEDGERLY.BUSINESS",
        "CREATE SEQUENCE IF NOT EXISTS LEDGERLY_UPLOAD_SEQUENCE",
        "CREATE TABLE IF NOT EXISTS UPLOADS",
        "CREATE TABLE IF NOT EXISTS BUSINESS_METRICS",
        "CREATE TABLE IF NOT EXISTS PULSE_HISTORY",
    ):
        assert statement in setup_sql


def test_setup_sql_grants_only_the_operations_used_by_the_adapter():
    setup_sql = (REPOSITORY_ROOT / "snowflake" / "setup.sql").read_text(
        encoding="utf-8"
    )

    assert "GRANT USAGE ON WAREHOUSE LEDGERLY_WH" in setup_sql
    assert (
        "GRANT USAGE ON SEQUENCE LEDGERLY.BUSINESS.LEDGERLY_UPLOAD_SEQUENCE"
        in setup_sql
    )
    assert (
        "GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA LEDGERLY.BUSINESS"
        in setup_sql
    )
    for destructive_grant in ("GRANT DELETE", "GRANT TRUNCATE", "GRANT DROP"):
        assert destructive_grant not in setup_sql
