"""FastAPI 依赖项

提供数据库会话、服务实例等依赖。
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session

from src.config import get_session_factory


def create_db_session() -> Session:
    """按需创建数据库会话。"""
    session_factory = get_session_factory()
    return session_factory()


def try_create_db_session() -> Session | None:
    """尝试创建数据库会话，失败时返回 None。"""
    try:
        return create_db_session()
    except Exception:
        return None


def get_db() -> Generator[Session, None, None]:
    """获取数据库会话

    使用 FastAPI 依赖注入，在请求结束时自动关闭会话。
    """
    db = create_db_session()
    try:
        yield db
    finally:
        db.close()
