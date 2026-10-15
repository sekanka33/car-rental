"""FastAPI application factory. Run with: uvicorn app.main:app --reload"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import API_VERSION, Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.realtime import TrackingHub
from app.db.session import build_engine, build_session_factory
from app.integrations.email import EmailSender, build_email_sender
from app.integrations.maps import MapsProvider, build_maps_provider
from app.integrations.payments import PaymentProvider, build_payment_provider
from app.integrations.storage import DocumentStorage, LocalDocumentStorage
from app.schemas.common import ErrorResponse

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    email_sender: EmailSender | None = None,
    document_storage: DocumentStorage | None = None,
    payment_provider: PaymentProvider | None | object = ...,
    maps_provider: MapsProvider | None | object = ...,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    # Connections are opened lazily, so the app starts even if the database is down;
    # /health then reports it as unavailable.
    engine = build_engine(settings.database_url.get_secret_value(), echo=settings.database_echo)

    @asynccontextmanager
    async def lifespan(started: FastAPI) -> AsyncIterator[None]:
        logger.info("Starting %s (%s)", settings.app_name, settings.app_env.value)
        started.state.tracking_hub.bind(asyncio.get_running_loop())
        yield
        engine.dispose()

    docs = settings.docs_enabled
    app = FastAPI(
        title=settings.app_name,
        version=API_VERSION,
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url=f"{settings.api_v1_prefix}/openapi.json" if docs else None,
        responses={
            401: {"model": ErrorResponse, "description": "Not authenticated"},
            403: {"model": ErrorResponse, "description": "Permission denied"},
            413: {"model": ErrorResponse, "description": "Upload too large"},
            422: {"model": ErrorResponse, "description": "Validation error"},
            503: {"model": ErrorResponse, "description": "Service unavailable"},
            500: {"model": ErrorResponse, "description": "Internal server error"},
        },
    )

    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = build_session_factory(engine)
    app.state.email_sender = email_sender or build_email_sender(settings)
    app.state.document_storage = document_storage or LocalDocumentStorage(
        settings.document_storage_dir
    )
    # `...` means "use the configured provider"; tests pass a fake or None explicitly.
    app.state.payment_provider = (
        build_payment_provider(settings) if payment_provider is ... else payment_provider
    )

    app.state.maps_provider = (
        build_maps_provider(settings) if maps_provider is ... else maps_provider
    )
    app.state.tracking_hub = TrackingHub()

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
