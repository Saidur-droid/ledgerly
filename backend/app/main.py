from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import get_settings
from app.core.database import Base, engine
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
        "status": "healthy",
        "service": "ledgerly-api",
        "business_storage": settings.storage_provider,
    }
