"""FastAPI 应用工厂

创建和配置 FastAPI 应用实例。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import search, briefs, opportunities, topics, watchlist, reviews, health


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例

    注册所有路由、中间件和异常处理器。
    """
    app = FastAPI(
        title="Daily News API",
        description="面向通用 AI Agent 的结构化知识 API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── CORS ──
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── 注册路由 ──
    app.include_router(search.router, prefix="/api/v1", tags=["search"])
    app.include_router(briefs.router, prefix="/api/v1", tags=["briefs"])
    app.include_router(opportunities.router, prefix="/api/v1", tags=["opportunities"])
    app.include_router(topics.router, prefix="/api/v1", tags=["topics"])
    app.include_router(watchlist.router, prefix="/api/v1", tags=["watchlist"])
    app.include_router(reviews.router, prefix="/api/v1", tags=["reviews"])
    app.include_router(health.router, prefix="/api/v1", tags=["health"])

    return app
