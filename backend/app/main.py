from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.routes import router
from app.core.config import get_settings
from app.core.database import Base, engine, get_db
from app.core.migrations import run_postgres_migrations


@asynccontextmanager
async def lifespan(_: FastAPI):
    if engine.dialect.name == "postgresql":
        run_postgres_migrations(engine)
    else:
        Base.metadata.create_all(bind=engine)
    yield


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    description="The API behind Ledgerly — Your business speaks.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "database": "postgresql",
    }


@app.get("/ready")
def readiness(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1")).scalar_one()
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=503,
            detail="Database is unavailable.",
        ) from error
    return {
        "status": "ready",
        "database": "postgresql",
    }
