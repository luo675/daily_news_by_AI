"""Alembic 环境配置

用于数据库迁移。使用同步模式执行迁移脚本。
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from src.config import DatabaseConfig
from src.domain.base import Base

# 导入所有模型，确保 Base.metadata 包含所有表定义
from src.domain.models import (  # noqa: F401
    Source,
    Document,
    DocumentSummary,
    Chunk,
    ChunkEmbedding,
    Entity,
    DocumentEntity,
    Topic,
    DocumentTopic,
    Conflict,
    OpportunityAssessment,
    OpportunityEvidence,
    DailyBrief,
    WatchlistItem,
    ApiKey,
    ReviewEdit,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 设置 target_metadata 供 autogenerate 使用
target_metadata = Base.metadata

# 从 DatabaseConfig 获取同步连接字符串
db_config = DatabaseConfig()
config.set_main_option("sqlalchemy.url", db_config.sync_url)


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 脚本而不连接数据库"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连接数据库执行迁移"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
