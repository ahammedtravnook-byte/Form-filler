"""FastAPI application factory for the PDF Filler API."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.core.config import settings
from api.core.logging import configure_logging, get_logger
from api.middleware.error_handler import ErrorHandlerMiddleware
from api.middleware.request_id import RequestIdMiddleware
from api.routes import admin_templates, documents, health, submissions, templates

_log = get_logger("api.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(level=settings.log_level, json_logs=settings.log_json)
    _log.info(
        "PDF Filler API starting up. Templates dir: %s", settings.templates_dir
    )
    if settings.admin_api_key == "change-me-in-production":
        _log.warning(
            "SECURITY: PDF_API_ADMIN_API_KEY is set to the default value. "
            "Set it to a strong secret in production."
        )
    yield
    _log.info("PDF Filler API shut down.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="PDF Filler API",
        version="1.0.0",
        description=(
            "Coordinate-based PDF template filler. "
            "Submit JSON data, receive a filled PDF."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Middleware — order matters: outermost runs first on request, last on response.
    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Tighten in production via env/config
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Fields-Written", "X-Fields-Skipped", "X-Warnings"],
    )

    # Routers
    app.include_router(health.router)
    app.include_router(templates.router, prefix="/api/v1")
    app.include_router(submissions.router, prefix="/api/v1")
    app.include_router(admin_templates.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_config=None,  # We configure logging ourselves
    )
