import pytest
from pydantic import ValidationError

from app.core.config import DEVELOPMENT_SECRET, Settings

PRODUCTION_DATABASE_URL = "postgresql+psycopg://user:password@db.example/ledgerly"


def test_cors_origins_are_normalized():
    settings = Settings(cors_origins="https://ledgerly.vercel.app/, https://app.ledgerly.com")
    assert settings.allowed_origins == [
        "https://ledgerly.vercel.app",
        "https://app.ledgerly.com",
    ]


def test_database_url_has_no_implicit_fallback():
    default_url = Settings.model_fields["database_url"].default
    assert default_url == ""


def test_development_rejects_non_postgres_application_database():
    with pytest.raises(ValidationError, match="must use PostgreSQL"):
        Settings(app_env="development", database_url="sqlite:///ledgerly.db")


def test_production_rejects_missing_database_url():
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(
            app_env="production",
            database_url="",
            secret_key="a-unique-production-secret-that-is-long-enough",
            cors_origins="https://ledgerly-one-xi.vercel.app",
        )


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


def test_production_allows_only_explicit_frontend_origins():
    settings = Settings(
        app_env="production",
        database_url=PRODUCTION_DATABASE_URL,
        secret_key="a-unique-production-secret-that-is-long-enough",
        cors_origins="https://ledgerly-one-xi.vercel.app",
    )
    assert settings.allowed_origins == ["https://ledgerly-one-xi.vercel.app"]


def test_production_rejects_missing_cors_origins():
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(
            app_env="production",
            database_url=PRODUCTION_DATABASE_URL,
            secret_key="a-unique-production-secret-that-is-long-enough",
            cors_origins="",
        )
