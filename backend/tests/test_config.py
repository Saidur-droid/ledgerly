import pytest
from pydantic import ValidationError

from app.core.config import DEVELOPMENT_SECRET, PRODUCTION_FRONTEND_ORIGIN, Settings


def test_cors_origins_are_normalized():
    settings = Settings(cors_origins="https://ledgerly.vercel.app/, https://app.ledgerly.com")
    assert settings.allowed_origins == [
        "https://ledgerly.vercel.app",
        "https://app.ledgerly.com",
    ]


def test_production_rejects_default_secret():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(
            app_env="production",
            secret_key=DEVELOPMENT_SECRET,
            cors_origins="https://ledgerly.vercel.app",
        )


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValidationError, match="Wildcard CORS"):
        Settings(
            app_env="production",
            secret_key="a-unique-production-secret-that-is-long-enough",
            cors_origins="*",
        )


def test_production_always_allows_the_deployed_vercel_frontend():
    settings = Settings(
        app_env="production",
        secret_key="a-unique-production-secret-that-is-long-enough",
        cors_origins="http://localhost:3000",
    )
    assert PRODUCTION_FRONTEND_ORIGIN in settings.allowed_origins
