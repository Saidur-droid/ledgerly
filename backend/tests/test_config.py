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


def test_postgres_is_the_default_application_database():
    default_url = Settings.model_fields["database_url"].default
    assert default_url.startswith("postgresql+psycopg://")


def test_development_rejects_non_postgres_application_database():
    with pytest.raises(ValidationError, match="must use PostgreSQL"):
        Settings(app_env="development", database_url="sqlite:///ledgerly.db")


def test_production_rejects_default_secret():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(
            app_env="production",
            database_url=PRODUCTION_DATABASE_URL,
            secret_key=DEVELOPMENT_SECRET,
            cors_origins="https://ledgerly.vercel.app",
        )


def test_production_rejects_non_postgres_database():
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
