from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from app.business_engine.storage import (
    BusinessStore,
    PostgreSQLBusinessStore,
    SnowflakeBusinessStore,
    StoredPulse,
    get_business_store,
)
from app.core.config import Settings


def snowflake_settings() -> Settings:
    return Settings(
        storage_provider="snowflake",
        snowflake_account="acme-org",
        snowflake_user="ledgerly_service",
        snowflake_password="secret",
        snowflake_role="LEDGERLY_ROLE",
    )


def test_storage_adapters_implement_the_complete_business_store_contract():
    required_methods = {
        name
        for name, member in BusinessStore.__dict__.items()
        if callable(member) and not name.startswith("_")
    }

    assert required_methods == {
        "create_upload",
        "get_metrics",
        "save_pulse",
        "list_uploads",
        "latest_context",
        "previous_pulse",
        "rollback",
        "close",
    }
    for adapter in (PostgreSQLBusinessStore, SnowflakeBusinessStore):
        assert required_methods <= {
            name for name in dir(adapter) if callable(getattr(adapter, name))
        }


def test_provider_switch_defaults_to_postgres():
    generator = get_business_store(MagicMock(), Settings())
    store = next(generator)
    try:
        assert isinstance(store, PostgreSQLBusinessStore)
        assert store.backend_name == "postgres"
    finally:
        generator.close()


@patch("snowflake.connector.connect")
def test_provider_switch_selects_snowflake(connect: MagicMock):
    generator = get_business_store(MagicMock(), snowflake_settings())
    store = next(generator)
    try:
        assert isinstance(store, SnowflakeBusinessStore)
        assert store.backend_name == "snowflake"
        connect.assert_called_once()
    finally:
        generator.close()


@patch("snowflake.connector.connect")
def test_uploads_and_queries_business_metrics_from_snowflake(connect: MagicMock):
    connection = connect.return_value
    cursor = connection.cursor.return_value
    uploaded_at = datetime.now(UTC)
    cursor.fetchone.side_effect = [
        (42,),
        (
            42,
            7,
            "june.csv",
            "csv",
            "checksum",
            1,
            0.78,
            '{"columns":["revenue"],"records":[{"revenue":55842}],"warnings":[]}',
            uploaded_at,
        ),
    ]

    store = SnowflakeBusinessStore(snowflake_settings())
    upload = store.create_upload(
        user_id=7,
        filename="june.csv",
        file_type="csv",
        checksum="checksum",
        row_count=1,
        confidence=0.78,
        normalized_data={
            "columns": ["revenue"],
            "records": [{"revenue": 55842}],
            "warnings": [],
        },
        metrics={"revenue": 55842, "expenses": 29510},
    )

    assert upload.id == 42
    assert upload.normalized_data["records"][0]["revenue"] == 55842
    assert "INSERT INTO UPLOADS" in cursor.execute.call_args_list[1].args[0]
    assert "INSERT INTO BUSINESS_METRICS" in cursor.executemany.call_args.args[0]
    connection.commit.assert_not_called()

    cursor.fetchall.return_value = [("expenses", 29510), ("revenue", 55842)]
    metrics = store.get_metrics(user_id=7, upload_id=42)

    assert metrics == {"expenses": 29510.0, "revenue": 55842.0}
    assert "FROM BUSINESS_METRICS" in cursor.execute.call_args.args[0]
    connect.assert_called_once()
    assert connect.call_args.kwargs["autocommit"] is False
    assert connect.call_args.kwargs["session_parameters"]["QUERY_TAG"] == "ledgerly_business_pipeline"


@patch("snowflake.connector.connect")
def test_pulse_history_commit_is_atomic_with_upload(connect: MagicMock):
    connection = connect.return_value
    cursor = connection.cursor.return_value
    pulse = StoredPulse(
        upload_id=42,
        score=82,
        confidence=0.78,
        summary="The uploaded data looks strong.",
        factors=[{"name": "Profitability", "score": 30}],
        metrics={"revenue": 55842, "net_margin": 47.16},
    )

    store = SnowflakeBusinessStore(snowflake_settings())
    store.save_pulse(user_id=7, pulse=pulse)

    sql, parameters = cursor.execute.call_args.args
    assert "INSERT INTO PULSE_HISTORY" in sql
    assert parameters[1:3] == (42, 7)
    connection.commit.assert_called_once()
