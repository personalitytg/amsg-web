from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analysis, analyze, health, sources
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AMSG Web API",
        description=(
            "Compression-based cross-domain anomaly detection over geophysical "
            "time series. REST + SSE wrapper around the AMSG pipeline."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api", tags=["meta"])
    app.include_router(sources.router, prefix="/api", tags=["sources"])
    app.include_router(analyze.router, prefix="/api", tags=["analysis"])
    app.include_router(analysis.router, prefix="/api", tags=["analysis"])

    return app


app = create_app()
