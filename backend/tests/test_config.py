import pytest
from pydantic import ValidationError

from app.core.config import DEVELOPMENT_SECRET, PRODUCTION_FRONTEND_ORIGIN, Settings

PRODUCTION_DATABASE_URL = "postgresql+psycopg://user:password@db.example/ledgerly"


def test_cors_origins_are_normalized():
    settings = Settings(cors_origins="https://ledgerly.vercel.app/, https://app.ledgerly.com")
    assert settings.allowed_origins == [
        "https://ledgerly.vercel.app",
        "https://app.ledgerly.com",
    ]


def test_postgres_is_the_default_storage_provider():
    assert Settings().storage_provider == "postgres"


def test_snowflake_provider_requires_complete_credentials():
    with pytest.raises(ValidationError, match="Snowflake storage requires"):
        Settings(storage_provider="snowflake")


def test_snowflake_provider_accepts_complete_credentials():
    settings = Settings(
        storage_provider="snowflake",
        snowflake_account="organization-account",
        snowflake_user="ledgerly_service",
        snowflake_password="token",
    )
    assert settings.storage_provider == "snowflake"
    assert settings.snowflake_configured


def test_production_rejects_default_secret():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(
            app_env="production",
            database_url=PRODUCTION_DATABASE_URL,
            secret_key=DEVELOPMENT_SECRET,
            cors_origins="https://ledgerly.vercel.app",
        )


def test_production_rejects_sqlite_database():
    with pytest.raises(ValidationError, match="must use PostgreSQL"):
        Settings(
            app_env="production",
            database_url="sqlite:///./data/ledgerly.db",
            secret_key="a-unique-production-secret-that-is-long-enough",
            cors_origins="https://ledgerly.vercel.app",
        )


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValidationError, match="Wildcard CORS"):
        Settings(
            app_env="production",
            database_url=PRODUCTION_DATABASE_URL,
            secret_key="a-unique-production-secret-that-is-long-enough",
            cors_origins="*",
        )


def test_production_always_allows_the_deployed_vercel_frontend():
    settings = Settings(
        app_env="production",
        database_url=PRODUCTION_DATABASE_URL,
        secret_key="a-unique-production-secret-that-is-long-enough",
        cors_origins="http://localhost:3000",
    )
    assert PRODUCTION_FRONTEND_ORIGIN in settings.allowed_origins
