"""FastAPI application factory.

Run locally with:
    uvicorn doculens.api.main:create_app --factory --reload
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from doculens import __version__
from doculens.api.middleware import (
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    SlidingWindowLimiter,
)
from doculens.api.routes_health import router as health_router
from doculens.config import Settings, get_settings
from doculens.logging_setup import configure_logging

log = logging.getLogger("doculens")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, secrets=[settings.secret_key])

    app = FastAPI(
        title="DocuLens API",
        version=__version__,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.state.settings = settings
    app.include_router(health_router)

    # add_middleware wraps outward: the LAST one added runs FIRST.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(
        RateLimitMiddleware,
        limiter=SlidingWindowLimiter(settings.rate_limit_per_minute, 60.0),
        exempt_paths={"/health"},
        trust_proxy=settings.trust_proxy,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
        max_age=600,
    )
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)

    log.info("DocuLens API %s starting (env=%s)", __version__, settings.env)
    return app
