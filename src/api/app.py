"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import (
    application_pipeline,
    briefs,
    health,
    opportunities,
    reviews,
    search,
    topics,
    watchlist,
    web,
)
from src.web.i18n import LANG_COOKIE_NAME, WebI18nContext, get_requested_lang, resolve_lang


def create_app() -> FastAPI:
    """Create the API application."""

    app = FastAPI(
        title="Daily News API",
        description="Structured knowledge API for general AI agents.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def web_i18n_middleware(request: Request, call_next):
        lang = resolve_lang(request)
        request.state.web_i18n = WebI18nContext(request=request, lang=lang)
        response = await call_next(request)
        requested_lang = get_requested_lang(request)
        if requested_lang is not None:
            response.set_cookie(LANG_COOKIE_NAME, requested_lang, samesite="lax")
        return response

    app.include_router(search.router, prefix="/api/v1", tags=["search"])
    app.include_router(application_pipeline.router, prefix="/api/v1", tags=["application"])
    app.include_router(briefs.router, prefix="/api/v1", tags=["briefs"])
    app.include_router(opportunities.router, prefix="/api/v1", tags=["opportunities"])
    app.include_router(topics.router, prefix="/api/v1", tags=["topics"])
    app.include_router(watchlist.router, prefix="/api/v1", tags=["watchlist"])
    app.include_router(reviews.router, prefix="/api/v1", tags=["reviews"])
    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(web.router)

    return app
