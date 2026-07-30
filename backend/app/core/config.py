from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEVELOPMENT_SECRET = "development-only-change-this-key-now"
PRODUCTION_FRONTEND_ORIGIN = "https://ledgerly-one-xi.vercel.app"


class Settings(BaseSettings):
    app_name: str = "Ledgerly API"
    app_env: str = "development"
    secret_key: str = Field(default=DEVELOPMENT_SECRET)
    database_url: str = (
        "postgresql+psycopg://ledgerly:ledgerly@localhost:5432/ledgerly"
    )
    cors_origins: str = "http://localhost:3000"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    max_upload_mb: int = 20
    access_token_minutes: int = 60 * 24
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        origins = [origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()]
        if self.app_env.lower() == "production" and PRODUCTION_FRONTEND_ORIGIN not in origins:
            origins.append(PRODUCTION_FRONTEND_ORIGIN)
        return origins

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        environment = self.app_env.lower()
        if environment == "test":
            return self
        if not self.database_url.startswith(
            ("postgres://", "postgresql://", "postgresql+psycopg://")
        ):
            raise ValueError("DATABASE_URL must use PostgreSQL.")
        if environment != "production":
            return self
        if self.secret_key == DEVELOPMENT_SECRET or len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY must be a unique value of at least 32 characters in production.")
        if not self.allowed_origins:
            raise ValueError("CORS_ORIGINS must contain at least one trusted frontend origin in production.")
        if "*" in self.allowed_origins:
            raise ValueError("Wildcard CORS origins are not allowed in production.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
