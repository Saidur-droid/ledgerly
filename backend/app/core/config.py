from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Ledgerly API"
    app_env: str = "development"
    secret_key: str = Field(default="development-only-change-this-key-now")
    database_url: str = "sqlite:///./data/ledgerly.db"
    frontend_url: str = "http://localhost:3000"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    max_upload_mb: int = 20
    access_token_minutes: int = 60 * 24

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
