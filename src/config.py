"""数据库配置模块

提供数据库连接字符串和引擎创建逻辑。
第一阶段使用 PostgreSQL + pgvector。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


@dataclass
class DatabaseConfig:
    """数据库连接配置

    优先从环境变量读取，未设置时使用默认值。
    """

    host: str = os.getenv("DB_HOST", "localhost")
    port: int = int(os.getenv("DB_PORT", "5432"))
    database: str = os.getenv("DB_NAME", "daily_news")
    user: str = os.getenv("DB_USER", "postgres")
    password: str = os.getenv("DB_PASSWORD", "postgres")

    @property
    def url(self) -> str:
        """异步连接字符串（供 SQLAlchemy 2.0 async 使用）"""
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )

    @property
    def sync_url(self) -> str:
        """同步连接字符串（供 Alembic 迁移使用）"""
        return (
            f"postgresql+psycopg2://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )


def create_sync_engine(config: DatabaseConfig | None = None, **kwargs) -> Engine:
    """创建同步数据库引擎（用于 Alembic 迁移和简单脚本）"""
    if config is None:
        config = DatabaseConfig()
    return create_engine(config.sync_url, echo=kwargs.pop("echo", False), **kwargs)


def create_session_factory(config: DatabaseConfig | None = None) -> sessionmaker[Session]:
    """创建 Session 工厂"""
    engine = create_sync_engine(config)
    return sessionmaker(bind=engine, expire_on_commit=False)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """懒加载全局 Session 工厂。

    避免在模块导入阶段立即要求数据库驱动存在。
    """
    return create_session_factory()
