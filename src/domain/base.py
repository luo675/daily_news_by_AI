"""SQLAlchemy 基类与公共 Mixin

提供所有模型共享的基础能力：
- UUID 主键
- created_at / updated_at 时间戳
- 声明式基类
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有模型的声明式基类"""

    pass


class UUIDPrimaryKey:
    """UUID 主键 Mixin

    所有业务表统一使用 UUID 作为主键，避免自增 ID 在分布式场景下的冲突。
    """

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        insert_default=uuid.uuid4,
    )


class TimestampMixin:
    """时间戳 Mixin

    为所有业务表提供 created_at / updated_at 字段。
    使用数据库服务器时间（UTC）作为默认值。
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
