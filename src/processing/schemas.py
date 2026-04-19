"""处理流水线共享数据结构。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.domain.enums import EntityType
from src.ingestion.schemas import RawDocumentInput


class BilingualSummary(BaseModel):
    """双语摘要结构。"""

    zh: str = Field(..., description="中文摘要")
    en: str = Field(..., description="英文摘要")
    bullets: list[str] = Field(default_factory=list, description="关键点列表")


class CleanedDocument(BaseModel):
    """清洗后的文档。"""

    raw_document: RawDocumentInput
    normalized_text: str = Field(..., description="规范化后的正文")
    normalized_title: str = Field(..., description="规范化后的标题")
    dedup_key: str = Field(..., description="去重键")
    removed_lines: int = Field(default=0, ge=0, description="移除的空白行数")
    metadata: dict[str, Any] = Field(default_factory=dict, description="清洗阶段附加信息")


class EntityMention(BaseModel):
    """实体抽取结果。"""

    entity_type: EntityType = Field(..., description="实体类型")
    name: str = Field(..., min_length=1, description="实体名称")
    normalized_name: str = Field(..., min_length=1, description="归一化名称")
    aliases: list[str] = Field(default_factory=list, description="别名列表")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="置信度")
    evidence_text: str | None = Field(None, description="命中的证据片段")


class TopicAssignment(BaseModel):
    """主题归类结果。"""

    topic_key: str = Field(..., min_length=1, description="主题键")
    topic_name: str = Field(..., min_length=1, description="主题展示名")
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0, description="相关性分数")
    rationale: str | None = Field(None, description="归类理由")


class ConflictSignal(BaseModel):
    """冲突检测信号。"""

    signal_type: str = Field(..., description="信号类型")
    description: str = Field(..., description="信号描述")
    evidence_text: str | None = Field(None, description="证据片段")


class ConflictRecord(BaseModel):
    """冲突检测结构。"""

    conflict_type: str = Field(..., description="冲突类型")
    resolution_status: str = Field(default="unresolved", description="处理状态")
    summary: str = Field(..., description="冲突摘要")
    uncertainty: bool = Field(default=True, description="是否保留不确定性")
    signals: list[ConflictSignal] = Field(default_factory=list, description="冲突信号")


class ProcessingResult(BaseModel):
    """处理流水线输出。"""

    cleaned_document: CleanedDocument
    summary: BilingualSummary
    entities: list[EntityMention] = Field(default_factory=list)
    topics: list[TopicAssignment] = Field(default_factory=list)
    conflicts: list[ConflictRecord] = Field(default_factory=list)

