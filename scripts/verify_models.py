"""验证数据模型定义完整性

检查：
1. 所有 16 张核心表是否已注册到 Base.metadata
2. 每张表是否有主键
3. 每张表是否有必要字段
4. 外键关系是否正确
5. 唯一约束是否设置
"""

import sys
import io

# Windows 终端兼容：强制 UTF-8 输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from src.domain.base import Base
from src.domain.models import (
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

# TC-06 要求的 16 张核心表
REQUIRED_TABLES = {
    "sources",
    "documents",
    "document_summaries",
    "chunks",
    "chunk_embeddings",
    "entities",
    "document_entities",
    "topics",
    "document_topics",
    "conflicts",
    "opportunity_assessments",
    "opportunity_evidence",
    "daily_briefs",
    "watchlist_items",
    "api_keys",
    "review_edits",
}


def verify() -> None:
    """执行验证"""
    errors: list[str] = []

    # 1. 检查表是否全部注册
    registered_tables = set(Base.metadata.tables.keys())
    missing = REQUIRED_TABLES - registered_tables
    extra = registered_tables - REQUIRED_TABLES
    if missing:
        errors.append(f"缺少表: {missing}")
    if extra:
        errors.append(f"多余表: {extra}")

    # 2. 逐表检查
    for table_name in REQUIRED_TABLES:
        if table_name not in Base.metadata.tables:
            continue
        table = Base.metadata.tables[table_name]

        # 检查主键
        if not table.primary_key.columns:
            errors.append(f"{table_name}: 缺少主键")

        # 检查是否有 created_at（除关联表外）
        no_timestamp_tables = {"document_entities", "document_topics", "opportunity_evidence", "review_edits"}
        if table_name not in no_timestamp_tables:
            if "created_at" not in table.columns:
                errors.append(f"{table_name}: 缺少 created_at")

    # 3. 检查关键外键
    fk_checks = {
        "documents": ["source_id"],
        "document_summaries": ["document_id"],
        "chunks": ["document_id"],
        "chunk_embeddings": ["chunk_id"],
        "document_entities": ["document_id", "entity_id"],
        "document_topics": ["document_id", "topic_id"],
        "opportunity_evidence": ["opportunity_id"],
        "watchlist_items": ["entity_id"],
    }
    for table_name, fk_columns in fk_checks.items():
        if table_name not in Base.metadata.tables:
            continue
        table = Base.metadata.tables[table_name]
        for fk_col in fk_columns:
            if fk_col not in table.columns:
                errors.append(f"{table_name}: 缺少外键列 {fk_col}")
            elif not any(fk.target_fullname for fk in table.columns[fk_col].foreign_keys):
                errors.append(f"{table_name}.{fk_col}: 未设置外键约束")

    # 4. 检查唯一约束
    uq_checks = {
        "documents": ["url"],
        "document_summaries": ["document_id"],
        "chunks": [("document_id", "chunk_index")],
        "chunk_embeddings": ["chunk_id"],
        "entities": [("entity_type", "name")],
        "document_entities": [("document_id", "entity_id")],
        "document_topics": [("document_id", "topic_id")],
        "watchlist_items": [("item_type", "item_value")],
        "api_keys": ["key_hash"],
    }
    for table_name, expected_uqs in uq_checks.items():
        if table_name not in Base.metadata.tables:
            continue
        table = Base.metadata.tables[table_name]
        existing_uqs = set()
        for constraint in table.constraints:
            if hasattr(constraint, "columns"):
                cols = tuple(sorted(c.name for c in constraint.columns))
                existing_uqs.add(cols)

        for expected in expected_uqs:
            if isinstance(expected, str):
                expected = (expected,)
            expected = tuple(sorted(expected))
            if expected not in existing_uqs:
                errors.append(f"{table_name}: 缺少唯一约束 {expected}")

    # 输出结果
    print("=" * 60)
    print("数据模型验证结果")
    print("=" * 60)
    print(f"已注册表数量: {len(registered_tables)}")
    print(f"要求表数量:   {len(REQUIRED_TABLES)}")
    print(f"已注册表:     {sorted(registered_tables)}")
    print()

    if errors:
        print(f"❌ 发现 {len(errors)} 个问题:")
        for e in errors:
            print(f"  - {e}")
    else:
        print("✅ 所有检查通过！数据模型定义完整。")

    # 打印每张表的字段概览
    print()
    print("=" * 60)
    print("表结构概览")
    print("=" * 60)
    for table_name in sorted(REQUIRED_TABLES):
        if table_name not in Base.metadata.tables:
            continue
        table = Base.metadata.tables[table_name]
        cols = [c.name for c in table.columns]
        fks = [c.name for c in table.columns if c.foreign_keys]
        print(f"\n  {table_name} ({len(cols)} 列)")
        print(f"    列: {', '.join(cols)}")
        if fks:
            print(f"    外键: {', '.join(fks)}")

    return len(errors) == 0


if __name__ == "__main__":
    success = verify()
    exit(0 if success else 1)
