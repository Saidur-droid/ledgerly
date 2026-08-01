from contextlib import asynccontextmanager
import logging
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.routes import router
from app.api.phase4 import router as phase4_router
from app.api.phase5 import router as phase5_router
from app.core.config import get_settings
from app.core.database import Base, engine, get_db
from app.core.migrations import run_postgres_migrations
from app.core.storage_health import storage_readiness


@asynccontextmanager
async def lifespan(_: FastAPI):
    if engine.dialect.name == "postgresql":
        run_postgres_migrations(engine)
    else:
        Base.metadata.create_all(bind=engine)
    yield


settings = get_settings()
LOGGER = logging.getLogger("ledgerly.api")
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
app.include_router(phase4_router)
app.include_router(phase5_router)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", "")[:100] or str(uuid.uuid4())
    try:
        response = await call_next(request)
    except Exception as error:
        # Deliberately log no body, query string, token, financial values, or user data.
        LOGGER.error("unhandled_request_error request_id=%s method=%s path=%s error_type=%s", request_id, request.method, request.url.path, type(error).__name__)
        return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred.", "request_id": request_id})
    response.headers["x-request-id"] = request_id
    return response


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


@app.get("/ready/storage")
def storage_health() -> dict[str, object]:
    try:
        result = storage_readiness(engine)
    except SQLAlchemyError as error:
        LOGGER.error("storage_readiness_failed error_type=%s", type(error).__name__)
        raise HTTPException(status_code=503, detail="Business data storage is unavailable.") from error
    if result["status"] != "ready":
        raise HTTPException(status_code=503, detail=result)
    return result
