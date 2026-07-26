from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

settings = get_settings()
if settings.database_url.startswith("sqlite:///") and settings.database_url not in {
    "sqlite://",
    "sqlite:///:memory:",
}:
    database_path = Path(settings.database_url.removeprefix("sqlite:///"))
    database_path.parent.mkdir(parents=True, exist_ok=True)

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine_options = {"connect_args": connect_args, "pool_pre_ping": True}
if settings.database_url in {"sqlite://", "sqlite:///:memory:"}:
    engine_options["poolclass"] = StaticPool
engine = create_engine(settings.database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
